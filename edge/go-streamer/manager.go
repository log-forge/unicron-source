package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/docker/docker/api/types"
	containertypes "github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
	"github.com/sirupsen/logrus"
)

type containerMetadata struct {
	ID    string
	Name  string
	Image string
}

type manager struct {
	docker       *client.Client
	hostID       string
	hostMemTotal uint64
	hostCPUCount int

	// Upstream connection to Central
	up *upstreamClient

	// On-demand stats streaming (start_stats/stop_stats)
	streamManager *StreamManager

	// Telemetry pipeline manager (OTel + Fluent Bit)
	telemetryMgr *TelemetryManager

	// Exec sessions for terminal access (future use)
	execMu       sync.Mutex
	execSessions map[string]*execSession

	// Log sessions for container log streaming
	logMu       sync.Mutex
	logSessions map[string]context.CancelFunc
}

type execSession struct {
	id        string
	container string
	execID    string
	attach    types.HijackedResponse
	cancel    context.CancelFunc
	closed    chan struct{}
	mu        sync.Mutex
}

func newManager(docker *client.Client, hostID string) *manager {
	m := &manager{
		docker:       docker,
		hostID:       hostID,
		execSessions: make(map[string]*execSession),
		logSessions:  make(map[string]context.CancelFunc),
	}

	// Capture host capacity for host-relative metrics
	if info, err := docker.Info(context.Background()); err != nil {
		logrus.WithError(err).Warn("[Manager] Failed to read host capacity")
	} else {
		m.hostMemTotal = uint64(info.MemTotal)
		m.hostCPUCount = info.NCPU
	}

	return m
}

// HandleCentralCommand processes commands received from Central via WebSocket
func (m *manager) HandleCentralCommand(env upstreamEnvelope) {
	switch env.Type {
	case "exec_start":
		var payload execStartCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			go m.startExecSession(payload)
		}
	case "exec_input":
		var payload execInputCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			go m.handleExecInput(payload)
		}
	case "exec_resize":
		var payload execResizeCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			go m.handleExecResize(payload)
		}
	case "exec_stop":
		var payload execStopCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			m.stopExecSession(payload.SessionID)
		}
	case "container_command_request":
		var payload containerCommandRequest
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			go m.handleContainerCommand(payload)
		}
	case "logs_start":
		var payload logsStartCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			go m.startLogStream(payload)
		}
	case "logs_stop":
		var payload logsStopCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			m.stopLogStream(payload.SessionID)
		}
	case "fast_tail_start":
		var payload fastTailCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			if m.telemetryMgr == nil {
				logrus.Warn("[Manager] Received fast_tail_start but TelemetryManager not initialized yet")
				return
			}
			m.telemetryMgr.HandleFastTailStart(payload)
		}
	case "fast_tail_stop":
		var payload fastTailCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			if m.telemetryMgr == nil {
				logrus.Warn("[Manager] Received fast_tail_stop but TelemetryManager not initialized yet")
				return
			}
			m.telemetryMgr.HandleFastTailStop(payload)
		}
	case "files_list":
		var payload filesListCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			go m.handleFilesList(payload)
		}
	case "file_read":
		var payload fileReadCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			go m.handleFileRead(payload)
		}
	case "command":
		// Central sends {"type": "command", "data": {"action": "start_stats"|"stop_stats", "container_id": "..."}}
		var cmdData struct {
			Action      string `json:"action"`
			ContainerID string `json:"container_id"`
		}
		if err := json.Unmarshal(env.Data, &cmdData); err == nil {
			switch cmdData.Action {
			case "start_stats":
				go m.handleStartStats(cmdData.ContainerID)
			case "stop_stats":
				go m.handleStopStats(cmdData.ContainerID)
			}
		}
	case "run_script":
		var payload runScriptCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			go m.handleRunScript(payload)
		}
	case "monitoring_toggle":
		var payload monitoringToggleCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			if m.telemetryMgr == nil {
				logrus.Warn("[Manager] Received monitoring_toggle but TelemetryManager not initialized yet")
				return
			}
			go func() {
				defer func() {
					if r := recover(); r != nil {
						logrus.WithField("panic", r).Error("[Manager] Panic in monitoring toggle handler")
					}
				}()
				m.telemetryMgr.HandleToggle(payload)
			}()
		}
	case "monitoring_sync":
		var payload monitoringSyncCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			if m.telemetryMgr == nil {
				logrus.Warn("[Manager] Received monitoring_sync but TelemetryManager not initialized yet")
				return
			}
			go func() {
				defer func() {
					if r := recover(); r != nil {
						logrus.WithField("panic", r).Error("[Manager] Panic in monitoring sync handler")
					}
				}()
				m.telemetryMgr.HandleSync(payload)
			}()
		}
	case "agent_decommission":
		var payload agentDecommissionCommand
		if err := json.Unmarshal(env.Data, &payload); err == nil {
			go m.handleAgentDecommission(payload)
		}
	case "request_inventory":
		// Central requests fresh inventory (e.g., when cache is empty)
		logrus.Info("[Manager] Received request_inventory from Central")
		go m.sendFullInventory()
	}
}

