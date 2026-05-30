package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"errors"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestNormalizeCSVSpaces(t *testing.T) {
	got := normalizeCSVSpaces(" localhost,127.0.0.1 , , unicron.central ")
	want := "localhost, 127.0.0.1, unicron.central"
	if got != want {
		t.Fatalf("normalizeCSVSpaces() = %q, want %q", got, want)
	}
}

func TestRenderTraefikConfig(t *testing.T) {
	rendered := renderTraefikConfig("rule: '{{HOSTS_OR_RULES}}'", "localhost, 127.0.0.1")
	for _, want := range []string{"Host(`localhost`)", "Host(`127.0.0.1`)"} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("rendered config missing %q: %s", want, rendered)
		}
	}
}

func TestTraefikArgs(t *testing.T) {
	cfg := RuntimeConfig{
		DataDir:         "/var/lib/unicron",
		CentralPort:     "443",
		CentralMTLSPort: "8443",
	}
	args := traefikArgs(cfg)
	joined := strings.Join(args, "\n")
	for _, want := range []string{
		"--providers.file.filename=/var/lib/unicron/traefik/traefik-config.yaml",
		"--entrypoints.websecure.address=:443",
		"--entrypoints.mtls.address=:8443",
	} {
		if !strings.Contains(joined, want) {
			t.Fatalf("traefik args missing %q: %s", want, joined)
		}
	}
}

func withCleanEnv(t *testing.T) {
	t.Helper()
	previous := os.Environ()
	os.Clearenv()
	t.Cleanup(func() {
		os.Clearenv()
		for _, entry := range previous {
			parts := strings.SplitN(entry, "=", 2)
			if len(parts) == 2 {
				_ = os.Setenv(parts[0], parts[1])
			}
		}
	})
}

func TestEnsureInternalSecretsGeneratesAndPersistsMissingValues(t *testing.T) {
	withCleanEnv(t)
	cfg := RuntimeConfig{DataDir: t.TempDir()}

	if err := ensureInternalSecrets(cfg); err != nil {
		t.Fatal(err)
	}

	for _, spec := range internalSecretSpecs(cfg) {
		value := os.Getenv(spec.EnvName)
		if len(value) < spec.MinLen {
			t.Fatalf("%s length = %d, want at least %d", spec.EnvName, len(value), spec.MinLen)
		}
		onDisk, err := readSecretFile(spec.Path)
		if err != nil {
			t.Fatal(err)
		}
		if onDisk != value {
			t.Fatalf("%s persisted value mismatch", spec.EnvName)
		}
	}
}

func TestEnsureInternalSecretsReusesPersistedValuesOnRestart(t *testing.T) {
	withCleanEnv(t)
	cfg := RuntimeConfig{DataDir: t.TempDir()}

	if err := ensureInternalSecrets(cfg); err != nil {
		t.Fatal(err)
	}
	persisted := map[string]string{}
	for _, spec := range internalSecretSpecs(cfg) {
		persisted[spec.EnvName] = os.Getenv(spec.EnvName)
		if err := os.Setenv(spec.EnvName, strings.Repeat("x", max(spec.MinLen, 40))); err != nil {
			t.Fatal(err)
		}
	}

	if err := ensureInternalSecrets(cfg); err != nil {
		t.Fatal(err)
	}
	for _, spec := range internalSecretSpecs(cfg) {
		if got := os.Getenv(spec.EnvName); got != persisted[spec.EnvName] {
			t.Fatalf("%s = %q, want persisted value %q", spec.EnvName, got, persisted[spec.EnvName])
		}
	}
}

func TestEnsureInternalSecretsSeedsFromEnvironment(t *testing.T) {
	withCleanEnv(t)
	cfg := RuntimeConfig{DataDir: t.TempDir()}
	seeded := map[string]string{}
	for _, spec := range internalSecretSpecs(cfg) {
		value := "seed-" + strings.ToLower(strings.ReplaceAll(spec.EnvName, "_", "-")) + "-" + strings.Repeat("x", max(spec.MinLen, 1))
		seeded[spec.EnvName] = value
		if err := os.Setenv(spec.EnvName, value); err != nil {
			t.Fatal(err)
		}
	}

	if err := ensureInternalSecrets(cfg); err != nil {
		t.Fatal(err)
	}
	for _, spec := range internalSecretSpecs(cfg) {
		onDisk, err := readSecretFile(spec.Path)
		if err != nil {
			t.Fatal(err)
		}
		if onDisk != seeded[spec.EnvName] {
			t.Fatalf("%s persisted value = %q, want seeded value %q", spec.EnvName, onDisk, seeded[spec.EnvName])
		}
	}
}

