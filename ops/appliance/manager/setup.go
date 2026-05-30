package main

import (
	"fmt"
	"os"
	"strings"
)

func setupAppliance(cfg RuntimeConfig) error {
	for _, dir := range []string{
		cfg.DataDir + "/backend",
		cfg.DataDir + "/mongo",
		cfg.DataDir + "/notifier",
		cfg.DataDir + "/otelcol",
		cfg.DataDir + "/postgres",
		cfg.DataDir + "/redis",
		cfg.DataDir + "/secrets",
		cfg.DataDir + "/traefik",
		cfg.DataDir + "/victoria-logs",
		cfg.DataDir + "/victoria-metrics",
		cfg.StepPath + "/certs",
		cfg.StepPath + "/config",
		cfg.StepPath + "/public",
		cfg.StepPath + "/secrets",
		cfg.StepPath + "/trust",
		cfg.StepPath + "/traefik-certs",
		cfg.StepPath + "/ra-provisioner",
		"/run/postgresql",
		cfg.TmpDir,
	} {
		if err := ensureDir(dir, 0o755); err != nil {
			return fmt.Errorf("create %s: %w", dir, err)
		}
	}
	if err := ensureDir(cfg.DataDir+"/secrets", 0o700); err != nil {
		return fmt.Errorf("create %s: %w", cfg.DataDir+"/secrets", err)
	}
	_ = os.Chmod(cfg.TmpDir, 0o1777)

	if err := ensureInternalSecrets(cfg); err != nil {
		return err
	}

	if err := preparePostgresRuntimeDirs(cfg.DataDir+"/postgres", "/run/postgresql"); err != nil {
		return err
	}
	chownR("redis:redis", cfg.DataDir+"/redis")
	chownR("mongodb:mongodb", cfg.DataDir+"/mongo")
	chownR(
		"unicron:unicron",
		cfg.DataDir+"/backend",
		cfg.DataDir+"/notifier",
		cfg.DataDir+"/otelcol",
		cfg.DataDir+"/victoria-logs",
		cfg.DataDir+"/victoria-metrics",
		cfg.StepPath+"/trust",
		cfg.StepPath+"/ra-provisioner",
	)

	if err := reconcileInitializedPostgres(cfg, cfg.DataDir+"/postgres", "/run/postgresql"); err != nil {
		return err
	}

	if err := ensureStepPasswordFiles(cfg); err != nil {
		return err
	}

	ensureLoopbackHostAlias("unicron-stepca")
	ensureLoopbackHostAlias("unicron-stepca-ra")
	ensureLoopbackHostAlias("unicron.central")
	ensureLoopbackHostAlias(cfg.CentralFQDN)

	logf("APPLIANCE-ENTRY", "Initializing or validating appliance PKI material")
	if err := bootstrapPKI(cfg); err != nil {
		return err
	}

	logf("APPLIANCE-ENTRY", "Rendering Traefik and OTel configuration")
	if err := renderTraefikFile(cfg); err != nil {
		return err
	}
	if err := copyFile(cfg.OTelConfigSource, cfg.DataDir+"/otelcol/collector-config.yaml", 0o664); err != nil {
		return err
	}
	chownR("unicron:unicron", cfg.DataDir+"/otelcol")
	return nil
}

func ensureLoopbackHostAlias(alias string) {
	if alias == "" {
		return
	}
	body, err := os.ReadFile("/etc/hosts")
	if err == nil {
		for _, field := range strings.Fields(string(body)) {
			if field == alias {
				return
			}
		}
	}
	f, err := os.OpenFile("/etc/hosts", os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = fmt.Fprintf(f, "127.0.0.1 %s\n", alias)
}
