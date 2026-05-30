package main

import (
	"encoding/json"
	"testing"
	"time"

	containertypes "github.com/docker/docker/api/types/container"
)

func TestProcessStatsIncludesContainerKeyInUpstreamPayload(t *testing.T) {
	up := newTestUpstreamClient(2, 2, 10*time.Millisecond)
	sm := &StreamManager{
		images:    map[string]string{"docker-123": "registry:5000/unicron-go-streamer:latest"},
		hostID:    "herald",
		upstream:  up,
		prevStats: make(map[string]*containerPrevStats),
		cache:     NewStatsCache(time.Minute),
	}

	stats := &containertypes.StatsResponse{
		MemoryStats: containertypes.MemoryStats{
			Usage: 1024,
			Limit: 2048,
		},
		Networks: map[string]containertypes.NetworkStats{
			"eth0": {RxBytes: 10, TxBytes: 20},
		},
	}

	sm.processStats(stats, "docker-123", "unicron-agent-herald")

	env := readTelemetryEnvelope(t, up)
	if env.Type != "stats" {
		t.Fatalf("unexpected telemetry envelope type %q", env.Type)
	}

	var payload map[string]any
	if err := json.Unmarshal(env.Data, &payload); err != nil {
		t.Fatalf("unmarshal stats payload: %v", err)
	}
	if got := payload["container_key"]; got != "herald:unicron-agent-herald" {
		t.Fatalf("expected canonical container_key, got %+v", got)
	}
}
