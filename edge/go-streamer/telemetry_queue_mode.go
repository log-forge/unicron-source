package main

import (
	"os"
	"strconv"
	"strings"

	"github.com/sirupsen/logrus"
)

const (
	telemetryQueueModeDurable = "durable"
	telemetryQueueModeMemory  = "memory"
	defaultMemoryQueueMB      = "256"
	defaultDiskQueueMB        = "1024"
	otelQueueUnitsPerMB       = 250
	otelQueueSizeMin          = 1000
	otelQueueSizeMax          = 200000
	defaultFlbMemBufLimit     = "256MB"
	defaultFlbTailDBPath      = "/tmp/flb/flb_monitored.db"
	memoryFlbTailDBPath       = "/dev/shm/flb_monitored.db"
)

func resolveTelemetryQueueMode() string {
	mode := strings.ToLower(strings.TrimSpace(os.Getenv("TELEMETRY_QUEUE_MODE")))
	switch mode {
	case "", telemetryQueueModeDurable:
		return telemetryQueueModeDurable
	case telemetryQueueModeMemory, "memory-only", "memory_only", "in-memory":
		return telemetryQueueModeMemory
	default:
		logrus.WithField("telemetry_queue_mode", mode).
			Warn("[Telemetry] Unsupported TELEMETRY_QUEUE_MODE, defaulting to durable")
		return telemetryQueueModeDurable
	}
}

func telemetryDurableQueueEnabled(mode string) bool {
	return mode == telemetryQueueModeDurable
}

func ensureTelemetryQueueEnvDefaults() {
	setDefaultEnv("TELEMETRY_MEMORY_QUEUE_MB", defaultMemoryQueueMB)
	setDefaultEnv("TELEMETRY_DISK_QUEUE_MB", defaultDiskQueueMB)
	setDefaultEnv("FLB_MEM_BUF_LIMIT", defaultFlbMemBufLimit)
	setDefaultEnv("FLB_STORAGE_BACKLOG_MEM_LIMIT", defaultFlbMemBufLimit)
	setDefaultEnv("FLB_STORAGE_TOTAL_LIMIT", defaultDiskQueueMB+"MB")
	setDefaultEnv("FLB_STORAGE_SYNC", "normal")
	setDefaultEnv("UPSTREAM_CRITICAL_QUEUE_SIZE", strconv.Itoa(defaultCriticalQueueSize))
	setDefaultEnv("UPSTREAM_TELEMETRY_QUEUE_SIZE", strconv.Itoa(defaultTelemetryQueueSize))
	setDefaultEnv("UPSTREAM_CRITICAL_ENQUEUE_TIMEOUT_MS", strconv.Itoa(defaultCriticalEnqueueTimeoutMs))
	mode := resolveTelemetryQueueMode()
	ensureOTelQueueSize(mode)

	if strings.TrimSpace(os.Getenv("FLB_TAIL_DB_PATH")) == "" {
		if telemetryDurableQueueEnabled(mode) {
			_ = os.Setenv("FLB_TAIL_DB_PATH", defaultFlbTailDBPath)
		} else {
			_ = os.Setenv("FLB_TAIL_DB_PATH", memoryFlbTailDBPath)
		}
	}
}

func ensureOTelQueueSize(mode string) {
	if strings.TrimSpace(os.Getenv("OTEL_SENDING_QUEUE_SIZE")) != "" {
		return
	}

	memoryMB := parsePositiveEnvInt("TELEMETRY_MEMORY_QUEUE_MB", 256)
	diskMB := parsePositiveEnvInt("TELEMETRY_DISK_QUEUE_MB", 1024)
	budgetMB := memoryMB
	if telemetryDurableQueueEnabled(mode) {
		budgetMB = diskMB
	}

	queueSize := budgetMB * otelQueueUnitsPerMB
	if queueSize < otelQueueSizeMin {
		queueSize = otelQueueSizeMin
	}
	if queueSize > otelQueueSizeMax {
		queueSize = otelQueueSizeMax
	}

	_ = os.Setenv("OTEL_SENDING_QUEUE_SIZE", strconv.Itoa(queueSize))
}

func parsePositiveEnvInt(key string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	v, err := strconv.Atoi(raw)
	if err != nil || v <= 0 {
		return fallback
	}
	return v
}

func setDefaultEnv(key string, value string) {
	if strings.TrimSpace(os.Getenv(key)) == "" {
		_ = os.Setenv(key, value)
	}
}
