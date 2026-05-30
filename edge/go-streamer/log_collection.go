package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/sirupsen/logrus"
)

const (
	localLogIngestHost       = "127.0.0.1"
	localLogIngestPort       = 8686
	localLogIngestPath       = "/internal/logs/batch"
	localLiveLogIngestPort   = 8687
	localLiveLogIngestPath   = "/internal/logs/live/batch"
	localLogIngestHeader     = "FLUENT-TAG"
	localOTLPLogsURL         = "http://127.0.0.1:4318/v1/logs"
	defaultMetaCacheTTL      = 300 * time.Second
	defaultLogRequestTimeout = 10 * time.Second
	defaultLiveTailHistory   = "500"
	maxSeedFrameSize         = 1 << 20 // 1 MiB – reject malformed Docker stream frames larger than this
	maxSeedRows              = 10_000  // hard ceiling on history rows from a single seedHistory call
	dockerContainersRootPath = "/var/lib/docker/containers"
)

var logPathAccessible = func(path string) bool {
	path = strings.TrimSpace(path)
	if path == "" {
		return false
	}
	_, err := os.Stat(path)
	return err == nil
}

var dockerDesktopWSLContainerRoots = []string{
	"/host/root/mnt/wsl/docker-desktop-data/version-pack-data/community/docker/containers",
	"/host/root/mnt/wsl/docker-desktop-data/data/docker/containers",
	"/host/root/run/desktop/mnt/host/wsl/docker-desktop-data/version-pack-data/community/docker/containers",
	"/host/root/run/desktop/mnt/host/wsl/docker-desktop-data/data/docker/containers",
	"/mnt/wsl/docker-desktop-data/version-pack-data/community/docker/containers",
	"/mnt/wsl/docker-desktop-data/data/docker/containers",
	"/run/desktop/mnt/host/wsl/docker-desktop-data/version-pack-data/community/docker/containers",
	"/run/desktop/mnt/host/wsl/docker-desktop-data/data/docker/containers",
}

var dockerDesktopWSLBindMountRoots = []string{
	"/host/root/mnt/wsl/docker-desktop-bind-mounts",
	"/host/root/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts",
	"/mnt/wsl/docker-desktop-bind-mounts",
	"/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts",
}

type dockerInspector interface {
	ContainerInspect(context.Context, string) (types.ContainerJSON, error)
	ContainerLogs(context.Context, string, container.LogsOptions) (io.ReadCloser, error)
}

type logSourceMode string

const (
	logSourcePush        logSourceMode = "push"
	logSourceTail        logSourceMode = "tail"
	logSourceUnavailable logSourceMode = "unavailable"
)

type logIssueCode string

const (
	logIssueInspectFailed     logIssueCode = "inspect_failed"
	logIssueMissingLogPath    logIssueCode = "missing_log_path"
	logIssueUnsupportedSource logIssueCode = "unsupported_source"
)

type logCollectionPlan struct {
	Key               ContainerKey
	ContainerName     string
	DockerContainerID string
	Image             string
	LogPath           string
	UsesTTY           bool
	SourceMode        logSourceMode
	Issue             logIssueCode
}

func (p logCollectionPlan) monitoredKey() string {
	return p.Key.String()
}

func (p logCollectionPlan) fluentBitTag() string {
	name := strings.TrimSpace(strings.TrimPrefix(p.ContainerName, "/"))
	if name == "" {
		name = strings.TrimSpace(strings.TrimPrefix(p.Key.Name, "/"))
	}
	if name == "" {
		return ""
	}
	return "docker." + name
}

func (p logCollectionPlan) isHealthy() bool {
	return p.SourceMode == logSourcePush || p.SourceMode == logSourceTail
}

func (p logCollectionPlan) publicStatus() string {
	if p.isHealthy() {
		return "ok"
	}
	return "unavailable"
}

func (p logCollectionPlan) state() logCollectionState {
	return logCollectionState{
		PublicStatus:      p.publicStatus(),
		Issue:             string(p.Issue),
		ContainerName:     p.ContainerName,
		DockerContainerID: p.DockerContainerID,
		Image:             p.Image,
	}
}

type logCollectionState struct {
	PublicStatus      string
	Issue             string
	ContainerName     string
	DockerContainerID string
	Image             string
}

func (s logCollectionState) publicEqual(other logCollectionState) bool {
	return s.PublicStatus == other.PublicStatus && s.Issue == other.Issue
}

func (s logCollectionState) payload(hostID string, key ContainerKey) logCollectionStateChangedPayload {
	payload := logCollectionStateChangedPayload{
		HostID:              hostID,
		Name:                key.Name,
		Image:               key.Image,
		LogCollectionStatus: s.PublicStatus,
	}
	if s.Issue != "" {
		payload.LogCollectionIssue = s.Issue
	}
	if s.ContainerName != "" {
		payload.ContainerName = s.ContainerName
	}
	if s.DockerContainerID != "" {
		payload.DockerContainerID = s.DockerContainerID
	}
	return payload
}

type cachedLogCollectionPlan struct {
	plan      logCollectionPlan
	updatedAt time.Time
}

type logCollectionPlanCache struct {
	ttl      time.Duration
	mu       sync.RWMutex
	byName   map[string]cachedLogCollectionPlan
	byDocker map[string]cachedLogCollectionPlan
}

func newLogCollectionPlanCache(ttl time.Duration) *logCollectionPlanCache {
	if ttl <= 0 {
		ttl = defaultMetaCacheTTL
	}
	return &logCollectionPlanCache{
		ttl:      ttl,
		byName:   make(map[string]cachedLogCollectionPlan),
		byDocker: make(map[string]cachedLogCollectionPlan),
	}
}

