package main

// Control messages exchanged between Central and Agent over the upstream WebSocket.

type execStartCommand struct {
	SessionID string `json:"session_id"`
	Container string `json:"container"`
	Rows      int    `json:"rows"`
	Cols      int    `json:"cols"`
}

type execInputCommand struct {
	SessionID string `json:"session_id"`
	Data      string `json:"data"`
}

type execResizeCommand struct {
	SessionID string `json:"session_id"`
	Rows      int    `json:"rows"`
	Cols      int    `json:"cols"`
}

type execStopCommand struct {
	SessionID string `json:"session_id"`
}

type execStartedPayload struct {
	SessionID string `json:"session_id"`
	Success   bool   `json:"success"`
	Message   string `json:"message,omitempty"`
}

type execOutputPayload struct {
	SessionID string `json:"session_id"`
	Data      string `json:"data"`
}

type execExitPayload struct {
	SessionID string `json:"session_id"`
	Message   string `json:"message,omitempty"`
	Code      int    `json:"code"`
}

// Container command types
type containerCommandRequest struct {
	RequestID string                 `json:"request_id"`
	Container string                 `json:"container"`
	Action    string                 `json:"action"` // restart, stop, start, kill
	Params    map[string]interface{} `json:"params,omitempty"`
}

type containerCommandResponse struct {
	RequestID string `json:"request_id"`
	Success   bool   `json:"success"`
	Message   string `json:"message,omitempty"`
	Error     string `json:"error,omitempty"`
}

// Logs streaming commands
type logsStartCommand struct {
	SessionID string `json:"session_id"`
	Container string `json:"container"`
	Follow    bool   `json:"follow"`
	Tail      string `json:"tail"`  // "all" or number like "100"
	Since     string `json:"since"` // Docker timestamp format, e.g. "2024-01-01T00:00:00Z"
}

type logsStopCommand struct {
	SessionID string `json:"session_id"`
}

type logsOutputPayload struct {
	SessionID string `json:"session_id"`
	Data      string `json:"data"`
}

type logsErrorPayload struct {
	SessionID string `json:"session_id"`
	Error     string `json:"error"`
}

type fastTailSource string

const (
	fastTailSourceMonitored fastTailSource = "monitored"
	fastTailSourceLiveOnly  fastTailSource = "live_only"
)

type fastTailCommand struct {
	ContainerKey string         `json:"container_key"`
	Source       fastTailSource `json:"source,omitempty"`
	HistoryTail  string         `json:"history_tail,omitempty"`
	HistorySince string         `json:"history_since,omitempty"`
}

type fastLogsFramePayload struct {
	ContainerKey string           `json:"container_key"`
	Row          normalizedLogRow `json:"row"`
}

type fastLogsErrorPayload struct {
	ContainerKey string `json:"container_key"`
	Error        string `json:"error"`
}

// File browsing commands
type filesListCommand struct {
	RequestID string `json:"request_id"`
	Container string `json:"container"`
	Path      string `json:"path"`
}

type fileReadCommand struct {
	RequestID string `json:"request_id"`
	Container string `json:"container"`
	Path      string `json:"path"`
}

type filesListResponse struct {
	RequestID string      `json:"request_id"`
	Path      string      `json:"path"`
	Entries   []fileEntry `json:"entries"`
	Error     string      `json:"error,omitempty"`
}

type fileEntry struct {
	Name     string `json:"name"`
	Path     string `json:"path"`
	Type     string `json:"type"` // "file" or "directory"
	Size     int64  `json:"size"`
	Modified string `json:"modified,omitempty"`
}

type fileReadResponse struct {
	RequestID string `json:"request_id"`
	Path      string `json:"path"`
	Content   string `json:"content"`
	Size      int64  `json:"size"`
	Error     string `json:"error,omitempty"`
}

// Stats streaming commands (on-demand from Central via StatsRelay)
type startStatsCommand struct {
	ContainerID string `json:"container_id"`
}

type stopStatsCommand struct {
	ContainerID string `json:"container_id"`
}

type statsFramePayload struct {
	ContainerID   string  `json:"container_id"`
	ContainerName string  `json:"container_name"`
	CPUPercent    float64 `json:"cpu_percent"`
	MemoryUsage   uint64  `json:"memory_usage"`
	MemoryLimit   uint64  `json:"memory_limit"`
	MemoryPercent float64 `json:"memory_percent"`
	NetworkRx     uint64  `json:"network_rx"`
	NetworkTx     uint64  `json:"network_tx"`
	BlockRead     uint64  `json:"block_read"`
	BlockWrite    uint64  `json:"block_write"`
	Timestamp     string  `json:"timestamp"`
}

// Run script command (alert remediation action)
type runScriptCommand struct {
	RequestID   string `json:"request_id"`
	ContainerID string `json:"container_id"`
	Script      string `json:"script"`
}

type runScriptResponse struct {
	RequestID string `json:"request_id"`
	Success   bool   `json:"success"`
	Output    string `json:"output"`
	ExitCode  int    `json:"exit_code"`
	Error     string `json:"error,omitempty"`
}

// Monitoring toggle command (from Central to Agent)
type monitoringToggleCommand struct {
	RequestID   string `json:"request_id"`
	ContainerID string `json:"container_id"`
	Name        string `json:"name"`  // pre-resolved by Central
	Image       string `json:"image"` // pre-resolved by Central
	Enabled     bool   `json:"enabled"`
}

// Monitoring sync command (from Central to Agent on reconnect)
type monitoringSyncCommand struct {
	Containers []struct {
		Name    string `json:"name"`
		Image   string `json:"image"`
		Enabled bool   `json:"enabled"`
	} `json:"containers"`
}

// Monitoring toggle ACK (from Agent to Central)
type monitoringToggleAck struct {
	RequestID string `json:"request_id"`
	Success   bool   `json:"success"`
	Error     string `json:"error,omitempty"`
}

// Telemetry health status (from Agent to Central)
type telemetryHealthPayload struct {
	Healthy   bool  `json:"healthy"`
	Timestamp int64 `json:"timestamp"`
}

// Agent decommission command (from Central to Agent)
type agentDecommissionCommand struct {
	RequestID string `json:"request_id"`
	Reason    string `json:"reason,omitempty"`
	WipeData  bool   `json:"wipe_data"`
}

type agentDecommissionAck struct {
	RequestID string `json:"request_id"`
	Success   bool   `json:"success"`
	Error     string `json:"error,omitempty"`
}

// Log collection state transition (from agent to Central).
type logCollectionStateChangedPayload struct {
	HostID              string `json:"host_id"`
	Name                string `json:"name"`
	Image               string `json:"image"`
	ContainerName       string `json:"container_name,omitempty"`
	DockerContainerID   string `json:"docker_container_id,omitempty"`
	LogCollectionStatus string `json:"log_collection_status"`
	LogCollectionIssue  string `json:"log_collection_issue,omitempty"`
}
