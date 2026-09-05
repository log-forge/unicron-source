package main

import (
	"context"
	"os"
	"os/exec"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

func serviceSpecs() []ServiceSpec {
	return []ServiceSpec{
		{Name: "postgres", StartSecs: 5 * time.Second, Critical: true},
		{Name: "redis", StartSecs: 3 * time.Second, Critical: true},
		{Name: "stepca", StartSecs: 5 * time.Second, Critical: true},
		{Name: "stepca-ra", StartSecs: 5 * time.Second, Critical: true},
		{Name: "traefik", StartSecs: 5 * time.Second, Critical: true},
		{Name: "victoria-metrics", StartSecs: 5 * time.Second, Critical: true},
		{Name: "victoria-logs", StartSecs: 5 * time.Second, Critical: true},
		{Name: "central-auth", StartSecs: 5 * time.Second, Critical: true},
		{Name: "backend", StartSecs: 5 * time.Second, Critical: true},
		{Name: "frontend", StartSecs: 5 * time.Second, Critical: true},
		{Name: "alert-engine", StartSecs: 5 * time.Second, Critical: true},
		{Name: "notifier", StartSecs: 5 * time.Second, Critical: true},
		{Name: "notifier-worker", StartSecs: 5 * time.Second, Critical: true},
		{Name: "otel", StartSecs: 5 * time.Second, Critical: true},
	}
}

func supervisedServiceSpecs(cfg RuntimeConfig) []ServiceSpec {
	specs := append([]ServiceSpec{}, serviceSpecs()...)
	if cfg.LegacyAuthMigrationRequired {
		mongo := ServiceSpec{Name: "mongo", StartSecs: 5 * time.Second, Critical: true}
		specs = append(specs[:2], append([]ServiceSpec{mongo}, specs[2:]...)...)
	}
	if cfg.SelfUpdateEnabled {
		specs = append(specs, ServiceSpec{Name: "appliance-updater", StartSecs: 2 * time.Second, Critical: false})
	}
	return specs
}

func supervise(ctx context.Context, cfg RuntimeConfig) error {
	specs := supervisedServiceSpecs(cfg)
	store := newStatusStore(cfg.StatusFile, specs)
	store.heartbeat()

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	sigCh := make(chan os.Signal, 4)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
	go func() {
		sig := <-sigCh
		logf("APPLIANCE-ENTRY", "Received %s; stopping appliance services", sig)
		cancel()
	}()

	var wg sync.WaitGroup
	for _, spec := range specs {
		spec := spec
		wg.Add(1)
		go func() {
			defer wg.Done()
			superviseService(ctx, cfg, spec, store)
		}()
		time.Sleep(100 * time.Millisecond)
	}

	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()
	for {
		select {
		case <-ticker.C:
			store.heartbeat()
		case <-ctx.Done():
			<-done
			return nil
		case <-done:
			return nil
		}
	}
}

func superviseService(ctx context.Context, cfg RuntimeConfig, spec ServiceSpec, store *statusStore) {
	restarts := 0
	for {
		if ctx.Err() != nil {
			return
		}
		exe, err := os.Executable()
		if err != nil || exe == "" {
			exe = defaultManagerPath
		}
		cmd := exec.CommandContext(ctx, exe, "run-service", spec.Name)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		cmd.Env = os.Environ()
		cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

		logf("APPLIANCE-ENTRY", "Starting service %s", spec.Name)
		if err := cmd.Start(); err != nil {
			store.update(spec.Name, func(status ServiceStatus) ServiceStatus {
				status.State = "failed"
				status.Message = err.Error()
				status.Restarts = restarts
				return status
			})
			time.Sleep(2 * time.Second)
			restarts++
			continue
		}

		pid := cmd.Process.Pid
		started := time.Now().UTC()
		store.update(spec.Name, func(status ServiceStatus) ServiceStatus {
			status.State = "starting"
			status.PID = pid
			status.LastStart = started
			status.ExitCode = 0
			status.Message = ""
			status.Restarts = restarts
			return status
		})

		exited := make(chan error, 1)
		go func() {
			exited <- cmd.Wait()
		}()

		runningTimer := time.NewTimer(spec.StartSecs)
		select {
		case <-runningTimer.C:
			store.update(spec.Name, func(status ServiceStatus) ServiceStatus {
				if status.PID == pid && status.State == "starting" {
					status.State = "running"
				}
				return status
			})
		case err := <-exited:
			if !runningTimer.Stop() {
				<-runningTimer.C
			}
			storeExit(spec.Name, store, pid, restarts, err)
			restarts++
			sleepOrDone(ctx, 1*time.Second)
			continue
		case <-ctx.Done():
			if !runningTimer.Stop() {
				<-runningTimer.C
			}
			terminateProcessGroup(pid, 10*time.Second)
			<-exited
			return
		}

		select {
		case err := <-exited:
			storeExit(spec.Name, store, pid, restarts, err)
			restarts++
			sleepOrDone(ctx, 1*time.Second)
		case <-ctx.Done():
			terminateProcessGroup(pid, 10*time.Second)
			<-exited
			return
		}
	}
}

func storeExit(name string, store *statusStore, pid, restarts int, err error) {
	code := exitCode(err)
	msg := ""
	if signal, ok := exitSignal(err); ok {
		formattedSignal := formatSignal(signal)
		msg = "terminated by " + formattedSignal
		logf("APPLIANCE-ENTRY", "Service %s terminated by %s (exit code %d)", name, formattedSignal, code)
	} else {
		if err != nil {
			msg = err.Error()
		}
		logf("APPLIANCE-ENTRY", "Service %s exited with code %d", name, code)
	}
	store.update(name, func(status ServiceStatus) ServiceStatus {
		status.State = "exited"
		status.PID = pid
		status.LastExit = time.Now().UTC()
		status.ExitCode = code
		status.Message = msg
		status.Restarts = restarts
		return status
	})
}

func sleepOrDone(ctx context.Context, d time.Duration) {
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-ctx.Done():
	case <-timer.C:
	}
}
