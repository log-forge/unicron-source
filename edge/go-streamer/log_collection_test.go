package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
)

type fakeDockerInspector struct {
	inspect func(context.Context, string) (types.ContainerJSON, error)
	logs    func(context.Context, string, container.LogsOptions) (io.ReadCloser, error)
}

func (f fakeDockerInspector) ContainerInspect(ctx context.Context, ref string) (types.ContainerJSON, error) {
	return f.inspect(ctx, ref)
}

func (f fakeDockerInspector) ContainerLogs(
	ctx context.Context,
	ref string,
	options container.LogsOptions,
) (io.ReadCloser, error) {
	if f.logs != nil {
		return f.logs(ctx, ref, options)
	}
	return io.NopCloser(strings.NewReader("")), nil
}

func testContainerJSON(name, image, driver, address, logPath string) types.ContainerJSON {
	return testContainerJSONWithTTY(name, image, driver, address, logPath, false)
}

func testContainerJSONWithTTY(name, image, driver, address, logPath string, tty bool) types.ContainerJSON {
	return types.ContainerJSON{
		ContainerJSONBase: &types.ContainerJSONBase{
			ID:      "container-id-" + name,
			Name:    "/" + name,
			Driver:  driver,
			LogPath: logPath,
			HostConfig: &container.HostConfig{
				LogConfig: container.LogConfig{
					Type: driver,
					Config: map[string]string{
						"fluentd-address": address,
					},
				},
			},
			Image: image,
		},
		Config: &container.Config{
			Image: image,
			Tty:   tty,
		},
	}
}

func TestBuildLogCollectionPlanClassifiesSources(t *testing.T) {
	previousLogPathAccessible := logPathAccessible
	logPathAccessible = func(path string) bool {
		return path == "/var/lib/docker/containers/tail/tail-json.log"
	}
	defer func() {
		logPathAccessible = previousLogPathAccessible
	}()

	inspector := fakeDockerInspector{
		inspect: func(ctx context.Context, ref string) (types.ContainerJSON, error) {
			switch ref {
			case "push":
				return testContainerJSON("push", "example/app:push", "fluentd", "127.0.0.1:24224", ""), nil
			case "tail":
				return testContainerJSON("tail", "example/app:tail", "json-file", "", "/var/lib/docker/containers/tail/tail-json.log"), nil
			case "missing":
				return testContainerJSON("missing", "example/app:missing", "json-file", "", ""), nil
			case "unsupported":
				return testContainerJSON("unsupported", "example/app:unsupported", "journald", "", ""), nil
			case "inaccessible":
				return testContainerJSON("inaccessible", "example/app:inaccessible", "json-file", "", "/var/lib/docker/containers/inaccessible/inaccessible-json.log"), nil
			default:
				return types.ContainerJSON{}, io.EOF
			}
		},
	}

	cases := []struct {
		name    string
		ref     string
		mode    logSourceMode
		issue   logIssueCode
		wantTag string
	}{
		{name: "push", ref: "push", mode: logSourcePush, wantTag: "docker.push"},
		{name: "tail", ref: "tail", mode: logSourceTail, wantTag: "docker.tail"},
		{name: "inaccessible_tail", ref: "inaccessible", mode: logSourceUnavailable, issue: logIssueMissingLogPath},
		{name: "missing_path", ref: "missing", mode: logSourceUnavailable, issue: logIssueMissingLogPath},
		{name: "unsupported", ref: "unsupported", mode: logSourceUnavailable, issue: logIssueUnsupportedSource},
		{name: "inspect_failed", ref: "absent", mode: logSourceUnavailable, issue: logIssueInspectFailed},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			plan := buildLogCollectionPlan(context.Background(), inspector, ContainerKey{Name: tc.ref, Image: "example/app"})
			if tc.issue == logIssueInspectFailed {
				plan = buildLogCollectionPlanForRef(context.Background(), inspector, tc.ref)
			}
			if plan.SourceMode != tc.mode {
				t.Fatalf("expected mode %q, got %q", tc.mode, plan.SourceMode)
			}
			if plan.Issue != tc.issue {
				t.Fatalf("expected issue %q, got %q", tc.issue, plan.Issue)
			}
			if tc.wantTag != "" && plan.fluentBitTag() != tc.wantTag {
				t.Fatalf("expected tag %q, got %q", tc.wantTag, plan.fluentBitTag())
			}
		})
	}
}

