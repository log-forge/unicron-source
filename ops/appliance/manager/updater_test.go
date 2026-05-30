package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

type fakeDockerDaemon struct {
	socket string
	mu     sync.Mutex
	pulls  int
}

type fakeDockerOptions struct {
	currentImage   string
	currentImageID string
	latestImageID  string
	pullError      string
}

func startFakeDockerDaemon(t *testing.T, opts fakeDockerOptions) *fakeDockerDaemon {
	t.Helper()

	socket := filepath.Join(t.TempDir(), "docker.sock")
	listener, err := net.Listen("unix", socket)
	if err != nil {
		t.Fatal(err)
	}

	daemon := &fakeDockerDaemon{socket: socket}
	containerName := "unicron-appliance"
	if opts.latestImageID == "" {
		opts.latestImageID = opts.currentImageID
	}

	server := &http.Server{
		Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			switch {
			case r.Method == http.MethodGet && r.URL.Path == "/_ping":
				_, _ = w.Write([]byte("OK"))
			case r.Method == http.MethodGet && r.URL.Path == "/containers/"+containerName+"/json":
				writeJSON(w, http.StatusOK, dockerContainerInspect{
					ID:    "container-123",
					Name:  "/" + containerName,
					Image: opts.currentImageID,
					Config: map[string]any{
						"Image": opts.currentImage,
					},
				})
			case r.Method == http.MethodPost && r.URL.Path == "/images/create":
				daemon.mu.Lock()
				daemon.pulls++
				daemon.mu.Unlock()
				if opts.pullError != "" {
					_, _ = fmt.Fprintf(w, "{\"error\":%q}\n", opts.pullError)
					return
				}
				_, _ = w.Write([]byte("{\"status\":\"ok\"}\n"))
			case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/images/") && strings.HasSuffix(r.URL.Path, "/json"):
				writeJSON(w, http.StatusOK, dockerImageInspect{ID: opts.latestImageID})
			default:
				http.NotFound(w, r)
			}
		}),
	}

	go func() {
		_ = server.Serve(listener)
	}()
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = server.Shutdown(ctx)
		_ = listener.Close()
	})

	return daemon
}

func (d *fakeDockerDaemon) pullCount() int {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.pulls
}

func newTestUpdateService(t *testing.T, daemon *fakeDockerDaemon) *updateService {
	t.Helper()
	return newUpdateService(RuntimeConfig{
		DockerSocket:           daemon.socket,
		UpdateStateFile:        filepath.Join(t.TempDir(), "state.json"),
		UpdateInterval:         time.Hour,
		ApplianceContainerName: "unicron-appliance",
	})
}

func newTestUpdateConfig(t *testing.T, daemon *fakeDockerDaemon) RuntimeConfig {
	t.Helper()
	return RuntimeConfig{
		DockerSocket:           daemon.socket,
		UpdateStateFile:        filepath.Join(t.TempDir(), "state.json"),
		UpdateInterval:         time.Hour,
		ApplianceContainerName: "unicron-appliance",
	}
}

