package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
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
	if err := setupAppliance(cfg); err != nil {
		return err
	}
	logf("APPLIANCE-ENTRY", "Starting managed appliance runtime")
	return supervise(context.Background(), cfg)
}
