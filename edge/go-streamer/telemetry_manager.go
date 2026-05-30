package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/docker/docker/client"
	"github.com/sirupsen/logrus"
)

// TelemetryManager orchestrates the dynamic telemetry pipeline:
// - Manages monitoring state (which containers are enabled)
// - Generates a static OTel Collector config and dynamic Fluent Bit config
// - Supervises OTel and Fluent Bit processes
// - Debounces rapid toggle commands into single config updates
// - Reports health status to Central
type TelemetryManager struct {
	state            *MonitoringState
	configGen        *ConfigGenerator
	otelSupervisor   *ProcessSupervisor
	fbPushSupervisor *ProcessSupervisor
	fbSupervisor     *ProcessSupervisor
	liveFBSupervisor *ProcessSupervisor
	debouncer        *ConfigDebouncer
	liveDebouncer    *ConfigDebouncer
	upstream         *upstreamClient
	docker           *client.Client
	hostID           string
	ctx              context.Context
	cancel           context.CancelFunc
	logCollector     *logCollectionService
	liveLogCollector *logCollectionService
	logStateMu       sync.Mutex
	logStates        map[string]logCollectionState
	lastHealthy      bool // track overall health for event-driven reporting
	mu               sync.Mutex
}

// NewTelemetryManager creates and wires up all telemetry components.
func NewTelemetryManager(docker *client.Client, upstream *upstreamClient, hostID string) (*TelemetryManager, error) {
	// Create monitoring state with default persistence path
	state := NewMonitoringState("/var/lib/go-streamer/monitoring-state.json")

	// Create config generator
	configGen, err := NewConfigGenerator(docker)
	if err != nil {
		return nil, err
	}

	ctx, cancel := context.WithCancel(context.Background())

	tm := &TelemetryManager{
		state:     state,
		configGen: configGen,
		upstream:  upstream,
		docker:    docker,
		hostID:    hostID,
		ctx:       ctx,
		cancel:    cancel,
		logStates: make(map[string]logCollectionState),
	}
	logCollector, err := newLogCollectionService(hostID, state, docker, logCollectionServiceOptions{
		ingestPort:       localLogIngestPort,
		ingestPath:       localLogIngestPath,
		requireMonitored: true,
		sendOTLP:         true,
	})
	if err != nil {
		return nil, err
	}
	if configGen.logCollectionCache != nil {
		logCollector.planCache = configGen.logCollectionCache
	}
	logCollector.fastLaneSender = upstream
	tm.logCollector = logCollector
	liveCollector, err := newLogCollectionService(hostID, nil, docker, logCollectionServiceOptions{
		ingestPort:       localLiveLogIngestPort,
		ingestPath:       localLiveLogIngestPath,
		requireMonitored: false,
		sendOTLP:         false,
	})
	if err != nil {
		return nil, err
	}
	liveCollector.fastLaneSender = upstream
	tm.liveLogCollector = liveCollector

	// OTel Collector supervisor
	otelBin := os.Getenv("OTEL_COLLECTOR_BIN")
	if otelBin == "" {
		otelBin = "/otelcol/otelcol"
	}
	tm.otelSupervisor = NewProcessSupervisor(
		"otel-collector",
		otelBin,
		[]string{"--config", "/tmp/otel-edge.yaml"},
		tm.handleHealthChange,
	)

	// Fluent Bit supervisor
	fbBin := os.Getenv("FLUENT_BIT_BIN")
	if fbBin == "" {
		fbBin = "/opt/fluent-bit/bin/fluent-bit"
	}
	tm.fbSupervisor = NewProcessSupervisor(
		"fluent-bit-tail",
		fbBin,
		[]string{"-c", "/tmp/fluent-bit.conf"},
		tm.handleHealthChange,
	)
	tm.fbPushSupervisor = NewProcessSupervisor(
		"fluent-bit-push",
		fbBin,
		[]string{"-c", "/tmp/fluent-bit-push.conf"},
		tm.handleHealthChange,
	)
	tm.liveFBSupervisor = NewProcessSupervisor(
		"fluent-bit-live",
		fbBin,
		[]string{"-c", "/tmp/fluent-bit-live.conf"},
		nil,
	)

	// Debouncer with 3-second window
	tm.debouncer = NewConfigDebouncer(3*time.Second, tm.applyConfigUpdate)
	tm.liveDebouncer = NewConfigDebouncer(1*time.Second, tm.applyLiveConfigUpdate)

	return tm, nil
}

