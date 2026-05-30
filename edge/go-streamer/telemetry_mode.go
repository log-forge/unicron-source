package main

import (
	"os"
	"strings"

	"github.com/sirupsen/logrus"
)

const (
	telemetryModeHybrid = "hybrid"
	telemetryModeScrape = "scrape"
)

func resolveTelemetryMode() string {
	mode := strings.ToLower(strings.TrimSpace(os.Getenv("TELEMETRY_MODE")))
	switch mode {
	case "", telemetryModeHybrid:
		return telemetryModeHybrid
	case telemetryModeScrape:
		return telemetryModeScrape
	default:
		logrus.WithField("telemetry_mode", mode).Warn("[Telemetry] Unsupported TELEMETRY_MODE, defaulting to hybrid")
		return telemetryModeHybrid
	}
}

func telemetryPushEnabled(mode string) bool {
	return mode == telemetryModeHybrid
}
