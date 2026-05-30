package main

import (
	"strings"

	containertypes "github.com/docker/docker/api/types/container"
)

// metricsFrame is the JSON payload for metrics streaming over WebSocket
type metricsFrame struct {
	Version       int            `json:"v"`
	HostID        string         `json:"host_id,omitempty"`
	ContainerID   string         `json:"container_id"`
	ContainerName string         `json:"container_name"`
	Image         string         `json:"image"`
	Timestamp     string         `json:"timestamp"`
	Metrics       map[string]any `json:"metrics"`
}

// computeCPUPercentUnix implements the Docker CLI Linux style CPU% calculation
func computeCPUPercentUnix(v containertypes.StatsResponse) float64 {
	if v.PreCPUStats.CPUUsage.TotalUsage == 0 || v.PreCPUStats.SystemUsage == 0 {
		return 0.0
	}
	cpuDelta := float64(v.CPUStats.CPUUsage.TotalUsage - v.PreCPUStats.CPUUsage.TotalUsage)
	systemDelta := float64(v.CPUStats.SystemUsage - v.PreCPUStats.SystemUsage)
	if systemDelta <= 0.0 || cpuDelta < 0.0 {
		return 0.0
	}
	onlineCPUs := float64(v.CPUStats.OnlineCPUs)
	if onlineCPUs == 0.0 {
		onlineCPUs = float64(len(v.CPUStats.CPUUsage.PercpuUsage))
		if onlineCPUs == 0 {
			onlineCPUs = 1
		}
	}
	cpuPercent := (cpuDelta / systemDelta) * onlineCPUs * 100.0
	if cpuPercent < 0 || cpuPercent > onlineCPUs*100.0 {
		return 0.0
	}
	return cpuPercent
}

// accumulateNetIO sums network I/O across all interfaces
func accumulateNetIO(v containertypes.StatsResponse) (rx float64, tx float64) {
	for _, nw := range v.Networks {
		rx += float64(nw.RxBytes)
		tx += float64(nw.TxBytes)
	}
	return
}

// accumulateBlockIO sums block I/O read and write bytes
func accumulateBlockIO(v containertypes.StatsResponse) (read float64, write float64) {
	for _, bio := range v.BlkioStats.IoServiceBytesRecursive {
		switch strings.ToLower(bio.Op) {
		case "read":
			read += float64(bio.Value)
		case "write":
			write += float64(bio.Value)
		}
	}
	return
}