// sendFullInventory collects and sends full container inventory to Central
func (m *manager) sendFullInventory() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	conts, err := m.docker.ContainerList(ctx, containertypes.ListOptions{All: true})
	if err != nil {
		logrus.WithError(err).Warn("[Inventory] Failed to list containers for request_inventory")
		return
	}

	items := make([]map[string]any, 0, len(conts))
	for _, c := range conts {
		name := ""
		if len(c.Names) > 0 {
			name = strings.TrimPrefix(c.Names[0], "/")
		}

		item := map[string]any{
			"container_id": c.ID,
			"name":         name,
			"image":        c.Image,
			"status":       c.State,
			"labels":       c.Labels,
			"ports":        c.Ports,
			"started_at":   "",
		}

		// Inspect for additional details
		inspectCtx, inspectCancel := context.WithTimeout(context.Background(), 2*time.Second)
		inspect, inspectErr := m.docker.ContainerInspect(inspectCtx, c.ID)
		inspectCancel()

		if inspectErr == nil {
			if inspect.State != nil {
				item["started_at"] = inspect.State.StartedAt
			}
			if inspect.NetworkSettings != nil {
				item["networks"] = inspect.NetworkSettings.Networks
			}
			if inspect.Mounts != nil {
				item["mounts"] = inspect.Mounts
			}
			if inspect.Config != nil && inspect.Config.Env != nil {
				item["environment"] = inspect.Config.Env
			}
		}

		items = append(items, item)
	}

	payload := map[string]any{
		"host_id":    m.hostID,
		"containers": items,
		"timestamp":  time.Now().Unix(),
	}
	m.up.sendInventory(payload)
	logrus.WithField("count", len(items)).Info("[Inventory] Sent inventory in response to request_inventory")
}

func (m *manager) inspectContainer(ctx context.Context, name string) (containerMetadata, error) {
	containerName := strings.TrimPrefix(name, "/")
	inspect, err := m.docker.ContainerInspect(ctx, containerName)
	if err != nil {
		return containerMetadata{}, fmt.Errorf("container %s not found: %w", containerName, err)
	}

	meta := containerMetadata{
		ID:    inspect.ID,
		Name:  strings.TrimPrefix(inspect.Name, "/"),
		Image: inspect.Config.Image,
	}

	return meta, nil
}