func readMetaCacheTTL() time.Duration {
	raw := strings.TrimSpace(os.Getenv("DOCKER_META_CACHE_TTL"))
	if raw == "" {
		return defaultMetaCacheTTL
	}
	if secs, err := strconv.Atoi(raw); err == nil && secs >= 0 {
		return time.Duration(secs) * time.Second
	}
	return defaultMetaCacheTTL
}

func inspectContainerLogTarget(inspector dockerInspector, containerName string) (string, string, bool, error) {
	containerName = strings.TrimSpace(strings.TrimPrefix(containerName, "/"))
	if containerName == "" {
		return "", "", false, fmt.Errorf("container name is required")
	}
	if inspector == nil {
		return "", "", false, fmt.Errorf("docker inspector unavailable")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	inspect, err := inspector.ContainerInspect(ctx, containerName)
	if err != nil {
		return "", "", false, err
	}

	resolvedName := strings.TrimSpace(strings.TrimPrefix(inspect.Name, "/"))
	if resolvedName == "" {
		resolvedName = containerName
	}
	usesTTY := inspect.Config != nil && inspect.Config.Tty
	return resolvedName, strings.TrimSpace(inspect.ID), usesTTY, nil
}

func resolveAccessibleLogPath(logPath string) string {
	logPath = strings.TrimSpace(logPath)
	if logPath == "" {
		return ""
	}

	candidates := []string{logPath}
	if strings.HasPrefix(logPath, "/") {
		candidates = append(candidates, filepath.Clean("/host/root"+logPath))
	}

	if suffix, ok := strings.CutPrefix(logPath, dockerContainersRootPath+"/"); ok {
		for _, root := range dockerDesktopWSLContainerRoots {
			root = strings.TrimSpace(root)
			if root == "" {
				continue
			}
			candidates = append(candidates, filepath.Join(root, suffix))
		}
		for _, root := range dockerDesktopWSLBindMountRoots {
			root = strings.TrimSpace(root)
			if root == "" {
				continue
			}
			patterns := []string{
				filepath.Join(root, "*", "var", "lib", "docker", "containers", suffix),
				filepath.Join(root, "*", "*", "var", "lib", "docker", "containers", suffix),
			}
			for _, pattern := range patterns {
				matches, err := filepath.Glob(pattern)
				if err != nil {
					continue
				}
				candidates = append(candidates, matches...)
			}
		}
	}

	seen := make(map[string]struct{}, len(candidates))
	for _, candidate := range candidates {
		candidate = strings.TrimSpace(candidate)
		if candidate == "" {
			continue
		}
		candidate = filepath.Clean(candidate)
		if _, ok := seen[candidate]; ok {
			continue
		}
		seen[candidate] = struct{}{}
		if logPathAccessible(candidate) {
			return candidate
		}
	}
	return ""
}

func (c *logCollectionPlanCache) replace(plans []logCollectionPlan) {
	byName := make(map[string]cachedLogCollectionPlan)
	byDocker := make(map[string]cachedLogCollectionPlan)
	now := time.Now().UTC()
	for _, plan := range plans {
		entry := cachedLogCollectionPlan{plan: plan, updatedAt: now}
		if name := strings.TrimSpace(strings.TrimPrefix(plan.ContainerName, "/")); name != "" {
			byName[name] = entry
		} else if name := strings.TrimSpace(strings.TrimPrefix(plan.Key.Name, "/")); name != "" {
			byName[name] = entry
		}
		if dockerID := strings.TrimSpace(plan.DockerContainerID); dockerID != "" {
			byDocker[dockerID] = entry
		}
	}

	c.mu.Lock()
	c.byName = byName
	c.byDocker = byDocker
	c.mu.Unlock()
}

func (c *logCollectionPlanCache) store(plan logCollectionPlan) {
	entry := cachedLogCollectionPlan{plan: plan, updatedAt: time.Now().UTC()}

	c.mu.Lock()
	defer c.mu.Unlock()
	if name := strings.TrimSpace(strings.TrimPrefix(plan.ContainerName, "/")); name != "" {
		c.byName[name] = entry
	} else if name := strings.TrimSpace(strings.TrimPrefix(plan.Key.Name, "/")); name != "" {
		c.byName[name] = entry
	}
	if dockerID := strings.TrimSpace(plan.DockerContainerID); dockerID != "" {
		c.byDocker[dockerID] = entry
	}
}

func (c *logCollectionPlanCache) resolve(containerName, dockerID string) (logCollectionPlan, bool) {
	containerName = strings.TrimSpace(strings.TrimPrefix(containerName, "/"))
	dockerID = strings.TrimSpace(dockerID)

	c.mu.RLock()
	nameEntry, hasName := c.byName[containerName]
	dockerEntry, hasDocker := c.byDocker[dockerID]
	c.mu.RUnlock()

	if hasName && time.Since(nameEntry.updatedAt) <= c.ttl {
		return nameEntry.plan, true
	}
	if hasDocker && time.Since(dockerEntry.updatedAt) <= c.ttl {
		return dockerEntry.plan, true
	}
	return logCollectionPlan{}, false
}

func (g *ConfigGenerator) BuildLogCollectionPlan(keys []ContainerKey) []logCollectionPlan {
	plans := make([]logCollectionPlan, 0, len(keys))
	pushEnabled := telemetryPushEnabled(resolveTelemetryMode())
	for _, key := range keys {
		plans = append(plans, inspectLogCollectionPlan(g.docker, key, pushEnabled))
	}
	if g.logCollectionCache != nil {
		g.logCollectionCache.replace(plans)
	}
	return plans
}

type logCollectionResolvedRecord struct {
	Tag       string
	Timestamp any
	Record    map[string]any
}

type normalizedLogRow struct {
	Time              string         `json:"time"`
	Msg               string         `json:"msg"`
	MsgJSON           map[string]any `json:"msg_json,omitempty"`
	ContainerKey      string         `json:"container_key"`
	ContainerName     string         `json:"container_name"`
	DockerContainerID string         `json:"docker_container_id,omitempty"`
	HeraldID          string         `json:"herald_id"`
	HeraldName        string         `json:"herald_name"`
	ServiceName       string         `json:"service_name"`
	ServiceNamespace  string         `json:"service_namespace"`
	Stream            string         `json:"stream,omitempty"`
	Severity          string         `json:"severity,omitempty"`
}

type fastLaneEnvelopeSender interface {
	sendEnvelope(upstreamEnvelope)
}

type logCollectionServiceOptions struct {
	ingestPort       int
	ingestPath       string
	requireMonitored bool
	sendOTLP         bool
}

type logCollectionService struct {
	hostID             string
	heraldName         string
	state              *MonitoringState
	inspector          dockerInspector
	planCache          *logCollectionPlanCache
	client             *http.Client
	otlpURL            string
	server             *http.Server
	ingestPort         int
	ingestPath         string
	requireMonitored   bool
	sendOTLP           bool
	fastLaneMu         sync.RWMutex
	activeFastTail     map[string]struct{}
	activeContainersMu sync.RWMutex
	activeContainers   map[string]logCollectionPlan
	fastLaneSender     fastLaneEnvelopeSender
}

func newLogCollectionService(hostID string, state *MonitoringState, inspector dockerInspector, opts logCollectionServiceOptions) (*logCollectionService, error) {
	heraldName := strings.TrimSpace(os.Getenv("HERALD_NAME"))
	if heraldName == "" {
		heraldName = hostID
	}
	if opts.ingestPort <= 0 {
		opts.ingestPort = localLogIngestPort
	}
	if strings.TrimSpace(opts.ingestPath) == "" {
		opts.ingestPath = localLogIngestPath
	}
	return &logCollectionService{
		hostID:           hostID,
		heraldName:       heraldName,
		state:            state,
		inspector:        inspector,
		planCache:        newLogCollectionPlanCache(readMetaCacheTTL()),
		client:           &http.Client{Timeout: defaultLogRequestTimeout},
		otlpURL:          localOTLPLogsURL,
		ingestPort:       opts.ingestPort,
		ingestPath:       opts.ingestPath,
		requireMonitored: opts.requireMonitored,
		sendOTLP:         opts.sendOTLP,
		activeFastTail:   make(map[string]struct{}),
		activeContainers: make(map[string]logCollectionPlan),
	}, nil
}

func (s *logCollectionService) start(ctx context.Context) error {
	if s.server != nil {
		return nil
	}
	mux := http.NewServeMux()
	mux.HandleFunc(s.ingestPath, s.handleBatch)

	addr := fmt.Sprintf("%s:%d", localLogIngestHost, s.ingestPort)
	s.server = &http.Server{
		Addr:              addr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = s.server.Shutdown(shutdownCtx)
	}()

	go func() {
		if err := s.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logrus.WithError(err).Fatal("[LogCollection] Local ingest server failed")
		}
	}()

	logrus.WithField("addr", addr).Info("[LogCollection] Local ingest server started")
	return nil
}

