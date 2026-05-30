package main

import (
	"context"
	"fmt"
	"net/http"
	"time"
)

type healthEndpoint struct {
	name string
	url  string
}

func healthEndpoints(cfg RuntimeConfig) []healthEndpoint {
	return []healthEndpoint{
		{name: "central-auth", url: "http://127.0.0.1:3020/readyz"},
		{name: "backend", url: "http://127.0.0.1:8000/api/health"},
		{name: "frontend", url: "http://127.0.0.1:" + cfg.FrontendPort + "/healthz"},
		{name: "alert-engine", url: "http://127.0.0.1:8011/health"},
		{name: "notifier", url: "http://127.0.0.1:8012/health"},
		{name: "victoria-metrics", url: "http://127.0.0.1:8428/health"},
		{name: "victoria-logs", url: "http://127.0.0.1:9428/health"},
		{name: "otel", url: "http://127.0.0.1:13133/healthz"},
	}
}

func runHealthcheck(cfg RuntimeConfig) error {
	snapshot, err := readStatus(cfg.StatusFile)
	if err != nil {
		return err
	}
	if age := time.Since(snapshot.UpdatedAt); age > 45*time.Second {
		return fmt.Errorf("manager status is stale: %s", age.Round(time.Second))
	}
	for _, spec := range serviceSpecs() {
		status, ok := snapshot.Services[spec.Name]
		if !ok {
			return fmt.Errorf("missing service status for %s", spec.Name)
		}
		if status.State != "running" {
			return fmt.Errorf("service %s is %s: %s", spec.Name, status.State, status.Message)
		}
		if status.PID <= 0 || !processAlive(status.PID) {
			return fmt.Errorf("service %s pid %d is not alive", spec.Name, status.PID)
		}
	}

	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	client := &http.Client{Timeout: 2 * time.Second}
	for _, endpoint := range healthEndpoints(cfg) {
		if err := checkEndpoint(ctx, client, endpoint); err != nil {
			return err
		}
	}
	return nil
}

func checkEndpoint(ctx context.Context, client *http.Client, endpoint healthEndpoint) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.url, nil)
	if err != nil {
		return err
	}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("%s health failed: %w", endpoint.name, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 400 {
		return fmt.Errorf("%s health returned status %d", endpoint.name, resp.StatusCode)
	}
	return nil
}
