package main

import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path"
	"strings"
	"time"

	"github.com/sirupsen/logrus"
)

const registerRebootstrapRequiredCode = "REBOOTSTRAP_REQUIRED"

type registerHTTPError struct {
	StatusCode int
	Body       string
	Failure    *registerFailureDetail
	Recovery   *registerAuthRecoveryDetail
}

func (e *registerHTTPError) Error() string {
	return e.reportReason()
}

func (e *registerHTTPError) reportReason() string {
	if e.Failure != nil && strings.TrimSpace(e.Failure.Message) != "" {
		return strings.TrimSpace(e.Failure.Message)
	}
	body := strings.TrimSpace(e.Body)
	if body == "" {
		return fmt.Sprintf("register returned HTTP %d", e.StatusCode)
	}
	return fmt.Sprintf("register returned HTTP %d: %s", e.StatusCode, body)
}

func isRegisterRebootstrapRequired(err error) bool {
	var httpErr *registerHTTPError
	if !errors.As(err, &httpErr) {
		return false
	}
	if httpErr.StatusCode != http.StatusUnauthorized && httpErr.StatusCode != http.StatusForbidden {
		return false
	}
	recovery := httpErr.Recovery
	if recovery == nil {
		recovery = parseRegisterAuthRecoveryDetail([]byte(httpErr.Body))
	}
	return recovery != nil && recovery.Code == registerRebootstrapRequiredCode
}

type registerFailPayload struct {
	HeraldID   string                 `json:"herald_id"`
	HeraldName string                 `json:"herald_name,omitempty"`
	Reason     string                 `json:"reason,omitempty"`
	Failure    *registerFailureDetail `json:"failure,omitempty"`
}

type registerFailureDetail struct {
	Code    string `json:"code"`
	Message string `json:"message,omitempty"`
}

type registerAuthRecoveryDetail struct {
	Code    string `json:"code"`
	Message string `json:"message,omitempty"`
}

type registerPayload struct {
	CPUCount int `json:"cpu_count,omitempty"`
}

type registerFailureReporter struct {
	cfg        config
	lastReason string
	send       func(config, string, *registerFailureDetail) error
}

func newRegisterFailureReporter(cfg config) *registerFailureReporter {
	return &registerFailureReporter{
		cfg:  cfg,
		send: reportRegisterFailure,
	}
}

func (r *registerFailureReporter) Report(err error) {
	if r == nil || err == nil {
		return
	}
	var httpErr *registerHTTPError
	if !errors.As(err, &httpErr) {
		return
	}
	reason := strings.TrimSpace(httpErr.reportReason())
	if reason == "" || reason == r.lastReason {
		return
	}
	if sendErr := r.send(r.cfg, reason, httpErr.Failure); sendErr != nil {
		logrus.WithError(sendErr).Warn("[Register] Failed to report repeated registration failure to Central")
	}
	r.lastReason = reason
}

func (r *registerFailureReporter) Clear() {
	if r == nil {
		return
	}
	r.lastReason = ""
}

// registerHerald calls POST /api/herald/register on Central via mTLS.
// This activates the enrollment token and creates the Herald DB row that
// must exist before inventory sync can persist containers.
//
// The call is idempotent: Central returns 200 for already-registered heralds.
func registerHerald(cfg config, cpuCount int) error {
	registerURL, err := buildRegisterURL(cfg)
	if err != nil {
		return fmt.Errorf("cannot build register URL: %w", err)
	}

	tlsCfg, err := buildMTLSClientConfig(cfg)
	if err != nil {
		return fmt.Errorf("cannot build mTLS config: %w", err)
	}

	client := &http.Client{
		Transport: &http.Transport{TLSClientConfig: tlsCfg},
		Timeout:   15 * time.Second,
	}

	payload, err := json.Marshal(registerPayload{CPUCount: cpuCount})
	if err != nil {
		return fmt.Errorf("failed to build register payload: %w", err)
	}

	req, err := http.NewRequest("POST", registerURL, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("failed to create register request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("register request failed: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))

	switch {
	case resp.StatusCode == http.StatusOK:
		logrus.WithField("url", registerURL).Info("[Register] Herald registered with Central")
		return nil
	default:
		return &registerHTTPError{
			StatusCode: resp.StatusCode,
			Body:       string(body),
			Failure:    parseRegisterFailureDetail(body),
			Recovery:   parseRegisterAuthRecoveryDetail(body),
		}
	}
}

