package main

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type applianceSecretSpec struct {
	EnvName string
	Path    string
	MinLen  int
	Bytes   int
}

func internalSecretSpecs(cfg RuntimeConfig) []applianceSecretSpec {
	secretDir := filepath.Join(cfg.DataDir, "secrets")
	return []applianceSecretSpec{
		{EnvName: "POSTGRES_PASSWORD", Path: filepath.Join(secretDir, "postgres-password"), MinLen: 1, Bytes: 32},
		{EnvName: "INTERNAL_API_SECRET", Path: filepath.Join(secretDir, "internal-api-secret"), MinLen: 24, Bytes: 32},
		{EnvName: "CENTRAL_AUTH_SECRET", Path: filepath.Join(secretDir, "central-auth-secret"), MinLen: 32, Bytes: 32},
		{EnvName: "CSRF_COOKIE_SECRET", Path: filepath.Join(secretDir, "csrf-cookie-secret"), MinLen: 32, Bytes: 32},
		{EnvName: "CSRF_SECRET", Path: filepath.Join(secretDir, "csrf-secret"), MinLen: 32, Bytes: 32},
	}
}

func stepPasswordSecretSpecs(cfg RuntimeConfig) []applianceSecretSpec {
	paths := newPKIPaths(cfg)
	return []applianceSecretSpec{
		{EnvName: "STEP_CA_PASSWORD", Path: paths.caPassword, MinLen: 1, Bytes: 32},
		{EnvName: "STEP_CA_PROVISIONER_PASSWORD", Path: paths.provisionerPW, MinLen: 1, Bytes: 32},
		{EnvName: "STEP_CA_RA_PASSWORD", Path: paths.raPassword, MinLen: 1, Bytes: 32},
	}
}

func ensureInternalSecrets(cfg RuntimeConfig) error {
	if err := ensureDir(filepath.Join(cfg.DataDir, "secrets"), 0o700); err != nil {
		return err
	}
	for _, spec := range internalSecretSpecs(cfg) {
		if _, err := ensureSecret(spec); err != nil {
			return err
		}
	}
	return validateRequiredSecrets()
}

func ensureStepPasswordFiles(cfg RuntimeConfig) error {
	for _, spec := range stepPasswordSecretSpecs(cfg) {
		if _, err := ensureSecret(spec); err != nil {
			return err
		}
	}
	return nil
}

func ensureSecret(spec applianceSecretSpec) (string, error) {
	if fileNonEmpty(spec.Path) {
		value, err := readSecretFile(spec.Path)
		if err != nil {
			return "", err
		}
		if err := validateSecretValue(spec.EnvName, value, spec.MinLen); err != nil {
			return "", err
		}
		if envValue := strings.TrimSpace(os.Getenv(spec.EnvName)); envValue != "" && envValue != value {
			logf("APPLIANCE-ENTRY", "%s is already persisted; ignoring environment override", spec.EnvName)
		}
		_ = os.Setenv(spec.EnvName, value)
		_ = os.Chmod(spec.Path, 0o600)
		return value, nil
	}

	value := strings.TrimSpace(os.Getenv(spec.EnvName))
	source := "environment"
	if value == "" {
		generated, err := randomSecret(spec.Bytes)
		if err != nil {
			return "", fmt.Errorf("generate %s: %w", spec.EnvName, err)
		}
		value = generated
		source = "generated"
	}
	if err := validateSecretValue(spec.EnvName, value, spec.MinLen); err != nil {
		return "", err
	}
	if err := writeFilePrivate(spec.Path, value); err != nil {
		return "", fmt.Errorf("persist %s to %s: %w", spec.EnvName, spec.Path, err)
	}
	_ = os.Setenv(spec.EnvName, value)
	logf("APPLIANCE-ENTRY", "Persisted %s from %s", spec.EnvName, source)
	return value, nil
}

func readSecretFile(path string) (string, error) {
	body, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(body)), nil
}

func validateSecretValue(name, value string, minLen int) error {
	if strings.TrimSpace(value) == "" {
		return fmt.Errorf("%s is empty", name)
	}
	if minLen > 0 && len(value) < minLen {
		return fmt.Errorf("%s must be at least %d characters", name, minLen)
	}
	return nil
}

func randomSecret(byteCount int) (string, error) {
	if byteCount <= 0 {
		byteCount = 32
	}
	buf := make([]byte, byteCount)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}
