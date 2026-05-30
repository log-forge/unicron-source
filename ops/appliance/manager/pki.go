package main

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type pkiPaths struct {
	stepPath string
	certs    string
	secrets  string
	public   string
	config   string
	raDB     string
	trust    string
	traefik  string
	raExport string

	stamp           string
	rootCert        string
	rootFingerprint string
	traefikCert     string
	traefikKey      string
	localhostCert   string
	localhostKey    string
	caPassword      string
	provisionerPW   string
	raPassword      string
	raJWK           string
	raJWKPublic     string
	caConfig        string
	raConfig        string
}

func newPKIPaths(cfg RuntimeConfig) pkiPaths {
	stepPath := cfg.StepPath
	return pkiPaths{
		stepPath:        stepPath,
		certs:           stepPath + "/certs",
		secrets:         stepPath + "/secrets",
		public:          stepPath + "/public",
		config:          stepPath + "/config",
		raDB:            stepPath + "/ra-db",
		trust:           stepPath + "/trust",
		traefik:         stepPath + "/traefik-certs",
		raExport:        stepPath + "/ra-provisioner",
		stamp:           stepPath + "/.bootstrapped",
		rootCert:        stepPath + "/certs/root_ca.crt",
		rootFingerprint: stepPath + "/certs/root_ca_fingerprint.txt",
		traefikCert:     stepPath + "/certs/unicron-traefik-leaf.crt",
		traefikKey:      stepPath + "/certs/unicron-traefik-leaf.key",
		localhostCert:   stepPath + "/certs/unicron-localhost-leaf.crt",
		localhostKey:    stepPath + "/certs/unicron-localhost-leaf.key",
		caPassword:      stepPath + "/secrets/ca.jwk.pw",
		provisionerPW:   stepPath + "/secrets/provisioner.jwk.pw",
		raPassword:      stepPath + "/secrets/ra.jwk.pw",
		raJWK:           stepPath + "/secrets/ra.jwk.json",
		raJWKPublic:     stepPath + "/public/ra.jwk.json.pub",
		caConfig:        stepPath + "/config/ca.json",
		raConfig:        stepPath + "/config/ra-ca.json",
	}
}

func bootstrapPKI(cfg RuntimeConfig) error {
	paths := newPKIPaths(cfg)
	logf("BOOTSTRAP", "[Info] Starting unicron bootstrap process")

	for _, secret := range []string{paths.caPassword, paths.provisionerPW, paths.raPassword} {
		if !fileNonEmpty(secret) {
			return fmt.Errorf("required secret file not found: %s", secret)
		}
	}
	if err := validatePKIDurations(cfg); err != nil {
		return err
	}

	if fileExists(paths.stamp) {
		logf("BOOTSTRAP", "[Info] Bootstrap stamp found; validating existing PKI material")
		if err := ensureBootstrappedPKIReady(cfg, paths); err != nil {
			return err
		}
		logf("BOOTSTRAP", "[Info] PKI initialization already complete and valid")
		return nil
	}

	if hasAnyPKIMaterial(paths) {
		return fmt.Errorf("PKI material exists but bootstrap stamp %s is missing; refusing to initialize over partial state", paths.stamp)
	}

	for _, dir := range []string{paths.certs, paths.secrets, paths.public, paths.config, paths.raDB} {
		if err := ensureDir(dir, 0o755); err != nil {
			return err
		}
	}
	_ = os.Chown(paths.raDB, 1000, 1000)

	ctx := context.Background()
	logf("BOOTSTRAP", "[Info] Initializing Step CA PKI")
	args := []string{
		"ca", "init",
		"--deployment-type", "standalone",
		"--name", "unicron CA",
	}
	for _, dns := range csvFields(cfg.StepCADNS) {
		args = append(args, "--dns", dns)
	}
	args = append(args,
		"--address", ":9000",
		"--provisioner", "admin",
		"--password-file", paths.caPassword,
		"--provisioner-password-file", paths.provisionerPW,
		"--no-db",
	)
	if err := runCommand(ctx, "step", args, commandOptions{}); err != nil {
		return err
	}

	fingerprint, err := rootFingerprint(ctx, paths)
	if err != nil {
		return err
	}
	if err := os.WriteFile(paths.rootFingerprint, []byte(fingerprint+"\n"), 0o644); err != nil {
		return err
	}

	if !fileNonEmpty(paths.raJWKPublic) || !fileNonEmpty(paths.raJWK) {
		logf("BOOTSTRAP", "[Info] Creating JWK for Step RA")
		_ = os.Remove(paths.raJWKPublic)
		_ = os.Remove(paths.raJWK)
		if err := runCommand(ctx, "step", []string{
			"crypto", "jwk", "create",
			paths.raJWKPublic, paths.raJWK,
			"--kty", "OKP",
			"--curve", "Ed25519",
			"--password-file", paths.raPassword,
		}, commandOptions{}); err != nil {
			return err
		}
	}

	if err := writeRAConfig(cfg, paths, fingerprint); err != nil {
		return err
	}
	if err := ensureRAProvisioner(ctx, cfg, paths); err != nil {
		return err
	}
	if err := issueTraefikCert(ctx, cfg, paths); err != nil {
		return err
	}
	if err := validateTraefikLeafStrict(ctx, cfg, paths); err != nil {
		return err
	}
	if err := issueLocalhostCert(ctx, cfg, paths); err != nil {
		return err
	}
	if err := syncExportCerts(cfg, paths); err != nil {
		return err
	}
	if err := os.WriteFile(paths.stamp, []byte(time.Now().UTC().Format(time.RFC3339)+"\n"), 0o644); err != nil {
		return err
	}
	logf("BOOTSTRAP", "[Info] PKI initialization complete")
	return nil
}

