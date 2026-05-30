package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

type applianceUpdateState struct {
	AutoUpdateEnabled bool           `json:"auto_update_enabled"`
	CheckState        string         `json:"check_state,omitempty"`
	LastCheck         *time.Time     `json:"last_check,omitempty"`
	LastApply         *time.Time     `json:"last_apply,omitempty"`
	LastError         string         `json:"last_error,omitempty"`
	CurrentImage      string         `json:"current_image,omitempty"`
	CurrentImageID    string         `json:"current_image_id,omitempty"`
	TrackedImage      string         `json:"tracked_image,omitempty"`
	LatestImage       string         `json:"latest_image,omitempty"`
	LatestImageID     string         `json:"latest_image_id,omitempty"`
	UpdateAvailable   bool           `json:"update_available"`
	RollbackImage     string         `json:"rollback_image,omitempty"`
	RollbackContainer string         `json:"rollback_container,omitempty"`
	RollbackConfig    map[string]any `json:"rollback_config,omitempty"`
}

type applianceUpdateStatus struct {
	Status            string     `json:"status"`
	UpdaterHealth     string     `json:"updater_health"`
	AutoUpdateEnabled bool       `json:"auto_update_enabled"`
	CheckState        string     `json:"check_state"`
	InProgress        bool       `json:"in_progress"`
	LastCheck         *time.Time `json:"last_check,omitempty"`
	LastApply         *time.Time `json:"last_apply,omitempty"`
	LastError         string     `json:"last_error,omitempty"`
	CurrentImage      string     `json:"current_image,omitempty"`
	CurrentImageID    string     `json:"current_image_id,omitempty"`
	TrackedImage      string     `json:"tracked_image,omitempty"`
	LatestImage       string     `json:"latest_image,omitempty"`
	LatestImageID     string     `json:"latest_image_id,omitempty"`
	UpdateAvailable   bool       `json:"update_available"`
	RollbackImage     string     `json:"rollback_image,omitempty"`
	RollbackAvailable bool       `json:"rollback_available"`
}

type applianceUpdateSettings struct {
	AutoUpdateEnabled bool `json:"auto_update_enabled"`
}

const (
	updateCheckStateUnknown  = "unknown"
	updateCheckStateOK       = "ok"
	updateCheckStateFailed   = "check_failed"
	updateCheckStateNoSource = "no_update_source"
)

const localUpdateSourceMessage = "Unicron updates are unavailable because this container was started from a local image. Restart the appliance with the official Docker Hub image logforge/unicron:latest to receive updates."

type updateService struct {
	cfg    RuntimeConfig
	docker *dockerClient

	stateMu sync.Mutex
	state   applianceUpdateState

	jobMu     sync.Mutex
	jobActive bool
}

func runApplianceUpdater(cfg RuntimeConfig) error {
	service := newUpdateService(cfg)
	if err := service.loadState(); err != nil {
		return err
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go service.autoUpdateLoop(ctx)

	server := &http.Server{
		Addr:              cfg.UpdaterAddr,
		Handler:           service.routes(),
		ReadHeaderTimeout: 5 * time.Second,
	}
	logf("APPLIANCE-UPDATER", "Listening on http://%s", cfg.UpdaterAddr)
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}

func newUpdateService(cfg RuntimeConfig) *updateService {
	return &updateService{
		cfg:    cfg,
		docker: newDockerClient(cfg.DockerSocket),
		state:  defaultUpdateState(),
	}
}

func defaultUpdateState() applianceUpdateState {
	return applianceUpdateState{AutoUpdateEnabled: true}
}

func (s *updateService) routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/status", s.handleStatus)
	mux.HandleFunc("/check", s.handleCheck)
	mux.HandleFunc("/apply", s.handleApply)
	mux.HandleFunc("/rollback", s.handleRollback)
	mux.HandleFunc("/settings", s.handleSettings)
	return mux
}

func (s *updateService) handleStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeMethodNotAllowed(w)
		return
	}
	writeJSON(w, http.StatusOK, s.publicStatus(r.Context()))
}

func (s *updateService) handleCheck(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeMethodNotAllowed(w)
		return
	}
	s.runJobHTTP(w, r, "check", func(ctx context.Context) error {
		return s.checkForUpdate(ctx)
	})
}

func (s *updateService) handleApply(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeMethodNotAllowed(w)
		return
	}
	s.runJobHTTP(w, r, "apply", func(ctx context.Context) error {
		return s.applyLatest(ctx)
	})
}