// Start loads persisted state, generates initial configs, and starts supervisors.
func (tm *TelemetryManager) Start() {
	log := logrus.WithField("component", "TelemetryManager")

	// 1. Load persisted state
	if err := tm.state.LoadFromDisk(); err != nil {
		log.WithError(err).Error("failed to load monitoring state from disk")
	}

	// 2. Generate initial OTel config
	if err := tm.configGen.GenerateOTelConfig(); err != nil {
		log.WithError(err).Error("failed to generate initial OTel config")
	}

	// 3. Generate stable push Fluent Bit config. Monitoring changes must not
	// reload this listener because Docker's Fluentd driver pushes through it.
	if err := tm.configGen.GeneratePushFluentBitConfig(); err != nil {
		log.WithError(err).Error("failed to generate initial push Fluent Bit config")
	}

	// 4. Generate initial tail Fluent Bit config and prime log collection state
	if err := tm.rebuildLogCollectionConfig(); err != nil {
		log.WithError(err).Error("failed to generate initial Fluent Bit config")
	}

	// 5. Start loopback ingest server for Fluent Bit batches
	if tm.logCollector != nil {
		if err := tm.logCollector.start(tm.ctx); err != nil {
			log.WithError(err).Error("failed to start loopback log collector")
		}
	}
	if tm.liveLogCollector != nil {
		if err := tm.liveLogCollector.start(tm.ctx); err != nil {
			log.WithError(err).Error("failed to start live-only log collector")
		}
		if err := tm.configGen.GenerateLiveFluentBitConfig(nil); err != nil {
			log.WithError(err).Error("failed to generate initial live-only Fluent Bit config")
		}
	}

	// 6. Start OTel supervisor
	go tm.otelSupervisor.Run(tm.ctx)

	// 7. Start Fluent Bit supervisors
	if tm.fbPushSupervisor != nil {
		go tm.fbPushSupervisor.Run(tm.ctx)
	}
	go tm.fbSupervisor.Run(tm.ctx)
	if tm.liveFBSupervisor != nil {
		go tm.liveFBSupervisor.Run(tm.ctx)
	}

	log.WithField("monitored_count", len(tm.state.MonitoredKeys())).Info("TelemetryManager started")
}

// HandleToggle processes a monitoring_toggle command from Central.
// Updates state, persists to disk, triggers debounced config update, and sends ACK.
func (tm *TelemetryManager) HandleToggle(cmd monitoringToggleCommand) {
	log := logrus.WithFields(logrus.Fields{
		"component":  "TelemetryManager",
		"container":  cmd.Name,
		"enabled":    cmd.Enabled,
		"request_id": cmd.RequestID,
	})

	// 1. Update state
	tm.state.SetEnabled(cmd.Name, cmd.Image, cmd.Enabled)

	// 2. Persist to disk
	if err := tm.state.SaveToDisk(); err != nil {
		log.WithError(err).Error("failed to persist monitoring state")
	}

	// 3. Trigger debounced config update
	tm.debouncer.Trigger()

	// 4. Send ACK to Central
	ack := monitoringToggleAck{RequestID: cmd.RequestID, Success: true}
	data, _ := json.Marshal(ack)
	tm.upstream.sendEnvelope(upstreamEnvelope{Type: "monitoring_toggle_ack", Data: data})

	// 5. Log toggle action
	action := "disabled"
	if cmd.Enabled {
		action = "enabled"
	}
	log.WithField("action", action).Info("monitoring toggle processed")
}

// HandleSync processes a monitoring_sync command from Central on reconnect.
// Replaces local state entirely with Central's list.
func (tm *TelemetryManager) HandleSync(cmd monitoringSyncCommand) {
	log := logrus.WithFields(logrus.Fields{
		"component":       "TelemetryManager",
		"container_count": len(cmd.Containers),
	})

	// 1. Build new state map from sync payload
	newState := make(map[string]bool, len(cmd.Containers))
	for _, c := range cmd.Containers {
		if c.Enabled {
			key := ContainerKey{Name: c.Name, Image: c.Image}.String()
			newState[key] = true
		}
	}

	// 2. Replace local state
	tm.state.ReplaceAll(newState)

	// 3. Persist to disk
	if err := tm.state.SaveToDisk(); err != nil {
		log.WithError(err).Error("failed to persist synced state")
	}

	// 4. Trigger debounced config update
	tm.debouncer.Trigger()

	// 5. Log sync
	log.Info("monitoring sync processed")
}

