package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"
)

func runService(cfg RuntimeConfig, name string) error {
	switch name {
	case "postgres":
		return runPostgres(cfg)
	case "redis":
		return runRedis(cfg)
	case "mongo":
		return runMongo(cfg)
	case "stepca":
		return runStepCARuntime(cfg)
	case "stepca-ra":
		return runStepCARA(cfg)
	case "traefik":
		return runTraefik(cfg)
	case "central-auth":
		return runCentralAuth(cfg)
	case "backend":
		return runBackend(cfg)
	case "frontend":
		return runFrontend(cfg)
	case "alert-engine":
		return runAlertEngine(cfg)
	case "notifier":
		return runNotifier(cfg)
	case "notifier-worker":
		return runNotifierWorker(cfg)
	case "victoria-metrics":
		return runVictoriaMetrics(cfg)
	case "victoria-logs":
		return runVictoriaLogs(cfg)
	case "otel":
		return runOTel(cfg)
	case "appliance-updater":
		return runApplianceUpdater(cfg)
	default:
		return fmt.Errorf("unknown service: %s", name)
	}
}

func runPostgres(cfg RuntimeConfig) error {
	pgData := cfg.DataDir + "/postgres"
	socketDir := "/run/postgresql"
	if err := preparePostgresRuntimeDirs(pgData, socketDir); err != nil {
		return err
	}
	if !fileNonEmpty(pgData + "/PG_VERSION") {
		if err := bootstrapPostgresFromSeed(cfg, pgData, socketDir); err != nil {
			return err
		}
	}
	return execAs("postgres", "postgres", "", "/usr/lib/postgresql/15/bin/postgres", []string{
		"-D", pgData,
		"-c", "unix_socket_directories=" + socketDir,
	})
}

func runRedis(cfg RuntimeConfig) error {
	dir := cfg.DataDir + "/redis"
	if err := ensureDir(dir, 0o755); err != nil {
		return err
	}
	chownR("redis:redis", dir)
	conf := dir + "/redis.conf"
	body := fmt.Sprintf(`bind 127.0.0.1
port 6379
protected-mode yes
dir %s
appendonly yes
save 900 1
save 300 10
save 60 10000
logfile ""
`, dir)
	if err := os.WriteFile(conf, []byte(body), 0o640); err != nil {
		return err
	}
	chownPath("redis:redis", conf)
	_ = os.Chmod(conf, 0o640)
	return execAs("redis", "redis", "", "redis-server", []string{conf})
}

func runMongo(cfg RuntimeConfig) error {
	dir := cfg.DataDir + "/mongo"
	if err := ensureDir(dir, 0o755); err != nil {
		return err
	}
	chownR("mongodb:mongodb", dir)
	return execAs("mongodb", "mongodb", "", "mongod", []string{
		"--dbpath", dir,
		"--bind_ip", "127.0.0.1",
		"--port", "27017",
		"--nounixsocket",
		"--wiredTigerCacheSizeGB", envOrDefault("MONGO_WIREDTIGER_CACHE_GB", "0.25"),
	})
}

func runStepCARA(cfg RuntimeConfig) error {
	if err := waitHTTPSInsecure("https://127.0.0.1:9000/health", "step-ca", 120); err != nil {
		return err
	}
	return execAs("", "", "", "step-ca", []string{
		"--issuer-password-file", cfg.DataDir + "/pki/secrets/ra.jwk.pw",
		cfg.DataDir + "/pki/config/ra-ca.json",
	})
}

func runTraefik(cfg RuntimeConfig) error {
	cert := cfg.DataDir + "/pki/traefik-certs/unicron-traefik-leaf.crt"
	key := cfg.DataDir + "/pki/traefik-certs/unicron-traefik-leaf.key"
	for !fileNonEmpty(cert) || !fileNonEmpty(key) {
		logf("APPLIANCE:traefik", "Waiting for Traefik certificate material")
		time.Sleep(time.Second)
	}
	args := traefikArgs(cfg)
	return execAs("", "", "", "traefik", args)
}