func (s *logCollectionService) replacePlans(plans []logCollectionPlan) {
	s.planCache.replace(plans)
}

func (s *logCollectionService) handleBatch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "failed to read request body", http.StatusBadRequest)
		return
	}

	records, err := parseLogCollectionBatch(body, r.Header.Get(localLogIngestHeader))
	if err != nil {
		http.Error(w, "invalid log batch", http.StatusBadRequest)
		return
	}

	accepted, dropped, err := s.processBatch(records)
	if err != nil {
		http.Error(w, "failed to forward logs", http.StatusBadGateway)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]int{
		"accepted": accepted,
		"dropped":  dropped,
	})
}

func (s *logCollectionService) processBatch(records []logCollectionResolvedRecord) (int, int, error) {
	rows := make([]normalizedLogRow, 0, len(records))
	dropped := 0
	for _, rec := range records {
		row, ok := s.resolveAndNormalize(rec)
		if !ok {
			dropped++
			continue
		}
		rows = append(rows, row)
	}
	if len(rows) == 0 {
		return 0, dropped, nil
	}
	if s.sendOTLP {
		if err := s.sendOTLPRows(rows); err != nil {
			return len(rows), dropped, err
		}
	}
	s.sendFastLaneRows(rows)
	return len(rows), dropped, nil
}

func (s *logCollectionService) setFastTailActive(containerKey string, active bool) {
	containerKey = strings.TrimSpace(containerKey)
	if containerKey == "" {
		return
	}
	s.fastLaneMu.Lock()
	defer s.fastLaneMu.Unlock()
	if active {
		s.activeFastTail[containerKey] = struct{}{}
		return
	}
	delete(s.activeFastTail, containerKey)
}