func (m *manager) handleContainerCommand(req containerCommandRequest) {
	resp := containerCommandResponse{
		RequestID: req.RequestID,
		Success:   false,
	}

	ctx := context.Background()

	meta, err := m.inspectContainer(ctx, req.Container)
	if err != nil {
		resp.Error = fmt.Sprintf("container not found: %v", err)
		m.sendContainerCommandResponse(resp)
		return
	}

	containerID := meta.ID

	switch req.Action {
	case "restart":
		timeout := 10
		if t, ok := req.Params["timeout"].(float64); ok {
			timeout = int(t)
		}
		err = m.docker.ContainerRestart(ctx, containerID, containertypes.StopOptions{Timeout: &timeout})
		if err != nil {
			resp.Error = fmt.Sprintf("restart failed: %v", err)
		} else {
			resp.Success = true
			resp.Message = "Container restarted successfully"
		}

	case "stop":
		timeout := 10
		if t, ok := req.Params["timeout"].(float64); ok {
			timeout = int(t)
		}
		err = m.docker.ContainerStop(ctx, containerID, containertypes.StopOptions{Timeout: &timeout})
		if err != nil {
			resp.Error = fmt.Sprintf("stop failed: %v", err)
		} else {
			resp.Success = true
			resp.Message = "Container stopped successfully"
		}

	case "start":
		err = m.docker.ContainerStart(ctx, containerID, containertypes.StartOptions{})
		if err != nil {
			resp.Error = fmt.Sprintf("start failed: %v", err)
		} else {
			resp.Success = true
			resp.Message = "Container started successfully"
		}

	case "kill":
		signal := "SIGKILL"
		if s, ok := req.Params["signal"].(string); ok {
			signal = s
		}
		err = m.docker.ContainerKill(ctx, containerID, signal)
		if err != nil {
			resp.Error = fmt.Sprintf("kill failed: %v", err)
		} else {
			resp.Success = true
			resp.Message = fmt.Sprintf("Container killed with signal %s", signal)
		}

	default:
		resp.Error = fmt.Sprintf("unknown action: %s", req.Action)
	}

	m.sendContainerCommandResponse(resp)
}

func (m *manager) sendContainerCommandResponse(resp containerCommandResponse) {
	b, _ := json.Marshal(resp)
	m.up.sendEnvelope(upstreamEnvelope{Type: "container_command_response", Data: b})
}

func (m *manager) handleAgentDecommission(cmd agentDecommissionCommand) {
	ack := agentDecommissionAck{
		RequestID: cmd.RequestID,
		Success:   true,
	}
	ackBytes, _ := json.Marshal(ack)
	m.up.sendEnvelope(upstreamEnvelope{Type: "agent_decommission_ack", Data: ackBytes})

	logrus.WithFields(logrus.Fields{
		"request_id": cmd.RequestID,
		"wipe_data":  cmd.WipeData,
		"reason":     cmd.Reason,
	}).Warn("[Manager] Received agent decommission command; beginning self-destruct")

	if m.telemetryMgr != nil {
		m.telemetryMgr.Stop()
	}

	if cmd.WipeData {
		paths := []string{
			"/agent-data/certs",
			"/var/lib/go-streamer/monitoring-state.json",
			"/var/lib/otelcol/queue",
			"/tmp/flb",
		}
		for _, p := range paths {
			if err := os.RemoveAll(p); err != nil {
				logrus.WithError(err).WithField("path", p).Warn("[Manager] Failed to remove decommission path")
			} else {
				logrus.WithField("path", p).Info("[Manager] Removed decommission path")
			}
		}
	}

	selfID, _ := os.Hostname()
	selfID = strings.TrimSpace(selfID)
	if selfID != "" {
		if _, err := m.docker.ContainerUpdate(context.Background(), selfID, containertypes.UpdateConfig{
			RestartPolicy: containertypes.RestartPolicy{Name: "no"},
		}); err != nil {
			logrus.WithError(err).Warn("[Manager] Failed to disable container restart policy on decommission")
		} else {
			logrus.WithField("container_id", selfID).Info("[Manager] Disabled restart policy for decommission")
		}

		// Best effort self-removal so decommission behaves like `agent-down`
		// (container + attached volumes removed from host).
		if err := m.docker.ContainerRemove(
			context.Background(),
			selfID,
			containertypes.RemoveOptions{
				Force:         true,
				RemoveVolumes: true,
			},
		); err != nil {
			logrus.WithError(err).WithField("container_id", selfID).Warn("[Manager] Failed to remove own container during decommission")
		} else {
			logrus.WithField("container_id", selfID).Warn("[Manager] Requested self-removal for decommission")
			return
		}
	}

	_ = os.MkdirAll("/agent-data", 0o755)
	_ = os.WriteFile(filepath.Clean("/agent-data/decommissioned"), []byte(time.Now().UTC().Format(time.RFC3339)), 0o644)

	time.Sleep(500 * time.Millisecond)
	logrus.Warn("[Manager] Agent self-destruct complete; exiting process")
	os.Exit(0)
}