func traefikArgs(cfg RuntimeConfig) []string {
	args := []string{
		"--ping=true",
		"--ping.entrypoint=web",
		"--providers.file.filename=" + cfg.DataDir + "/traefik/traefik-config.yaml",
		"--providers.file.watch=true",
		"--entrypoints.web.address=:80",
		"--entrypoints.web.http.redirections.entrypoint.to=websecure",
		"--entrypoints.web.http.redirections.entrypoint.scheme=https",
		"--entrypoints.web.http.redirections.entrypoint.permanent=true",
		"--entrypoints.websecure.address=:" + cfg.CentralPort,
		"--entrypoints.websecure.http.tls.options=default@file",
		"--entrypoints.mtls.address=:" + cfg.CentralMTLSPort,
		"--entrypoints.mtls.http.tls=true",
		"--entrypoints.mtls.http.tls.options=mtls@file",
		"--log.level=" + envOrDefault("TRAEFIK_LOG_LEVEL", "INFO"),
	}
	if os.Getenv("TRAEFIK_ACCESS_LOG") == "true" {
		args = append(args,
			"--accesslog=true",
			"--accesslog.format=json",
			"--accesslog.fields.defaultmode=drop",
			"--accesslog.fields.names.StartUTC=keep",
			"--accesslog.fields.names.ClientAddr=keep",
			"--accesslog.fields.names.RequestHost=keep",
			"--accesslog.fields.names.RequestMethod=keep",
			"--accesslog.fields.names.DownstreamStatus=keep",
			"--accesslog.fields.names.Duration=keep",
			"--accesslog.fields.names.RouterName=keep",
			"--accesslog.fields.names.ServiceName=keep",
		)
	}
	return args
}

func runCentralAuth(cfg RuntimeConfig) error {
	if err := waitTCP("127.0.0.1", 27017, "MongoDB", 120); err != nil {
		return err
	}
	publicOrigin := fmt.Sprintf("https://%s:%s", cfg.CentralFQDN, cfg.PublicCentralPort)
	setServiceEnv(map[string]string{
		"PORT":            "3020",
		"MONGODB_URI":     "mongodb://127.0.0.1:27017",
		"MONGODB_DB_NAME": cfg.CentralAuthMongoDBName,
		"MONGODB_TLS":     "false",
	})
	setDefaultEnv("CENTRAL_AUTH_BASE_URL", cfg.CentralAuthPublicURL)
	setDefaultEnv(
		"CORS_ORIGINS",
		strings.Join([]string{
			publicOrigin,
			fmt.Sprintf("https://%s:%s", cfg.CentralFQDN, cfg.CentralPort),
			fmt.Sprintf("https://localhost:%s", cfg.PublicCentralPort),
			fmt.Sprintf("https://localhost:%s", cfg.CentralPort),
			fmt.Sprintf("https://127.0.0.1:%s", cfg.PublicCentralPort),
			fmt.Sprintf("https://127.0.0.1:%s", cfg.CentralPort),
		}, ","),
	)
	return execAs("unicron", "unicron", "/opt/unicron/central-auth", "node", []string{"dist/index.js"})
}

func setCommonAppEnv() {
	setServiceEnv(map[string]string{
		"ENVIRONMENT":             envOrDefault("ENVIRONMENT", "production"),
		"POSTGRES_HOST":           "127.0.0.1",
		"POSTGRES_PORT":           "5432",
		"REDIS_URL":               "redis://127.0.0.1:6379/0",
		"SOCKETIO_REDIS_URL":      "redis://127.0.0.1:6379/0",
		"CENTRAL_URL":             "http://127.0.0.1:8000",
		"CENTRAL_VERIFY_TLS":      "false",
		"CENTRAL_AUTH_BASE_URL":   "http://127.0.0.1:3020",
		"CENTRAL_AUTH_VERIFY_TLS": "false",
		"VLOGS_BASE":              "http://127.0.0.1:9428",
		"VMETRICS_BASE":           "http://127.0.0.1:8428",
	})
}

type runtimeWaiter struct {
	Postgres func(RuntimeConfig) error
	TCP      func(host string, port int, name string, attempts int) error
	HTTP     func(url, name string, attempts int) error
}

var defaultRuntimeWaiter = runtimeWaiter{
	Postgres: waitPostgres,
	TCP:      waitTCP,
	HTTP:     waitHTTP,
}