func (s *logCollectionService) isFastTailActive(containerKey string) bool {
	s.fastLaneMu.RLock()
	defer s.fastLaneMu.RUnlock()
	_, ok := s.activeFastTail[strings.TrimSpace(containerKey)]
	return ok
}

func (s *logCollectionService) activeContainerCount() int {
	s.activeContainersMu.RLock()
	defer s.activeContainersMu.RUnlock()
	return len(s.activeContainers)
}

func (s *logCollectionService) activateContainer(containerKey string) (bool, error) {
	containerKey = strings.TrimSpace(containerKey)
	if containerKey == "" {
		return false, fmt.Errorf("container_key is required")
	}
	name := runtimeContainerName(containerKey)
	if name == "" {
		return false, fmt.Errorf("invalid container_key %q", containerKey)
	}

	plan := inspectLogCollectionPlan(s.inspector, ContainerKey{Name: name}, false)
	if !plan.isHealthy() {
		return false, fmt.Errorf("logs unavailable for %s", containerKey)
	}
	plan.Key = ContainerKey{Name: name, Image: strings.TrimSpace(plan.Image)}

	s.activeContainersMu.Lock()
	defer s.activeContainersMu.Unlock()
	if _, exists := s.activeContainers[containerKey]; exists {
		return false, nil
	}
	s.activeContainers[containerKey] = plan
	s.planCache.store(plan)
	return true, nil
}

func (s *logCollectionService) deactivateContainer(containerKey string) bool {
	containerKey = strings.TrimSpace(containerKey)
	if containerKey == "" {
		return false
	}
	s.activeContainersMu.Lock()
	defer s.activeContainersMu.Unlock()
	if _, exists := s.activeContainers[containerKey]; !exists {
		return false
	}
	delete(s.activeContainers, containerKey)
	return true
}

func (s *logCollectionService) isContainerActive(containerKey string) bool {
	s.activeContainersMu.RLock()
	defer s.activeContainersMu.RUnlock()
	_, ok := s.activeContainers[strings.TrimSpace(containerKey)]
	return ok
}

func (s *logCollectionService) activePlans() []logCollectionPlan {
	s.activeContainersMu.RLock()
	defer s.activeContainersMu.RUnlock()
	plans := make([]logCollectionPlan, 0, len(s.activeContainers))
	for _, plan := range s.activeContainers {
		plans = append(plans, plan)
	}
	return plans
}

func (s *logCollectionService) resolveAndNormalize(rec logCollectionResolvedRecord) (normalizedLogRow, bool) {
	normalizedRecord := normalizeEmbeddedLogRecord(rec.Record)
	containerName := resolveContainerName(rec.Tag, normalizedRecord)
	dockerID := resolveDockerContainerID(normalizedRecord)
	plan, ok := s.resolvePlan(containerName, dockerID)
	if !ok || !plan.isHealthy() {
		return normalizedLogRow{}, false
	}

	message := resolveLogMessage(normalizedRecord)
	if message == "" {
		return normalizedLogRow{}, false
	}

	resolvedName := strings.TrimSpace(strings.TrimPrefix(plan.ContainerName, "/"))
	if resolvedName == "" {
		resolvedName = strings.TrimSpace(strings.TrimPrefix(containerName, "/"))
	}
	if resolvedName == "" {
		resolvedName = strings.TrimSpace(strings.TrimPrefix(plan.Key.Name, "/"))
	}
	if resolvedName == "" {
		return normalizedLogRow{}, false
	}

	dockerContainerID := strings.TrimSpace(dockerID)
	if dockerContainerID == "" {
		dockerContainerID = strings.TrimSpace(plan.DockerContainerID)
	}
	runtimeKey := s.hostID + ":" + resolvedName
	if s.requireMonitored {
		if s.state == nil || !s.state.IsMonitored(plan.Key.Name, plan.Key.Image) {
			return normalizedLogRow{}, false
		}
	} else if !s.isContainerActive(runtimeKey) {
		return normalizedLogRow{}, false
	}

	timestamp := rec.Timestamp
	if !hasMeaningfulValue(timestamp) {
		timestamp = normalizedRecord["time"]
	}

	return normalizedLogRow{
		Time:              normalizeLogTimestamp(timestamp),
		Msg:               message,
		MsgJSON:           normalizedRecord,
		ContainerKey:      runtimeKey,
		ContainerName:     resolvedName,
		DockerContainerID: dockerContainerID,
		HeraldID:          s.hostID,
		HeraldName:        s.heraldName,
		ServiceName:       resolvedName,
		ServiceNamespace:  "unicron.herald",
		Stream:            resolveLogStream(normalizedRecord),
		Severity:          resolveLogSeverity(normalizedRecord),
	}, true
}

func (s *logCollectionService) resolvePlan(containerName, dockerID string) (logCollectionPlan, bool) {
	if plan, ok := s.planCache.resolve(containerName, dockerID); ok {
		return plan, true
	}

	if s.requireMonitored && s.state != nil {
		if key, ok := s.state.KeyForName(containerName); ok {
			plan := logCollectionPlan{
				Key:               key,
				ContainerName:     strings.TrimSpace(strings.TrimPrefix(containerName, "/")),
				DockerContainerID: strings.TrimSpace(dockerID),
				Image:             key.Image,
				SourceMode:        logSourcePush,
			}
			s.planCache.store(plan)
			return plan, true
		}
	}

	return logCollectionPlan{}, false
}