func TestEnsureStepPasswordFilesGeneratedWhenAbsent(t *testing.T) {
	withCleanEnv(t)
	cfg := RuntimeConfig{
		DataDir:  t.TempDir(),
		StepPath: filepath.Join(t.TempDir(), "pki"),
	}

	if err := ensureStepPasswordFiles(cfg); err != nil {
		t.Fatal(err)
	}

	for _, spec := range stepPasswordSecretSpecs(cfg) {
		value := os.Getenv(spec.EnvName)
		if value == "" {
			t.Fatalf("%s was not exported", spec.EnvName)
		}
		onDisk, err := readSecretFile(spec.Path)
		if err != nil {
			t.Fatal(err)
		}
		if onDisk != value {
			t.Fatalf("%s persisted value mismatch", spec.EnvName)
		}
	}
}

func TestLoadConfigDefaultsPublicCentralMTLSPortToInternalPort(t *testing.T) {
	withCleanEnv(t)
	t.Setenv("UNICRON_CENTRAL_MTLS_PORT", "8555")
	t.Setenv("UNICRON_PUBLIC_CENTRAL_MTLS_PORT", "")

	cfg := loadConfig()

	if cfg.PublicCentralMTLSPort != "8555" {
		t.Fatalf("PublicCentralMTLSPort = %q, want %q", cfg.PublicCentralMTLSPort, "8555")
	}
	if got := os.Getenv("UNICRON_PUBLIC_CENTRAL_MTLS_PORT"); got != "8555" {
		t.Fatalf("UNICRON_PUBLIC_CENTRAL_MTLS_PORT env = %q, want %q", got, "8555")
	}
}

func TestLoadConfigKeepsPublicCentralMTLSPortOverride(t *testing.T) {
	withCleanEnv(t)
	t.Setenv("UNICRON_CENTRAL_MTLS_PORT", "8443")
	t.Setenv("UNICRON_PUBLIC_CENTRAL_MTLS_PORT", "9443")

	cfg := loadConfig()

	if cfg.PublicCentralMTLSPort != "9443" {
		t.Fatalf("PublicCentralMTLSPort = %q, want %q", cfg.PublicCentralMTLSPort, "9443")
	}
}

func TestSupervisedServiceSpecsIncludesNonCriticalUpdater(t *testing.T) {
	specs := supervisedServiceSpecs(RuntimeConfig{SelfUpdateEnabled: true})
	var found bool
	for _, spec := range specs {
		if spec.Name == "appliance-updater" {
			found = true
			if spec.Critical {
				t.Fatal("appliance-updater must not be healthcheck-critical")
			}
		}
	}
	if !found {
		t.Fatal("appliance-updater was not supervised when self-update is enabled")
	}

	disabled := supervisedServiceSpecs(RuntimeConfig{SelfUpdateEnabled: false})
	for _, spec := range disabled {
		if spec.Name == "appliance-updater" {
			t.Fatal("appliance-updater was supervised when self-update is disabled")
		}
	}
}

func TestAlertEngineWaitsForBackendAfterCentralAuth(t *testing.T) {
	var calls []string
	waiter := runtimeWaiter{
		Postgres: func(RuntimeConfig) error {
			calls = append(calls, "postgres")
			return nil
		},
		TCP: func(host string, port int, name string, attempts int) error {
			calls = append(calls, "tcp:"+name+":"+host+":"+strconv.Itoa(port))
			return nil
		},
		HTTP: func(url, name string, attempts int) error {
			calls = append(calls, "http:"+name+":"+url)
			return nil
		},
	}

	if err := waitAlertEngineDependencies(RuntimeConfig{}, waiter); err != nil {
		t.Fatal(err)
	}

	want := []string{
		"postgres",
		"tcp:Redis:127.0.0.1:6379",
		"http:central-auth:http://127.0.0.1:3020/readyz",
		"http:backend:http://127.0.0.1:8000/api/health",
	}
	if strings.Join(calls, "\n") != strings.Join(want, "\n") {
		t.Fatalf("dependency calls = %#v, want %#v", calls, want)
	}
}

func TestLatestImageRefTracksLatest(t *testing.T) {
	cases := map[string]string{
		"unicron-appliance:v1.2.3":                  "unicron-appliance:latest",
		"logforge/unicron:v1.2.3":                   "logforge/unicron:latest",
		"registry.local:5000/unicron/app:v1.2.3":    "registry.local:5000/unicron/app:latest",
		"registry.local:5000/unicron/app@sha256:ab": "registry.local:5000/unicron/app:latest",
		"logforge/unicron":                          "logforge/unicron:latest",
		"sha256:abcdef":                             "",
	}
	for input, want := range cases {
		if got := latestImageRef(input); got != want {
			t.Fatalf("latestImageRef(%q) = %q, want %q", input, got, want)
		}
	}
}