func TestResolveAccessibleLogPathPrefersHostRootTranslation(t *testing.T) {
	inspectPath := "/var/lib/docker/containers/web/web-json.log"

	previousLogPathAccessible := logPathAccessible
	previousContainerRoots := dockerDesktopWSLContainerRoots
	previousBindRoots := dockerDesktopWSLBindMountRoots
	logPathAccessible = func(path string) bool {
		return path == "/host/root/var/lib/docker/containers/web/web-json.log"
	}
	dockerDesktopWSLContainerRoots = nil
	dockerDesktopWSLBindMountRoots = nil
	defer func() {
		logPathAccessible = previousLogPathAccessible
		dockerDesktopWSLContainerRoots = previousContainerRoots
		dockerDesktopWSLBindMountRoots = previousBindRoots
	}()

	resolved := resolveAccessibleLogPath(inspectPath)
	if resolved != "/host/root/var/lib/docker/containers/web/web-json.log" {
		t.Fatalf("expected host-root translation, got %q", resolved)
	}
}

func TestBuildLogCollectionPlanResolvesWSLBindMountLogPath(t *testing.T) {
	containerID := strings.Repeat("a", 64)
	inspectPath := filepath.Join(dockerContainersRootPath, containerID, containerID+"-json.log")

	tempRoot := t.TempDir()
	bindRoot := filepath.Join(tempRoot, "docker-desktop-bind-mounts")
	resolvedPath := filepath.Join(
		bindRoot,
		"Ubuntu",
		"hash123",
		"var",
		"lib",
		"docker",
		"containers",
		containerID,
		containerID+"-json.log",
	)
	if err := os.MkdirAll(filepath.Dir(resolvedPath), 0o755); err != nil {
		t.Fatalf("mkdir translated log path: %v", err)
	}
	if err := os.WriteFile(resolvedPath, []byte("seed"), 0o644); err != nil {
		t.Fatalf("write translated log path: %v", err)
	}

	previousContainerRoots := dockerDesktopWSLContainerRoots
	previousBindRoots := dockerDesktopWSLBindMountRoots
	previousLogPathAccessible := logPathAccessible
	dockerDesktopWSLContainerRoots = nil
	dockerDesktopWSLBindMountRoots = []string{bindRoot}
	logPathAccessible = func(path string) bool {
		_, err := os.Stat(path)
		return err == nil
	}
	defer func() {
		dockerDesktopWSLContainerRoots = previousContainerRoots
		dockerDesktopWSLBindMountRoots = previousBindRoots
		logPathAccessible = previousLogPathAccessible
	}()

	plan := buildLogCollectionPlan(context.Background(), fakeDockerInspector{
		inspect: func(ctx context.Context, ref string) (types.ContainerJSON, error) {
			return testContainerJSON("web", "example/app:v1", "json-file", "", inspectPath), nil
		},
	}, ContainerKey{Name: "web", Image: "example/app:v1"})

	if plan.SourceMode != logSourceTail {
		t.Fatalf("expected translated WSL path to stay healthy, got mode %q", plan.SourceMode)
	}
	if plan.LogPath != resolvedPath {
		t.Fatalf("expected translated path %q, got %q", resolvedPath, plan.LogPath)
	}
}

