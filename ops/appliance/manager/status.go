package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type ServiceSpec struct {
	Name      string
	StartSecs time.Duration
	Critical  bool
}

type ServiceStatus struct {
	Name      string    `json:"name"`
	State     string    `json:"state"`
	PID       int       `json:"pid"`
	Restarts  int       `json:"restarts"`
	LastStart time.Time `json:"last_start,omitempty"`
	LastExit  time.Time `json:"last_exit,omitempty"`
	ExitCode  int       `json:"exit_code,omitempty"`
	Message   string    `json:"message,omitempty"`
}

type StatusSnapshot struct {
	UpdatedAt time.Time                `json:"updated_at"`
	Services  map[string]ServiceStatus `json:"services"`
}

type statusStore struct {
	mu       sync.Mutex
	path     string
	services map[string]ServiceStatus
}

func newStatusStore(path string, specs []ServiceSpec) *statusStore {
	services := make(map[string]ServiceStatus, len(specs))
	for _, spec := range specs {
		services[spec.Name] = ServiceStatus{Name: spec.Name, State: "pending"}
	}
	return &statusStore{path: path, services: services}
}

func (s *statusStore) update(name string, mutate func(ServiceStatus) ServiceStatus) {
	s.mu.Lock()
	defer s.mu.Unlock()
	current := s.services[name]
	if current.Name == "" {
		current.Name = name
	}
	s.services[name] = mutate(current)
	_ = s.writeLocked()
}

func (s *statusStore) heartbeat() {
	s.mu.Lock()
	defer s.mu.Unlock()
	_ = s.writeLocked()
}

func (s *statusStore) writeLocked() error {
	snapshot := StatusSnapshot{
		UpdatedAt: time.Now().UTC(),
		Services:  make(map[string]ServiceStatus, len(s.services)),
	}
	for name, status := range s.services {
		snapshot.Services[name] = status
	}
	body, err := json.MarshalIndent(snapshot, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(s.path), 0o755); err != nil {
		return err
	}
	tmp := s.path + ".tmp"
	if err := os.WriteFile(tmp, body, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, s.path)
}

func readStatus(path string) (StatusSnapshot, error) {
	var snapshot StatusSnapshot
	body, err := os.ReadFile(path)
	if err != nil {
		return snapshot, err
	}
	err = json.Unmarshal(body, &snapshot)
	return snapshot, err
}
