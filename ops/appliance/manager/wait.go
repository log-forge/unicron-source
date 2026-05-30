package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"time"
)

func waitTCP(host string, port int, name string, attempts int) error {
	address := fmt.Sprintf("%s:%d", host, port)
	for attempt := 0; attempt < attempts; attempt++ {
		conn, err := net.DialTimeout("tcp", address, time.Second)
		if err == nil {
			_ = conn.Close()
			return nil
		}
		time.Sleep(time.Second)
	}
	return fmt.Errorf("timed out waiting for %s at %s", name, address)
}

func waitHTTP(url, name string, attempts int) error {
	client := &http.Client{Timeout: 2 * time.Second}
	return waitHTTPWithClient(context.Background(), client, url, name, attempts)
}

func waitHTTPWithClient(ctx context.Context, client *http.Client, url, name string, attempts int) error {
	var lastErr error
	for attempt := 0; attempt < attempts; attempt++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			return err
		}
		resp, err := client.Do(req)
		if err == nil {
			_, _ = io.Copy(io.Discard, resp.Body)
			_ = resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 400 {
				return nil
			}
			lastErr = fmt.Errorf("status %d", resp.StatusCode)
		} else {
			lastErr = err
		}
		time.Sleep(time.Second)
	}
	return fmt.Errorf("timed out waiting for %s at %s: %w", name, url, lastErr)
}

func waitPostgres(cfg RuntimeConfig) error {
	env := commandEnv(map[string]string{"PGPASSWORD": os.Getenv("POSTGRES_PASSWORD")})
	for attempt := 0; attempt < 120; attempt++ {
		cmd := exec.Command(
			"pg_isready",
			"-h", "127.0.0.1",
			"-p", "5432",
			"-U", cfg.PostgresUser,
			"-d", cfg.PostgresDB,
		)
		cmd.Env = env
		cmd.Stdout = io.Discard
		cmd.Stderr = io.Discard
		if err := cmd.Run(); err == nil {
			return nil
		}
		time.Sleep(time.Second)
	}
	return fmt.Errorf("timed out waiting for Postgres")
}