func runtimeContainerName(containerKey string) string {
	containerKey = strings.TrimSpace(containerKey)
	if containerKey == "" {
		return ""
	}
	if idx := strings.Index(containerKey, ":"); idx >= 0 && idx+1 < len(containerKey) {
		return strings.TrimSpace(strings.TrimPrefix(containerKey[idx+1:], "/"))
	}
	return strings.TrimSpace(strings.TrimPrefix(containerKey, "/"))
}

func (s *logCollectionService) emitFastLogsError(containerKey string, err error) {
	if s.fastLaneSender == nil || err == nil {
		return
	}
	payload, marshalErr := json.Marshal(fastLogsErrorPayload{
		ContainerKey: strings.TrimSpace(containerKey),
		Error:        err.Error(),
	})
	if marshalErr != nil {
		logrus.WithError(marshalErr).WithField("container_key", containerKey).Warn("[LogCollection] failed to marshal fast lane error")
		return
	}
	s.fastLaneSender.sendEnvelope(upstreamEnvelope{Type: "fast_logs_error", Data: payload})
}

func (s *logCollectionService) seedHistory(ctx context.Context, containerKey, tail, since string) error {
	containerKey = strings.TrimSpace(containerKey)
	if containerKey == "" {
		return fmt.Errorf("container_key is required")
	}
	name := runtimeContainerName(containerKey)
	if name == "" {
		return fmt.Errorf("invalid container_key %q", containerKey)
	}

	resolvedName, dockerID, usesTTY, err := inspectContainerLogTarget(s.inspector, name)
	if err != nil {
		return fmt.Errorf("logs unavailable for %s", containerKey)
	}
	if dockerID == "" {
		return fmt.Errorf("docker container id unavailable for %s", containerKey)
	}

	opts := container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Follow:     false,
		Timestamps: true,
	}
	tail = strings.TrimSpace(tail)
	if tail == "" && strings.TrimSpace(since) == "" {
		tail = defaultLiveTailHistory
	}
	if tail != "" {
		opts.Tail = tail
	}
	if strings.TrimSpace(since) != "" {
		opts.Since = strings.TrimSpace(since)
	}

	reader, err := s.inspector.ContainerLogs(ctx, dockerID, opts)
	if err != nil {
		return err
	}
	defer reader.Close()

	var rows []normalizedLogRow
	if usesTTY {
		rows, err = s.readTTYSeedRows(reader, containerKey, resolvedName, dockerID)
	} else {
		rows, err = s.readFramedSeedRows(reader, containerKey, resolvedName, dockerID)
	}
	// Send whatever rows were successfully parsed, even on partial read failure.
	if len(rows) > 0 {
		s.sendFastLaneRows(rows)
	}
	return err
}

func (s *logCollectionService) readTTYSeedRows(
	reader io.Reader,
	containerKey string,
	resolvedName string,
	dockerID string,
) ([]normalizedLogRow, error) {
	rows := make([]normalizedLogRow, 0, 128)
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 0, 64*1024), maxSeedFrameSize)
	for scanner.Scan() {
		if len(rows) >= maxSeedRows {
			logrus.WithField("container_key", containerKey).Warn("[LogCollection] seedHistory reached row limit")
			break
		}
		line := strings.TrimRight(scanner.Text(), "\r\n")
		if strings.TrimSpace(line) == "" {
			continue
		}
		rows = append(rows, s.buildSeedHistoryRow(containerKey, resolvedName, dockerID, line, ""))
	}
	return rows, scanner.Err()
}

func (s *logCollectionService) readFramedSeedRows(
	reader io.Reader,
	containerKey string,
	resolvedName string,
	dockerID string,
) ([]normalizedLogRow, error) {
	rows := make([]normalizedLogRow, 0, 128)
	buf := make([]byte, 8)
	var readErr error
	for {
		if len(rows) >= maxSeedRows {
			logrus.WithField("container_key", containerKey).Warn("[LogCollection] seedHistory reached row limit")
			break
		}
		if _, err := io.ReadFull(reader, buf); err != nil {
			if err != io.EOF && err != io.ErrUnexpectedEOF {
				readErr = err
			}
			break
		}
		size := int(buf[4])<<24 | int(buf[5])<<16 | int(buf[6])<<8 | int(buf[7])
		if size <= 0 {
			continue
		}
		if size > maxSeedFrameSize {
			logrus.WithFields(logrus.Fields{
				"container_key": containerKey,
				"frame_size":    size,
			}).Warn("[LogCollection] skipping oversized Docker log frame in seedHistory")
			if _, err := io.CopyN(io.Discard, reader, int64(size)); err != nil {
				if err != io.EOF && err != io.ErrUnexpectedEOF {
					readErr = err
				}
				break
			}
			continue
		}
		payload := make([]byte, size)
		if _, err := io.ReadFull(reader, payload); err != nil {
			if err != io.EOF && err != io.ErrUnexpectedEOF {
				readErr = err
			}
			break
		}
		line := strings.TrimRight(string(payload), "\r\n")
		if strings.TrimSpace(line) == "" {
			continue
		}
		stream := ""
		switch buf[0] {
		case 1:
			stream = "stdout"
		case 2:
			stream = "stderr"
		}
		rows = append(rows, s.buildSeedHistoryRow(containerKey, resolvedName, dockerID, line, stream))
	}
	return rows, readErr
}