func parseRegisterFailureDetail(body []byte) *registerFailureDetail {
	var envelope struct {
		Detail json.RawMessage `json:"detail"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return nil
	}

	raw := envelope.Detail
	if len(raw) == 0 {
		raw = body
	}
	raw = bytes.TrimSpace(raw)
	if len(raw) == 0 || raw[0] != '{' {
		return nil
	}

	var detail registerFailureDetail
	if err := json.Unmarshal(raw, &detail); err != nil {
		return nil
	}
	if strings.TrimSpace(detail.Code) == "" {
		return nil
	}
	if detail.Code == registerRebootstrapRequiredCode {
		return nil
	}
	return &detail
}

func parseRegisterAuthRecoveryDetail(body []byte) *registerAuthRecoveryDetail {
	var envelope struct {
		Detail json.RawMessage `json:"detail"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return nil
	}

	raw := envelope.Detail
	if len(raw) == 0 {
		raw = body
	}
	raw = bytes.TrimSpace(raw)
	if len(raw) == 0 || raw[0] != '{' {
		return nil
	}

	var detail registerAuthRecoveryDetail
	if err := json.Unmarshal(raw, &detail); err != nil {
		return nil
	}
	if detail.Code != registerRebootstrapRequiredCode {
		return nil
	}
	return &detail
}

// buildRegisterURL derives the full registration URL from config.
//
// Strategy:
//   - Use CENTRAL_MTLS_URL for scheme+host+port (mTLS entrypoint).
//   - Extract the path prefix (e.g. "/unicron") from CENTRAL_URL so the
//     request routes correctly through the reverse proxy.
//   - Append the backend route /api/herald/register.
func buildRegisterURL(cfg config) (string, error) {
	base := normalizeCentralMTLSBaseURL(cfg.centralMTLSURL)
	if base == "" {
		return "", fmt.Errorf("CENTRAL_MTLS_URL is not configured")
	}

	pathPrefix := cfg.centralRootPrefix
	if pathPrefix == "" {
		pathPrefix = deriveCentralRootPrefix(cfg.centralURL, cfg.centralWSURL)
	}

	return base + pathPrefix + "/api/herald/register", nil
}

func buildRegisterFailureURL(cfg config) (string, error) {
	base := normalizeCentralMTLSBaseURL(cfg.centralMTLSURL)
	if base == "" {
		return "", fmt.Errorf("CENTRAL_MTLS_URL is not configured")
	}

	pathPrefix := cfg.centralRootPrefix
	if pathPrefix == "" {
		pathPrefix = deriveCentralRootPrefix(cfg.centralURL, cfg.centralWSURL)
	}

	return base + pathPrefix + "/api/herald/register/fail", nil
}

// deriveCentralRootPrefix returns the Central route prefix (for example "/unicron").
// CENTRAL_URL wins when it has a meaningful path; otherwise the helper falls back
// to CENTRAL_WS_URL and strips any "/api/..." suffix back to the shared root.
func deriveCentralRootPrefix(centralURL, centralWSURL string) string {
	if prefix := extractCentralRootPrefix(centralURL); prefix != "" {
		return prefix
	}
	return extractCentralRootPrefix(centralWSURL)
}

func extractCentralRootPrefix(rawURL string) string {
	rawURL = strings.TrimSpace(rawURL)
	if rawURL == "" {
		return ""
	}
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return ""
	}
	return normalizeCentralRootPrefix(parsed.Path)
}

func normalizeCentralRootPrefix(rawPath string) string {
	rawPath = strings.TrimSpace(rawPath)
	if rawPath == "" || rawPath == "/" {
		return ""
	}

	cleaned := path.Clean(rawPath)
	if cleaned == "." || cleaned == "/" {
		return ""
	}
	if !strings.HasPrefix(cleaned, "/") {
		cleaned = "/" + cleaned
	}

	if idx := strings.Index(cleaned, "/api/"); idx >= 0 {
		cleaned = cleaned[:idx]
	} else if strings.HasSuffix(cleaned, "/api") {
		cleaned = strings.TrimSuffix(cleaned, "/api")
	}

	cleaned = strings.TrimRight(cleaned, "/")
	if cleaned == "" || cleaned == "/" {
		return ""
	}
	return cleaned
}

