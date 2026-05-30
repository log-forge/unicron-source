package main

import (
	"sync"
	"time"
)

// ContainerStats represents stats for a single container
type ContainerStats struct {
	ContainerID   string
	ContainerName string
	HostID        string
	CPUPercent    float64
	MemoryUsage   uint64
	MemoryLimit   uint64
	MemoryPercent float64
	NetworkRx     uint64
	NetworkTx     uint64
	BlockRead     uint64
	BlockWrite    uint64
	LastUpdate    time.Time
}

// StatsCache stores container stats in memory with TTL-based expiry
type StatsCache struct {
	mu             sync.RWMutex
	containerStats map[string]*ContainerStats
	ttl            time.Duration
}

// NewStatsCache creates a new stats cache
func NewStatsCache(ttl time.Duration) *StatsCache {
	return &StatsCache{
		containerStats: make(map[string]*ContainerStats),
		ttl:            ttl,
	}
}

// UpdateContainerStats updates stats for a container
func (c *StatsCache) UpdateContainerStats(stats *ContainerStats) {
	stats.LastUpdate = time.Now()
	c.mu.Lock()
	c.containerStats[stats.ContainerID] = stats
	c.mu.Unlock()
}

// GetContainerStats returns stats for a specific container
func (c *StatsCache) GetContainerStats(containerID string) (*ContainerStats, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	stats, ok := c.containerStats[containerID]
	return stats, ok
}

// GetAllContainerStats returns all container stats
func (c *StatsCache) GetAllContainerStats() []*ContainerStats {
	c.mu.RLock()
	defer c.mu.RUnlock()

	result := make([]*ContainerStats, 0, len(c.containerStats))
	for _, stats := range c.containerStats {
		result = append(result, stats)
	}
	return result
}

// RemoveContainerStats removes stats for a container
func (c *StatsCache) RemoveContainerStats(containerID string) {
	c.mu.Lock()
	delete(c.containerStats, containerID)
	c.mu.Unlock()
}

// CleanStaleStats removes stats older than TTL
func (c *StatsCache) CleanStaleStats() {
	now := time.Now()
	c.mu.Lock()
	defer c.mu.Unlock()

	for id, stats := range c.containerStats {
		if now.Sub(stats.LastUpdate) > c.ttl {
			delete(c.containerStats, id)
		}
	}
}
