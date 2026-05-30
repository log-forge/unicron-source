package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
)

// ContainerKey identifies a container by name+image composite key.
type ContainerKey struct {
	Name  string `json:"name"`
	Image string `json:"image"`
}

// String returns the composite key string used for map lookups.
func (k ContainerKey) String() string { return k.Name + "|" + k.Image }

// ParseContainerKey parses a "name|image" string back into a ContainerKey.
func ParseContainerKey(s string) ContainerKey {
	parts := strings.SplitN(s, "|", 2)
	if len(parts) == 2 {
		return ContainerKey{Name: parts[0], Image: parts[1]}
	}
	return ContainerKey{Name: s}
}

// MonitoredContainer holds resolved container info for config generation.
type MonitoredContainer struct {
	Name    string
	Image   string
	LogPath string // resolved via Docker inspect
}

// persistedState is the on-disk JSON format for monitoring state.
type persistedState struct {
	Containers map[string]bool `json:"containers"` // "name|image" -> true
	UpdatedAt  string          `json:"updated_at"` // RFC3339
}

// MonitoringState tracks which containers have monitoring enabled.
// Thread-safe via RWMutex. Persists to disk as JSON.
type MonitoringState struct {
	mu         sync.RWMutex
	containers map[string]bool // key is ContainerKey.String()
	filePath   string
}

func normalizeMonitoringName(name string) string {
	return strings.TrimSpace(strings.TrimPrefix(name, "/"))
}

func normalizeMonitoringImage(image string) string {
	return strings.TrimSpace(image)
}

// NewMonitoringState creates a new MonitoringState with the given persistence path.
func NewMonitoringState(filePath string) *MonitoringState {
	if filePath == "" {
		filePath = "/var/lib/go-streamer/monitoring-state.json"
	}
	return &MonitoringState{
		containers: make(map[string]bool),
		filePath:   filePath,
	}
}

// SetEnabled adds or removes a container from monitoring state.
func (s *MonitoringState) SetEnabled(name, image string, enabled bool) {
	name = normalizeMonitoringName(name)
	image = normalizeMonitoringImage(image)
	if name == "" {
		return
	}
	key := ContainerKey{Name: name, Image: image}.String()
	s.mu.Lock()
	defer s.mu.Unlock()
	for raw := range s.containers {
		if ParseContainerKey(raw).Name == name {
			delete(s.containers, raw)
		}
	}
	if enabled {
		s.containers[key] = true
	}
}

// IsMonitored returns whether a container is currently enabled for monitoring.
func (s *MonitoringState) IsMonitored(name, image string) bool {
	name = normalizeMonitoringName(name)
	image = normalizeMonitoringImage(image)
	if name == "" {
		return false
	}
	key := ContainerKey{Name: name, Image: image}.String()
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.containers[key] {
		return true
	}
	for raw, enabled := range s.containers {
		if !enabled {
			continue
		}
		if ParseContainerKey(raw).Name == name {
			return true
		}
	}
	return false
}

// MonitoredKeys returns a slice of all currently monitored container keys.
func (s *MonitoringState) MonitoredKeys() []ContainerKey {
	s.mu.RLock()
	defer s.mu.RUnlock()
	keys := make([]ContainerKey, 0, len(s.containers))
	for k := range s.containers {
		keys = append(keys, ParseContainerKey(k))
	}
	return keys
}

// KeyForName returns the monitored key for a container name when it is unique.
func (s *MonitoringState) KeyForName(name string) (ContainerKey, bool) {
	name = normalizeMonitoringName(name)
	if name == "" {
		return ContainerKey{}, false
	}

	s.mu.RLock()
	defer s.mu.RUnlock()

	var match ContainerKey
	found := false
	for raw := range s.containers {
		key := ParseContainerKey(raw)
		if key.Name != name {
			continue
		}
		if found {
			return ContainerKey{}, false
		}
		match = key
		found = true
	}
	return match, found
}

// ReplaceAll atomically replaces the entire monitoring state map.
// Used for Central sync to reconcile state.
func (s *MonitoringState) ReplaceAll(containers map[string]bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.containers = make(map[string]bool, len(containers))
	for k, v := range containers {
		if v {
			s.containers[k] = true
		}
	}
}

// LoadFromDisk reads the persisted state from disk.
// Returns nil if the file does not exist (fresh start).
func (s *MonitoringState) LoadFromDisk() error {
	data, err := os.ReadFile(s.filePath)
	if err != nil {
		if os.IsNotExist(err) {
			logrus.WithField("path", s.filePath).Info("[TelemetryState] No persisted state file, starting fresh")
			return nil
		}
		return err
	}

	var persisted persistedState
	if err := json.Unmarshal(data, &persisted); err != nil {
		logrus.WithError(err).Warn("[TelemetryState] Failed to parse persisted state, starting fresh")
		return nil
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	s.containers = make(map[string]bool, len(persisted.Containers))
	for k, v := range persisted.Containers {
		if v {
			s.containers[k] = true
		}
	}

	logrus.WithFields(logrus.Fields{
		"count":      len(s.containers),
		"updated_at": persisted.UpdatedAt,
	}).Info("[TelemetryState] Loaded persisted monitoring state")

	return nil
}

// SaveToDisk atomically writes the current monitoring state to disk.
func (s *MonitoringState) SaveToDisk() error {
	s.mu.RLock()
	state := persistedState{
		Containers: make(map[string]bool, len(s.containers)),
		UpdatedAt:  time.Now().UTC().Format(time.RFC3339),
	}
	for k, v := range s.containers {
		state.Containers[k] = v
	}
	s.mu.RUnlock()

	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return err
	}

	// Ensure parent directory exists
	dir := filepath.Dir(s.filePath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}

	return atomicWriteFile(s.filePath, data, 0644)
}

// atomicWriteFile writes data to a file atomically using temp file + rename.
// This ensures no partial reads are possible even if the process crashes mid-write.
func atomicWriteFile(path string, data []byte, perm os.FileMode) error {
	dir := filepath.Dir(path)

	// Create temp file in same directory (ensures same filesystem for rename)
	tmp, err := os.CreateTemp(dir, ".tmp-*")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()

	// Clean up on any error
	success := false
	defer func() {
		if !success {
			_ = tmp.Close()
			_ = os.Remove(tmpPath)
		}
	}()

	// Write data
	if _, err := tmp.Write(data); err != nil {
		return err
	}

	// Fsync to ensure data is on disk before rename
	if err := tmp.Sync(); err != nil {
		return err
	}

	// Close before chmod/rename
	if err := tmp.Close(); err != nil {
		return err
	}

	// Set permissions
	if err := os.Chmod(tmpPath, perm); err != nil {
		return err
	}

	// Atomic rename
	if err := os.Rename(tmpPath, path); err != nil {
		return err
	}

	success = true
	return nil
}