func validatePKIDurations(cfg RuntimeConfig) error {
	renew, err := positiveInt("TRAEFIK_RENEW_EXPIRES_IN_SECONDS", cfg.TraefikRenewExpiresInSeconds)
	if err != nil {
		return err
	}
	notAfter, err := positiveInt("TRAEFIK_CERT_NOT_AFTER_SECONDS", cfg.TraefikCertNotAfterSeconds)
	if err != nil {
		return err
	}
	if renew >= notAfter {
		return fmt.Errorf("TRAEFIK_RENEW_EXPIRES_IN_SECONDS (%d) must be less than TRAEFIK_CERT_NOT_AFTER_SECONDS (%d)", renew, notAfter)
	}
	return nil
}

func positiveInt(name, value string) (int, error) {
	parsed, err := strconv.Atoi(value)
	if err != nil || parsed <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer (got %q)", name, value)
	}
	return parsed, nil
}

type certificateInspection struct {
	Leaf          *x509.Certificate
	Intermediates []*x509.Certificate
	NotBefore     time.Time
	NotAfter      time.Time
	Expired       bool
}

type pkiValidationOps struct {
	now                        func() time.Time
	validateBase               func(context.Context, pkiPaths) error
	inspectLeaf                func(string, time.Time) (certificateInspection, error)
	validateLeafIgnoringExpiry func(RuntimeConfig, pkiPaths, certificateInspection) error
	validateLeafStrict         func(context.Context, RuntimeConfig, pkiPaths) error
	issueLeaf                  func(context.Context, RuntimeConfig, pkiPaths) error
	syncExports                func(RuntimeConfig, pkiPaths) error
}

func defaultPKIValidationOps() pkiValidationOps {
	return pkiValidationOps{
		now:                        time.Now,
		validateBase:               validateBasePKI,
		inspectLeaf:                inspectLeafCertificate,
		validateLeafIgnoringExpiry: validateTraefikLeafIgnoringExpiry,
		validateLeafStrict:         validateTraefikLeafStrict,
		issueLeaf:                  issueTraefikCert,
		syncExports:                syncExportCerts,
	}
}

func ensureBootstrappedPKIReady(cfg RuntimeConfig, paths pkiPaths) error {
	return ensureBootstrappedPKIReadyWithOps(cfg, paths, defaultPKIValidationOps())
}