func (m *manager) startExecSession(cmd execStartCommand) {
	ctx, cancel := context.WithCancel(context.Background())
	meta, err := m.inspectContainer(ctx, cmd.Container)
	if err != nil {
		m.sendExecStarted(cmd.SessionID, false, err.Error())
		cancel()
		return
	}

	execConfig := containertypes.ExecOptions{
		AttachStdout: true,
		AttachStderr: true,
		AttachStdin:  true,
		Tty:          true,
		Cmd:          []string{"/bin/sh"},
		Env:          []string{"TERM=xterm-256color"},
		WorkingDir:   "/",
	}

	execID, err := m.docker.ContainerExecCreate(ctx, meta.ID, execConfig)
	if err != nil {
		m.sendExecStarted(cmd.SessionID, false, err.Error())
		cancel()
		return
	}

	attach, err := m.docker.ContainerExecAttach(ctx, execID.ID, containertypes.ExecAttachOptions{Detach: false, Tty: true})
	if err != nil {
		m.sendExecStarted(cmd.SessionID, false, err.Error())
		cancel()
		return
	}

	session := &execSession{
		id:        cmd.SessionID,
		container: meta.ID,
		execID:    execID.ID,
		attach:    attach,
		cancel:    cancel,
		closed:    make(chan struct{}),
	}

	m.execMu.Lock()
	m.execSessions[cmd.SessionID] = session
	m.execMu.Unlock()

	m.sendExecStarted(cmd.SessionID, true, "")

	go m.streamExecOutput(session)
}

func (m *manager) handleExecInput(cmd execInputCommand) {
	m.execMu.Lock()
	session, ok := m.execSessions[cmd.SessionID]
	m.execMu.Unlock()
	if !ok {
		return
	}

	session.mu.Lock()
	defer session.mu.Unlock()
	if session.attach.Conn != nil {
		_, _ = session.attach.Conn.Write([]byte(cmd.Data))
	}
}

func (m *manager) handleExecResize(cmd execResizeCommand) {
	m.execMu.Lock()
	session, ok := m.execSessions[cmd.SessionID]
	m.execMu.Unlock()
	if !ok {
		return
	}

	opts := containertypes.ResizeOptions{
		Height: uint(cmd.Rows),
		Width:  uint(cmd.Cols),
	}
	_ = m.docker.ContainerExecResize(context.Background(), session.execID, opts)
}

func (m *manager) stopExecSession(sessionID string) {
	m.execMu.Lock()
	session, ok := m.execSessions[sessionID]
	if ok {
		delete(m.execSessions, sessionID)
	}
	m.execMu.Unlock()

	if ok && session != nil {
		session.mu.Lock()
		select {
		case <-session.closed:
		default:
			close(session.closed)
			if session.attach.Conn != nil {
				_ = session.attach.Conn.Close()
			}
			if session.cancel != nil {
				session.cancel()
			}
		}
		session.mu.Unlock()
	}
}

func (m *manager) streamExecOutput(session *execSession) {
	buf := make([]byte, 4096)
	for {
		n, err := session.attach.Reader.Read(buf)
		if n > 0 {
			chunk := make([]byte, n)
			copy(chunk, buf[:n])
			m.sendExecOutput(session.id, chunk)
		}
		if err != nil {
			break
		}
	}

	m.execMu.Lock()
	delete(m.execSessions, session.id)
	m.execMu.Unlock()

	inspect, err := m.docker.ContainerExecInspect(context.Background(), session.execID)
	code := 0
	if err == nil {
		code = inspect.ExitCode
	}

	session.mu.Lock()
	select {
	case <-session.closed:
	default:
		close(session.closed)
		if session.attach.Conn != nil {
			_ = session.attach.Conn.Close()
		}
		if session.cancel != nil {
			session.cancel()
		}
	}
	session.mu.Unlock()

	m.sendExecExit(session.id, code, "session ended")
}