func (s *updateService) handleRollback(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeMethodNotAllowed(w)
		return
	}
	s.runJobHTTP(w, r, "rollback", func(ctx context.Context) error {
		return s.rollback(ctx)
	})
}

func (s *updateService) handleSettings(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut {
		writeMethodNotAllowed(w)
		return
	}
	var body applianceUpdateSettings
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}
	_ = body
	writeJSON(w, http.StatusOK, s.publicStatus(r.Context()))
}

func (s *updateService) runJobHTTP(w http.ResponseWriter, r *http.Request, name string, fn func(context.Context) error) {
	if !s.beginJob() {
		writeJSON(w, http.StatusConflict, map[string]string{"error": "another appliance update job is already running"})
		return
	}
	defer s.endJob()

	ctx, cancel := dockerContext(r.Context(), 20*time.Minute)
	defer cancel()
	if err := fn(ctx); err != nil {
		logf("APPLIANCE-UPDATER", "%s failed: %v", name, err)
		s.recordError(err)
	}
	writeJSON(w, http.StatusOK, s.publicStatus(r.Context()))
}

func (s *updateService) beginJob() bool {
	s.jobMu.Lock()
	defer s.jobMu.Unlock()
	if s.jobActive {
		return false
	}
	s.jobActive = true
	return true
}

func (s *updateService) endJob() {
	s.jobMu.Lock()
	defer s.jobMu.Unlock()
	s.jobActive = false
}

func (s *updateService) jobInProgress() bool {
	s.jobMu.Lock()
	defer s.jobMu.Unlock()
	return s.jobActive
}

func (s *updateService) publicStatus(ctx context.Context) applianceUpdateStatus {
	state := s.copyState()
	health := "ok"
	lastError := state.LastError
	healthError := ""
	checkState := normalizedUpdateCheckState(state.CheckState, lastError)
	if checkState == updateCheckStateFailed && s.isLocalOnlyUpdateRef(state.CurrentImage, state.TrackedImage) {
		checkState = updateCheckStateNoSource
		lastError = localUpdateSourceMessage
	}
	if err := dockerSocketExists(s.cfg.DockerSocket); err != nil {
		health = "degraded"
		healthError = err.Error()
	} else {
		pingCtx, cancel := dockerContext(ctx, time.Second)
		if err := s.docker.ping(pingCtx); err != nil {
			health = "degraded"
			healthError = err.Error()
		}
		cancel()
	}
	if healthError != "" {
		lastError = healthError
	}
	inProgress := s.jobInProgress()
	status := "ok"
	if health != "ok" {
		status = "degraded"
	} else if checkState == updateCheckStateFailed || checkState == updateCheckStateNoSource {
		status = checkState
	}
	if inProgress {
		status = "updating"
	}
	return applianceUpdateStatus{
		Status:            status,
		UpdaterHealth:     health,
		AutoUpdateEnabled: true,
		CheckState:        checkState,
		InProgress:        inProgress,
		LastCheck:         state.LastCheck,
		LastApply:         state.LastApply,
		LastError:         lastError,
		CurrentImage:      state.CurrentImage,
		CurrentImageID:    state.CurrentImageID,
		TrackedImage:      state.TrackedImage,
		LatestImage:       state.LatestImage,
		LatestImageID:     state.LatestImageID,
		UpdateAvailable:   state.UpdateAvailable,
		RollbackImage:     state.RollbackImage,
		RollbackAvailable: state.RollbackImage != "" && (state.RollbackContainer != "" || len(state.RollbackConfig) > 0),
	}
}

func (s *updateService) loadState() error {
	state := defaultUpdateState()
	body, err := os.ReadFile(s.cfg.UpdateStateFile)
	if err != nil {
		if !os.IsNotExist(err) {
			return err
		}
		s.state = state
		return s.saveStateLocked()
	}
	if err := json.Unmarshal(body, &state); err != nil {
		return err
	}
	normalized := normalizeUpdateState(state)
	s.state = normalized
	if !updateStatesEqual(state, normalized) {
		return s.saveStateLocked()
	}
	return nil
}

func (s *updateService) copyState() applianceUpdateState {
	s.stateMu.Lock()
	defer s.stateMu.Unlock()
	return cloneUpdateState(s.state)
}

