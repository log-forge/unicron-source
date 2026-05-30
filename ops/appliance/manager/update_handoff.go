package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type updateHandoffArgs struct {
	OldContainer string
	OldName      string
	NewContainer string
	NewName      string
	StateFile    string
	Socket       string
}

func runUpdateHandoff(cfg RuntimeConfig, args []string) error {
	parsed, err := parseUpdateHandoffArgs(cfg, args)
	if err != nil {
		return err
	}
	docker := newDockerClient(parsed.Socket)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()

	if err := docker.stopContainer(ctx, parsed.OldContainer, 30); err != nil && !isAlreadyStoppedError(err) {
		handoffError(parsed.StateFile, fmt.Errorf("failed to stop current appliance container: %w", err))
		return err
	}
	if err := docker.startContainer(ctx, parsed.NewContainer); err != nil {
		restoreErr := restoreAfterFailedHandoff(ctx, docker, parsed)
		if restoreErr != nil {
			err = fmt.Errorf("%w; restore failed: %v", err, restoreErr)
		}
		handoffError(parsed.StateFile, fmt.Errorf("failed to start replacement appliance container: %w", err))
		return err
	}

	now := time.Now().UTC()
	newInspect, _ := docker.inspectContainer(ctx, parsed.NewContainer)
	updateStateFile(parsed.StateFile, func(state applianceUpdateState) applianceUpdateState {
		state.LastApply = &now
		state.LastError = ""
		state.UpdateAvailable = false
		if newInspect.ID != "" {
			state.CurrentImage = containerConfigString(newInspect, "Image")
			state.CurrentImageID = newInspect.Image
		}
		return state
	})
	return nil
}

func parseUpdateHandoffArgs(cfg RuntimeConfig, args []string) (updateHandoffArgs, error) {
	parsed := updateHandoffArgs{
		StateFile: cfg.UpdateStateFile,
		Socket:    cfg.DockerSocket,
	}
	for i := 0; i < len(args); i++ {
		key := args[i]
		if !strings.HasPrefix(key, "--") {
			return parsed, fmt.Errorf("unexpected update-handoff argument %q", key)
		}
		if i+1 >= len(args) {
			return parsed, fmt.Errorf("missing value for %s", key)
		}
		value := args[i+1]
		i++
		switch key {
		case "--old":
			parsed.OldContainer = value
		case "--old-name":
			parsed.OldName = value
		case "--new":
			parsed.NewContainer = value
		case "--new-name":
			parsed.NewName = value
		case "--state":
			parsed.StateFile = value
		case "--socket":
			parsed.Socket = value
		default:
			return parsed, fmt.Errorf("unknown update-handoff argument %s", key)
		}
	}
	if parsed.OldContainer == "" || parsed.NewContainer == "" || parsed.NewName == "" {
		return parsed, fmt.Errorf("usage: update-handoff --old <id> --old-name <name> --new <id> --new-name <name> [--state <path>] [--socket <path>]")
	}
	return parsed, nil
}

func restoreAfterFailedHandoff(ctx context.Context, docker *dockerClient, args updateHandoffArgs) error {
	var errs []string
	failedName := uniqueContainerName(args.NewName + "-failed")
	if err := docker.renameContainer(ctx, args.NewContainer, failedName); err != nil {
		errs = append(errs, err.Error())
	}
	if args.OldName != "" {
		if err := docker.renameContainer(ctx, args.OldContainer, args.NewName); err != nil {
			errs = append(errs, err.Error())
		}
	}
	if err := docker.startContainer(ctx, args.OldContainer); err != nil {
		errs = append(errs, err.Error())
	}
	if len(errs) > 0 {
		return fmt.Errorf("%s", strings.Join(errs, "; "))
	}
	return nil
}

func handoffError(stateFile string, err error) {
	updateStateFile(stateFile, func(state applianceUpdateState) applianceUpdateState {
		state.LastError = err.Error()
		return state
	})
}

func updateStateFile(path string, mut func(applianceUpdateState) applianceUpdateState) {
	state := defaultUpdateState()
	if body, err := os.ReadFile(path); err == nil {
		_ = json.Unmarshal(body, &state)
	}
	state = mut(state)
	body, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, body, 0o600); err != nil {
		return
	}
	_ = os.Rename(tmp, path)
}

func isAlreadyStoppedError(err error) bool {
	if err == nil {
		return false
	}
	message := strings.ToLower(err.Error())
	return strings.Contains(message, "not running") || strings.Contains(message, "is already stopped") || strings.Contains(message, "returned 304")
}