func TestReplacementCreateSpecPreservesContainerConfig(t *testing.T) {
	current := dockerContainerInspect{
		ID:    "abcdef1234567890",
		Image: "sha256:old",
		Config: map[string]any{
			"Image":    "example/unicron:v1",
			"Env":      []any{"A=B"},
			"Hostname": "abcdef123456",
			"Labels":   map[string]any{"app": "unicron"},
		},
		HostConfig: map[string]any{
			"Binds":          []any{"unicron-data:/var/lib/unicron", "/var/run/docker.sock:/var/run/docker.sock"},
			"ReadonlyRootfs": true,
			"RestartPolicy":  map[string]any{"Name": "unless-stopped"},
		},
		NetworkSettings: dockerNetworkSettings{
			Networks: map[string]map[string]any{
				"unicron-network": {"Aliases": []any{"unicron.central"}},
			},
		},
	}

	spec := replacementCreateSpec(current, "example/unicron:latest")
	if spec["Image"] != "example/unicron:latest" {
		t.Fatalf("replacement image = %v", spec["Image"])
	}
	if _, ok := spec["Hostname"]; ok {
		t.Fatal("default Docker hostname should not be copied to replacement")
	}
	hostConfig, ok := spec["HostConfig"].(map[string]any)
	if !ok {
		t.Fatal("replacement HostConfig missing")
	}
	if hostConfig["ReadonlyRootfs"] != true {
		t.Fatalf("ReadonlyRootfs = %v, want true", hostConfig["ReadonlyRootfs"])
	}
	if _, ok := spec["NetworkingConfig"].(map[string]any); !ok {
		t.Fatal("replacement NetworkingConfig missing")
	}
}

func TestWaitTCP(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	done := make(chan struct{})
	go func() {
		defer close(done)
		conn, err := listener.Accept()
		if err == nil {
			_ = conn.Close()
		}
	}()
	port := listener.Addr().(*net.TCPAddr).Port
	if err := waitTCP("127.0.0.1", port, "test", 1); err != nil {
		t.Fatal(err)
	}
	<-done
}

func TestHealthcheckStatusAggregation(t *testing.T) {
	tmpDir := t.TempDir()
	statusPath := filepath.Join(tmpDir, "status.json")
	specs := serviceSpecs()
	store := newStatusStore(statusPath, specs)
	for _, spec := range specs {
		spec := spec
		store.update(spec.Name, func(status ServiceStatus) ServiceStatus {
			status.State = "running"
			status.PID = os.Getpid()
			return status
		})
	}
	store.heartbeat()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	client := server.Client()
	if err := checkEndpoint(ctx, client, healthEndpoint{name: "test", url: server.URL}); err != nil {
		t.Fatal(err)
	}

	snapshot, err := readStatus(statusPath)
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshot.Services) != len(specs) {
		t.Fatalf("read %d services, want %d", len(snapshot.Services), len(specs))
	}
}

func TestInspectLeafCertificateExpiry(t *testing.T) {
	now := time.Date(2026, 5, 9, 12, 0, 0, 0, time.UTC)

	expired, err := inspectLeafCertificate(writeTestCertificate(t, now.Add(-time.Minute)), now)
	if err != nil {
		t.Fatal(err)
	}
	if !expired.Expired {
		t.Fatalf("expired certificate was reported as valid; not_after=%s", expired.NotAfter)
	}

	valid, err := inspectLeafCertificate(writeTestCertificate(t, now.Add(time.Minute)), now)
	if err != nil {
		t.Fatal(err)
	}
	if valid.Expired {
		t.Fatalf("valid certificate was reported as expired; not_after=%s", valid.NotAfter)
	}
}

func TestEnsureBootstrappedPKIReadyValidLeafDoesNotReissue(t *testing.T) {
	now := time.Date(2026, 5, 9, 12, 0, 0, 0, time.UTC)
	var calls []string
	issueCalls := 0
	ops := testPKIValidationOps(now, &calls)
	ops.inspectLeaf = func(_ string, _ time.Time) (certificateInspection, error) {
		calls = append(calls, "inspect")
		return certificateInspection{NotAfter: now.Add(time.Hour), Expired: false}, nil
	}
	ops.issueLeaf = func(context.Context, RuntimeConfig, pkiPaths) error {
		issueCalls++
		calls = append(calls, "issue")
		return nil
	}

	if err := ensureBootstrappedPKIReadyWithOps(RuntimeConfig{}, pkiPaths{}, ops); err != nil {
		t.Fatal(err)
	}
	if issueCalls != 0 {
		t.Fatalf("issueLeaf called %d times, want 0", issueCalls)
	}
	assertCalls(t, calls, []string{"base", "inspect", "strict", "sync"})
}