func runBackend(cfg RuntimeConfig) error {
	setCommonAppEnv()
	if err := waitPostgres(cfg); err != nil {
		return err
	}
	if err := waitTCP("127.0.0.1", 6379, "Redis", 120); err != nil {
		return err
	}
	if err := waitHTTP("http://127.0.0.1:3020/readyz", "central-auth", 120); err != nil {
		return err
	}
	setServiceEnv(map[string]string{
		"API_BASE_URL":                     "/unicron/api",
		"ROOT_PATH":                        "/unicron",
		"UNICRON_CENTRAL_MTLS_PORT":        cfg.CentralMTLSPort,
		"UNICRON_PUBLIC_CENTRAL_MTLS_PORT": cfg.PublicCentralMTLSPort,
		"UNICRON_DATA_DIR":                 cfg.DataDir + "/backend",
		"ROOT_CA":                          cfg.DataDir + "/pki/trust/root_ca.crt",
		"REMOTE_AGENT_IMAGE":               envOrDefault("REMOTE_AGENT_IMAGE", "logforge/unicron-agent:latest"),
		"LOCAL_AGENT_CENTRAL_URL":          envOrDefault("LOCAL_AGENT_CENTRAL_URL", "https://unicron.central/unicron"),
		"LOCAL_AGENT_DOCKER_NETWORK":       envOrDefault("LOCAL_AGENT_DOCKER_NETWORK", "unicron-network"),
		"CA_URL":                           fmt.Sprintf("https://%s:9000", cfg.CentralFQDN),
		"RA_URL":                           "https://unicron-stepca-ra:9100",
		"RA_PROVISIONER_KEY":               cfg.DataDir + "/pki/ra-provisioner/ra.jwk.json",
		"RA_PROVISIONER_PASSWORD_FILE":     cfg.DataDir + "/pki/ra-provisioner/ra.jwk.pw",
		"ALERT_ENGINE_URL":                 "http://127.0.0.1:8011",
		"APPLIANCE_UPDATER_URL":            "http://" + cfg.UpdaterAddr,
	})
	cwd := cfg.DataDir + "/backend"
	if err := runCommand(context.Background(), "/opt/unicron/bin/backend-migrate", nil, commandOptions{user: "unicron", group: "unicron", cwd: cwd}); err != nil {
		return err
	}
	return execAs("unicron", "unicron", cwd, "/opt/unicron/bin/backend-api", nil)
}

func runFrontend(cfg RuntimeConfig) error {
	if err := waitHTTP("http://127.0.0.1:8000/api/health", "backend", 120); err != nil {
		return err
	}
	setServiceEnv(map[string]string{
		"PORT":                       cfg.FrontendPort,
		"VITE_NODE_ENV":              "production",
		"VITE_API_BASE_URL":          "/unicron/api",
		"VITE_EXTERNAL_API_BASE_URL": "",
		"VITE_SHOW_RQ_DEVTOOLS":      "false",
		"VITE_BETTER_AUTH_URL":       "",
		"VITE_AUTH_BASE_URL":         "/unicron/auth",
		"VITE_AUTH_MODE":             "cookie",
		"AUTH_BASE_URL":              "http://127.0.0.1:3020",
		"INTERNAL_API_BASE_URL":      "http://127.0.0.1:8000",
	})
	return execAs("unicron", "unicron", "/opt/unicron/frontend", "node", []string{"dist/server/index.js"})
}

func runAlertEngine(cfg RuntimeConfig) error {
	setCommonAppEnv()
	if err := waitAlertEngineDependencies(cfg, defaultRuntimeWaiter); err != nil {
		return err
	}
	setServiceEnv(map[string]string{
		"ROOT_PATH":                  "/alert-engine",
		"CENTRAL_SOCKETIO_URL":       "http://127.0.0.1:8000",
		"CENTRAL_SOCKETIO_PATH":      "/api/socket.io",
		"CENTRAL_INTERNAL_SECRET":    os.Getenv("INTERNAL_API_SECRET"),
		"OTEL_COLLECTOR_METRICS_URL": "http://127.0.0.1:8888/metrics",
	})
	return execAs("unicron", "unicron", cfg.DataDir+"/backend", "/opt/unicron/bin/alert-engine-api", nil)
}