func TestResolveAndNormalizeUsesCanonicalContainerKey(t *testing.T) {
	state := NewMonitoringState("")
	state.SetEnabled("web", "example/app:v1", true)

	service := &logCollectionService{
		hostID:           "host-a",
		heraldName:       "host-a",
		state:            state,
		planCache:        newLogCollectionPlanCache(time.Minute),
		requireMonitored: true,
	}
	service.planCache.store(logCollectionPlan{
		Key:               ContainerKey{Name: "web", Image: "example/app:v1"},
		ContainerName:     "web",
		DockerContainerID: "abc123",
		Image:             "example/app:v1",
		LogPath:           "/var/lib/docker/containers/web/web-json.log",
		SourceMode:        logSourceTail,
	})

	row, ok := service.resolveAndNormalize(logCollectionResolvedRecord{
		Tag:       "docker.web",
		Timestamp: "2026-03-20T01:02:03Z",
		Record: map[string]any{
			"log":          "hello world",
			"stream":       "stdout",
			"severity":     "info",
			"container_id": "abc123",
		},
	})
	if !ok {
		t.Fatalf("expected record to normalize")
	}
	if row.ContainerKey != "host-a:web" {
		t.Fatalf("unexpected container key %q", row.ContainerKey)
	}
	if row.ContainerName != "web" {
		t.Fatalf("unexpected container name %q", row.ContainerName)
	}
	if row.Msg != "hello world" {
		t.Fatalf("unexpected message %q", row.Msg)
	}
	if row.HeraldID != "host-a" || row.HeraldName != "host-a" {
		t.Fatalf("unexpected herald fields: %+v", row)
	}
	if row.ServiceName != "web" {
		t.Fatalf("unexpected service name %q", row.ServiceName)
	}
	if row.ServiceNamespace != "unicron.herald" {
		t.Fatalf("unexpected service namespace %q", row.ServiceNamespace)
	}
}

func TestResolveAndNormalizeFallsBackToMonitoredNameWhenStateImageIsMissing(t *testing.T) {
	state := NewMonitoringState("")
	state.SetEnabled("web", "", true)

	service := &logCollectionService{
		hostID:           "host-a",
		heraldName:       "host-a",
		state:            state,
		planCache:        newLogCollectionPlanCache(time.Minute),
		requireMonitored: true,
	}
	service.planCache.store(logCollectionPlan{
		Key:               ContainerKey{Name: "web", Image: "example/app:v1"},
		ContainerName:     "web",
		DockerContainerID: "abc123",
		Image:             "example/app:v1",
		SourceMode:        logSourcePush,
	})

	row, ok := service.resolveAndNormalize(logCollectionResolvedRecord{
		Tag: "pushed.logs",
		Record: map[string]any{
			"log":            "hello from fluentd",
			"container_name": "/web",
			"container_id":   "abc123",
			"source":         "stdout",
		},
	})
	if !ok {
		t.Fatalf("expected record to normalize with name-only monitored fallback")
	}
	if row.ContainerKey != "host-a:web" {
		t.Fatalf("unexpected container key %q", row.ContainerKey)
	}
	if row.Msg != "hello from fluentd" {
		t.Fatalf("unexpected message %q", row.Msg)
	}
}

func TestResolveAndNormalizeUnwrapsEmbeddedDockerJSONLog(t *testing.T) {
	state := NewMonitoringState("")
	state.SetEnabled("web", "example/app:v1", true)

	service := &logCollectionService{
		hostID:           "host-a",
		heraldName:       "host-a",
		state:            state,
		planCache:        newLogCollectionPlanCache(time.Minute),
		requireMonitored: true,
	}
	service.planCache.store(logCollectionPlan{
		Key:               ContainerKey{Name: "web", Image: "example/app:v1"},
		ContainerName:     "web",
		DockerContainerID: "abc123",
		Image:             "example/app:v1",
		LogPath:           "/var/lib/docker/containers/web/web-json.log",
		SourceMode:        logSourceTail,
	})

	row, ok := service.resolveAndNormalize(logCollectionResolvedRecord{
		Tag: "docker.web",
		Record: map[string]any{
			"log":          "{\"log\":\"synthetic log line Lorum Ipsum\\n\",\"stream\":\"stdout\",\"time\":\"2026-03-24T06:07:40.308248751Z\"}",
			"container_id": "abc123",
		},
	})
	if !ok {
		t.Fatalf("expected record to normalize")
	}
	if row.Msg != "synthetic log line Lorum Ipsum" {
		t.Fatalf("unexpected unwrapped message %q", row.Msg)
	}
	if row.Stream != "stdout" {
		t.Fatalf("unexpected stream %q", row.Stream)
	}
	if row.Time != "2026-03-24T06:07:40.308248751Z" {
		t.Fatalf("unexpected time %q", row.Time)
	}
	if row.MsgJSON == nil || row.MsgJSON["log"] != "synthetic log line Lorum Ipsum" {
		t.Fatalf("unexpected msg_json %+v", row.MsgJSON)
	}
}

