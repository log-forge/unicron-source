package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	defaultDataDir       = "/var/lib/unicron"
	defaultManagerPath   = "/usr/local/bin/unicron-appliance-manager"
	defaultStatusPath    = "/run/unicron-appliance/status.json"
	defaultOTelConfigSrc = "/opt/unicron/appliance/otel-collector-config.yaml"
	defaultTraefikTpl    = "/opt/unicron/appliance/traefik-config.template.yaml"
	defaultDockerSocket  = "/var/run/docker.sock"
	defaultUpdaterAddr   = "127.0.0.1:7078"
)

type RuntimeConfig struct {
	DataDir                  string
	StepPath                 string
	TmpDir                   string
	TraefikDynamicConfigFile string
	TraefikTemplateFile      string
	OTelConfigSource         string
	StatusFile               string
	DockerSocket             string
	SelfUpdateEnabled        bool
	UpdateImageRef           string
	UpdaterAddr              string
	UpdateStateFile          string
	UpdateInterval           time.Duration
	ApplianceContainerName   string

	CentralFQDN           string
	CentralPort           string
	PublicCentralPort     string
	CentralMTLSPort       string
	PublicCentralMTLSPort string
	FrontendPort          string

	PostgresUser string
	PostgresDB   string

	CentralAuthMongoDBName string
	CentralAuthCookieName  string
	CentralAuthPublicURL   string

	TraefikRouterHosts string
	TraefikCertSANs    string
	StepCADNS          string
	StepRADNS          string

	TraefikCertNotAfterSeconds   string
	TraefikRenewExpiresInSeconds string
	RADefaultTLSCertDuration     string
	RAMaxTLSCertDuration         string
}

func loadConfig() RuntimeConfig {
	dataDir := setDefaultEnv("UNICRON_DATA_DIR", defaultDataDir)
	stepPath := setDefaultEnv("STEPPATH", dataDir+"/pki")
	traefikConfig := setDefaultEnv("TRAEFIK_DYNAMIC_CONFIG_FILE", dataDir+"/traefik/traefik-config.yaml")
	tmpDir := setDefaultEnv("TMPDIR", "/run/pyinstaller")
	selfUpdateEnabled := parseBoolEnv(setDefaultEnv("UNICRON_SELF_UPDATE_ENABLED", "true"), true)
	updaterAddr := setDefaultEnv("UNICRON_APPLIANCE_UPDATER_ADDR", defaultUpdaterAddr)
	updateInterval := parseDurationSecondsEnv("UNICRON_UPDATE_INTERVAL_SECONDS", 6*time.Hour)

	centralFQDN := setDefaultEnv("UNICRON_CENTRAL_FQDN", "unicron.central")
	centralPort := setDefaultEnv("UNICRON_CENTRAL_PORT", "443")
	publicCentralPort := setDefaultEnv("UNICRON_PUBLIC_CENTRAL_PORT", centralPort)
	mtlsPort := setDefaultEnv("UNICRON_CENTRAL_MTLS_PORT", "8443")
	publicMTLSPort := setDefaultEnv("UNICRON_PUBLIC_CENTRAL_MTLS_PORT", mtlsPort)
	frontendPort := setDefaultEnv("UNICRON_FRONTEND_PORT", "5173")

	postgresUser := setDefaultEnv("POSTGRES_USER", "unicron")
	postgresDB := setDefaultEnv("POSTGRES_DB", "unicron")
	setDefaultEnv("CENTRAL_ADMIN_USERNAME", "admin")
	setDefaultEnv("CENTRAL_ADMIN_RECOVERY_OVERRIDE", "false")
	authDBName := setDefaultEnv("CENTRAL_AUTH_MONGODB_DB_NAME", "unicron_central_auth")
	authCookieName := setDefaultEnv("CENTRAL_AUTH_COOKIE_NAME", "unicron.central_auth.session")
	authPublicURL := setDefaultEnv("CENTRAL_AUTH_PUBLIC_BASE_URL", fmt.Sprintf("https://%s:%s", centralFQDN, publicCentralPort))

	routerHosts := setDefaultEnv(
		"TRAEFIK_ROUTER_HOSTS",
		normalizeCSVSpaces(fmt.Sprintf("localhost, 127.0.0.1, host.docker.internal, unicron.central, %s", centralFQDN)),
	)
	certSANs := setDefaultEnv(
		"TRAEFIK_CERT_SANS",
		normalizeCSVSpaces(fmt.Sprintf("localhost, 127.0.0.1, host.docker.internal, unicron.central, unicron-stepca, unicron-stepca-ra, %s", centralFQDN)),
	)
	stepCADNS := setDefaultEnv(
		"STEP_CA_DNS",
		normalizeCSVSpaces(fmt.Sprintf("unicron.central, unicron-stepca, %s", centralFQDN)),
	)
	stepRADNS := setDefaultEnv(
		"STEP_RA_DNS",
		normalizeCSVSpaces(fmt.Sprintf("unicron.central, unicron-stepca-ra, %s", centralFQDN)),
	)
	notAfter := setDefaultEnv("TRAEFIK_CERT_NOT_AFTER_SECONDS", "43200")
	renewExpires := setDefaultEnv("TRAEFIK_RENEW_EXPIRES_IN_SECONDS", "28800")
	raDefaultDur := setDefaultEnv("RA_DEFAULT_TLS_CERT_DURATION", "12h")
	raMaxDur := setDefaultEnv("RA_MAX_TLS_CERT_DURATION", "12h")
	setDefaultEnv("TRAEFIK_EXPOSE_VICTORIA_UI", "false")

	return RuntimeConfig{
		DataDir:                      dataDir,
		StepPath:                     stepPath,
		TmpDir:                       tmpDir,
		TraefikDynamicConfigFile:     traefikConfig,
		TraefikTemplateFile:          envOrDefault("TRAEFIK_TEMPLATE_FILE", defaultTraefikTpl),
		OTelConfigSource:             envOrDefault("OTEL_CONFIG_SOURCE", defaultOTelConfigSrc),
		StatusFile:                   envOrDefault("UNICRON_APPLIANCE_STATUS_FILE", defaultStatusPath),
		DockerSocket:                 envOrDefault("UNICRON_APPLIANCE_DOCKER_SOCKET", defaultDockerSocket),
		SelfUpdateEnabled:            selfUpdateEnabled,
		UpdateImageRef:               envOrDefault("UNICRON_UPDATE_IMAGE_REF", ""),
		UpdaterAddr:                  updaterAddr,
		UpdateStateFile:              envOrDefault("UNICRON_UPDATE_STATE_FILE", dataDir+"/appliance-update/state.json"),
		UpdateInterval:               updateInterval,
		ApplianceContainerName:       envOrDefault("UNICRON_APPLIANCE_CONTAINER_NAME", ""),
		CentralFQDN:                  centralFQDN,
		CentralPort:                  centralPort,
		PublicCentralPort:            publicCentralPort,
		CentralMTLSPort:              mtlsPort,
		PublicCentralMTLSPort:        publicMTLSPort,
		FrontendPort:                 frontendPort,
		PostgresUser:                 postgresUser,
		PostgresDB:                   postgresDB,
		CentralAuthMongoDBName:       authDBName,
		CentralAuthCookieName:        authCookieName,
		CentralAuthPublicURL:         authPublicURL,
		TraefikRouterHosts:           routerHosts,
		TraefikCertSANs:              certSANs,
		StepCADNS:                    stepCADNS,
		StepRADNS:                    stepRADNS,
		TraefikCertNotAfterSeconds:   notAfter,
		TraefikRenewExpiresInSeconds: renewExpires,
		RADefaultTLSCertDuration:     raDefaultDur,
		RAMaxTLSCertDuration:         raMaxDur,
	}
}

