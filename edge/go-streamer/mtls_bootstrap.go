package main

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"

	"github.com/sirupsen/logrus"
)

// BootstrapConfig holds configuration for certificate bootstrap
type BootstrapConfig struct {
	EnrollToken   string
	AgentName     string
	CentralURL    string
	CAFingerprint string
	CertNotAfter  int    // seconds, default 43200 = 12h
	CertPath      string // default: /agent-data/certs/agent.crt
	KeyPath       string // default: /agent-data/certs/agent.key
	CAPath        string // default: /agent-data/certs/root_ca.crt
}

// fetchRootCA fetches the root CA certificate from Central and validates its fingerprint
func fetchRootCA(cfg BootstrapConfig) error {
	logrus.WithField("url", cfg.CentralURL+"/api/pki/ca/root").Info("[Bootstrap] Fetching root CA certificate")

	// Create HTTP client that skips TLS verification for initial CA fetch only
	// This is necessary because we don't have the CA cert yet
	client := &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				InsecureSkipVerify: true,
			},
		},
	}

	resp, err := client.Get(cfg.CentralURL + "/api/pki/ca/root")
	if err != nil {
		return fmt.Errorf("failed to fetch root CA: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("root CA fetch failed with status %d", resp.StatusCode)
	}

	// Parse JSON response
	var result struct {
		RootCAPEM string `json:"root_ca_pem"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("failed to parse root CA response: %w", err)
	}

	// Decode PEM to get DER bytes
	block, _ := pem.Decode([]byte(result.RootCAPEM))
	if block == nil {
		return fmt.Errorf("failed to decode root CA PEM")
	}

	// Parse x509 certificate
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return fmt.Errorf("failed to parse root CA certificate: %w", err)
	}

	// Compute SHA256 fingerprint of DER bytes
	hash := sha256.Sum256(cert.Raw)
	fingerprint := hex.EncodeToString(hash[:])

	// Normalize configured fingerprint (lowercase, strip colons)
	expectedFingerprint := strings.ToLower(strings.ReplaceAll(cfg.CAFingerprint, ":", ""))

	// Compare fingerprints
	if fingerprint != expectedFingerprint {
		return fmt.Errorf("CA fingerprint mismatch: expected=%s, got=%s", expectedFingerprint, fingerprint)
	}

	logrus.WithField("fingerprint", fingerprint).Info("[Bootstrap] Root CA fingerprint verified")

	// Write CA PEM to file
	if err := os.WriteFile(cfg.CAPath, []byte(result.RootCAPEM), 0644); err != nil {
		return fmt.Errorf("failed to write root CA to %s: %w", cfg.CAPath, err)
	}

	logrus.WithField("path", cfg.CAPath).Info("[Bootstrap] Root CA saved")
	return nil
}

// generateCSR generates an RSA key pair and CSR with SPIFFE URI SAN
func generateCSR(cfg BootstrapConfig) (string, error) {
	logrus.WithField("agent_name", cfg.AgentName).Info("[Bootstrap] Generating RSA key and CSR")

	// Generate RSA 2048-bit key
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return "", fmt.Errorf("failed to generate RSA key: %w", err)
	}

	// Build CSR template
	spiffeURI, err := url.Parse(fmt.Sprintf("spiffe://unicron/streamer/%s", cfg.AgentName))
	if err != nil {
		return "", fmt.Errorf("failed to parse SPIFFE URI: %w", err)
	}

	template := x509.CertificateRequest{
		Subject: pkix.Name{
			CommonName: fmt.Sprintf("streamer-%s", cfg.AgentName),
		},
		DNSNames: []string{fmt.Sprintf("streamer-%s", cfg.AgentName)},
		URIs:     []*url.URL{spiffeURI},
	}

	// Create CSR
	csrDER, err := x509.CreateCertificateRequest(rand.Reader, &template, privateKey)
	if err != nil {
		return "", fmt.Errorf("failed to create CSR: %w", err)
	}

	// PEM-encode private key (PKCS1)
	privateKeyPEM := pem.EncodeToMemory(&pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: x509.MarshalPKCS1PrivateKey(privateKey),
	})

	// Write private key to file with restricted permissions
	if err := os.WriteFile(cfg.KeyPath, privateKeyPEM, 0600); err != nil {
		return "", fmt.Errorf("failed to write private key to %s: %w", cfg.KeyPath, err)
	}

	logrus.WithField("path", cfg.KeyPath).Info("[Bootstrap] Private key saved")

	// PEM-encode CSR
	csrPEM := pem.EncodeToMemory(&pem.Block{
		Type:  "CERTIFICATE REQUEST",
		Bytes: csrDER,
	})

	return string(csrPEM), nil
}

// bootstrapCertificate requests a signed certificate from Central using the enrollment token
func bootstrapCertificate(cfg BootstrapConfig, csrPEM string) error {
	logrus.Info("[Bootstrap] Requesting certificate from Central")

	// Load CA cert into pool
	caPEM, err := os.ReadFile(cfg.CAPath)
	if err != nil {
		return fmt.Errorf("failed to read CA certificate: %w", err)
	}

	caPool := x509.NewCertPool()
	if !caPool.AppendCertsFromPEM(caPEM) {
		return fmt.Errorf("failed to parse CA certificate")
	}

	// Create HTTP client with CA validation
	client := &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				RootCAs: caPool,
			},
		},
	}

	// Build request body
	requestBody := map[string]interface{}{
		"csr_pem":           csrPEM,
		"not_after_seconds": cfg.CertNotAfter,
	}

	bodyJSON, err := json.Marshal(requestBody)
	if err != nil {
		return fmt.Errorf("failed to marshal request body: %w", err)
	}

	// Create HTTP request
	req, err := http.NewRequest("POST", cfg.CentralURL+"/api/pki/cert/bootstrap", strings.NewReader(string(bodyJSON)))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+cfg.EnrollToken)

	// Send request
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send bootstrap request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("bootstrap request failed with status %d", resp.StatusCode)
	}

	// Parse response
	var result struct {
		CertPEM  string `json:"cert_pem"`
		ChainPEM string `json:"chain_pem"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("failed to parse bootstrap response: %w", err)
	}

	// Concatenate cert + chain to form full bundle
	certBundle := result.CertPEM + "\n" + result.ChainPEM

	// Write certificate bundle to file
	if err := os.WriteFile(cfg.CertPath, []byte(certBundle), 0644); err != nil {
		return fmt.Errorf("failed to write certificate to %s: %w", cfg.CertPath, err)
	}

	logrus.WithField("path", cfg.CertPath).Info("[Bootstrap] Certificate saved")
	return nil
}

// bootstrapAgent orchestrates the full bootstrap process
func bootstrapAgent(cfg BootstrapConfig) error {
	logrus.WithFields(logrus.Fields{
		"agent_name":   cfg.AgentName,
		"central_url":  cfg.CentralURL,
		"cert_path":    cfg.CertPath,
		"key_path":     cfg.KeyPath,
		"ca_path":      cfg.CAPath,
		"not_after_h":  cfg.CertNotAfter / 3600,
	}).Info("[Bootstrap] Starting agent certificate bootstrap")

	// Step 1: Fetch and verify root CA
	if err := fetchRootCA(cfg); err != nil {
		return fmt.Errorf("root CA fetch failed: %w", err)
	}

	// Step 2: Generate key pair and CSR
	csrPEM, err := generateCSR(cfg)
	if err != nil {
		return fmt.Errorf("CSR generation failed: %w", err)
	}

	// Step 3: Bootstrap certificate
	if err := bootstrapCertificate(cfg, csrPEM); err != nil {
		return fmt.Errorf("certificate bootstrap failed: %w", err)
	}

	logrus.Info("[Bootstrap] Agent certificate bootstrap completed successfully")
	return nil
}