func TestParseLogCollectionBatch(t *testing.T) {
	body := []byte("{\"log\":\"hello\",\"container_name\":\"/web\",\"container_id\":\"abc123\",\"timestamp\":\"2026-03-20T01:02:03Z\"}\n")
	records, err := parseLogCollectionBatch(body, "docker.web")
	if err != nil {
		t.Fatalf("parseLogCollectionBatch failed: %v", err)
	}
	if len(records) != 1 {
		t.Fatalf("expected 1 record, got %d", len(records))
	}
	if records[0].Tag != "docker.web" {
		t.Fatalf("unexpected tag %q", records[0].Tag)
	}
	if records[0].Record["container_name"] != "/web" {
		t.Fatalf("unexpected payload %+v", records[0].Record)
	}
}

func TestSendOTLPRowsPostsOTLPJSON(t *testing.T) {
	var gotPath string
	var gotContentType string
	var gotPayload map[string]any

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotContentType = r.Header.Get("Content-Type")
		body, _ := io.ReadAll(r.Body)
		if err := json.Unmarshal(body, &gotPayload); err != nil {
			t.Fatalf("unmarshal payload: %v", err)
		}
		w.WriteHeader(http.StatusAccepted)
	}))
	defer srv.Close()

	service := &logCollectionService{
		client:  srv.Client(),
		otlpURL: srv.URL + "/v1/logs",
	}
	err := service.sendOTLPRows([]normalizedLogRow{{
		Time:             "2026-03-20T01:02:03Z",
		Msg:              "hello",
		MsgJSON:          map[string]any{"log": "hello"},
		ContainerKey:     "host-a:web",
		ContainerName:    "web",
		HeraldID:         "host-a",
		HeraldName:       "host-a",
		ServiceName:      "web",
		ServiceNamespace: "unicron.herald",
	}})
	if err != nil {
		t.Fatalf("sendOTLPRows failed: %v", err)
	}
	if gotPath != "/v1/logs" {
		t.Fatalf("unexpected path %q", gotPath)
	}
	if gotContentType != "application/json" {
		t.Fatalf("unexpected content type %q", gotContentType)
	}

	resourceLogs, ok := gotPayload["resourceLogs"].([]any)
	if !ok || len(resourceLogs) != 1 {
		t.Fatalf("unexpected resourceLogs payload: %+v", gotPayload)
	}
	first, ok := resourceLogs[0].(map[string]any)
	if !ok {
		t.Fatalf("unexpected first resourceLog: %+v", resourceLogs[0])
	}
	scopeLogs, ok := first["scopeLogs"].([]any)
	if !ok || len(scopeLogs) != 1 {
		t.Fatalf("unexpected scopeLogs payload: %+v", first)
	}
	scopeLog, ok := scopeLogs[0].(map[string]any)
	if !ok {
		t.Fatalf("unexpected scopeLog payload: %+v", scopeLogs[0])
	}
	logRecords, ok := scopeLog["logRecords"].([]any)
	if !ok || len(logRecords) != 1 {
		t.Fatalf("unexpected logRecords payload: %+v", scopeLog)
	}
	logRecord, ok := logRecords[0].(map[string]any)
	if !ok {
		t.Fatalf("unexpected logRecord payload: %+v", logRecords[0])
	}
	body, ok := logRecord["body"].(map[string]any)
	if !ok || body["stringValue"] != "hello" {
		t.Fatalf("unexpected log body: %+v", logRecord["body"])
	}
}