func (s *updateService) updateState(mut func(applianceUpdateState) applianceUpdateState) {
	s.stateMu.Lock()
	defer s.stateMu.Unlock()
	s.state = normalizeUpdateState(mut(cloneUpdateState(s.state)))
	if err := s.saveStateLocked(); err != nil {
		logf("APPLIANCE-UPDATER", "Failed to save update state: %v", err)
	}
}

func (s *updateService) recordError(err error) {
	if err == nil {
		return
	}
	s.updateState(func(state applianceUpdateState) applianceUpdateState {
		state.LastError = err.Error()
		state.CheckState = updateCheckStateFailed
		return state
	})
}

func (s *updateService) saveStateLocked() error {
	s.state = normalizeUpdateState(s.state)
	body, err := json.MarshalIndent(s.state, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(s.cfg.UpdateStateFile), 0o755); err != nil {
		return err
	}
	tmp := s.cfg.UpdateStateFile + ".tmp"
	if err := os.WriteFile(tmp, body, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, s.cfg.UpdateStateFile)
}

func cloneUpdateState(state applianceUpdateState) applianceUpdateState {
	cloned := state
	cloned.RollbackConfig = cloneMap(state.RollbackConfig)
	return cloned
}

func normalizeUpdateState(state applianceUpdateState) applianceUpdateState {
	state.AutoUpdateEnabled = true
	return state
}

func updateStatesEqual(a, b applianceUpdateState) bool {
	aBody, aErr := json.Marshal(a)
	bBody, bErr := json.Marshal(b)
	return aErr == nil && bErr == nil && string(aBody) == string(bBody)
}

func (s *updateService) autoUpdateLoop(ctx context.Context) {
	timer := time.NewTimer(3 * time.Second)
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-timer.C:
			s.runAutoUpdate(ctx)
			timer.Reset(s.cfg.UpdateInterval)
		}
	}
}

func (s *updateService) runAutoUpdate(ctx context.Context) {
	if !s.beginJob() {
		return
	}
	defer s.endJob()
	jobCtx, cancel := dockerContext(ctx, 20*time.Minute)
	defer cancel()
	if err := s.applyLatest(jobCtx); err != nil {
		logf("APPLIANCE-UPDATER", "auto-update failed: %v", err)
		s.recordError(err)
	}
}

func (s *updateService) checkForUpdate(ctx context.Context) error {
	if err := dockerSocketExists(s.cfg.DockerSocket); err != nil {
		return err
	}
	current, err := s.currentContainer(ctx)
	if err != nil {
		return err
	}
	currentRef := containerConfigString(current, "Image")
	trackedRef := s.trackedImageRef(currentRef)
	if trackedRef == "" {
		return fmt.Errorf("could not resolve an update image reference from current image %q", currentRef)
	}
	now := time.Now().UTC()
	s.updateState(func(state applianceUpdateState) applianceUpdateState {
		state.CurrentImage = currentRef
		state.CurrentImageID = current.Image
		state.TrackedImage = trackedRef
		state.LastCheck = &now
		return state
	})

	if s.isLocalOnlyUpdateRef(currentRef, trackedRef) {
		s.updateState(func(state applianceUpdateState) applianceUpdateState {
			state.CurrentImage = currentRef
			state.CurrentImageID = current.Image
			state.TrackedImage = trackedRef
			state.LatestImage = ""
			state.LatestImageID = ""
			state.UpdateAvailable = false
			state.LastCheck = &now
			state.LastError = localUpdateSourceMessage
			state.CheckState = updateCheckStateNoSource
			return state
		})
		return nil
	}

	if err := s.docker.pullImage(ctx, trackedRef); err != nil {
		checkErr := fmt.Errorf("update check failed for %s: %w", trackedRef, err)
		s.recordCheckFailure(now, currentRef, current.Image, trackedRef, checkErr)
		return checkErr
	}
	latest, err := s.docker.inspectImage(ctx, trackedRef)
	if err != nil {
		checkErr := fmt.Errorf("update check failed for %s: %w", trackedRef, err)
		s.recordCheckFailure(now, currentRef, current.Image, trackedRef, checkErr)
		return checkErr
	}
	updateAvailable := !sameImageID(current.Image, latest.ID)
	s.updateState(func(state applianceUpdateState) applianceUpdateState {
		state.CurrentImage = currentRef
		state.CurrentImageID = current.Image
		state.TrackedImage = trackedRef
		state.LatestImage = trackedRef
		state.LatestImageID = latest.ID
		state.UpdateAvailable = updateAvailable
		state.LastCheck = &now
		state.LastError = ""
		state.CheckState = updateCheckStateOK
		return state
	})
	return nil
}