func ensureBootstrappedPKIReadyWithOps(cfg RuntimeConfig, paths pkiPaths, ops pkiValidationOps) error {
	ctx := context.Background()
	if err := ops.validateBase(ctx, paths); err != nil {
		return err
	}

	now := ops.now()
	inspection, err := ops.inspectLeaf(paths.traefikCert, now)
	if err != nil {
		return fmt.Errorf("inspect Traefik certificate: %w", err)
	}
	if inspection.Expired {
		if err := ops.validateLeafIgnoringExpiry(cfg, paths, inspection); err != nil {
			return fmt.Errorf("expired Traefik certificate has a non-expiry validation failure: %w", err)
		}
		logf("PKI", "[Warn] Traefik certificate expired at %s; reissuing leaf certificate in place", inspection.NotAfter.UTC().Format(time.RFC3339))
		if err := ops.issueLeaf(ctx, cfg, paths); err != nil {
			return fmt.Errorf("reissue expired Traefik certificate: %w", err)
		}
		refreshed, err := ops.inspectLeaf(paths.traefikCert, now)
		if err != nil {
			return fmt.Errorf("inspect reissued Traefik certificate: %w", err)
		}
		if refreshed.Expired {
			return fmt.Errorf("reissued Traefik certificate is already expired: not_after=%s", refreshed.NotAfter.UTC().Format(time.RFC3339))
		}
	}

	if err := ops.validateLeafStrict(ctx, cfg, paths); err != nil {
		return err
	}
	return ops.syncExports(cfg, paths)
}

func validateBasePKI(ctx context.Context, paths pkiPaths) error {
	if !fileExists(paths.stamp) {
		return fmt.Errorf("bootstrap stamp missing: %s", paths.stamp)
	}
	required := []struct {
		path string
		desc string
	}{
		{paths.rootCert, "root CA certificate"},
		{paths.rootFingerprint, "root CA fingerprint"},
		{paths.caConfig, "CA configuration file"},
		{paths.raConfig, "RA configuration"},
		{paths.raJWK, "RA JWK JSON"},
		{paths.raJWKPublic, "RA JWK JSON public key"},
		{paths.localhostCert, "localhost certificate"},
		{paths.localhostKey, "localhost private key"},
		{paths.caPassword, "CA password file"},
		{paths.provisionerPW, "CA provisioner password file"},
		{paths.raPassword, "RA provisioner password file"},
	}
	missing := make([]string, 0)
	for _, item := range required {
		if !fileNonEmpty(item.path) {
			missing = append(missing, fmt.Sprintf("%s (%s)", item.path, item.desc))
		}
	}
	if len(missing) > 0 {
		return fmt.Errorf("one or more required cert/key files are missing or empty: %s", strings.Join(missing, "; "))
	}
	actual, err := rootFingerprint(ctx, paths)
	if err != nil {
		return err
	}
	expectedRaw, err := os.ReadFile(paths.rootFingerprint)
	if err != nil {
		return err
	}
	expected := strings.TrimSpace(string(expectedRaw))
	if actual != expected {
		return fmt.Errorf("root CA fingerprint mismatch: expected %s got %s", expected, actual)
	}
	hasProvisioner, err := caConfigHasProvisioner(paths.caConfig, "ra@unicron")
	if err != nil {
		return err
	}
	if !hasProvisioner {
		return fmt.Errorf("CA configuration does not contain required provisioner ra@unicron")
	}
	raFingerprint, err := raConfigFingerprint(paths.raConfig)
	if err != nil {
		return err
	}
	if raFingerprint != actual {
		return fmt.Errorf("RA configuration does not reference current root fingerprint")
	}
	return nil
}

func hasAnyPKIMaterial(paths pkiPaths) bool {
	for _, path := range []string{
		paths.caConfig,
		paths.rootCert,
		paths.certs + "/intermediate_ca.crt",
		paths.secrets + "/root_ca_key",
		paths.secrets + "/intermediate_ca_key",
		paths.raJWK,
		paths.raJWKPublic,
		paths.raConfig,
		paths.traefikCert,
		paths.traefikKey,
		paths.localhostCert,
		paths.localhostKey,
	} {
		if _, err := os.Stat(path); err == nil {
			return true
		}
	}
	return false
}

