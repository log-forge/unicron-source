package pki

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net/url"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestInspectCertificateMissing(t *testing.T) {
	dir := t.TempDir()
	got := InspectCertificateAt(
		filepath.Join(dir, "agent.crt"),
		filepath.Join(dir, "agent.key"),
		filepath.Join(dir, "root_ca.crt"),
		"edge-a",
		time.Hour,
		time.Now(),
	)
	if got.Status != CertificateMissing {
		t.Fatalf("expected missing status, got %s (%s)", got.Status, got.Reason)
	}
}

func TestInspectCertificateValid(t *testing.T) {
	now := time.Date(2026, 4, 25, 12, 0, 0, 0, time.UTC)
	paths := writeTestMaterial(t, "edge-a", now.Add(-time.Hour), now.Add(4*time.Hour), false)

	got := InspectCertificateAt(paths.cert, paths.key, paths.ca, "edge-a", time.Hour, now)
	if got.Status != CertificateValid {
		t.Fatalf("expected valid status, got %s (%s)", got.Status, got.Reason)
	}
	if got.SPIFFEURI != "spiffe://unicron/streamer/edge-a" {
		t.Fatalf("unexpected SPIFFE URI %q", got.SPIFFEURI)
	}
}

func TestInspectCertificateRenewalRequired(t *testing.T) {
	now := time.Date(2026, 4, 25, 12, 0, 0, 0, time.UTC)
	paths := writeTestMaterial(t, "edge-a", now.Add(-time.Hour), now.Add(30*time.Minute), false)

	got := InspectCertificateAt(paths.cert, paths.key, paths.ca, "edge-a", time.Hour, now)
	if got.Status != CertificateRenewalRequired {
		t.Fatalf("expected renewal required status, got %s (%s)", got.Status, got.Reason)
	}
}

func TestInspectCertificateExpired(t *testing.T) {
	now := time.Date(2026, 4, 25, 12, 0, 0, 0, time.UTC)
	paths := writeTestMaterial(t, "edge-a", now.Add(-2*time.Hour), now.Add(-time.Minute), false)

	got := InspectCertificateAt(paths.cert, paths.key, paths.ca, "edge-a", time.Hour, now)
	if got.Status != CertificateExpired {
		t.Fatalf("expected expired status, got %s (%s)", got.Status, got.Reason)
	}
}

func TestInspectCertificateRejectsWrongSPIFFE(t *testing.T) {
	now := time.Date(2026, 4, 25, 12, 0, 0, 0, time.UTC)
	paths := writeTestMaterial(t, "other-edge", now.Add(-time.Hour), now.Add(4*time.Hour), false)

	got := InspectCertificateAt(paths.cert, paths.key, paths.ca, "edge-a", time.Hour, now)
	if got.Status != CertificateInvalid {
		t.Fatalf("expected invalid status, got %s (%s)", got.Status, got.Reason)
	}
}

func TestInspectCertificateRejectsMismatchedKey(t *testing.T) {
	now := time.Date(2026, 4, 25, 12, 0, 0, 0, time.UTC)
	paths := writeTestMaterial(t, "edge-a", now.Add(-time.Hour), now.Add(4*time.Hour), true)

	got := InspectCertificateAt(paths.cert, paths.key, paths.ca, "edge-a", time.Hour, now)
	if got.Status != CertificateInvalid {
		t.Fatalf("expected invalid status, got %s (%s)", got.Status, got.Reason)
	}
}

type certPaths struct {
	cert string
	key  string
	ca   string
}

func writeTestMaterial(t *testing.T, agentName string, notBefore time.Time, notAfter time.Time, mismatchKey bool) certPaths {
	t.Helper()
	dir := t.TempDir()

	rootKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate root key: %v", err)
	}
	rootTemplate := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "test-root"},
		NotBefore:             notBefore.Add(-time.Hour),
		NotAfter:              notAfter.Add(24 * time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageCRLSign,
	}
	rootDER, err := x509.CreateCertificate(rand.Reader, rootTemplate, rootTemplate, &rootKey.PublicKey, rootKey)
	if err != nil {
		t.Fatalf("create root cert: %v", err)
	}

	leafKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate leaf key: %v", err)
	}
	spiffeURI, err := url.Parse("spiffe://unicron/streamer/" + agentName)
	if err != nil {
		t.Fatalf("parse spiffe URI: %v", err)
	}
	leafTemplate := &x509.Certificate{
		SerialNumber: big.NewInt(2),
		Subject:      pkix.Name{CommonName: "streamer-" + agentName},
		DNSNames:     []string{"streamer-" + agentName},
		URIs:         []*url.URL{spiffeURI},
		NotBefore:    notBefore,
		NotAfter:     notAfter,
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth},
	}
	leafDER, err := x509.CreateCertificate(rand.Reader, leafTemplate, rootTemplate, &leafKey.PublicKey, rootKey)
	if err != nil {
		t.Fatalf("create leaf cert: %v", err)
	}

	keyToWrite := leafKey
	if mismatchKey {
		keyToWrite, err = rsa.GenerateKey(rand.Reader, 2048)
		if err != nil {
			t.Fatalf("generate mismatched key: %v", err)
		}
	}

	paths := certPaths{
		cert: filepath.Join(dir, "agent.crt"),
		key:  filepath.Join(dir, "agent.key"),
		ca:   filepath.Join(dir, "root_ca.crt"),
	}
	writePEM(t, paths.cert, "CERTIFICATE", leafDER)
	writePEM(t, paths.ca, "CERTIFICATE", rootDER)
	writePEM(t, paths.key, "RSA PRIVATE KEY", x509.MarshalPKCS1PrivateKey(keyToWrite))
	return paths
}

func writePEM(t *testing.T, path string, typ string, der []byte) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatalf("create %s: %v", path, err)
	}
	defer f.Close()
	if err := pem.Encode(f, &pem.Block{Type: typ, Bytes: der}); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}