func parseBoolEnv(value string, fallback bool) bool {
	normalized := strings.ToLower(strings.TrimSpace(value))
	if normalized == "" {
		return fallback
	}
	switch normalized {
	case "1", "true", "yes", "y", "on":
		return true
	case "0", "false", "no", "n", "off":
		return false
	default:
		return fallback
	}
}

func parseDurationSecondsEnv(name string, fallback time.Duration) time.Duration {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback
	}
	seconds, err := strconv.Atoi(value)
	if err != nil || seconds <= 0 {
		return fallback
	}
	return time.Duration(seconds) * time.Second
}

func setDefaultEnv(key, value string) string {
	if current := os.Getenv(key); current != "" {
		return current
	}
	_ = os.Setenv(key, value)
	return value
}

func envOrDefault(key, value string) string {
	if current := os.Getenv(key); current != "" {
		return current
	}
	return value
}

func requireEnv(name string) error {
	if strings.TrimSpace(os.Getenv(name)) == "" {
		return fmt.Errorf("%s is required", name)
	}
	return nil
}

func requireEnvMinLen(name string, minLen int) error {
	value := os.Getenv(name)
	if value == "" {
		return fmt.Errorf("%s is required", name)
	}
	if len(value) < minLen {
		return fmt.Errorf("%s must be at least %d characters", name, minLen)
	}
	return nil
}

func validateRequiredSecrets() error {
	for _, name := range []string{
		"POSTGRES_PASSWORD",
		"INTERNAL_API_SECRET",
	} {
		if err := requireEnv(name); err != nil {
			return err
		}
	}
	for _, item := range []struct {
		name string
		min  int
	}{
		{"CENTRAL_AUTH_SECRET", 32},
		{"CSRF_COOKIE_SECRET", 32},
		{"CSRF_SECRET", 32},
	} {
		if err := requireEnvMinLen(item.name, item.min); err != nil {
			return err
		}
	}
	return nil
}

func normalizeCSVSpaces(value string) string {
	parts := csvFields(value)
	return strings.Join(parts, ", ")
}

func csvFields(value string) []string {
	rawParts := strings.Split(value, ",")
	parts := make([]string, 0, len(rawParts))
	for _, raw := range rawParts {
		item := strings.TrimSpace(raw)
		if item != "" {
			parts = append(parts, item)
		}
	}
	return parts
}