func rootFingerprint(ctx context.Context, paths pkiPaths) (string, error) {
	certs, err := parseCertificatePEMFile(paths.rootCert)
	if err != nil {
		return "", err
	}
	fingerprint := sha256.Sum256(certs[0].Raw)
	return hex.EncodeToString(fingerprint[:]), nil
}

func writeRAConfig(cfg RuntimeConfig, paths pkiPaths, fingerprint string) error {
	pubRaw, err := os.ReadFile(paths.raJWKPublic)
	if err != nil {
		return err
	}
	var pubKey any
	if err := json.Unmarshal(pubRaw, &pubKey); err != nil {
		return err
	}
	body := map[string]any{
		"address":  ":9100",
		"dnsNames": csvFields(cfg.StepRADNS),
		"logger": map[string]any{
			"format": "text",
			"level":  "debug",
		},
		"db": map[string]any{
			"type":       "badgerV2",
			"dataSource": paths.raDB,
		},
		"authority": map[string]any{
			"type":                            "stepcas",
			"certificateAuthority":            fmt.Sprintf("https://%s:9000", cfg.CentralFQDN),
			"certificateAuthorityFingerprint": fingerprint,
			"certificateIssuer": map[string]any{
				"type":        "jwk",
				"provisioner": "ra@unicron",
			},
			"provisioners": []map[string]any{
				{
					"type": "JWK",
					"name": "ra@unicron",
					"key":  pubKey,
				},
			},
		},
	}
	rendered, err := json.MarshalIndent(body, "", "  ")
	if err != nil {
		return err
	}
	rendered = append(rendered, '\n')
	return os.WriteFile(paths.raConfig, rendered, 0o644)
}

func ensureRAProvisioner(ctx context.Context, cfg RuntimeConfig, paths pkiPaths) error {
	hasProvisioner, err := caConfigHasProvisioner(paths.caConfig, "ra@unicron")
	if err != nil {
		return err
	}
	if hasProvisioner {
		return nil
	}
	logf("BOOTSTRAP", "[Info] Adding JWK provisioner ra@unicron to the CA")
	return runCommand(ctx, "step", []string{
		"ca", "provisioner", "add", "ra@unicron",
		"--type=JWK",
		"--private-key", paths.raJWK,
		"--public-key", paths.raJWKPublic,
		"--password-file", paths.raPassword,
		"--allow-renewal-after-expiry",
		"--x509-default-dur", cfg.RADefaultTLSCertDuration,
		"--x509-max-dur", cfg.RAMaxTLSCertDuration,
		"--ca-config", paths.caConfig,
	}, commandOptions{})
}

func issueTraefikCert(ctx context.Context, cfg RuntimeConfig, paths pkiPaths) error {
	logf("BOOTSTRAP", "[Info] Generating Traefik certificate signed by the root CA")
	args := []string{
		"ca", "certificate",
		"unicron-traefik",
		paths.traefikCert,
		paths.traefikKey,
		"--offline",
		"--force",
		"--ca-config", paths.caConfig,
	}
	for _, san := range csvFields(cfg.TraefikCertSANs) {
		args = append(args, "--san", san)
	}
	args = append(args,
		"--password-file", paths.caPassword,
		"--provisioner", "ra@unicron",
		"--provisioner-password-file", paths.raPassword,
		"--not-after", cfg.TraefikCertNotAfterSeconds+"s",
	)
	return runCommand(ctx, "step", args, commandOptions{})
}

func issueLocalhostCert(ctx context.Context, cfg RuntimeConfig, paths pkiPaths) error {
	logf("BOOTSTRAP", "[Info] Issuing development localhost certificate")
	args := []string{
		"ca", "certificate",
		"unicron-localhost",
		paths.localhostCert,
		paths.localhostKey,
		"--offline",
		"--force",
		"--ca-config", paths.caConfig,
	}
	for _, san := range csvFields(cfg.TraefikCertSANs) {
		args = append(args, "--san", san)
	}
	args = append(args,
		"--san", "spiffe://unicron/herald/localhost-herald-id",
		"--san", "spiffe://unicron/herald/localhost-herald-common-name",
		"--password-file", paths.caPassword,
		"--provisioner", "ra@unicron",
		"--provisioner-password-file", paths.raPassword,
	)
	return runCommand(ctx, "step", args, commandOptions{})
}