func normalizeCentralMTLSBaseURL(rawURL string) string {
	rawURL = strings.TrimSpace(rawURL)
	if rawURL == "" {
		return ""
	}
	if !strings.Contains(rawURL, "://") {
		rawURL = "https://" + rawURL
	}
	parsed, err := url.Parse(rawURL)
	if err != nil || parsed.Host == "" {
		return strings.TrimRight(rawURL, "/")
	}
	scheme := strings.TrimSpace(parsed.Scheme)
	if scheme == "" {
		scheme = "https"
	}
	return strings.TrimRight((&url.URL{Scheme: scheme, Host: parsed.Host}).String(), "/")
}

// retryStep retries fn with exponential backoff. attempts <= 0 means unlimited.
func retryStep(step string, attempts int, initialDelay time.Duration, fn func() error) error {
	unlimited := attempts <= 0
	delay := initialDelay
	if delay <= 0 {
		delay = time.Second
	}
	var lastErr error
	for attempt := 1; unlimited || attempt <= attempts; attempt++ {
		if err := fn(); err == nil {
			if attempt > 1 {
				logrus.WithFields(logrus.Fields{"step": step, "attempt": attempt}).Info("Step recovered after retry")
			}
			return nil
		} else {
			lastErr = err
		}
		if !unlimited && attempt == attempts {
			break
		}
		logrus.WithFields(logrus.Fields{
			"step":     step,
			"attempt":  attempt,
			"retry_in": delay.String(),
			"error":    lastErr.Error(),
		}).Warn("Step failed, retrying")
		time.Sleep(delay)
		if delay < 10*time.Second {
			delay *= 2
			if delay > 10*time.Second {
				delay = 10 * time.Second
			}
		}
	}
	return fmt.Errorf("%s failed after %d attempts: %w", step, attempts, lastErr)
}

// buildMTLSClientConfig loads the agent's mTLS certificate materials.
func buildMTLSClientConfig(cfg config) (*tls.Config, error) {
	cert, err := tls.LoadX509KeyPair(cfg.certPath, cfg.keyPath)
	if err != nil {
		return nil, fmt.Errorf("failed to load client certificate: %w", err)
	}

	caPEM, err := os.ReadFile(cfg.caPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read CA certificate: %w", err)
	}

	caPool := x509.NewCertPool()
	if !caPool.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("failed to parse CA certificate")
	}

	return &tls.Config{
		Certificates: []tls.Certificate{cert},
		RootCAs:      caPool,
	}, nil
}

func reportRegisterFailure(cfg config, reason string, failure *registerFailureDetail) error {
	failureURL, err := buildRegisterFailureURL(cfg)
	if err != nil {
		return fmt.Errorf("cannot build register failure URL: %w", err)
	}

	tlsCfg, err := buildMTLSClientConfig(cfg)
	if err != nil {
		return fmt.Errorf("cannot build mTLS config: %w", err)
	}

	payload, err := buildRegisterFailurePayload(cfg, reason, failure)
	if err != nil {
		return fmt.Errorf("failed to marshal register failure payload: %w", err)
	}

	client := &http.Client{
		Transport: &http.Transport{TLSClientConfig: tlsCfg},
		Timeout:   15 * time.Second,
	}
	req, err := http.NewRequest(http.MethodPost, failureURL, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("failed to create register failure request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("register failure request failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("register failure returned HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	return nil
}

func buildRegisterFailurePayload(cfg config, reason string, failure *registerFailureDetail) ([]byte, error) {
	return json.Marshal(registerFailPayload{
		HeraldID:   strings.TrimSpace(cfg.hostID),
		HeraldName: strings.TrimSpace(cfg.agentName),
		Reason:     strings.TrimSpace(reason),
		Failure:    failure,
	})
}