func (m *manager) sendExecStarted(sessionID string, success bool, message string) {
	payload := execStartedPayload{
		SessionID: sessionID,
		Success:   success,
		Message:   message,
	}
	data, _ := json.Marshal(payload)
	m.up.sendEnvelope(upstreamEnvelope{Type: "exec_started", Data: data})
}

func (m *manager) sendExecOutput(sessionID string, data []byte) {
	payload := execOutputPayload{
		SessionID: sessionID,
		Data:      string(data),
	}
	b, _ := json.Marshal(payload)
	m.up.sendEnvelope(upstreamEnvelope{Type: "exec_output", Data: b})
}

func (m *manager) sendExecExit(sessionID string, code int, message string) {
	payload := execExitPayload{
		SessionID: sessionID,
		Message:   message,
		Code:      code,
	}
	b, _ := json.Marshal(payload)
	m.up.sendEnvelope(upstreamEnvelope{Type: "exec_exit", Data: b})
}

// Log streaming handlers

func (m *manager) startLogStream(cmd logsStartCommand) {
	ctx, cancel := context.WithCancel(context.Background())

	meta, err := m.inspectContainer(ctx, cmd.Container)
	if err != nil {
		m.sendLogsError(cmd.SessionID, err.Error())
		cancel()
		return
	}

	m.logMu.Lock()
	// Stop existing session if any
	if existing, ok := m.logSessions[cmd.SessionID]; ok {
		existing()
	}
	m.logSessions[cmd.SessionID] = cancel
	m.logMu.Unlock()

	opts := containertypes.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Follow:     cmd.Follow,
		Timestamps: true,
	}
	if cmd.Tail != "" {
		opts.Tail = cmd.Tail
	} else {
		opts.Tail = "100"
	}
	if cmd.Since != "" {
		opts.Since = cmd.Since
	}

	reader, err := m.docker.ContainerLogs(ctx, meta.ID, opts)
	if err != nil {
		m.sendLogsError(cmd.SessionID, err.Error())
		m.logMu.Lock()
		delete(m.logSessions, cmd.SessionID)
		m.logMu.Unlock()
		cancel()
		return
	}
	defer reader.Close()

	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 64*1024), 64*1024)
	for scanner.Scan() {
		select {
		case <-ctx.Done():
			return
		default:
		}
		line := scanner.Bytes()
		// Docker log lines may have 8-byte header for non-TTY containers
		// Strip header if present (first byte indicates stream type)
		if len(line) > 8 && (line[0] == 1 || line[0] == 2) {
			line = line[8:]
		}
		// Skip empty lines
		lineStr := strings.TrimSpace(string(line))
		if lineStr == "" {
			continue
		}
		m.sendLogsOutput(cmd.SessionID, string(line))
	}

	m.logMu.Lock()
	delete(m.logSessions, cmd.SessionID)
	m.logMu.Unlock()
}

func (m *manager) stopLogStream(sessionID string) {
	m.logMu.Lock()
	cancel, ok := m.logSessions[sessionID]
	if ok {
		delete(m.logSessions, sessionID)
	}
	m.logMu.Unlock()
	if ok {
		cancel()
	}
}

func (m *manager) sendLogsOutput(sessionID string, data string) {
	payload := logsOutputPayload{SessionID: sessionID, Data: data}
	b, _ := json.Marshal(payload)
	m.up.sendEnvelope(upstreamEnvelope{Type: "logs_output", Data: b})
}

func (m *manager) sendLogsError(sessionID string, errMsg string) {
	payload := logsErrorPayload{SessionID: sessionID, Error: errMsg}
	b, _ := json.Marshal(payload)
	m.up.sendEnvelope(upstreamEnvelope{Type: "logs_error", Data: b})
}

// File browsing handlers