func verifyTraefikSANs(ctx context.Context, cfg RuntimeConfig, paths pkiPaths) error {
	for _, san := range csvFields(cfg.TraefikCertSANs) {
		logf("BOOTSTRAP", "[Info] Verifying Traefik certificate for SAN: %s", san)
		if err := runCommand(ctx, "step", []string{
			"certificate", "verify", paths.traefikCert,
			"--roots", paths.rootCert,
			"--host", san,
		}, commandOptions{quiet: true}); err != nil {
			return fmt.Errorf("Traefik certificate verification for SAN %q failed: %w", san, err)
		}
	}
	return nil
}

func validateTraefikLeafStrict(ctx context.Context, cfg RuntimeConfig, paths pkiPaths) error {
	if err := validateTraefikKeyPair(paths); err != nil {
		return err
	}
	if err := runCommand(ctx, "step", []string{"certificate", "verify", paths.traefikCert, "--roots", paths.rootCert}, commandOptions{quiet: true}); err != nil {
		return fmt.Errorf("Traefik certificate does not verify against root CA: %w", err)
	}
	return verifyTraefikSANs(ctx, cfg, paths)
}

func validateTraefikLeafIgnoringExpiry(cfg RuntimeConfig, paths pkiPaths, inspection certificateInspection) error {
	if err := validateTraefikKeyPair(paths); err != nil {
		return err
	}
	roots, err := loadCertPool(paths.rootCert)
	if err != nil {
		return err
	}
	intermediates := x509.NewCertPool()
	for _, cert := range inspection.Intermediates {
		intermediates.AddCert(cert)
	}
	validity := inspection.Leaf.NotAfter.Sub(inspection.Leaf.NotBefore)
	if validity <= 0 {
		return fmt.Errorf("Traefik certificate has invalid validity window: not_before=%s not_after=%s", inspection.Leaf.NotBefore.UTC().Format(time.RFC3339), inspection.Leaf.NotAfter.UTC().Format(time.RFC3339))
	}
	verifyTime := inspection.Leaf.NotBefore.Add(validity / 2)
	baseOpts := x509.VerifyOptions{
		Roots:         roots,
		Intermediates: intermediates,
		CurrentTime:   verifyTime,
	}
	if _, err := inspection.Leaf.Verify(baseOpts); err != nil {
		return fmt.Errorf("Traefik certificate chain does not verify against root CA ignoring expiry: %w", err)
	}
	for _, san := range csvFields(cfg.TraefikCertSANs) {
		opts := baseOpts
		opts.DNSName = san
		if _, err := inspection.Leaf.Verify(opts); err != nil {
			return fmt.Errorf("Traefik certificate verification for SAN %q failed ignoring expiry: %w", san, err)
		}
	}
	return nil
}

func validateTraefikKeyPair(paths pkiPaths) error {
	if _, err := tls.LoadX509KeyPair(paths.traefikCert, paths.traefikKey); err != nil {
		return fmt.Errorf("Traefik certificate/key pair is invalid: %w", err)
	}
	return nil
}

func inspectLeafCertificate(path string, now time.Time) (certificateInspection, error) {
	certs, err := parseCertificatePEMFile(path)
	if err != nil {
		return certificateInspection{}, err
	}
	leaf := certs[0]
	return certificateInspection{
		Leaf:          leaf,
		Intermediates: certs[1:],
		NotBefore:     leaf.NotBefore,
		NotAfter:      leaf.NotAfter,
		Expired:       !now.Before(leaf.NotAfter),
	}, nil
}