func (s *updateService) recordCheckFailure(now time.Time, currentRef, currentImageID, trackedRef string, err error) {
	s.updateState(func(state applianceUpdateState) applianceUpdateState {
		state.CurrentImage = currentRef
		state.CurrentImageID = currentImageID
		state.TrackedImage = trackedRef
		state.UpdateAvailable = false
		state.LastCheck = &now
		state.LastError = err.Error()
		state.CheckState = updateCheckStateFailed
		return state
	})
}

func (s *updateService) applyLatest(ctx context.Context) error {
	if err := s.checkForUpdate(ctx); err != nil {
		return err
	}
	state := s.copyState()
	if !state.UpdateAvailable {
		return nil
	}
	current, err := s.currentContainer(ctx)
	if err != nil {
		return err
	}
	return s.stageReplacement(ctx, current, state.TrackedImage, state.LatestImageID)
}

func (s *updateService) rollback(ctx context.Context) error {
	state := s.copyState()
	if state.RollbackImage == "" {
		return fmt.Errorf("rollback is not available")
	}
	current, err := s.currentContainer(ctx)
	if err != nil {
		return err
	}
	currentName := s.currentContainerName(current)
	if currentName == "" {
		return fmt.Errorf("could not resolve current appliance container name")
	}

	rollbackContainer := dockerContainerInspect{}
	rollbackOriginalName := state.RollbackContainer
	if state.RollbackContainer != "" {
		rollbackContainer, err = s.docker.inspectContainer(ctx, state.RollbackContainer)
	}
	if err != nil || rollbackContainer.ID == "" {
		if len(state.RollbackConfig) == 0 {
			if err != nil {
				return fmt.Errorf("rollback container is unavailable: %w", err)
			}
			return errors.New("rollback container is unavailable")
		}
		tempName := uniqueContainerName(currentName + "-rollback-restore")
		rollbackID, createErr := s.docker.createContainer(ctx, tempName, state.RollbackConfig)
		if createErr != nil {
			return createErr
		}
		rollbackOriginalName = tempName
		rollbackContainer, err = s.docker.inspectContainer(ctx, rollbackID)
		if err != nil {
			_ = s.docker.removeContainer(context.Background(), rollbackID, true)
			return err
		}
	}

	currentBackupName := uniqueContainerName(currentName + "-rollback-current")
	if err := s.docker.renameContainer(ctx, current.ID, currentBackupName); err != nil {
		return err
	}
	if err := s.docker.renameContainer(ctx, rollbackContainer.ID, currentName); err != nil {
		_ = s.docker.renameContainer(context.Background(), current.ID, currentName)
		return err
	}

	nextRollbackConfig := replacementCreateSpec(current, containerConfigString(current, "Image"))
	previousState := cloneUpdateState(state)
	s.updateState(func(state applianceUpdateState) applianceUpdateState {
		state.RollbackImage = containerConfigString(current, "Image")
		state.RollbackContainer = currentBackupName
		state.RollbackConfig = nextRollbackConfig
		return state
	})

	if err := s.startHandoff(ctx, current, currentBackupName, rollbackContainer, currentName); err != nil {
		restoreName := rollbackOriginalName
		if restoreName == "" {
			restoreName = uniqueContainerName(currentName + "-rollback-restore")
		}
		_ = s.docker.renameContainer(context.Background(), rollbackContainer.ID, restoreName)
		_ = s.docker.renameContainer(context.Background(), current.ID, currentName)
		s.updateState(func(state applianceUpdateState) applianceUpdateState {
			previousState.LastError = err.Error()
			return previousState
		})
		return err
	}
	return nil
}