func (m *manager) handleFilesList(cmd filesListCommand) {
	ctx := context.Background()
	meta, err := m.inspectContainer(ctx, cmd.Container)
	if err != nil {
		m.sendFilesListResponse(cmd.RequestID, cmd.Path, nil, err.Error())
		return
	}

	// Use exec to list directory contents in container
	lsCmd := []string{"ls", "-la", "--time-style=full-iso", cmd.Path}
	execConfig := containertypes.ExecOptions{
		AttachStdout: true,
		AttachStderr: true,
		Cmd:          lsCmd,
	}

	execID, err := m.docker.ContainerExecCreate(ctx, meta.ID, execConfig)
	if err != nil {
		m.sendFilesListResponse(cmd.RequestID, cmd.Path, nil, err.Error())
		return
	}

	attach, err := m.docker.ContainerExecAttach(ctx, execID.ID, containertypes.ExecAttachOptions{})
	if err != nil {
		m.sendFilesListResponse(cmd.RequestID, cmd.Path, nil, err.Error())
		return
	}
	defer attach.Close()

	output, _ := io.ReadAll(attach.Reader)
	outputStr := string(output)

	entries := parseDirectoryListing(outputStr, cmd.Path)
	m.sendFilesListResponse(cmd.RequestID, cmd.Path, entries, "")
}

func parseDirectoryListing(output string, basePath string) []fileEntry {
	var entries []fileEntry
	lines := strings.Split(output, "\n")

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "total") {
			continue
		}

		fields := strings.Fields(line)
		if len(fields) < 9 {
			continue
		}

		name := strings.Join(fields[8:], " ")
		if name == "." || name == ".." {
			continue
		}

		entryType := "file"
		if fields[0][0] == 'd' {
			entryType = "directory"
		} else if fields[0][0] == 'l' {
			if idx := strings.Index(name, " -> "); idx >= 0 {
				name = name[:idx]
			}
		}

		var size int64
		fmt.Sscanf(fields[4], "%d", &size)

		entryPath := basePath
		if !strings.HasSuffix(entryPath, "/") {
			entryPath += "/"
		}
		entryPath += name

		modified := ""
		if len(fields) >= 8 {
			modified = fields[5] + "T" + fields[6]
		}

		entries = append(entries, fileEntry{
			Name:     name,
			Path:     entryPath,
			Type:     entryType,
			Size:     size,
			Modified: modified,
		})
	}
	return entries
}

func (m *manager) handleFileRead(cmd fileReadCommand) {
	ctx := context.Background()
	meta, err := m.inspectContainer(ctx, cmd.Container)
	if err != nil {
		m.sendFileReadResponse(cmd.RequestID, cmd.Path, "", 0, err.Error())
		return
	}

	catCmd := []string{"head", "-c", "1048576", cmd.Path}
	execConfig := containertypes.ExecOptions{
		AttachStdout: true,
		AttachStderr: true,
		Cmd:          catCmd,
	}

	execID, err := m.docker.ContainerExecCreate(ctx, meta.ID, execConfig)
	if err != nil {
		m.sendFileReadResponse(cmd.RequestID, cmd.Path, "", 0, err.Error())
		return
	}

	attach, err := m.docker.ContainerExecAttach(ctx, execID.ID, containertypes.ExecAttachOptions{})
	if err != nil {
		m.sendFileReadResponse(cmd.RequestID, cmd.Path, "", 0, err.Error())
		return
	}
	defer attach.Close()

	output, _ := io.ReadAll(attach.Reader)
	content := stripDockerHeader(output)

	m.sendFileReadResponse(cmd.RequestID, cmd.Path, string(content), int64(len(content)), "")
}

func stripDockerHeader(data []byte) []byte {
	if len(data) > 8 && (data[0] == 1 || data[0] == 2) && data[1] == 0 && data[2] == 0 && data[3] == 0 {
		return data[8:]
	}
	return data
}

func (m *manager) sendFilesListResponse(requestID string, path string, entries []fileEntry, errMsg string) {
	payload := filesListResponse{
		RequestID: requestID,
		Path:      path,
		Entries:   entries,
		Error:     errMsg,
	}
	b, _ := json.Marshal(payload)
	m.up.sendEnvelope(upstreamEnvelope{Type: "files_list_response", Data: b})
}