func parseCertificatePEMFile(path string) ([]*x509.Certificate, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	certs := make([]*x509.Certificate, 0)
	for len(raw) > 0 {
		var block *pem.Block
		block, raw = pem.Decode(raw)
		if block == nil {
			break
		}
		if block.Type != "CERTIFICATE" {
			continue
		}
		cert, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			return nil, err
		}
		certs = append(certs, cert)
	}
	if len(certs) == 0 {
		return nil, fmt.Errorf("no PEM certificate blocks found in %s", path)
	}
	return certs, nil
}

func loadCertPool(path string) (*x509.CertPool, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(raw) {
		return nil, fmt.Errorf("no PEM certificate blocks found in %s", path)
	}
	return pool, nil
}

func caConfigHasProvisioner(path, name string) (bool, error) {
	body, err := readJSONFile(path)
	if err != nil {
		return false, fmt.Errorf("parse CA configuration: %w", err)
	}
	return jsonHasFieldValue(body, "name", name), nil
}

func raConfigFingerprint(path string) (string, error) {
	body, err := readJSONFile(path)
	if err != nil {
		return "", fmt.Errorf("parse RA configuration: %w", err)
	}
	fingerprint, ok := jsonStringField(body, "certificateAuthorityFingerprint")
	if !ok || fingerprint == "" {
		return "", fmt.Errorf("RA configuration missing certificateAuthorityFingerprint")
	}
	return fingerprint, nil
}

func readJSONFile(path string) (any, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var body any
	if err := json.Unmarshal(raw, &body); err != nil {
		return nil, err
	}
	return body, nil
}

func jsonHasFieldValue(value any, field, want string) bool {
	switch typed := value.(type) {
	case map[string]any:
		for key, child := range typed {
			if key == field {
				if got, ok := child.(string); ok && got == want {
					return true
				}
			}
			if jsonHasFieldValue(child, field, want) {
				return true
			}
		}
	case []any:
		for _, child := range typed {
			if jsonHasFieldValue(child, field, want) {
				return true
			}
		}
	}
	return false
}

func jsonStringField(value any, field string) (string, bool) {
	switch typed := value.(type) {
	case map[string]any:
		for key, child := range typed {
			if key == field {
				got, ok := child.(string)
				return got, ok
			}
			if got, ok := jsonStringField(child, field); ok {
				return got, true
			}
		}
	case []any:
		for _, child := range typed {
			if got, ok := jsonStringField(child, field); ok {
				return got, true
			}
		}
	}
	return "", false
}

func syncExportCerts(cfg RuntimeConfig, paths pkiPaths) error {
	logf("PKI", "[Info] Exporting validated material for least-privilege mounts")
	for _, dir := range []string{paths.trust, paths.traefik, paths.raExport} {
		if err := ensureDir(dir, 0o755); err != nil {
			return err
		}
	}
	for _, item := range []struct {
		src  string
		dst  string
		mode os.FileMode
	}{
		{paths.rootCert, paths.trust + "/root_ca.crt", 0o444},
		{paths.rootFingerprint, paths.trust + "/root_ca_fingerprint.txt", 0o444},
		{paths.traefikCert, paths.traefik + "/unicron-traefik-leaf.crt", 0o444},
		{paths.traefikKey, paths.traefik + "/unicron-traefik-leaf.key", 0o400},
		{paths.rootCert, paths.traefik + "/root_ca.crt", 0o444},
		{paths.raJWK, paths.raExport + "/ra.jwk.json", 0o400},
		{paths.raPassword, paths.raExport + "/ra.jwk.pw", 0o400},
	} {
		if err := copyFile(item.src, item.dst, item.mode); err != nil {
			return err
		}
	}
	chownPath("unicron:unicron", paths.raExport+"/ra.jwk.json")
	chownPath("unicron:unicron", paths.raExport+"/ra.jwk.pw")
	if err := touch(cfg.TraefikDynamicConfigFile); err != nil {
		logf("PKI", "[Warn] Could not touch %s: %v", cfg.TraefikDynamicConfigFile, err)
	}
	return nil
}

func validateRuntimePKI(cfg RuntimeConfig, paths pkiPaths) error {
	return ensureBootstrappedPKIReady(cfg, paths)
}
