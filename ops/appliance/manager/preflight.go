package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"syscall"
	"time"
)

const mongoCompatibilityCheckTimeout = 10 * time.Second

func legacyMongoMigrationRequired(cfg RuntimeConfig) (bool, error) {
	if fileNonEmpty(cfg.LegacyAuthMigrationMarker) {
		return false, nil
	}

	entries, err := os.ReadDir(cfg.DataDir + "/mongo")
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("inspect legacy MongoDB auth data: %w", err)
	}
	for _, entry := range entries {
		name := entry.Name()
		if name == "WiredTiger" || name == "storage.bson" || strings.HasPrefix(name, "collection-") || strings.HasPrefix(name, "index-") {
			return true, nil
		}
	}
	return false, nil
}

func checkMongoRuntimeCompatibility() error {
	if cpuInfo, err := os.ReadFile("/proc/cpuinfo"); err == nil {
		if err := checkMongoCPUFeatures(runtime.GOARCH, string(cpuInfo)); err != nil {
			return err
		}
	}

	ctx, cancel := context.WithTimeout(context.Background(), mongoCompatibilityCheckTimeout)
	defer cancel()
	return probeMongoRuntime(ctx, "mongod", "--version")
}

func checkMongoCPUFeatures(arch, cpuInfo string) error {
	if arch != "amd64" {
		return nil
	}
	fieldFound, avxAvailable := cpuInfoFeatureStatus(cpuInfo, "flags", "avx")
	if fieldFound && !avxAvailable {
		return errors.New("the existing Central Auth data needs a one-time MongoDB migration, but MongoDB 7 requires AVX on x86_64 and Docker does not expose the avx CPU flag; migrate this appliance volume on an AVX-capable host")
	}
	return nil
}

func cpuInfoFeatureStatus(cpuInfo, field, feature string) (bool, bool) {
	fieldFound := false
	for _, line := range strings.Split(cpuInfo, "\n") {
		key, value, found := strings.Cut(line, ":")
		if !found || !strings.EqualFold(strings.TrimSpace(key), field) {
			continue
		}
		fieldFound = true
		featureFound := false
		for _, candidate := range strings.Fields(value) {
			if strings.EqualFold(candidate, feature) {
				featureFound = true
				break
			}
		}
		if !featureFound {
			return true, false
		}
	}
	return fieldFound, fieldFound
}

func probeMongoRuntime(ctx context.Context, command string, args ...string) error {
	var output bytes.Buffer
	cmd := exec.CommandContext(ctx, command, args...)
	cmd.Stdout = &output
	cmd.Stderr = &output
	err := cmd.Run()
	if err == nil {
		return nil
	}
	if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		return fmt.Errorf("MongoDB runtime compatibility check timed out after %s", mongoCompatibilityCheckTimeout)
	}
	if signal, ok := exitSignal(err); ok {
		if signal == syscall.SIGILL {
			return fmt.Errorf("the existing Central Auth data needs a one-time migration, but MongoDB terminated by %s because this CPU does not expose a supported instruction set; migrate this appliance volume on an AVX-capable host", formatSignal(signal))
		}
		return fmt.Errorf("MongoDB runtime compatibility check terminated by %s", formatSignal(signal))
	}
	detail := strings.TrimSpace(output.String())
	if detail != "" {
		return fmt.Errorf("MongoDB runtime compatibility check failed: %w: %s", err, detail)
	}
	return fmt.Errorf("MongoDB runtime compatibility check failed: %w", err)
}