func (m *manager) sendFileReadResponse(requestID string, path string, content string, size int64, errMsg string) {
	payload := fileReadResponse{
		RequestID: requestID,
		Path:      path,
		Content:   content,
		Size:      size,
		Error:     errMsg,
	}
	b, _ := json.Marshal(payload)
	m.up.sendEnvelope(upstreamEnvelope{Type: "file_read_response", Data: b})
}

// On-demand stats streaming handlers

func (m *manager) handleStartStats(containerID string) {
	if m.streamManager == nil {
		logrus.Warn("[Manager] StreamManager not initialized, cannot start stats")
		return
	}

	// Look up container name from Docker
	ctx := context.Background()
	inspect, err := m.docker.ContainerInspect(ctx, containerID)
	if err != nil {
		logrus.WithError(err).WithField("container_id", containerID).Warn("[Manager] Cannot inspect container for start_stats")
		return
	}

	containerName := strings.TrimPrefix(inspect.Name, "/")
	image := ""
	if inspect.Config != nil {
		image = inspect.Config.Image
	}

	if err := m.streamManager.StartStream(context.Background(), containerID, containerName, image); err != nil {
		logrus.WithError(err).WithField("container", containerName).Warn("[Manager] Failed to start on-demand stats stream")
	} else {
		logrus.WithFields(logrus.Fields{
			"container": containerName,
			"id":        containerID[:12],
		}).Info("[Manager] On-demand stats stream started")
	}
}

func (m *manager) handleStopStats(containerID string) {
	if m.streamManager == nil {
		return
	}
	m.streamManager.StopStream(containerID)
	logrus.WithField("container_id", containerID[:12]).Info("[Manager] On-demand stats stream stopped")
}

// Run script handler (alert remediation action)

func (m *manager) handleRunScript(cmd runScriptCommand) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	resp := runScriptResponse{
		RequestID: cmd.RequestID,
		Success:   false,
	}

	// Validate script is not empty
	if cmd.Script == "" {
		resp.Error = "script cannot be empty"
		m.sendRunScriptResponse(resp)
		return
	}

	// Inspect container
	meta, err := m.inspectContainer(ctx, cmd.ContainerID)
	if err != nil {
		resp.Error = fmt.Sprintf("container not found: %v", err)
		m.sendRunScriptResponse(resp)
		return
	}

	// Create exec with /bin/sh -c to run the script
	execConfig := containertypes.ExecOptions{
		AttachStdout: true,
		AttachStderr: true,
		Cmd:          []string{"/bin/sh", "-c", cmd.Script},
	}

	execID, err := m.docker.ContainerExecCreate(ctx, meta.ID, execConfig)
	if err != nil {
		resp.Error = fmt.Sprintf("exec create failed: %v", err)
		m.sendRunScriptResponse(resp)
		return
	}

	attach, err := m.docker.ContainerExecAttach(ctx, execID.ID, containertypes.ExecAttachOptions{})
	if err != nil {
		resp.Error = fmt.Sprintf("exec attach failed: %v", err)
		m.sendRunScriptResponse(resp)
		return
	}
	defer attach.Close()

	// Read output (limited to 1MB to prevent memory issues)
	output, _ := io.ReadAll(io.LimitReader(attach.Reader, 1<<20))
	content := stripDockerHeader(output)

	// Get exit code
	inspect, err := m.docker.ContainerExecInspect(ctx, execID.ID)
	exitCode := 0
	if err == nil {
		exitCode = inspect.ExitCode
	}

	resp.Success = exitCode == 0
	resp.Output = string(content)
	resp.ExitCode = exitCode
	m.sendRunScriptResponse(resp)

	logrus.WithFields(logrus.Fields{
		"container":  meta.Name,
		"request_id": cmd.RequestID,
		"exit_code":  exitCode,
	}).Info("[Manager] run_script completed")
}

func (m *manager) sendRunScriptResponse(resp runScriptResponse) {
	b, _ := json.Marshal(resp)
	m.up.sendEnvelope(upstreamEnvelope{Type: "run_script_response", Data: b})
}