func TestProcessBatchTeesOnlyActiveFastLaneRows(t *testing.T) {
	var otlpRequests int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		otlpRequests++
		w.WriteHeader(http.StatusAccepted)
	}))
	defer srv.Close()

	state := NewMonitoringState("")
	state.SetEnabled("web", "example/app:v1", true)
	up := newTestUpstreamClient(8, 8, 10*time.Millisecond)
	service := &logCollectionService{
		hostID:           "host-a",
		heraldName:       "host-a",
		state:            state,
		planCache:        newLogCollectionPlanCache(time.Minute),
		client:           srv.Client(),
		otlpURL:          srv.URL + "/v1/logs",
		activeFastTail:   make(map[string]struct{}),
		fastLaneSender:   up,
		requireMonitored: true,
		sendOTLP:         true,
	}
	service.planCache.store(logCollectionPlan{
		Key:               ContainerKey{Name: "web", Image: "example/app:v1"},
		ContainerName:     "web",
		DockerContainerID: "abc123",
		Image:             "example/app:v1",
		LogPath:           "/var/lib/docker/containers/web/web-json.log",
		SourceMode:        logSourceTail,
	})

	records := []logCollectionResolvedRecord{{
		Tag:       "docker.web",
		Timestamp: "2026-03-21T12:00:00Z",
		Record: map[string]any{
			"log":          "hello world",
			"stream":       "stdout",
			"container_id": "abc123",
		},
	}}

	accepted, dropped, err := service.processBatch(records)
	if err != nil {
		t.Fatalf("processBatch without fast lane failed: %v", err)
	}
	if accepted != 1 || dropped != 0 {
		t.Fatalf("unexpected batch result accepted=%d dropped=%d", accepted, dropped)
	}
	if otlpRequests != 1 {
		t.Fatalf("expected one OTLP request, got %d", otlpRequests)
	}
	select {
	case msg := <-up.telemetry:
		t.Fatalf("expected no fast-lane frame before activation, got %+v", msg)
	default:
	}

	service.setFastTailActive("host-a:web", true)
	accepted, dropped, err = service.processBatch(records)
	if err != nil {
		t.Fatalf("processBatch with fast lane failed: %v", err)
	}
	if accepted != 1 || dropped != 0 {
		t.Fatalf("unexpected batch result accepted=%d dropped=%d", accepted, dropped)
	}
	if otlpRequests != 2 {
		t.Fatalf("expected two OTLP requests after second batch, got %d", otlpRequests)
	}

	env := readTelemetryEnvelope(t, up)
	if env.Type != "fast_logs_frame" {
		t.Fatalf("unexpected telemetry envelope type %q", env.Type)
	}
	var payload fastLogsFramePayload
	if err := json.Unmarshal(env.Data, &payload); err != nil {
		t.Fatalf("unmarshal fast lane payload: %v", err)
	}
	if payload.ContainerKey != "host-a:web" {
		t.Fatalf("unexpected container key %q", payload.ContainerKey)
	}
	if payload.Row.Msg != "hello world" {
		t.Fatalf("unexpected fast lane row %+v", payload.Row)
	}
}