func (tm *TelemetryManager) HandleFastTailStart(cmd fastTailCommand) {
	containerKey := strings.TrimSpace(cmd.ContainerKey)
	if containerKey == "" {
		return
	}
	source := cmd.Source
	if source == "" {
		source = fastTailSourceMonitored
	}
	switch source {
	case fastTailSourceLiveOnly:
		if tm.liveLogCollector == nil {
			return
		}
		if _, err := tm.liveLogCollector.activateContainer(containerKey); err != nil {
			tm.liveLogCollector.emitFastLogsError(containerKey, err)
			return
		}
		tm.liveLogCollector.setFastTailActive(containerKey, true)
		tm.liveDebouncer.Trigger()
		if strings.TrimSpace(cmd.HistoryTail) != "" || strings.TrimSpace(cmd.HistorySince) != "" {
			go func() {
				if err := tm.liveLogCollector.seedHistory(tm.ctx, containerKey, cmd.HistoryTail, cmd.HistorySince); err != nil {
					tm.liveLogCollector.emitFastLogsError(containerKey, err)
				}
			}()
		}
	default:
		if tm.logCollector == nil {
			return
		}
		tm.logCollector.setFastTailActive(containerKey, true)
	}
}

func (tm *TelemetryManager) HandleFastTailStop(cmd fastTailCommand) {
	containerKey := strings.TrimSpace(cmd.ContainerKey)
	if containerKey == "" {
		return
	}
	source := cmd.Source
	if source == "" {
		source = fastTailSourceMonitored
	}
	switch source {
	case fastTailSourceLiveOnly:
		if tm.liveLogCollector == nil {
			return
		}
		tm.liveLogCollector.setFastTailActive(containerKey, false)
		if tm.liveLogCollector.deactivateContainer(containerKey) {
			tm.liveDebouncer.Trigger()
		}
	default:
		if tm.logCollector == nil {
			return
		}
		tm.logCollector.setFastTailActive(containerKey, false)
	}
}

// applyConfigUpdate is called by the debouncer after 3 seconds of inactivity.
// Monitoring changes only affect the reloadable tail Fluent Bit pipeline. OTel
// and the stable push listener stay running.
func (tm *TelemetryManager) applyConfigUpdate() {
	log := logrus.WithField("component", "TelemetryManager")

	// 1. Generate tail Fluent Bit config and update log collection state
	if err := tm.rebuildLogCollectionConfig(); err != nil {
		log.WithError(err).Error("failed to generate Fluent Bit config on update")
		return
	}

	// 2. Hot-reload only the tail Fluent Bit pipeline via HTTP API.
	triggerFluentBitReload()

	log.WithField("monitored_count", len(tm.state.MonitoredKeys())).Info("monitoring update applied without OTel or push-listener restart")
}

func (tm *TelemetryManager) applyLiveConfigUpdate() {
	log := logrus.WithField("component", "TelemetryManager")
	if tm.configGen == nil || tm.liveLogCollector == nil {
		return
	}

	plans := tm.liveLogCollector.activePlans()
	if err := tm.configGen.GenerateLiveFluentBitConfig(plans); err != nil {
		log.WithError(err).Error("failed to generate live-only Fluent Bit config on update")
		return
	}

	triggerFluentBitReloadPort(2021)
	log.WithField("active_live_containers", tm.liveLogCollector.activeContainerCount()).Info("live-only log update applied")
}

func (tm *TelemetryManager) rebuildLogCollectionConfig() error {
	if tm.configGen == nil {
		return nil
	}

	plans := tm.configGen.BuildLogCollectionPlan(tm.state.MonitoredKeys())
	if tm.logCollector != nil {
		tm.logCollector.replacePlans(plans)
	}
	tm.reconcileLogCollectionPlans(plans)
	return tm.configGen.GenerateFluentBitConfig(plans)
}

