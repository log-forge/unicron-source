package main

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

func TestCheckMongoCPUFeaturesRejectsAMD64WithoutAVX(t *testing.T) {
	cpuInfo := "flags : fpu sse sse2 sse4_1 sse4_2\n"

	err := checkMongoCPUFeatures("amd64", cpuInfo)

	if err == nil {
		t.Fatal("checkMongoCPUFeatures() succeeded without AVX")
	}
	for _, want := range []string{"one-time MongoDB migration", "MongoDB 7 requires AVX", "AVX-capable host"} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error %q does not contain %q", err, want)
		}
	}
}

func TestCheckMongoCPUFeaturesAcceptsAMD64WithAVX(t *testing.T) {
	cpuInfo := "flags : fpu sse sse2 avx avx2\n"

	if err := checkMongoCPUFeatures("amd64", cpuInfo); err != nil {
		t.Fatal(err)
	}
}

func TestCheckMongoCPUFeaturesDefersWhenCPUFlagsAreUnavailable(t *testing.T) {
	if err := checkMongoCPUFeatures("amd64", "processor : 0\n"); err != nil {
		t.Fatal(err)
	}
}

func TestCheckMongoCPUFeaturesDoesNotApplyX86RuleToARM64(t *testing.T) {
	if err := checkMongoCPUFeatures("arm64", "Features : fp asimd\n"); err != nil {
		t.Fatal(err)
	}
}

func TestProbeMongoRuntimeReportsSIGILL(t *testing.T) {
	err := probeMongoRuntime(context.Background(), "/bin/sh", "-c", "kill -ILL $$")

	if err == nil {
		t.Fatal("probeMongoRuntime() succeeded after SIGILL")
	}
	for _, want := range []string{"one-time migration", "SIGILL", "CPU", "AVX-capable host"} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error %q does not contain %q", err, want)
		}
	}
}

func TestLegacyMongoMigrationRequiredOnlyForUnmigratedData(t *testing.T) {
	dataDir := t.TempDir()
	cfg := RuntimeConfig{
		DataDir:                   dataDir,
		LegacyAuthMigrationMarker: filepath.Join(dataDir, "central-auth", "mongodb-migration-complete"),
	}

	required, err := legacyMongoMigrationRequired(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if required {
		t.Fatal("empty appliance data unexpectedly requires MongoDB migration")
	}

	if err := os.MkdirAll(filepath.Join(dataDir, "mongo"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dataDir, "mongo", "WiredTiger"), []byte("legacy-data"), 0o600); err != nil {
		t.Fatal(err)
	}
	required, err = legacyMongoMigrationRequired(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if !required {
		t.Fatal("legacy MongoDB data was not detected")
	}

	if err := os.MkdirAll(filepath.Dir(cfg.LegacyAuthMigrationMarker), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(cfg.LegacyAuthMigrationMarker, []byte("completed\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	required, err = legacyMongoMigrationRequired(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if required {
		t.Fatal("completed migration still requires MongoDB")
	}
}

func TestSupervisedServiceSpecsOnlyIncludesMongoForLegacyMigration(t *testing.T) {
	fresh := supervisedServiceSpecs(RuntimeConfig{})
	legacy := supervisedServiceSpecs(RuntimeConfig{LegacyAuthMigrationRequired: true})

	for _, spec := range fresh {
		if spec.Name == "mongo" {
			t.Fatal("fresh appliance starts MongoDB")
		}
	}
	found := false
	for _, spec := range legacy {
		if spec.Name == "mongo" {
			found = true
		}
	}
	if !found {
		t.Fatal("legacy migration did not start MongoDB")
	}
}

func TestExitCodeAndSignalPreserveSIGILL(t *testing.T) {
	err := exec.Command("/bin/sh", "-c", "kill -ILL $$").Run()

	if got := exitCode(err); got != 132 {
		t.Fatalf("exitCode() = %d, want 132", got)
	}
	signal, ok := exitSignal(err)
	if !ok {
		t.Fatal("exitSignal() did not report a signal")
	}
	if signal != syscall.SIGILL {
		t.Fatalf("exitSignal() = %v, want SIGILL", signal)
	}
	if got := formatSignal(signal); got != "SIGILL (illegal instruction)" {
		t.Fatalf("formatSignal() = %q", got)
	}
}

func TestStoreExitRecordsSIGILL(t *testing.T) {
	err := exec.Command("/bin/sh", "-c", "kill -ILL $$").Run()
	statusPath := filepath.Join(t.TempDir(), "status.json")
	store := newStatusStore(statusPath, []ServiceSpec{{Name: "mongo", Critical: true}})

	storeExit("mongo", store, 42, 3, err)

	snapshot, readErr := readStatus(statusPath)
	if readErr != nil {
		t.Fatal(readErr)
	}
	status := snapshot.Services["mongo"]
	if status.ExitCode != 132 {
		t.Fatalf("ExitCode = %d, want 132", status.ExitCode)
	}
	if status.Message != "terminated by SIGILL (illegal instruction)" {
		t.Fatalf("Message = %q", status.Message)
	}
	if status.Restarts != 3 {
		t.Fatalf("Restarts = %d, want 3", status.Restarts)
	}
}