func (s *updateService) stageReplacement(ctx context.Context, current dockerContainerInspect, imageRef, imageID string) error {
	currentName := s.currentContainerName(current)
	if currentName == "" {
		return fmt.Errorf("could not resolve current appliance container name")
	}

	replacementName := uniqueContainerName(currentName + "-update")
	replacementSpec := replacementCreateSpec(current, imageRef)
	replacementID, err := s.docker.createContainer(ctx, replacementName, replacementSpec)
	if err != nil {
		return err
	}
	replacement, err := s.docker.inspectContainer(ctx, replacementID)
	if err != nil {
		_ = s.docker.removeContainer(context.Background(), replacementID, true)
		return err
	}

	rollbackName := uniqueContainerName(currentName + "-rollback")
	if err := s.docker.renameContainer(ctx, current.ID, rollbackName); err != nil {
		_ = s.docker.removeContainer(context.Background(), replacementID, true)
		return err
	}
	if err := s.docker.renameContainer(ctx, replacementID, currentName); err != nil {
		_ = s.docker.renameContainer(context.Background(), current.ID, currentName)
		_ = s.docker.removeContainer(context.Background(), replacementID, true)
		return err
	}

	s.updateState(func(state applianceUpdateState) applianceUpdateState {
		state.LatestImage = imageRef
		state.LatestImageID = imageID
		state.RollbackImage = containerConfigString(current, "Image")
		state.RollbackContainer = rollbackName
		state.RollbackConfig = replacementCreateSpec(current, containerConfigString(current, "Image"))
		state.LastError = ""
		return state
	})

	if err := s.startHandoff(ctx, current, rollbackName, replacement, currentName); err != nil {
		_ = s.docker.renameContainer(context.Background(), replacementID, replacementName)
		_ = s.docker.renameContainer(context.Background(), current.ID, currentName)
		return err
	}
	return nil
}

func (s *updateService) startHandoff(ctx context.Context, old dockerContainerInspect, oldName string, next dockerContainerInspect, nextName string) error {
	helperName := uniqueContainerName(nextName + "-handoff")
	spec := helperCreateSpec(old, []string{
		"update-handoff",
		"--old", old.ID,
		"--old-name", oldName,
		"--new", next.ID,
		"--new-name", nextName,
		"--state", s.cfg.UpdateStateFile,
		"--socket", s.cfg.DockerSocket,
	})
	helperID, err := s.docker.createContainer(ctx, helperName, spec)
	if err != nil {
		return err
	}
	if err := s.docker.startContainer(ctx, helperID); err != nil {
		_ = s.docker.removeContainer(context.Background(), helperID, true)
		return err
	}
	return nil
}

func (s *updateService) currentContainer(ctx context.Context) (dockerContainerInspect, error) {
	var lastErr error
	for _, candidate := range s.currentContainerCandidates() {
		if candidate == "" {
			continue
		}
		inspect, err := s.docker.inspectContainer(ctx, candidate)
		if err == nil {
			return inspect, nil
		}
		lastErr = err
	}
	if lastErr != nil {
		return dockerContainerInspect{}, lastErr
	}
	return dockerContainerInspect{}, fmt.Errorf("could not resolve current appliance container")
}

func (s *updateService) currentContainerCandidates() []string {
	hostname, _ := os.Hostname()
	return []string{
		s.cfg.ApplianceContainerName,
		os.Getenv("HOSTNAME"),
		hostname,
	}
}

func (s *updateService) currentContainerName(inspect dockerContainerInspect) string {
	if strings.TrimSpace(s.cfg.ApplianceContainerName) != "" {
		return sanitizeContainerName(s.cfg.ApplianceContainerName)
	}
	return sanitizeContainerName(strings.TrimPrefix(inspect.Name, "/"))
}

func (s *updateService) trackedImageRef(currentImage string) string {
	if override := strings.TrimSpace(s.cfg.UpdateImageRef); override != "" {
		return override
	}
	return latestImageRef(currentImage)
}

func (s *updateService) isLocalOnlyUpdateRef(currentRef, trackedRef string) bool {
	if strings.TrimSpace(s.cfg.UpdateImageRef) != "" {
		return false
	}
	return isDefaultLocalApplianceImage(currentRef) || isDefaultLocalApplianceImage(trackedRef)
}

func isDefaultLocalApplianceImage(ref string) bool {
	return imageRepository(ref) == "unicron-appliance"
}

func imageRepository(ref string) string {
	ref = strings.TrimSpace(ref)
	if ref == "" {
		return ""
	}
	if strings.Contains(ref, "@") {
		ref = strings.SplitN(ref, "@", 2)[0]
	}
	lastSlash := strings.LastIndex(ref, "/")
	lastColon := strings.LastIndex(ref, ":")
	if lastColon > lastSlash {
		ref = ref[:lastColon]
	}
	return ref
}

func normalizedUpdateCheckState(checkState, lastError string) string {
	switch checkState {
	case updateCheckStateOK, updateCheckStateFailed, updateCheckStateNoSource:
		return checkState
	}
	if strings.TrimSpace(lastError) != "" {
		return updateCheckStateFailed
	}
	return updateCheckStateUnknown
}

