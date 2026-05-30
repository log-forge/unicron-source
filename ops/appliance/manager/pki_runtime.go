package main

import (
	"context"
	"crypto/tls"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"syscall"
	"time"
)

func runStepCARuntime(cfg RuntimeConfig) error {
	paths := newPKIPaths(cfg)
	logf("PKI-RUNTIME", "[Info] Validating production PKI material")
	if err := ensureBootstrappedPKIReady(cfg, paths); err != nil {
		return err
	}

	stepCmd := exec.Command("step-ca", "--password-file", paths.caPassword, paths.caConfig)
	stepCmd.Stdout = os.Stdout
	stepCmd.Stderr = os.Stderr
	if err := stepCmd.Start(); err != nil {
		return err
	}
	logf("PKI-RUNTIME", "[Info] step-ca started with PID %d", stepCmd.Process.Pid)

	stepDone := make(chan error, 1)
	go func() { stepDone <- stepCmd.Wait() }()

	if err := waitForStepCAHealth(stepCmd.Process.Pid, stepDone); err != nil {
		_ = stepCmd.Process.Signal(syscall.SIGTERM)
		return err
	}

	renewSeconds, err := positiveInt("TRAEFIK_RENEW_EXPIRES_IN_SECONDS", cfg.TraefikRenewExpiresInSeconds)
	if err != nil {
		_ = stepCmd.Process.Signal(syscall.SIGTERM)
		return err
	}
	renewCmd := exec.Command(
		"step", "ca", "renew", paths.traefikCert, paths.traefikKey,
		"--ca-url", "https://unicron-stepca:9000",
		"--root", paths.rootCert,
		"--exec", "/usr/local/bin/unicron-pki-renew-hook",
		"--expires-in", fmt.Sprintf("%ds", renewSeconds),
		"--daemon",
	)
	renewCmd.Stdout = os.Stdout
	renewCmd.Stderr = os.Stderr
	renewCmd.Env = os.Environ()
	if err := renewCmd.Start(); err != nil {
		_ = stepCmd.Process.Signal(syscall.SIGTERM)
		return err
	}
	logf("PKI-RUNTIME", "[Info] Traefik certificate renew daemon started with PID %d", renewCmd.Process.Pid)
	renewDone := make(chan error, 1)
	go func() { renewDone <- renewCmd.Wait() }()

	sigCh := make(chan os.Signal, 2)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
	defer signal.Stop(sigCh)

	for {
		select {
		case sig := <-sigCh:
			logf("PKI-RUNTIME", "[Info] Received %s; stopping PKI children", sig)
			_ = renewCmd.Process.Signal(syscall.SIGTERM)
			_ = stepCmd.Process.Signal(syscall.SIGTERM)
			waitWithTimeout(renewDone, 5*time.Second)
			waitWithTimeout(stepDone, 5*time.Second)
			return nil
		case err := <-stepDone:
			_ = renewCmd.Process.Signal(syscall.SIGTERM)
			waitWithTimeout(renewDone, 5*time.Second)
			return err
		case err := <-renewDone:
			_ = stepCmd.Process.Signal(syscall.SIGTERM)
			waitWithTimeout(stepDone, 5*time.Second)
			if err == nil {
				return fmt.Errorf("Traefik certificate renew daemon exited unexpectedly")
			}
			return fmt.Errorf("Traefik certificate renew daemon exited unexpectedly: %w", err)
		}
	}
}

func waitForStepCAHealth(pid int, stepDone <-chan error) error {
	client := &http.Client{
		Timeout:   1 * time.Second,
		Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}},
	}
	for attempt := 0; attempt < 60; attempt++ {
		select {
		case err := <-stepDone:
			if err == nil {
				return fmt.Errorf("step-ca exited before becoming healthy")
			}
			return fmt.Errorf("step-ca exited before becoming healthy: %w", err)
		default:
		}
		resp, err := client.Get("https://localhost:9000/health")
		if err == nil {
			_ = resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 400 {
				logf("PKI-RUNTIME", "[Info] step-ca health endpoint is ready")
				return nil
			}
		}
		if !processAlive(pid) {
			return fmt.Errorf("step-ca exited before becoming healthy")
		}
		time.Sleep(1 * time.Second)
	}
	return fmt.Errorf("timed out waiting for step-ca health endpoint")
}

func waitWithTimeout(done <-chan error, timeout time.Duration) {
	timer := time.NewTimer(timeout)
	defer timer.Stop()
	select {
	case <-done:
	case <-timer.C:
	}
}

func runPKIRenewHook(cfg RuntimeConfig) error {
	paths := newPKIPaths(cfg)
	if err := copyFile(paths.traefikCert, paths.traefik+"/unicron-traefik-leaf.crt", 0o444); err != nil {
		return err
	}
	if err := copyFile(paths.traefikKey, paths.traefik+"/unicron-traefik-leaf.key", 0o400); err != nil {
		return err
	}
	if err := copyFile(paths.rootCert, paths.traefik+"/root_ca.crt", 0o444); err != nil {
		return err
	}
	if err := touch(cfg.TraefikDynamicConfigFile); err != nil {
		return err
	}
	logf("RENEW-HOOK", "Traefik certs renewed successfully")
	return nil
}

func waitHTTPSInsecure(url, name string, attempts int) error {
	client := &http.Client{
		Timeout:   1 * time.Second,
		Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}},
	}
	return waitHTTPWithClient(context.Background(), client, url, name, attempts)
}
