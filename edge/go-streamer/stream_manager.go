package main

import (
	"context"
	"encoding/json"
	"io"
	"strings"
	"sync"
	"time"

	containertypes "github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
	"github.com/sirupsen/logrus"
)

// containerPrevStats tracks previous values for rate calculations
type containerPrevStats struct {
	netRx     uint64
	netTx     uint64
	blkRead   uint64
	blkWrite  uint64
	timestamp time.Time
}

// StreamManager manages persistent stats streams for containers
type StreamManager struct {
	cache        *StatsCache
	cli          *client.Client
	streams      map[string]context.CancelFunc // key: containerID -> cancel func
	streamsMu    sync.RWMutex
	containers   map[string]string // key: containerID -> containerName
	containersMu sync.RWMutex
	images       map[string]string // key: containerID -> image
	imagesMu     sync.RWMutex
	prevStats    map[string]*containerPrevStats // key: containerID -> previous stats for rate calc
	prevStatsMu  sync.RWMutex
	hostID       string
	upstream     *upstreamClient
	hostMemTotal uint64
	hostCPUCount int
}

// NewStreamManager creates a new stream manager
func NewStreamManager(cache *StatsCache, cli *client.Client, hostID string, upstream *upstreamClient) *StreamManager {
	sm := &StreamManager{
		cache:      cache,
		cli:        cli,
		streams:    make(map[string]context.CancelFunc),
		containers: make(map[string]string),
		images:     make(map[string]string),
		prevStats:  make(map[string]*containerPrevStats),
		hostID:     hostID,
		upstream:   upstream,
	}

	// Fetch host capacity for host-relative metrics
	if info, err := cli.Info(context.Background()); err == nil {
		sm.hostMemTotal = uint64(info.MemTotal)
		sm.hostCPUCount = info.NCPU
	} else {
		logrus.WithError(err).Warn("[StreamManager] Failed to read host capacity")
	}

	return sm
}

// StartStream starts a persistent stats stream for a container
func (sm *StreamManager) StartStream(ctx context.Context, containerID, containerName, image string) error {
	sm.streamsMu.Lock()

	if _, exists := sm.streams[containerID]; exists {
		sm.streamsMu.Unlock()
		return nil
	}

	streamCtx, cancel := context.WithCancel(ctx)
	sm.streams[containerID] = cancel
	sm.streamsMu.Unlock()

	sm.containersMu.Lock()
	sm.containers[containerID] = containerName
	sm.containersMu.Unlock()

	sm.imagesMu.Lock()
	sm.images[containerID] = image
	sm.imagesMu.Unlock()

	go sm.streamStats(streamCtx, containerID, containerName)

	logrus.WithFields(logrus.Fields{
		"container": containerName,
		"id":        containerID[:12],
	}).Info("[StreamManager] Started stats stream")

	return nil
}

// StopStream stops the stats stream for a container
func (sm *StreamManager) StopStream(containerID string) {
	sm.streamsMu.Lock()
	cancel, exists := sm.streams[containerID]
	if exists {
		cancel()
		delete(sm.streams, containerID)
	}
	sm.streamsMu.Unlock()

	sm.containersMu.Lock()
	containerName := sm.containers[containerID]
	delete(sm.containers, containerID)
	sm.containersMu.Unlock()

	sm.imagesMu.Lock()
	delete(sm.images, containerID)
	sm.imagesMu.Unlock()

	sm.prevStatsMu.Lock()
	delete(sm.prevStats, containerID)
	sm.prevStatsMu.Unlock()

	sm.cache.RemoveContainerStats(containerID)

	if exists {
		logrus.WithFields(logrus.Fields{
			"container": containerName,
			"id":        containerID[:12],
		}).Info("[StreamManager] Stopped stats stream")
	}
}

// HasStream checks if a stream exists for a container
func (sm *StreamManager) HasStream(containerID string) bool {
	sm.streamsMu.RLock()
	defer sm.streamsMu.RUnlock()
	_, exists := sm.streams[containerID]
	return exists
}

// GetActiveStreamIDs returns all container IDs with active streams
func (sm *StreamManager) GetActiveStreamIDs() []string {
	sm.streamsMu.RLock()
	defer sm.streamsMu.RUnlock()

	ids := make([]string, 0, len(sm.streams))
	for containerID := range sm.streams {
		ids = append(ids, containerID)
	}
	return ids
}

// streamStats maintains a persistent stats stream for a single container
func (sm *StreamManager) streamStats(ctx context.Context, containerID, containerName string) {
	defer func() {
		if r := recover(); r != nil {
			logrus.WithFields(logrus.Fields{
				"container": containerName,
				"panic":     r,
			}).Error("[StreamManager] Recovered from panic in stats stream")
		}
	}()

	backoff := time.Second
	maxBackoff := 30 * time.Second

	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		stats, err := sm.cli.ContainerStats(ctx, containerID, true)
		if err != nil {
			logrus.WithFields(logrus.Fields{
				"container": containerName,
				"error":     err,
				"backoff":   backoff,
			}).Warn("[StreamManager] Error opening stats stream, retrying")
			time.Sleep(backoff)
			if backoff < maxBackoff {
				backoff *= 2
			}
			continue
		}

		backoff = time.Second
		decoder := json.NewDecoder(stats.Body)

		streamActive := true
		for streamActive {
			select {
			case <-ctx.Done():
				stats.Body.Close()
				return
			default:
			}

			var stat containertypes.StatsResponse
			if err := decoder.Decode(&stat); err != nil {
				stats.Body.Close()
				if err == io.EOF || err == context.Canceled {
					logrus.WithField("container", containerName).Debug("[StreamManager] Stats stream ended")
				}
				streamActive = false
				break
			}

			sm.processStats(&stat, containerID, containerName)
		}

		time.Sleep(time.Second)
	}
}

