package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strconv"
	"syscall"
	"time"
)

type commandOptions struct {
	user  string
	group string
	cwd   string
	env   []string
	quiet bool
}

func commandEnv(overrides map[string]string) []string {
	env := os.Environ()
	for key, value := range overrides {
		env = upsertEnv(env, key, value)
	}
	return env
}

func upsertEnv(env []string, key, value string) []string {
	prefix := key + "="
	for i, item := range env {
		if len(item) >= len(prefix) && item[:len(prefix)] == prefix {
			env[i] = prefix + value
			return env
		}
	}
	return append(env, prefix+value)
}

func runCommand(ctx context.Context, name string, args []string, opts commandOptions) error {
	cmd := exec.CommandContext(ctx, name, args...)
	if opts.cwd != "" {
		cmd.Dir = opts.cwd
	}
	if len(opts.env) > 0 {
		cmd.Env = opts.env
	}
	if opts.user != "" {
		id, err := lookupIdentity(opts.user, opts.group)
		if err != nil {
			return err
		}
		cmd.Env = envForIdentity(cmd.Env, opts.user, id)
		cmd.SysProcAttr = &syscall.SysProcAttr{
			Credential: &syscall.Credential{Uid: uint32(id.uid), Gid: uint32(id.gid)},
		}
	}
	if opts.quiet {
		cmd.Stdout = io.Discard
		cmd.Stderr = io.Discard
	} else {
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
	}
	return cmd.Run()
}

func commandOutput(ctx context.Context, name string, args []string, opts commandOptions) (string, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	if opts.cwd != "" {
		cmd.Dir = opts.cwd
	}
	if len(opts.env) > 0 {
		cmd.Env = opts.env
	}
	if opts.user != "" {
		id, err := lookupIdentity(opts.user, opts.group)
		if err != nil {
			return "", err
		}
		cmd.Env = envForIdentity(cmd.Env, opts.user, id)
		cmd.SysProcAttr = &syscall.SysProcAttr{
			Credential: &syscall.Credential{Uid: uint32(id.uid), Gid: uint32(id.gid)},
		}
	}
	output, err := cmd.Output()
	return string(output), err
}

func execAs(userName, groupName, cwd, name string, args []string) error {
	path, err := exec.LookPath(name)
	if err != nil {
		return err
	}
	if cwd != "" {
		if err := os.Chdir(cwd); err != nil {
			return err
		}
	}
	if userName != "" {
		id, err := lookupIdentity(userName, groupName)
		if err != nil {
			return err
		}
		env := envForIdentity(os.Environ(), userName, id)
		if err := syscall.Setgroups([]int{id.gid}); err != nil {
			return fmt.Errorf("setgroups for %s: %w", userName, err)
		}
		if err := syscall.Setgid(id.gid); err != nil {
			return fmt.Errorf("setgid for %s: %w", userName, err)
		}
		if err := syscall.Setuid(id.uid); err != nil {
			return fmt.Errorf("setuid for %s: %w", userName, err)
		}
		return syscall.Exec(path, append([]string{name}, args...), env)
	}
	argv := append([]string{name}, args...)
	return syscall.Exec(path, argv, os.Environ())
}

func envForIdentity(env []string, userName string, id identity) []string {
	if len(env) == 0 {
		env = os.Environ()
	}
	home := id.home
	if home == "" || home == "/nonexistent" {
		home = "/opt/unicron"
	}
	env = upsertEnv(env, "HOME", home)
	env = upsertEnv(env, "USER", userName)
	env = upsertEnv(env, "LOGNAME", userName)
	return env
}

func exitCode(err error) int {
	if err == nil {
		return 0
	}
	if status, ok := waitStatus(err); ok {
		if status.Signaled() {
			return 128 + int(status.Signal())
		}
		return status.ExitStatus()
	}
	return 1
}

func exitSignal(err error) (syscall.Signal, bool) {
	status, ok := waitStatus(err)
	if !ok || !status.Signaled() {
		return 0, false
	}
	return status.Signal(), true
}

func waitStatus(err error) (syscall.WaitStatus, bool) {
	var exitErr *exec.ExitError
	if !errors.As(err, &exitErr) {
		return 0, false
	}
	status, ok := exitErr.Sys().(syscall.WaitStatus)
	return status, ok
}

func formatSignal(signal syscall.Signal) string {
	name := ""
	switch signal {
	case syscall.SIGABRT:
		name = "SIGABRT"
	case syscall.SIGBUS:
		name = "SIGBUS"
	case syscall.SIGFPE:
		name = "SIGFPE"
	case syscall.SIGILL:
		name = "SIGILL"
	case syscall.SIGINT:
		name = "SIGINT"
	case syscall.SIGKILL:
		name = "SIGKILL"
	case syscall.SIGSEGV:
		name = "SIGSEGV"
	case syscall.SIGTERM:
		name = "SIGTERM"
	}
	description := signal.String()
	if name == "" {
		return fmt.Sprintf("signal %d (%s)", signal, description)
	}
	return fmt.Sprintf("%s (%s)", name, description)
}

func processAlive(pid int) bool {
	if pid <= 0 {
		return false
	}
	_, err := os.Stat("/proc/" + strconv.Itoa(pid))
	return err == nil
}

func terminateProcessGroup(pid int, grace time.Duration) {
	if pid <= 0 {
		return
	}
	_ = syscall.Kill(-pid, syscall.SIGTERM)
	deadline := time.Now().Add(grace)
	for time.Now().Before(deadline) {
		if !processAlive(pid) {
			return
		}
		time.Sleep(200 * time.Millisecond)
	}
	_ = syscall.Kill(-pid, syscall.SIGKILL)
}
