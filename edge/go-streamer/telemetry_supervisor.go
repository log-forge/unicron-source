package main

import (
	"context"
	"os"
	"os/exec"
	"sync"
	"syscall"
	"time"

	"github.com/sirupsen/logrus"
)

// ProcessSupervisor manages a child process with automatic restart on crash.
// It keeps the process running indefinitely until the context is cancelled,
// restarting after a fixed 5-second delay on any exit.
type ProcessSupervisor struct {
	name           string                          // "otel-collector" or "fluent-bit" (for logging)
	binPath        string                          // absolute path to binary
	args           []string                        // command-line arguments
	restartDelay   time.Duration                   // fixed 5 seconds
	mu             sync.Mutex                      // protects cmd and healthy
	cmd            *exec.Cmd                       // current running command
	healthy        bool                            // current health state
	onHealthChange func(name string, healthy bool) // callback for health transitions
}

// NewProcessSupervisor creates a new supervisor for the given binary.
// The onHealthChange callback fires whenever the process transitions between
// healthy (running) and unhealthy (stopped/crashed) states.
func NewProcessSupervisor(name, binPath string, args []string, onHealthChange func(string, bool)) *ProcessSupervisor {
	return &ProcessSupervisor{
		name:           name,
		binPath:        binPath,
		args:           args,
		restartDelay:   5 * time.Second,
		onHealthChange: onHealthChange,
	}
}

// Run is the main supervision loop. It starts the process, waits for it to
// exit, then restarts after restartDelay. It runs until ctx is cancelled.
// This method blocks and should be called in a goroutine.
func (ps *ProcessSupervisor) Run(ctx context.Context) {
	log := logrus.WithField("supervisor", ps.name)

	for {
		// Check if context is already cancelled before starting
		select {
		case <-ctx.Done():
			ps.stop(log)
			return
		default:
		}

		// Create command with context for automatic cancellation
		cmd := exec.CommandContext(ctx, ps.binPath, ps.args...)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

		// Store cmd reference under mutex
		ps.mu.Lock()
		ps.cmd = cmd
		ps.mu.Unlock()

		// Start the process
		if err := cmd.Start(); err != nil {
			log.WithError(err).Error("failed to start process")
			ps.setHealthy(false)
			select {
			case <-ctx.Done():
				return
			case <-time.After(ps.restartDelay):
				continue
			}
		}

		// Process started successfully
		ps.setHealthy(true)
		log.WithField("pid", cmd.Process.Pid).Info("process started")

		// Wait for process to exit
		err := cmd.Wait()

		// Process exited
		ps.setHealthy(false)
		if err != nil {
			log.WithError(err).Warn("process exited with error")
		} else {
			log.Info("process exited normally")
		}

		// Check if context is cancelled before sleeping for restart
		select {
		case <-ctx.Done():
			return
		default:
		}

		// Wait before restarting
		log.WithField("delay", ps.restartDelay).Info("restarting after delay")
		select {
		case <-ctx.Done():
			return
		case <-time.After(ps.restartDelay):
		}
	}
}

// Restart triggers a graceful restart by sending SIGTERM to the running process.
// The Run loop will detect the exit and restart the process automatically.
// This is used when configuration changes require a process reload.
func (ps *ProcessSupervisor) Restart() {
	ps.mu.Lock()
	cmd := ps.cmd
	ps.mu.Unlock()

	if cmd != nil && cmd.Process != nil {
		logrus.WithField("supervisor", ps.name).Info("sending SIGTERM for restart")
		_ = cmd.Process.Signal(syscall.SIGTERM)
	}
}

// Stop permanently stops the supervised process. It sends SIGTERM first,
// then SIGKILL after 5 seconds if the process hasn't exited.
// Used during graceful shutdown.
func (ps *ProcessSupervisor) Stop() {
	ps.stop(logrus.WithField("supervisor", ps.name))
}

// stop is the internal implementation of Stop with a pre-configured logger.
func (ps *ProcessSupervisor) stop(log *logrus.Entry) {
	ps.mu.Lock()
	cmd := ps.cmd
	ps.mu.Unlock()

	if cmd == nil || cmd.Process == nil {
		return
	}

	log.Info("stopping process with SIGTERM")
	_ = cmd.Process.Signal(syscall.SIGTERM)

	// Wait up to 5 seconds for graceful exit
	done := make(chan struct{})
	go func() {
		// ProcessState is set after Wait returns, so we poll
		for i := 0; i < 50; i++ {
			if cmd.ProcessState != nil {
				close(done)
				return
			}
			time.Sleep(100 * time.Millisecond)
		}
		close(done)
	}()

	select {
	case <-done:
		if cmd.ProcessState != nil {
			log.Info("process stopped gracefully")
			return
		}
	case <-time.After(5 * time.Second):
	}

	// Force kill if still running
	log.Warn("process did not exit after 5s, sending SIGKILL")
	_ = cmd.Process.Signal(syscall.SIGKILL)
}

// setHealthy updates the health state and fires the callback on transitions.
func (ps *ProcessSupervisor) setHealthy(healthy bool) {
	ps.mu.Lock()
	changed := ps.healthy != healthy
	ps.healthy = healthy
	callback := ps.onHealthChange
	name := ps.name
	ps.mu.Unlock()

	if changed {
		logrus.WithFields(logrus.Fields{
			"supervisor": name,
			"healthy":    healthy,
		}).Info("health state changed")

		if callback != nil {
			callback(name, healthy)
		}
	}
}

// IsHealthy returns whether the supervised process is currently running.
// Thread-safe.
func (ps *ProcessSupervisor) IsHealthy() bool {
	ps.mu.Lock()
	defer ps.mu.Unlock()
	return ps.healthy
}

// Pid returns the current process PID, or 0 if not running.
// Thread-safe.
func (ps *ProcessSupervisor) Pid() int {
	ps.mu.Lock()
	defer ps.mu.Unlock()
	if ps.cmd != nil && ps.cmd.Process != nil {
		return ps.cmd.Process.Pid
	}
	return 0
}
