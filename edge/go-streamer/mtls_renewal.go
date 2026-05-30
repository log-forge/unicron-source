package main

import (
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/sirupsen/logrus"
)

// RenewalConfig holds configuration for certificate renewal
type RenewalConfig struct {
	CertPath       string        // path to current certificate
	KeyPath        string        // path to private key
	CAPath         string        // path to root CA
	CentralMTLSURL string        // mTLS base URL for Central
	RenewThreshold time.Duration // renew when time remaining < threshold (default 1h)
	CheckInterval  time.Duration // how often to check expiry (default 5min)
}

// startRenewalLoop runs in a goroutine and periodically checks for certificate renewal
func startRenewalLoop(cfg RenewalConfig) {
	logrus.WithFields(logrus.Fields{
		"renew_threshold": cfg.RenewThreshold,
		"check_interval":  cfg.CheckInterval,
	}).Info("[Renewal] Starting certificate renewal loop")

	ticker := time.NewTicker(cfg.CheckInterval)
	defer ticker.Stop()

	for range ticker.C {
		if err := renewCertIfNeeded(cfg); err != nil {
			logrus.WithError(err).Warn("[Renewal] Certificate renewal check failed")
		}
	}
}

// renewCertIfNeeded checks certificate expiry and renews if needed
func renewCertIfNeeded(cfg RenewalConfig) error {
	// Read current certificate
	certPEM, err := os.ReadFile(cfg.CertPath)
	if err != nil {
		return fmt.Errorf("failed to read certificate: %w", err)
	}

	// Parse PEM
	block, _ := pem.Decode(certPEM)
	if block == nil {
		return fmt.Errorf("failed to decode certificate PEM")
	}

	// Parse x509 certificate
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return fmt.Errorf("failed to parse certificate: %w", err)
	}

	// Check time until expiry
	timeRemaining := time.Until(cert.NotAfter)
	if timeRemaining > cfg.RenewThreshold {
		// Certificate still valid, no renewal needed
		logrus.WithFields(logrus.Fields{
			"expires_in":       timeRemaining.Round(time.Minute),
			"renew_threshold": cfg.RenewThreshold,
		}).Debug("[Renewal] Certificate still valid, no renewal needed")
		return nil
	}

	// Certificate expiring soon, renew it
	logrus.WithFields(logrus.Fields{
		"expires_in": timeRemaining.Round(time.Minute),
		"expires_at": cert.NotAfter,
	}).Warn("[Renewal] Certificate expiring soon, initiating renewal")

	// Read private key
	keyPEM, err := os.ReadFile(cfg.KeyPath)
	if err != nil {
		return fmt.Errorf("failed to read private key: %w", err)
	}

	// Parse private key PEM (support both PKCS1 and PKCS8)
	keyBlock, _ := pem.Decode(keyPEM)
	if keyBlock == nil {
		return fmt.Errorf("failed to decode private key PEM")
	}

	var privateKey *rsa.PrivateKey
	if keyBlock.Type == "RSA PRIVATE KEY" {
		// PKCS1
		privateKey, err = x509.ParsePKCS1PrivateKey(keyBlock.Bytes)
		if err != nil {
			return fmt.Errorf("failed to parse PKCS1 private key: %w", err)
		}
	} else if keyBlock.Type == "PRIVATE KEY" {
		// PKCS8
		parsedKey, err := x509.ParsePKCS8PrivateKey(keyBlock.Bytes)
		if err != nil {
			return fmt.Errorf("failed to parse PKCS8 private key: %w", err)
		}
		var ok bool
		privateKey, ok = parsedKey.(*rsa.PrivateKey)
		if !ok {
			return fmt.Errorf("private key is not RSA")
		}
	} else {
		return fmt.Errorf("unsupported private key type: %s", keyBlock.Type)
	}

	// Extract SPIFFE URI from current certificate
	if len(cert.URIs) == 0 {
		return fmt.Errorf("current certificate has no URI SANs")
	}
	spiffeURI := cert.URIs[0]

	// Extract agent name from SPIFFE URI (format: spiffe://unicron/streamer/{agent_name})
	pathParts := strings.Split(spiffeURI.Path, "/")
	if len(pathParts) < 3 {
		return fmt.Errorf("invalid SPIFFE URI format: %s", spiffeURI.String())
	}
	agentName := pathParts[len(pathParts)-1]

	// Generate new CSR with existing key
	template := x509.CertificateRequest{
		Subject: pkix.Name{
			CommonName: fmt.Sprintf("streamer-%s", agentName),
		},
		DNSNames: []string{fmt.Sprintf("streamer-%s", agentName)},
		URIs:     []*url.URL{spiffeURI},
	}

	csrDER, err := x509.CreateCertificateRequest(nil, &template, privateKey)
	if err != nil {
		return fmt.Errorf("failed to create renewal CSR: %w", err)
	}

	csrPEM := pem.EncodeToMemory(&pem.Block{
		Type:  "CERTIFICATE REQUEST",
		Bytes: csrDER,
	})

	// Sign CSR with mTLS
	if err := signCSRWithMTLS(cfg, string(csrPEM)); err != nil {
		return fmt.Errorf("failed to sign renewal CSR: %w", err)
	}

	logrus.Info("[Renewal] Certificate renewed successfully")
	return nil
}

// signCSRWithMTLS uses mTLS to request a new signed certificate from Central
func signCSRWithMTLS(cfg RenewalConfig, csrPEM string) error {
	logrus.Info("[Renewal] Requesting certificate signature with mTLS")

	// Build request body
	requestBody := map[string]interface{}{
		"csr_pem":           csrPEM,
		"not_after_seconds": 43200, // 12h
	}

	bodyJSON, err := json.Marshal(requestBody)
	if err != nil {
		return fmt.Errorf("failed to marshal request body: %w", err)
	}

	// Load client certificate and key
	clientCert, err := tls.LoadX509KeyPair(cfg.CertPath, cfg.KeyPath)
	if err != nil {
		return fmt.Errorf("failed to load client certificate: %w", err)
	}

	// Load CA certificate pool
	caPEM, err := os.ReadFile(cfg.CAPath)
	if err != nil {
		return fmt.Errorf("failed to read CA certificate: %w", err)
	}

	caPool := x509.NewCertPool()
	if !caPool.AppendCertsFromPEM(caPEM) {
		return fmt.Errorf("failed to parse CA certificate")
	}

	// Create HTTP client with mTLS
	client := &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				Certificates: []tls.Certificate{clientCert},
				RootCAs:      caPool,
			},
		},
	}

	// Create HTTP request
	req, err := http.NewRequest("POST", cfg.CentralMTLSURL+"/api/pki/cert/sign", strings.NewReader(string(bodyJSON)))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	// Send request
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send mTLS sign request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("mTLS sign request failed with status %d", resp.StatusCode)
	}

	// Parse response
	var result struct {
		CertPEM  string `json:"cert_pem"`
		ChainPEM string `json:"chain_pem"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("failed to parse sign response: %w", err)
	}

	// Concatenate cert + chain to form full bundle
	certBundle := result.CertPEM + "\n" + result.ChainPEM

	// Write new certificate bundle to file
	if err := os.WriteFile(cfg.CertPath, []byte(certBundle), 0644); err != nil {
		return fmt.Errorf("failed to write renewed certificate: %w", err)
	}

	logrus.WithField("path", cfg.CertPath).Info("[Renewal] Renewed certificate saved")
	return nil
}