func TestPersistedAutoUpdateFalseIsNormalizedToTrue(t *testing.T) {
	daemon := startFakeDockerDaemon(t, fakeDockerOptions{
		currentImage:   "logforge/unicron:v1.2.3",
		currentImageID: "sha256:current",
	})
	cfg := newTestUpdateConfig(t, daemon)
	if err := os.MkdirAll(filepath.Dir(cfg.UpdateStateFile), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(cfg.UpdateStateFile, []byte(`{"auto_update_enabled":false,"check_state":"ok"}`), 0o600); err != nil {
		t.Fatal(err)
	}

	service := newUpdateService(cfg)
	if err := service.loadState(); err != nil {
		t.Fatal(err)
	}

	status := service.publicStatus(context.Background())
	if !status.AutoUpdateEnabled {
		t.Fatal("status auto_update_enabled = false, want true")
	}
	body, err := os.ReadFile(cfg.UpdateStateFile)
	if err != nil {
		t.Fatal(err)
	}
	var persisted applianceUpdateState
	if err := json.Unmarshal(body, &persisted); err != nil {
		t.Fatal(err)
	}
	if !persisted.AutoUpdateEnabled {
		t.Fatalf("persisted auto_update_enabled = false after load; state=%s", body)
	}
}

func TestRunAutoUpdateIgnoresPersistedAutoUpdateDisabled(t *testing.T) {
	daemon := startFakeDockerDaemon(t, fakeDockerOptions{
		currentImage:   "logforge/unicron:v1.2.3",
		currentImageID: "sha256:same",
		latestImageID:  "sha256:same",
	})
	cfg := newTestUpdateConfig(t, daemon)
	if err := os.MkdirAll(filepath.Dir(cfg.UpdateStateFile), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(cfg.UpdateStateFile, []byte(`{"auto_update_enabled":false}`), 0o600); err != nil {
		t.Fatal(err)
	}
	service := newUpdateService(cfg)
	if err := service.loadState(); err != nil {
		t.Fatal(err)
	}

	service.runAutoUpdate(context.Background())

	if daemon.pullCount() != 1 {
		t.Fatalf("pulls = %d, want 1", daemon.pullCount())
	}
	if !service.publicStatus(context.Background()).AutoUpdateEnabled {
		t.Fatal("auto_update_enabled = false after auto-update")
	}
}

func TestSettingsEndpointIgnoresDisableAutoUpdate(t *testing.T) {
	daemon := startFakeDockerDaemon(t, fakeDockerOptions{
		currentImage:   "logforge/unicron:v1.2.3",
		currentImageID: "sha256:same",
	})
	service := newTestUpdateService(t, daemon)

	request := httptest.NewRequest(http.MethodPut, "/settings", strings.NewReader(`{"auto_update_enabled":false}`))
	recorder := httptest.NewRecorder()
	service.handleSettings(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("status code = %d, want %d: %s", recorder.Code, http.StatusOK, recorder.Body.String())
	}
	var status applianceUpdateStatus
	if err := json.Unmarshal(recorder.Body.Bytes(), &status); err != nil {
		t.Fatal(err)
	}
	if !status.AutoUpdateEnabled {
		t.Fatalf("settings response auto_update_enabled = false; body=%s", recorder.Body.String())
	}
}

func TestLocalOnlyUpdateCheckReportsNoSourceAndHealthyUpdater(t *testing.T) {
	daemon := startFakeDockerDaemon(t, fakeDockerOptions{
		currentImage:   "unicron-appliance:latest",
		currentImageID: "sha256:local",
	})
	service := newTestUpdateService(t, daemon)

	if err := service.checkForUpdate(context.Background()); err != nil {
		t.Fatal(err)
	}

	status := service.publicStatus(context.Background())
	if status.UpdaterHealth != "ok" {
		t.Fatalf("updater health = %q, want ok", status.UpdaterHealth)
	}
	if status.Status != updateCheckStateNoSource {
		t.Fatalf("status = %q, want %q", status.Status, updateCheckStateNoSource)
	}
	if status.CheckState != updateCheckStateNoSource {
		t.Fatalf("check state = %q, want %q", status.CheckState, updateCheckStateNoSource)
	}
	if status.LastError != localUpdateSourceMessage {
		t.Fatalf("last error = %q, want %q", status.LastError, localUpdateSourceMessage)
	}
	if status.UpdateAvailable {
		t.Fatal("local-only image should not report an update")
	}
	if daemon.pullCount() != 0 {
		t.Fatalf("pulls = %d, want 0", daemon.pullCount())
	}
}

func TestRealPullFailureReportsCheckFailedAndHealthyUpdater(t *testing.T) {
	daemon := startFakeDockerDaemon(t, fakeDockerOptions{
		currentImage:   "logforge/unicron:v1.2.3",
		currentImageID: "sha256:current",
		pullError:      "pull access denied",
	})
	service := newTestUpdateService(t, daemon)

	if err := service.checkForUpdate(context.Background()); err == nil {
		t.Fatal("checkForUpdate returned nil, want pull error")
	}

	status := service.publicStatus(context.Background())
	if status.UpdaterHealth != "ok" {
		t.Fatalf("updater health = %q, want ok", status.UpdaterHealth)
	}
	if status.Status != updateCheckStateFailed {
		t.Fatalf("status = %q, want %q", status.Status, updateCheckStateFailed)
	}
	if status.CheckState != updateCheckStateFailed {
		t.Fatalf("check state = %q, want %q", status.CheckState, updateCheckStateFailed)
	}
	if !strings.Contains(status.LastError, "update check failed for logforge/unicron:latest") || !strings.Contains(status.LastError, "pull access denied") {
		t.Fatalf("last error did not include clear check failure: %q", status.LastError)
	}
	if status.UpdateAvailable {
		t.Fatal("failed pull should not report an update")
	}
}

func TestSuccessfulSameImageCheckReportsHealthyNoUpdate(t *testing.T) {
	daemon := startFakeDockerDaemon(t, fakeDockerOptions{
		currentImage:   "logforge/unicron:v1.2.3",
		currentImageID: "sha256:same",
		latestImageID:  "sha256:same",
	})
	service := newTestUpdateService(t, daemon)

	if err := service.checkForUpdate(context.Background()); err != nil {
		t.Fatal(err)
	}

	status := service.publicStatus(context.Background())
	if status.Status != "ok" {
		t.Fatalf("status = %q, want ok", status.Status)
	}
	if status.UpdaterHealth != "ok" {
		t.Fatalf("updater health = %q, want ok", status.UpdaterHealth)
	}
	if status.CheckState != updateCheckStateOK {
		t.Fatalf("check state = %q, want %q", status.CheckState, updateCheckStateOK)
	}
	if status.LastError != "" {
		t.Fatalf("last error = %q, want empty", status.LastError)
	}
	if status.UpdateAvailable {
		t.Fatal("same image should not report an update")
	}
}

func TestUpdateAvailableCheckStillReportsUpdateAvailable(t *testing.T) {
	daemon := startFakeDockerDaemon(t, fakeDockerOptions{
		currentImage:   "logforge/unicron:v1.2.3",
		currentImageID: "sha256:current",
		latestImageID:  "sha256:latest",
	})
	service := newTestUpdateService(t, daemon)

	if err := service.checkForUpdate(context.Background()); err != nil {
		t.Fatal(err)
	}

	status := service.publicStatus(context.Background())
	if status.Status != "ok" {
		t.Fatalf("status = %q, want ok", status.Status)
	}
	if status.CheckState != updateCheckStateOK {
		t.Fatalf("check state = %q, want %q", status.CheckState, updateCheckStateOK)
	}
	if !status.UpdateAvailable {
		body, _ := json.Marshal(status)
		t.Fatalf("update_available = false, want true; status=%s", body)
	}
	if status.TrackedImage != "logforge/unicron:latest" {
		t.Fatalf("tracked image = %q", status.TrackedImage)
	}
}