func waitAlertEngineDependencies(cfg RuntimeConfig, waiter runtimeWaiter) error {
	if err := waiter.Postgres(cfg); err != nil {
		return err
	}
	if err := waiter.TCP("127.0.0.1", 6379, "Redis", 120); err != nil {
		return err
	}
	if err := waiter.HTTP("http://127.0.0.1:3020/readyz", "central-auth", 120); err != nil {
		return err
	}
	return waiter.HTTP("http://127.0.0.1:8000/api/health", "backend", 120)
}

func runNotifier(cfg RuntimeConfig) error {
	setCommonAppEnv()
	if err := waitPostgres(cfg); err != nil {
		return err
	}
	if err := waitTCP("127.0.0.1", 6379, "Redis", 120); err != nil {
		return err
	}
	if err := waitHTTP("http://127.0.0.1:3020/readyz", "central-auth", 120); err != nil {
		return err
	}
	setServiceEnv(map[string]string{
		"ROOT_PATH":           "/notifier",
		"ENCRYPTION_KEY_PATH": cfg.DataDir + "/notifier/encryption.key",
	})
	return execAs("unicron", "unicron", cfg.DataDir+"/notifier", "/opt/unicron/bin/notifier-api", nil)
}

func runNotifierWorker(cfg RuntimeConfig) error {
	setCommonAppEnv()
	if err := waitTCP("127.0.0.1", 6379, "Redis", 120); err != nil {
		return err
	}
	if err := waitHTTP("http://127.0.0.1:8012/health", "notifier", 120); err != nil {
		return err
	}
	setServiceEnv(map[string]string{
		"ROOT_PATH":           "/notifier",
		"ENCRYPTION_KEY_PATH": cfg.DataDir + "/notifier/encryption.key",
	})
	return execAs("unicron", "unicron", cfg.DataDir+"/notifier", "/opt/unicron/bin/notifier-worker", nil)
}

const victoriaRetentionPeriod = "7d"

func victoriaMetricsArgs(cfg RuntimeConfig) []string {
	dir := cfg.DataDir + "/victoria-metrics"
	return []string{
		"-storageDataPath=" + dir,
		"-retentionPeriod=" + victoriaRetentionPeriod,
		"-graphiteListenAddr=127.0.0.1:2003",
		"-opentsdbListenAddr=127.0.0.1:4242",
		"-influxListenAddr=127.0.0.1:8089",
		"-httpListenAddr=127.0.0.1:8428",
		"-loggerLevel=" + envOrDefault("VICTORIA_LOG_LEVEL", "INFO"),
		"-loggerFormat=json",
	}
}

func victoriaLogsArgs(cfg RuntimeConfig) []string {
	dir := cfg.DataDir + "/victoria-logs"
	return []string{
		"-storageDataPath=" + dir,
		"-retentionPeriod=" + victoriaRetentionPeriod,
		"-httpListenAddr=127.0.0.1:9428",
	}
}

func runVictoriaMetrics(cfg RuntimeConfig) error {
	dir := cfg.DataDir + "/victoria-metrics"
	if err := ensureDir(dir, 0o755); err != nil {
		return err
	}
	chownR("unicron:unicron", dir)
	return execAs("unicron", "unicron", "", "victoria-metrics", victoriaMetricsArgs(cfg))
}

func runVictoriaLogs(cfg RuntimeConfig) error {
	dir := cfg.DataDir + "/victoria-logs"
	if err := ensureDir(dir, 0o755); err != nil {
		return err
	}
	chownR("unicron:unicron", dir)
	return execAs("unicron", "unicron", "", "victoria-logs", victoriaLogsArgs(cfg))
}

func runOTel(cfg RuntimeConfig) error {
	if err := waitHTTP("http://127.0.0.1:8428/health", "VictoriaMetrics", 120); err != nil {
		return err
	}
	if err := waitHTTP("http://127.0.0.1:9428/health", "VictoriaLogs", 120); err != nil {
		return err
	}
	if err := waitHTTP("http://127.0.0.1:8000/api/health", "backend", 120); err != nil {
		return err
	}
	return execAs("unicron", "unicron", "", "otelcol-contrib", []string{"--config", cfg.DataDir + "/otelcol/collector-config.yaml"})
}

func setServiceEnv(values map[string]string) {
	for key, value := range values {
		_ = os.Setenv(key, value)
	}
}