func (s *logCollectionService) buildSeedHistoryRow(
	containerKey string,
	resolvedName string,
	dockerID string,
	line string,
	stream string,
) normalizedLogRow {
	ts := time.Now().UTC().Format(time.RFC3339Nano)
	msg := line
	if idx := strings.Index(line, " "); idx > 0 {
		ts = normalizeLogTimestamp(line[:idx])
		msg = line[idx+1:]
	}
	return normalizedLogRow{
		Time:              ts,
		Msg:               msg,
		ContainerKey:      containerKey,
		ContainerName:     resolvedName,
		DockerContainerID: dockerID,
		HeraldID:          s.hostID,
		HeraldName:        s.heraldName,
		ServiceName:       resolvedName,
		ServiceNamespace:  "unicron.herald",
		Stream:            stream,
	}
}

func (s *logCollectionService) sendOTLPRows(rows []normalizedLogRow) error {
	payload, err := buildOTLPLogsPayload(rows)
	if err != nil {
		return err
	}

	req, err := http.NewRequest(http.MethodPost, s.otlpURL, bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := s.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		responseBody, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return fmt.Errorf("otlp log ingest returned status %d: %s", resp.StatusCode, strings.TrimSpace(string(responseBody)))
	}
	return nil
}

func (s *logCollectionService) sendFastLaneRows(rows []normalizedLogRow) {
	if s.fastLaneSender == nil {
		return
	}
	for _, row := range rows {
		if !s.isFastTailActive(row.ContainerKey) {
			continue
		}
		payload, err := json.Marshal(fastLogsFramePayload{
			ContainerKey: row.ContainerKey,
			Row:          row,
		})
		if err != nil {
			logrus.WithError(err).WithField("container_key", row.ContainerKey).Warn("[LogCollection] failed to marshal fast lane row")
			continue
		}
		s.fastLaneSender.sendEnvelope(upstreamEnvelope{Type: "fast_logs_frame", Data: payload})
	}
}

func buildOTLPLogsPayload(rows []normalizedLogRow) ([]byte, error) {
	resourceLogs := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		resourceAttrs := []map[string]any{
			otlpJSONAttribute("herald_id", row.HeraldID),
			otlpJSONAttribute("herald_name", row.HeraldName),
			otlpJSONAttribute("container_key", row.ContainerKey),
			otlpJSONAttribute("container_name", row.ContainerName),
			otlpJSONAttribute("service_name", row.ServiceName),
			otlpJSONAttribute("service_namespace", row.ServiceNamespace),
		}
		if row.DockerContainerID != "" {
			resourceAttrs = append(resourceAttrs, otlpJSONAttribute("docker_container_id", row.DockerContainerID))
		}

		logAttrs := []map[string]any{
			otlpJSONAttribute("msg", row.Msg),
		}
		if row.MsgJSON != nil {
			logAttrs = append(logAttrs, otlpJSONAttribute("msg_json", row.MsgJSON))
		}
		if row.Stream != "" {
			logAttrs = append(logAttrs, otlpJSONAttribute("stream", row.Stream))
		}
		if row.Severity != "" {
			logAttrs = append(logAttrs, otlpJSONAttribute("severity", row.Severity))
		}

		logRecord := map[string]any{
			"timeUnixNano": otlpJSONUnixNano(row.Time),
			"body":         map[string]any{"stringValue": row.Msg},
			"attributes":   logAttrs,
		}
		if row.Severity != "" {
			logRecord["severityText"] = row.Severity
		}

		resourceLogs = append(resourceLogs, map[string]any{
			"resource": map[string]any{
				"attributes": resourceAttrs,
			},
			"scopeLogs": []map[string]any{
				{
					"scope": map[string]any{
						"name": "go-streamer.log-collection",
					},
					"logRecords": []map[string]any{logRecord},
				},
			},
		})
	}

	return json.Marshal(map[string]any{
		"resourceLogs": resourceLogs,
	})
}

func otlpJSONAttribute(key string, value any) map[string]any {
	return map[string]any{
		"key":   key,
		"value": otlpJSONAnyValue(value),
	}
}

func otlpJSONAnyValue(value any) map[string]any {
	switch v := value.(type) {
	case nil:
		return map[string]any{"stringValue": ""}
	case string:
		return map[string]any{"stringValue": v}
	case bool:
		return map[string]any{"boolValue": v}
	case int:
		return map[string]any{"intValue": strconv.Itoa(v)}
	case int64:
		return map[string]any{"intValue": strconv.FormatInt(v, 10)}
	case float64:
		return map[string]any{"doubleValue": v}
	case float32:
		return map[string]any{"doubleValue": float64(v)}
	case map[string]any:
		values := make([]map[string]any, 0, len(v))
		for key, item := range v {
			values = append(values, otlpJSONAttribute(key, item))
		}
		return map[string]any{
			"kvlistValue": map[string]any{
				"values": values,
			},
		}
	case []any:
		values := make([]map[string]any, 0, len(v))
		for _, item := range v {
			values = append(values, otlpJSONAnyValue(item))
		}
		return map[string]any{
			"arrayValue": map[string]any{
				"values": values,
			},
		}
	default:
		return map[string]any{"stringValue": fmt.Sprint(v)}
	}
}

func otlpJSONUnixNano(value string) string {
	parsed, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(value))
	if err != nil {
		parsed = time.Now().UTC()
	}
	return strconv.FormatInt(parsed.UnixNano(), 10)
}