func (tm *TelemetryManager) reconcileLogCollectionPlans(plans []logCollectionPlan) {
	nextStates := make(map[string]logCollectionState, len(plans))
	events := make([]logCollectionStateChangedPayload, 0, len(plans))

	tm.logStateMu.Lock()
	for _, plan := range plans {
		key := plan.monitoredKey()
		state := plan.state()
		nextStates[key] = state

		prev, ok := tm.logStates[key]
		if !ok || !prev.publicEqual(state) {
			events = append(events, state.payload(tm.hostID, plan.Key))
		}
	}
	for rawKey, prev := range tm.logStates {
		if _, ok := nextStates[rawKey]; ok {
			continue
		}
		if prev.PublicStatus != "unavailable" {
			continue
		}
		key := ParseContainerKey(rawKey)
		events = append(events, logCollectionState{
			PublicStatus:      "ok",
			ContainerName:     prev.ContainerName,
			DockerContainerID: prev.DockerContainerID,
			Image:             prev.Image,
		}.payload(tm.hostID, key))
	}
	tm.logStates = nextStates
	tm.logStateMu.Unlock()

	for _, evt := range events {
		tm.sendLogCollectionStateChanged(evt)
	}
}

func (tm *TelemetryManager) sendLogCollectionStateChanged(payload logCollectionStateChangedPayload) {
	if tm.upstream == nil {
		return
	}
	data, err := json.Marshal(payload)
	if err != nil {
		logrus.WithError(err).WithFields(logrus.Fields{
			"name":  payload.Name,
			"image": payload.Image,
		}).Warn("failed to marshal log-collection state payload")
		return
	}
	tm.upstream.sendEnvelope(upstreamEnvelope{Type: "log_collection_state_changed", Data: data})
}

// triggerFluentBitReload sends a POST to Fluent Bit's HTTP API to trigger config reload.
// This avoids a full process restart for Fluent Bit.
func triggerFluentBitReload() {
	triggerFluentBitReloadPort(2020)
}

func triggerFluentBitReloadPort(port int) {
	log := logrus.WithFields(logrus.Fields{"component": "TelemetryManager", "port": port})
	resp, err := http.Post(fmt.Sprintf("http://localhost:%d/api/v2/reload", port), "application/json", strings.NewReader("{}"))
	if err != nil {
		log.WithError(err).Warn("failed to trigger Fluent Bit reload (may not be ready yet)")
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		log.Info("Fluent Bit hot-reload triggered successfully")
	} else {
		log.WithField("status", resp.StatusCode).Warn("Fluent Bit reload returned non-success status")
	}
}

// handleHealthChange is called by ProcessSupervisors when health state transitions.
// Reports overall telemetry health to Central.
func (tm *TelemetryManager) handleHealthChange(name string, healthy bool) {
	tm.mu.Lock()
	defer tm.mu.Unlock()

	// Compute overall health: OTel, stable push Fluent Bit, and tail Fluent Bit must be healthy.
	overallHealthy := tm.otelSupervisor.IsHealthy() && tm.fbSupervisor.IsHealthy()
	if tm.fbPushSupervisor != nil {
		overallHealthy = overallHealthy && tm.fbPushSupervisor.IsHealthy()
	}

	// Only report on transitions
	if overallHealthy == tm.lastHealthy {
		return
	}
	tm.lastHealthy = overallHealthy

	// Send health event to Central
	payload := telemetryHealthPayload{
		Healthy:   overallHealthy,
		Timestamp: time.Now().Unix(),
	}
	data, _ := json.Marshal(payload)
	tm.upstream.sendEnvelope(upstreamEnvelope{Type: "telemetry_health", Data: data})

	logrus.WithFields(logrus.Fields{
		"component":       "TelemetryManager",
		"overall_healthy": overallHealthy,
		"trigger":         name,
	}).Info("telemetry health status changed")
}

// Stop gracefully shuts down the TelemetryManager and its child processes.
func (tm *TelemetryManager) Stop() {
	log := logrus.WithField("component", "TelemetryManager")

	// Cancel context (stops supervisor loops)
	tm.cancel()

	// Stop debouncer (cancel pending config updates)
	tm.debouncer.Stop()
	if tm.liveDebouncer != nil {
		tm.liveDebouncer.Stop()
	}

	log.Info("TelemetryManager stopped")
}
