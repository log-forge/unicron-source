package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

func main() {
	if err := dispatch(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func dispatch() error {
	cfg := loadConfig()
	invokedAs := filepath.Base(os.Args[0])
	if invokedAs == "unicron-pki-renew-hook" {
		return runPKIRenewHook(cfg)
	}

	if len(os.Args) < 2 {
		return runEntrypoint(cfg)
	}
	switch os.Args[1] {
	case "run":
		return runEntrypoint(cfg)
	case "run-service":
		if len(os.Args) != 3 {
			return fmt.Errorf("usage: %s run-service <name>", os.Args[0])
		}
		return runService(cfg, os.Args[2])
	case "healthcheck":
		return runHealthcheck(cfg)
	case "pki-renew-hook":
		return runPKIRenewHook(cfg)
	case "update-handoff":
		return runUpdateHandoff(cfg, os.Args[2:])
	default:
		return fmt.Errorf("unknown command %q", os.Args[1])
	}
}

func runEntrypoint(cfg RuntimeConfig) error {
	legacyMigrationRequired, err := legacyMongoMigrationRequired(cfg)
	if err != nil {
		return fmt.Errorf("appliance preflight failed: %w", err)
	}
	cfg.LegacyAuthMigrationRequired = legacyMigrationRequired
	_ = os.Setenv("UNICRON_LEGACY_AUTH_MIGRATION_REQUIRED", strconv.FormatBool(legacyMigrationRequired))
	if legacyMigrationRequired {
		if err := checkMongoRuntimeCompatibility(); err != nil {
			return fmt.Errorf("appliance preflight failed: %w", err)
		}
	}
	if err := setupAppliance(cfg); err != nil {
		return err
	}
	logf("APPLIANCE-ENTRY", "Starting managed appliance runtime")
	return supervise(context.Background(), cfg)
}
