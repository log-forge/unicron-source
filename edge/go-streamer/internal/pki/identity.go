package pki

import (
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// CertificateStatus describes whether persisted agent identity material can be
// reused safely on startup.
type CertificateStatus string

const (
	CertificateMissing         CertificateStatus = "missing"
	CertificateValid           CertificateStatus = "valid"
	CertificateRenewalRequired CertificateStatus = "renewal_required"
	CertificateExpired         CertificateStatus = "expired"
	CertificateInvalid         CertificateStatus = "invalid"
)

// CertificateInspection is the startup assessment for existing mTLS material.
type CertificateInspection struct {
	Status        CertificateStatus
	Reason        string
	NotAfter      time.Time
	TimeRemaining time.Duration
	SPIFFEURI     string
}

// InspectCertificate validates existing cert/key/CA material for the configured
// go-streamer agent identity.
func InspectCertificate(certPath, keyPath, caPath, agentName string, renewThreshold time.Duration) CertificateInspection {
	return InspectCertificateAt(certPath, keyPath, caPath, agentName, renewThreshold, time.Now())
}

// InspectCertificateAt is like InspectCertificate, with injectable time for tests.
func InspectCertificateAt(certPath, keyPath, caPath, agentName string, renewThreshold time.Duration, now time.Time) CertificateInspection {
	if strings.TrimSpace(certPath) == "" || strings.TrimSpace(keyPath) == "" || strings.TrimSpace(caPath) == "" {
		return CertificateInspection{Status: CertificateInvalid, Reason: "certificate, key, or CA path is empty"}
	}
	if _, err := os.Stat(certPath); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return CertificateInspection{Status: CertificateMissing, Reason: "certificate file missing"}
		}
		return CertificateInspection{Status: CertificateInvalid, Reason: fmt.Sprintf("certificate stat failed: %v", err)}
	}
	if _, err := os.Stat(keyPath); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return CertificateInspection{Status: CertificateMissing, Reason: "private key file missing"}
		}
		return CertificateInspection{Status: CertificateInvalid, Reason: fmt.Sprintf("private key stat failed: %v", err)}
	}
	if _, err := os.Stat(caPath); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return CertificateInspection{Status: CertificateMissing, Reason: "root CA file missing"}
		}
		return CertificateInspection{Status: CertificateInvalid, Reason: fmt.Sprintf("root CA stat failed: %v", err)}
	}

	if _, err := tls.LoadX509KeyPair(certPath, keyPath); err != nil {
		return CertificateInspection{Status: CertificateInvalid, Reason: fmt.Sprintf("certificate/key pair failed to load: %v", err)}
	}

	leaf, intermediates, err := loadCertificateBundle(certPath)
	if err != nil {
		return CertificateInspection{Status: CertificateInvalid, Reason: err.Error()}
	}

	inspection := CertificateInspection{
		Status:        CertificateValid,
		NotAfter:      leaf.NotAfter,
		TimeRemaining: leaf.NotAfter.Sub(now),
	}
	if len(leaf.URIs) > 0 {
		inspection.SPIFFEURI = leaf.URIs[0].String()
	}

	if !leaf.NotBefore.IsZero() && now.Before(leaf.NotBefore) {
		inspection.Status = CertificateInvalid
		inspection.Reason = fmt.Sprintf("certificate is not valid before %s", leaf.NotBefore.UTC().Format(time.RFC3339))
		return inspection
	}
	if !leaf.NotAfter.IsZero() && !now.Before(leaf.NotAfter) {
		inspection.Status = CertificateExpired
		inspection.Reason = fmt.Sprintf("certificate expired at %s", leaf.NotAfter.UTC().Format(time.RFC3339))
		return inspection
	}

	expectedSPIFFE := fmt.Sprintf("spiffe://unicron/streamer/%s", strings.TrimSpace(agentName))
	if !certificateHasURI(leaf, expectedSPIFFE) {
		inspection.Status = CertificateInvalid
		inspection.Reason = fmt.Sprintf("certificate SPIFFE identity does not match expected %s", expectedSPIFFE)
		return inspection
	}

	roots, err := loadRootPool(caPath)
	if err != nil {
		inspection.Status = CertificateInvalid
		inspection.Reason = err.Error()
		return inspection
	}
	if err := verifyLeaf(leaf, intermediates, roots, now); err != nil {
		inspection.Status = CertificateInvalid
		inspection.Reason = fmt.Sprintf("certificate chain verification failed: %v", err)
		return inspection
	}

	if renewThreshold > 0 && inspection.TimeRemaining <= renewThreshold {
		inspection.Status = CertificateRenewalRequired
		inspection.Reason = fmt.Sprintf("certificate expires within renewal window at %s", leaf.NotAfter.UTC().Format(time.RFC3339))
		return inspection
	}

	inspection.Reason = "certificate is reusable"
	return inspection
}

