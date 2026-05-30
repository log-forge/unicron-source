package main

import (
	"strings"
	"testing"
)

func TestVictoriaMetricsArgsUseSevenDayRetention(t *testing.T) {
	args := victoriaMetricsArgs(RuntimeConfig{DataDir: "/var/lib/unicron"})
	joined := strings.Join(args, "\n")

	for _, want := range []string{
		"-storageDataPath=/var/lib/unicron/victoria-metrics",
		"-retentionPeriod=7d",
	} {
		if !strings.Contains(joined, want) {
			t.Fatalf("victoria-metrics args missing %q: %s", want, joined)
		}
	}
	if strings.Contains(joined, "retention.maxDiskSpaceUsageBytes") {
		t.Fatalf("victoria-metrics args set free size cap: %s", joined)
	}
}

func TestVictoriaLogsArgsUseSevenDayRetention(t *testing.T) {
	args := victoriaLogsArgs(RuntimeConfig{DataDir: "/var/lib/unicron"})
	joined := strings.Join(args, "\n")

	for _, want := range []string{
		"-storageDataPath=/var/lib/unicron/victoria-logs",
		"-retentionPeriod=7d",
	} {
		if !strings.Contains(joined, want) {
			t.Fatalf("victoria-logs args missing %q: %s", want, joined)
		}
	}
	if strings.Contains(joined, "retention.maxDiskSpaceUsageBytes") {
		t.Fatalf("victoria-logs args set free size cap: %s", joined)
	}
}