func inspectLogCollectionPlan(inspector dockerInspector, key ContainerKey, pushEnabled bool) logCollectionPlan {
	plan := logCollectionPlan{
		Key:   key,
		Image: key.Image,
	}

	if inspector == nil {
		plan.SourceMode = logSourceUnavailable
		plan.Issue = logIssueInspectFailed
		return plan
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	inspect, err := inspector.ContainerInspect(ctx, key.Name)
	if err != nil {
		plan.SourceMode = logSourceUnavailable
		plan.Issue = logIssueInspectFailed
		return plan
	}

	if inspect.Config != nil {
		if image := strings.TrimSpace(inspect.Config.Image); image != "" {
			plan.Image = image
			plan.Key.Image = image
		}
		plan.UsesTTY = inspect.Config.Tty
	}
	plan.ContainerName = strings.TrimSpace(strings.TrimPrefix(inspect.Name, "/"))
	plan.DockerContainerID = strings.TrimSpace(inspect.ID)

	driver := ""
	var logConfig map[string]string
	if inspect.HostConfig != nil {
		driver = strings.ToLower(strings.TrimSpace(inspect.HostConfig.LogConfig.Type))
		if inspect.HostConfig.LogConfig.Config != nil {
			logConfig = inspect.HostConfig.LogConfig.Config
		}
	}
	if driver == "fluentd" && pushEnabled {
		if isLocalFluentdAddress(logConfig["fluentd-address"]) {
			plan.SourceMode = logSourcePush
			return plan
		}
	}

	if strings.TrimSpace(inspect.LogPath) != "" {
		logPath := resolveAccessibleLogPath(inspect.LogPath)
		if logPath == "" {
			plan.SourceMode = logSourceUnavailable
			plan.Issue = logIssueMissingLogPath
			return plan
		}
		plan.SourceMode = logSourceTail
		plan.LogPath = logPath
		return plan
	}

	plan.SourceMode = logSourceUnavailable
	if driver != "" && driver != "json-file" && driver != "local" && driver != "fluentd" {
		plan.Issue = logIssueUnsupportedSource
	} else {
		plan.Issue = logIssueMissingLogPath
	}
	return plan
}

func buildLogCollectionPlan(ctx context.Context, inspector dockerInspector, key ContainerKey) logCollectionPlan {
	_ = ctx
	return inspectLogCollectionPlan(inspector, key, telemetryPushEnabled(resolveTelemetryMode()))
}

func buildLogCollectionPlanForRef(ctx context.Context, inspector dockerInspector, ref string) logCollectionPlan {
	_ = ctx
	ref = strings.TrimSpace(strings.TrimPrefix(ref, "/"))
	if ref == "" {
		return logCollectionPlan{SourceMode: logSourceUnavailable, Issue: logIssueInspectFailed}
	}
	return buildLogCollectionPlan(context.Background(), inspector, ContainerKey{Name: ref})
}

func parseLogCollectionBatch(body []byte, fallbackTag string) ([]logCollectionResolvedRecord, error) {
	text := strings.TrimSpace(string(body))
	if text == "" {
		return nil, nil
	}

	if strings.HasPrefix(text, "{") || strings.HasPrefix(text, "[") {
		var payload any
		if err := json.Unmarshal([]byte(text), &payload); err == nil {
			return decodeLogCollectionPayload(payload, fallbackTag)
		}
	}

	records := make([]logCollectionResolvedRecord, 0)
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var payload any
		if err := json.Unmarshal([]byte(line), &payload); err != nil {
			return nil, err
		}
		decoded, err := decodeLogCollectionPayload(payload, fallbackTag)
		if err != nil {
			return nil, err
		}
		records = append(records, decoded...)
	}
	return records, nil
}

func decodeLogCollectionPayload(payload any, fallbackTag string) ([]logCollectionResolvedRecord, error) {
	switch value := payload.(type) {
	case []any:
		records := make([]logCollectionResolvedRecord, 0, len(value))
		for _, item := range value {
			decoded, err := decodeLogCollectionPayload(item, fallbackTag)
			if err != nil {
				return nil, err
			}
			records = append(records, decoded...)
		}
		return records, nil
	case map[string]any:
		if nested, ok := value["records"]; ok {
			return decodeLogCollectionPayload(nested, fallbackTag)
		}
		if nested, ok := value["logs"]; ok {
			return decodeLogCollectionPayload(nested, fallbackTag)
		}
		tag := firstStringValue(value, "tag")
		if tag == "" {
			tag = strings.TrimSpace(fallbackTag)
		}
		timestamp := value["timestamp"]
		record := value
		if nested, ok := value["record"]; ok {
			nestedMap, ok := nested.(map[string]any)
			if !ok {
				return nil, fmt.Errorf("record field is not an object")
			}
			record = nestedMap
		} else {
			record = recordJSONCopy(value)
			delete(record, "tag")
			delete(record, "timestamp")
		}
		if record == nil {
			record = map[string]any{}
		}
		return []logCollectionResolvedRecord{{
			Tag:       tag,
			Timestamp: timestamp,
			Record:    record,
		}}, nil
	default:
		return nil, fmt.Errorf("unsupported log payload")
	}
}

func normalizeLogTimestamp(value any) string {
	switch t := value.(type) {
	case string:
		if strings.TrimSpace(t) != "" {
			return strings.TrimSpace(t)
		}
	case float64:
		return time.Unix(int64(t), 0).UTC().Format(time.RFC3339Nano)
	case float32:
		return time.Unix(int64(t), 0).UTC().Format(time.RFC3339Nano)
	case int:
		return time.Unix(int64(t), 0).UTC().Format(time.RFC3339Nano)
	case int64:
		return time.Unix(t, 0).UTC().Format(time.RFC3339Nano)
	case json.Number:
		if i, err := t.Int64(); err == nil {
			return time.Unix(i, 0).UTC().Format(time.RFC3339Nano)
		}
		if f, err := t.Float64(); err == nil {
			return time.Unix(int64(f), 0).UTC().Format(time.RFC3339Nano)
		}
	case map[string]any:
		sec := extractNumberField(t, "sec", "seconds")
		if sec >= 0 {
			nsec := extractNumberField(t, "nsec", "nanosec")
			if nsec < 0 {
				nsec = 0
			}
			return time.Unix(sec, nsec).UTC().Format(time.RFC3339Nano)
		}
	}
	return time.Now().UTC().Format(time.RFC3339Nano)
}