// RemoveCertificateMaterial clears persisted identity material so fresh
// enrollment can safely overwrite a stale named volume.
func RemoveCertificateMaterial(certPath, keyPath, caPath string) error {
	var errs []string
	for _, p := range []string{certPath, keyPath, caPath} {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		cleaned := filepath.Clean(p)
		if err := os.Remove(cleaned); err != nil && !errors.Is(err, os.ErrNotExist) {
			errs = append(errs, fmt.Sprintf("%s: %v", cleaned, err))
		}
	}
	if len(errs) > 0 {
		return errors.New(strings.Join(errs, "; "))
	}
	return nil
}

func loadCertificateBundle(certPath string) (*x509.Certificate, *x509.CertPool, error) {
	certPEM, err := os.ReadFile(certPath)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to read certificate: %w", err)
	}

	var leaf *x509.Certificate
	intermediates := x509.NewCertPool()
	remaining := certPEM
	for {
		block, rest := pem.Decode(remaining)
		if block == nil {
			break
		}
		remaining = rest
		if block.Type != "CERTIFICATE" {
			continue
		}
		cert, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			return nil, nil, fmt.Errorf("failed to parse certificate block: %w", err)
		}
		if leaf == nil {
			leaf = cert
			continue
		}
		intermediates.AddCert(cert)
	}
	if leaf == nil {
		return nil, nil, fmt.Errorf("certificate bundle has no certificate blocks")
	}
	return leaf, intermediates, nil
}

func loadRootPool(caPath string) (*x509.CertPool, error) {
	caPEM, err := os.ReadFile(caPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read root CA: %w", err)
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("failed to parse root CA")
	}
	return roots, nil
}

func verifyLeaf(leaf *x509.Certificate, intermediates *x509.CertPool, roots *x509.CertPool, now time.Time) error {
	opts := x509.VerifyOptions{
		CurrentTime:   now,
		Roots:         roots,
		Intermediates: intermediates,
		KeyUsages:     []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth},
	}
	if _, err := leaf.Verify(opts); err == nil {
		return nil
	}

	// Some existing step-ca certificates do not carry a clientAuth EKU. Do not
	// strand installed agents solely because the older issuer used a broader EKU.
	opts.KeyUsages = []x509.ExtKeyUsage{x509.ExtKeyUsageAny}
	_, err := leaf.Verify(opts)
	return err
}

func certificateHasURI(cert *x509.Certificate, expected string) bool {
	expected = strings.TrimSpace(expected)
	if expected == "" {
		return false
	}
	for _, uri := range cert.URIs {
		if uri == nil {
			continue
		}
		if uri.String() == expected {
			return true
		}
	}
	// Be strict about parseable URI equality when String formatting differs.
	expectedURI, err := url.Parse(expected)
	if err != nil {
		return false
	}
	for _, uri := range cert.URIs {
		if uri != nil && uri.Scheme == expectedURI.Scheme && uri.Host == expectedURI.Host && uri.Path == expectedURI.Path {
			return true
		}
	}
	return false
}