func TestEnsureBootstrappedPKIReadyExpiredLeafReissuesAndExports(t *testing.T) {
	now := time.Date(2026, 5, 9, 12, 0, 0, 0, time.UTC)
	var calls []string
	inspectCalls := 0
	ops := testPKIValidationOps(now, &calls)
	ops.inspectLeaf = func(_ string, _ time.Time) (certificateInspection, error) {
		inspectCalls++
		calls = append(calls, "inspect")
		if inspectCalls == 1 {
			return certificateInspection{NotAfter: now.Add(-time.Minute), Expired: true}, nil
		}
		return certificateInspection{NotAfter: now.Add(time.Hour), Expired: false}, nil
	}

	if err := ensureBootstrappedPKIReadyWithOps(RuntimeConfig{}, pkiPaths{}, ops); err != nil {
		t.Fatal(err)
	}
	assertCalls(t, calls, []string{"base", "inspect", "ignore-expiry", "issue", "inspect", "strict", "sync"})
}

func TestEnsureBootstrappedPKIReadyBaseFailuresDoNotReissue(t *testing.T) {
	for _, tc := range []struct {
		name string
		err  error
	}{
		{name: "root fingerprint mismatch", err: errors.New("root CA fingerprint mismatch")},
		{name: "missing provisioner", err: errors.New("CA configuration does not contain required provisioner ra@unicron")},
	} {
		t.Run(tc.name, func(t *testing.T) {
			now := time.Date(2026, 5, 9, 12, 0, 0, 0, time.UTC)
			var calls []string
			ops := testPKIValidationOps(now, &calls)
			ops.validateBase = func(context.Context, pkiPaths) error {
				calls = append(calls, "base")
				return tc.err
			}

			err := ensureBootstrappedPKIReadyWithOps(RuntimeConfig{}, pkiPaths{}, ops)
			if !errors.Is(err, tc.err) {
				t.Fatalf("ensureBootstrappedPKIReadyWithOps() error = %v, want %v", err, tc.err)
			}
			assertCalls(t, calls, []string{"base"})
		})
	}
}

func TestEnsureBootstrappedPKIReadyExpiredLeafNonExpiryFailureDoesNotReissue(t *testing.T) {
	now := time.Date(2026, 5, 9, 12, 0, 0, 0, time.UTC)
	var calls []string
	ops := testPKIValidationOps(now, &calls)
	nonExpiryErr := errors.New("SAN mismatch")
	ops.inspectLeaf = func(_ string, _ time.Time) (certificateInspection, error) {
		calls = append(calls, "inspect")
		return certificateInspection{NotAfter: now.Add(-time.Minute), Expired: true}, nil
	}
	ops.validateLeafIgnoringExpiry = func(RuntimeConfig, pkiPaths, certificateInspection) error {
		calls = append(calls, "ignore-expiry")
		return nonExpiryErr
	}

	err := ensureBootstrappedPKIReadyWithOps(RuntimeConfig{}, pkiPaths{}, ops)
	if !errors.Is(err, nonExpiryErr) {
		t.Fatalf("ensureBootstrappedPKIReadyWithOps() error = %v, want %v", err, nonExpiryErr)
	}
	assertCalls(t, calls, []string{"base", "inspect", "ignore-expiry"})
}

func testPKIValidationOps(now time.Time, calls *[]string) pkiValidationOps {
	return pkiValidationOps{
		now: func() time.Time {
			return now
		},
		validateBase: func(context.Context, pkiPaths) error {
			*calls = append(*calls, "base")
			return nil
		},
		inspectLeaf: func(_ string, _ time.Time) (certificateInspection, error) {
			*calls = append(*calls, "inspect")
			return certificateInspection{NotAfter: now.Add(time.Hour), Expired: false}, nil
		},
		validateLeafIgnoringExpiry: func(RuntimeConfig, pkiPaths, certificateInspection) error {
			*calls = append(*calls, "ignore-expiry")
			return nil
		},
		validateLeafStrict: func(context.Context, RuntimeConfig, pkiPaths) error {
			*calls = append(*calls, "strict")
			return nil
		},
		issueLeaf: func(context.Context, RuntimeConfig, pkiPaths) error {
			*calls = append(*calls, "issue")
			return nil
		},
		syncExports: func(RuntimeConfig, pkiPaths) error {
			*calls = append(*calls, "sync")
			return nil
		},
	}
}

func assertCalls(t *testing.T, got, want []string) {
	t.Helper()
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("calls = %v, want %v", got, want)
	}
}

func writeTestCertificate(t *testing.T, notAfter time.Time) string {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{
		SerialNumber: big.NewInt(notAfter.UnixNano()),
		Subject:      pkix.Name{CommonName: "test.local"},
		NotBefore:    notAfter.Add(-2 * time.Hour),
		NotAfter:     notAfter,
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		DNSNames:     []string{"test.local"},
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "cert.pem")
	if err := os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}