func extractNumberField(record map[string]any, keys ...string) int64 {
	for _, key := range keys {
		value, ok := record[key]
		if !ok {
			continue
		}
		switch v := value.(type) {
		case float64:
			return int64(v)
		case float32:
			return int64(v)
		case int:
			return int64(v)
		case int64:
			return v
		case json.Number:
			if n, err := v.Int64(); err == nil {
				return n
			}
		case string:
			if strings.TrimSpace(v) == "" {
				continue
			}
			if n, err := strconv.ParseInt(strings.TrimSpace(v), 10, 64); err == nil {
				return n
			}
		}
	}
	return -1
}

func hasMeaningfulValue(value any) bool {
	if value == nil {
		return false
	}
	if str, ok := value.(string); ok {
		return strings.TrimSpace(str) != ""
	}
	return strings.TrimSpace(fmt.Sprint(value)) != "<nil>"
}

func firstStringValue(record map[string]any, keys ...string) string {
	for _, key := range keys {
		value, ok := record[key]
		if !ok || value == nil {
			continue
		}
		switch v := value.(type) {
		case string:
			v = strings.TrimSpace(v)
			if v != "" {
				return v
			}
		default:
			s := strings.TrimSpace(fmt.Sprint(v))
			if s != "" && s != "<nil>" {
				return s
			}
		}
	}
	return ""
}

func firstNonEmptyString(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func recordJSONCopy(record map[string]any) map[string]any {
	if record == nil {
		return nil
	}
	buf, err := json.Marshal(record)
	if err != nil {
		return record
	}
	var cloned map[string]any
	if err := json.Unmarshal(buf, &cloned); err != nil {
		return record
	}
	return cloned
}

func resolveContainerName(tag string, record map[string]any) string {
	tag = strings.TrimSpace(tag)
	if strings.HasPrefix(tag, "docker.") {
		if name := strings.TrimPrefix(tag, "docker."); name != "" {
			return strings.TrimPrefix(name, "/")
		}
	}
	if name := firstStringValue(record, "container_name", "container.name", "name"); name != "" {
		return strings.TrimPrefix(name, "/")
	}
	return ""
}

func resolveDockerContainerID(record map[string]any) string {
	return firstStringValue(record, "container_id", "container.id", "containerId", "docker_container_id")
}

func parseEmbeddedLogObject(raw string) map[string]any {
	raw = strings.TrimSpace(raw)
	if raw == "" || (!strings.HasPrefix(raw, "{") && !strings.HasPrefix(raw, "[")) {
		return nil
	}

	var parsed any
	if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
		return nil
	}
	record, ok := parsed.(map[string]any)
	if !ok {
		return nil
	}
	if firstStringValue(record, "log", "message", "body") == "" {
		return nil
	}
	return record
}

func normalizeEmbeddedLogRecord(record map[string]any) map[string]any {
	normalized := recordJSONCopy(record)
	if normalized == nil {
		return nil
	}

	raw := firstStringValue(normalized, "log", "message", "body")
	embedded := parseEmbeddedLogObject(raw)
	if embedded == nil {
		return normalized
	}

	if msg := firstStringValue(embedded, "log", "message", "body"); msg != "" {
		normalized["log"] = strings.TrimRight(msg, "\r\n")
	}
	if firstStringValue(normalized, "stream", "source") == "" {
		if stream := firstStringValue(embedded, "stream", "source"); stream != "" {
			normalized["stream"] = stream
		}
	}
	if firstStringValue(normalized, "time", "timestamp") == "" {
		if ts := firstStringValue(embedded, "time", "timestamp"); ts != "" {
			normalized["time"] = ts
		}
	}
	return normalized
}

func resolveLogMessage(record map[string]any) string {
	msg := firstStringValue(record, "log", "message", "body")
	if msg != "" {
		return strings.TrimRight(msg, "\r\n")
	}
	return ""
}

func resolveLogStream(record map[string]any) string {
	return firstStringValue(record, "stream", "source")
}

func resolveLogSeverity(record map[string]any) string {
	return firstStringValue(record, "severity", "level")
}

func isLocalFluentdAddress(raw string) bool {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return false
	}

	host := raw
	if strings.Contains(raw, "://") {
		parsed, err := url.Parse(raw)
		if err == nil && parsed != nil {
			if parsed.Host != "" {
				host = parsed.Host
			} else if parsed.Path != "" {
				host = parsed.Path
			}
		}
	}

	hostname := host
	port := ""
	if strings.Contains(host, ":") {
		if h, p, err := net.SplitHostPort(host); err == nil {
			hostname = h
			port = p
		} else {
			last := strings.LastIndex(host, ":")
			if last > -1 {
				hostname = host[:last]
				port = host[last+1:]
			}
		}
	}

	hostname = strings.TrimSpace(strings.TrimPrefix(hostname, "/"))
	port = strings.TrimSpace(port)
	switch hostname {
	case "localhost", "127.0.0.1", "::1":
		return port == "24224" || port == ""
	}
	return false
}