// processStats processes raw Docker stats and updates cache + upstream
func (sm *StreamManager) processStats(stat *containertypes.StatsResponse, containerID, containerName string) {
	cpuPercent := computeCPUPercentUnix(*stat)

	memUsage := stat.MemoryStats.Usage
	memLimit := stat.MemoryStats.Limit
	memPercent := 0.0
	if memLimit > 0 {
		memPercent = (float64(memUsage) / float64(memLimit)) * 100.0
	}

	// Host-relative metrics
	cpuPercentHost := 0.0
	if sm.hostCPUCount > 0 {
		// CPU percent is already normalized per core, scale to host
		cpuPercentHost = cpuPercent / float64(sm.hostCPUCount)
	}
	memPercentHost := 0.0
	if sm.hostMemTotal > 0 {
		memPercentHost = (float64(memUsage) / float64(sm.hostMemTotal)) * 100.0
	}

	// Network stats
	var netRx, netTx uint64
	for _, net := range stat.Networks {
		netRx += net.RxBytes
		netTx += net.TxBytes
	}

	// Block I/O stats
	var blockRead, blockWrite uint64
	for _, bio := range stat.BlkioStats.IoServiceBytesRecursive {
		if bio.Op == "Read" || bio.Op == "read" {
			blockRead += bio.Value
		} else if bio.Op == "Write" || bio.Op == "write" {
			blockWrite += bio.Value
		}
	}

	// Calculate rates from previous values
	now := time.Now()
	var netRxRate, netTxRate, blkReadRate, blkWriteRate float64

	sm.prevStatsMu.Lock()
	prev := sm.prevStats[containerID]
	if prev != nil {
		elapsed := now.Sub(prev.timestamp).Seconds()
		if elapsed > 0 {
			// Calculate bytes per second
			netRxRate = float64(netRx-prev.netRx) / elapsed
			netTxRate = float64(netTx-prev.netTx) / elapsed
			blkReadRate = float64(blockRead-prev.blkRead) / elapsed
			blkWriteRate = float64(blockWrite-prev.blkWrite) / elapsed

			// Handle counter resets (container restart)
			if netRx < prev.netRx {
				netRxRate = 0
			}
			if netTx < prev.netTx {
				netTxRate = 0
			}
			if blockRead < prev.blkRead {
				blkReadRate = 0
			}
			if blockWrite < prev.blkWrite {
				blkWriteRate = 0
			}
		}
	}
	// Update previous stats
	sm.prevStats[containerID] = &containerPrevStats{
		netRx:     netRx,
		netTx:     netTx,
		blkRead:   blockRead,
		blkWrite:  blockWrite,
		timestamp: now,
	}
	sm.prevStatsMu.Unlock()

	// Update cache
	containerStats := &ContainerStats{
		ContainerID:   containerID,
		ContainerName: containerName,
		HostID:        sm.hostID,
		CPUPercent:    cpuPercent,
		MemoryUsage:   memUsage,
		MemoryLimit:   memLimit,
		MemoryPercent: memPercent,
		NetworkRx:     netRx,
		NetworkTx:     netTx,
		BlockRead:     blockRead,
		BlockWrite:    blockWrite,
	}
	sm.cache.UpdateContainerStats(containerStats)

	// Send stats to Central (flat format matching frontend's ContainerStats interface)
	if sm.upstream != nil {
		sm.imagesMu.RLock()
		image := sm.images[containerID]
		sm.imagesMu.RUnlock()
		containerKey := strings.TrimSpace(sm.hostID) + ":" + strings.TrimSpace(containerName)

		statsPayload := map[string]any{
			"container_id":        containerID,
			"container_name":      containerName,
			"container_key":       containerKey,
			"host_id":             sm.hostID,
			"image":               image,
			"timestamp":           time.Now().Unix(),
			"cpu_percent":         cpuPercent,
			"cpu_percent_host":    cpuPercentHost,
			"memory_usage":        float64(memUsage),
			"memory_limit":        float64(memLimit),
			"memory_percent":      memPercent,
			"memory_percent_host": memPercentHost,
			"network_rx_bytes":    float64(netRx),
			"network_tx_bytes":    float64(netTx),
			"network_rx_rate_bps": netRxRate,
			"network_tx_rate_bps": netTxRate,
			"block_read_bytes":    float64(blockRead),
			"block_write_bytes":   float64(blockWrite),
			"block_read_bps":      blkReadRate,
			"block_write_bps":     blkWriteRate,
		}
		sm.upstream.sendStats(statsPayload)
	}
}

func minDuration(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
}