func latestImageRef(currentImage string) string {
	ref := strings.TrimSpace(currentImage)
	if ref == "" {
		return ""
	}
	if strings.Contains(ref, "@") {
		return strings.SplitN(ref, "@", 2)[0] + ":latest"
	}
	if strings.HasPrefix(ref, "sha256:") {
		return ""
	}
	lastSlash := strings.LastIndex(ref, "/")
	lastColon := strings.LastIndex(ref, ":")
	if lastColon > lastSlash {
		return ref[:lastColon] + ":latest"
	}
	return ref + ":latest"
}

func replacementCreateSpec(current dockerContainerInspect, imageRef string) map[string]any {
	config := cloneMap(current.Config)
	hostConfig := cloneMap(current.HostConfig)
	if config == nil {
		config = map[string]any{}
	}
	if hostConfig == nil {
		hostConfig = map[string]any{}
	}
	config["Image"] = imageRef
	if hostname, _ := config["Hostname"].(string); hostname != "" && strings.HasPrefix(current.ID, hostname) {
		delete(config, "Hostname")
	}
	config["HostConfig"] = hostConfig
	config["NetworkingConfig"] = networkingConfig(current.NetworkSettings.Networks)
	return config
}

func helperCreateSpec(current dockerContainerInspect, args []string) map[string]any {
	hostConfig := map[string]any{
		"AutoRemove":  true,
		"NetworkMode": "none",
	}
	if binds, ok := current.HostConfig["Binds"]; ok {
		hostConfig["Binds"] = binds
	}
	if mounts, ok := current.HostConfig["Mounts"]; ok {
		hostConfig["Mounts"] = mounts
	}
	return map[string]any{
		"Image":      current.Image,
		"Entrypoint": []string{defaultManagerPath},
		"Cmd":        args,
		"Env": []string{
			"UNICRON_APPLIANCE_DOCKER_SOCKET=" + defaultDockerSocket,
			"UNICRON_DATA_DIR=" + defaultDataDir,
		},
		"HostConfig": hostConfig,
	}
}

func networkingConfig(networks map[string]map[string]any) map[string]any {
	if len(networks) == 0 {
		return map[string]any{}
	}
	endpoints := make(map[string]any, len(networks))
	for name, settings := range networks {
		endpoint := map[string]any{}
		for _, key := range []string{"Aliases", "Links", "DriverOpts", "IPAMConfig", "MacAddress"} {
			if value, ok := settings[key]; ok && !isZeroJSONValue(value) {
				endpoint[key] = value
			}
		}
		endpoints[name] = endpoint
	}
	return map[string]any{"EndpointsConfig": endpoints}
}

func sameImageID(a, b string) bool {
	return strings.TrimSpace(a) != "" && strings.TrimSpace(a) == strings.TrimSpace(b)
}

func containerConfigString(inspect dockerContainerInspect, key string) string {
	if inspect.Config == nil {
		return ""
	}
	value, _ := inspect.Config[key].(string)
	return value
}

func cloneMap(input map[string]any) map[string]any {
	if input == nil {
		return nil
	}
	var output map[string]any
	body, err := json.Marshal(input)
	if err != nil {
		return nil
	}
	if err := json.Unmarshal(body, &output); err != nil {
		return nil
	}
	return output
}

func isZeroJSONValue(value any) bool {
	if value == nil {
		return true
	}
	switch typed := value.(type) {
	case string:
		return typed == ""
	case []any:
		return len(typed) == 0
	case map[string]any:
		return len(typed) == 0
	default:
		return false
	}
}

func sanitizeContainerName(name string) string {
	name = strings.TrimPrefix(strings.TrimSpace(name), "/")
	name = strings.Trim(name, "-_")
	return name
}

var invalidContainerNameChars = regexp.MustCompile(`[^A-Za-z0-9_.-]+`)

func uniqueContainerName(prefix string) string {
	base := invalidContainerNameChars.ReplaceAllString(sanitizeContainerName(prefix), "-")
	if base == "" {
		base = "unicron-appliance"
	}
	if len(base) > 48 {
		base = base[:48]
	}
	return fmt.Sprintf("%s-%d", base, time.Now().UTC().UnixNano())
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeMethodNotAllowed(w http.ResponseWriter) {
	writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
}