func TestReconcileLogCollectionPlansEmitsOnlyTransitions(t *testing.T) {
	up := newTestUpstreamClient(8, 8, 10*time.Millisecond)
	tm := &TelemetryManager{
		hostID:    "host-a",
		upstream:  up,
		logStates: make(map[string]logCollectionState),
	}

	unavailable := []logCollectionPlan{{
		Key:               ContainerKey{Name: "web", Image: "example/app:v1"},
		ContainerName:     "web",
		DockerContainerID: "abc123",
		Image:             "example/app:v1",
		SourceMode:        logSourceUnavailable,
		Issue:             logIssueMissingLogPath,
	}}

	tm.reconcileLogCollectionPlans(unavailable)
	first := readCriticalEnvelope(t, up)
	if first.Type != "log_collection_state_changed" {
		t.Fatalf("unexpected event type %q", first.Type)
	}
	var firstPayload logCollectionStateChangedPayload
	if err := json.Unmarshal(first.Data, &firstPayload); err != nil {
		t.Fatalf("unmarshal first payload: %v", err)
	}
	if firstPayload.LogCollectionStatus != "unavailable" || firstPayload.LogCollectionIssue != "missing_log_path" {
		t.Fatalf("unexpected first payload %+v", firstPayload)
	}

	tm.reconcileLogCollectionPlans(unavailable)
	select {
	case msg := <-up.critical:
		t.Fatalf("expected no duplicate event, got %+v", msg)
	default:
	}

	healthy := []logCollectionPlan{{
		Key:               ContainerKey{Name: "web", Image: "example/app:v1"},
		ContainerName:     "web",
		DockerContainerID: "abc123",
		Image:             "example/app:v1",
		LogPath:           "/var/lib/docker/containers/web/web-json.log",
		SourceMode:        logSourceTail,
	}}
	tm.reconcileLogCollectionPlans(healthy)
	second := readCriticalEnvelope(t, up)
	var secondPayload logCollectionStateChangedPayload
	if err := json.Unmarshal(second.Data, &secondPayload); err != nil {
		t.Fatalf("unmarshal second payload: %v", err)
	}
	if secondPayload.LogCollectionStatus != "ok" || secondPayload.LogCollectionIssue != "" {
		t.Fatalf("unexpected second payload %+v", secondPayload)
	}

	tm.reconcileLogCollectionPlans(unavailable)
	_ = readCriticalEnvelope(t, up)
	tm.reconcileLogCollectionPlans(nil)
	third := readCriticalEnvelope(t, up)
	var thirdPayload logCollectionStateChangedPayload
	if err := json.Unmarshal(third.Data, &thirdPayload); err != nil {
		t.Fatalf("unmarshal third payload: %v", err)
	}
	if thirdPayload.LogCollectionStatus != "ok" {
		t.Fatalf("expected disabled-monitoring clear event, got %+v", thirdPayload)
	}
}

func TestSeedHistoryParsesFramedDockerLogs(t *testing.T) {
	previousLogPathAccessible := logPathAccessible
	logPathAccessible = func(path string) bool { return true }
	defer func() {
		logPathAccessible = previousLogPathAccessible
	}()

	up := newTestUpstreamClient(8, 8, 10*time.Millisecond)
	service := &logCollectionService{
		hostID:         "host-a",
		heraldName:     "host-a",
		activeFastTail: map[string]struct{}{"host-a:web": {}},
		fastLaneSender: up,
		inspector: fakeDockerInspector{
			inspect: func(ctx context.Context, ref string) (types.ContainerJSON, error) {
				return testContainerJSONWithTTY("web", "example/app:v1", "json-file", "", "/var/lib/docker/containers/web/web-json.log", false), nil
			},
			logs: func(ctx context.Context, ref string, options container.LogsOptions) (io.ReadCloser, error) {
				payload := []byte("2026-03-24T12:00:00Z hello framed\n")
				frame := append([]byte{1, 0, 0, 0, 0, 0, 0, byte(len(payload))}, payload...)
				return io.NopCloser(strings.NewReader(string(frame))), nil
			},
		},
	}

	if err := service.seedHistory(context.Background(), "host-a:web", "", ""); err != nil {
		t.Fatalf("seedHistory failed: %v", err)
	}

	env := readTelemetryEnvelope(t, up)
	if env.Type != "fast_logs_frame" {
		t.Fatalf("unexpected telemetry envelope type %q", env.Type)
	}
	var payload fastLogsFramePayload
	if err := json.Unmarshal(env.Data, &payload); err != nil {
		t.Fatalf("unmarshal fast lane payload: %v", err)
	}
	if payload.Row.Msg != "hello framed" {
		t.Fatalf("unexpected framed row %+v", payload.Row)
	}
	if payload.Row.Stream != "stdout" {
		t.Fatalf("unexpected stream %q", payload.Row.Stream)
	}
}

func TestSeedHistoryParsesTTYLogsWithoutFrameHeaders(t *testing.T) {
	previousLogPathAccessible := logPathAccessible
	logPathAccessible = func(path string) bool { return true }
	defer func() {
		logPathAccessible = previousLogPathAccessible
	}()

	up := newTestUpstreamClient(8, 8, 10*time.Millisecond)
	service := &logCollectionService{
		hostID:         "host-a",
		heraldName:     "host-a",
		activeFastTail: map[string]struct{}{"host-a:web": {}},
		fastLaneSender: up,
		inspector: fakeDockerInspector{
			inspect: func(ctx context.Context, ref string) (types.ContainerJSON, error) {
				return testContainerJSONWithTTY("web", "example/app:v1", "json-file", "", "/var/lib/docker/containers/web/web-json.log", true), nil
			},
			logs: func(ctx context.Context, ref string, options container.LogsOptions) (io.ReadCloser, error) {
				return io.NopCloser(strings.NewReader("2026-03-24T12:00:00Z hello tty\n")), nil
			},
		},
	}

	if err := service.seedHistory(context.Background(), "host-a:web", "", ""); err != nil {
		t.Fatalf("seedHistory failed: %v", err)
	}

	env := readTelemetryEnvelope(t, up)
	if env.Type != "fast_logs_frame" {
		t.Fatalf("unexpected telemetry envelope type %q", env.Type)
	}
	var payload fastLogsFramePayload
	if err := json.Unmarshal(env.Data, &payload); err != nil {
		t.Fatalf("unmarshal fast lane payload: %v", err)
	}
	if payload.Row.Msg != "hello tty" {
		t.Fatalf("unexpected tty row %+v", payload.Row)
	}
	if payload.Row.Stream != "" {
		t.Fatalf("expected merged tty stream, got %q", payload.Row.Stream)
	}
}

func TestSeedHistoryWorksWhenTailPlanIsUnavailable(t *testing.T) {
	previousLogPathAccessible := logPathAccessible
	logPathAccessible = func(path string) bool { return false }
	defer func() {
		logPathAccessible = previousLogPathAccessible
	}()

	up := newTestUpstreamClient(8, 8, 10*time.Millisecond)
	service := &logCollectionService{
		hostID:         "host-a",
		heraldName:     "host-a",
		activeFastTail: map[string]struct{}{"host-a:web": {}},
		fastLaneSender: up,
		inspector: fakeDockerInspector{
			inspect: func(ctx context.Context, ref string) (types.ContainerJSON, error) {
				return testContainerJSONWithTTY("web", "example/app:v1", "json-file", "", "/var/lib/docker/containers/web/web-json.log", false), nil
			},
			logs: func(ctx context.Context, ref string, options container.LogsOptions) (io.ReadCloser, error) {
				payload := []byte("2026-03-24T12:00:00Z hello history\n")
				frame := append([]byte{1, 0, 0, 0, 0, 0, 0, byte(len(payload))}, payload...)
				return io.NopCloser(strings.NewReader(string(frame))), nil
			},
		},
	}

	if err := service.seedHistory(context.Background(), "host-a:web", "", ""); err != nil {
		t.Fatalf("seedHistory should not require a healthy tail plan: %v", err)
	}

	env := readTelemetryEnvelope(t, up)
	if env.Type != "fast_logs_frame" {
		t.Fatalf("unexpected telemetry envelope type %q", env.Type)
	}
	var payload fastLogsFramePayload
	if err := json.Unmarshal(env.Data, &payload); err != nil {
		t.Fatalf("unmarshal fast lane payload: %v", err)
	}
	if payload.Row.Msg != "hello history" {
		t.Fatalf("unexpected history row %+v", payload.Row)
	}
}

func readCriticalEnvelope(t *testing.T, up *upstreamClient) upstreamEnvelope {
	t.Helper()
	select {
	case msg := <-up.critical:
		var env upstreamEnvelope
		if err := json.Unmarshal(msg.payload, &env); err != nil {
			t.Fatalf("unmarshal envelope: %v", err)
		}
		return env
	case <-time.After(200 * time.Millisecond):
		t.Fatal("timed out waiting for critical envelope")
		return upstreamEnvelope{}
	}
}

func readTelemetryEnvelope(t *testing.T, up *upstreamClient) upstreamEnvelope {
	t.Helper()
	select {
	case msg := <-up.telemetry:
		var env upstreamEnvelope
		if err := json.Unmarshal(msg.payload, &env); err != nil {
			t.Fatalf("unmarshal envelope: %v", err)
		}
		return env
	case <-time.After(200 * time.Millisecond):
		t.Fatal("timed out waiting for telemetry envelope")
		return upstreamEnvelope{}
	}
}
