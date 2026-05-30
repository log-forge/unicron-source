package main

import (
	"bytes"
	"embed"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"text/template"

	"github.com/sirupsen/logrus"
)

//go:embed templates/*
var templateFS embed.FS

const (
	otelEdgeTmpl          = "templates/otel-edge.yaml.tmpl"
	fluentBitEdgeTmpl     = "templates/fluent-bit.conf.tmpl"
	fluentBitPushEdgeTmpl = "templates/fluent-bit-push.conf.tmpl"
	fluentBitLiveTmpl     = "templates/fluent-bit-live.conf.tmpl"
)

// otelTemplateData holds data passed to the OTel config template.
type otelTemplateData struct {
	PushMetricsEnabled   bool
	ScrapeMetricsEnabled bool
	DurableQueue         bool
	OTelQueueSize        int
}

// fluentBitTemplateData holds data passed to the Fluent Bit config template.
type fluentBitTemplateData struct {
	MonitoredContainers       []MonitoredContainer
	HasTailInputs             bool
	PushLogsEnabled           bool
	DurableQueue              bool
	FLBFlushSeconds           string
	FLBOutputWorkers          int
	FLBMemBufLimit            string
	FLBTailDBPath             string
	FLBStorageBacklogMemLimit string
	FLBStorageTotalLimit      string
	FLBStoragePath            string
	FLBStorageSync            string
	FLBStorageMaxChunksUp     string
}

type telemetryTemplateConfig struct {
	mode                      string
	pushEnabled               bool
	durableQueue              bool
	otelQueueSize             int
	flbFlushSeconds           string
	flbOutputWorkers          int
	flbMemBufLimit            string
	flbTailDBPath             string
	flbStorageBacklogMemLimit string
	flbStorageTotalLimit      string
	flbStoragePath            string
	flbPushStoragePath        string
	flbStorageSync            string
	flbStorageMaxChunksUp     string
}

func readTelemetryTemplateConfig() telemetryTemplateConfig {
	mode := resolveTelemetryMode()
	pushEnabled := telemetryPushEnabled(mode)
	queueMode := resolveTelemetryQueueMode()
	durableQueue := telemetryDurableQueueEnabled(queueMode)

	otelQueueSize := parsePositiveEnvInt("OTEL_SENDING_QUEUE_SIZE", 60000)

	flbFlushSeconds := strings.TrimSpace(os.Getenv("FLB_FLUSH_SECONDS"))
	if flbFlushSeconds == "" {
		flbFlushSeconds = "0.2"
	} else {
		if parsed, err := strconv.ParseFloat(flbFlushSeconds, 64); err != nil || parsed <= 0 {
			flbFlushSeconds = "0.2"
		}
	}

	flbOutputWorkers := parsePositiveEnvInt("FLB_OUTPUT_WORKERS", 2)
	flbMemBufLimit := strings.TrimSpace(os.Getenv("FLB_MEM_BUF_LIMIT"))
	if flbMemBufLimit == "" {
		flbMemBufLimit = defaultFlbMemBufLimit
	}

	flbTailDBPath := strings.TrimSpace(os.Getenv("FLB_TAIL_DB_PATH"))
	if flbTailDBPath == "" {
		if durableQueue {
			flbTailDBPath = defaultFlbTailDBPath
		} else {
			flbTailDBPath = memoryFlbTailDBPath
		}
	}

	flbStorageBacklogMemLimit := strings.TrimSpace(os.Getenv("FLB_STORAGE_BACKLOG_MEM_LIMIT"))
	if flbStorageBacklogMemLimit == "" {
		flbStorageBacklogMemLimit = flbMemBufLimit
	}

	flbStorageTotalLimit := strings.TrimSpace(os.Getenv("FLB_STORAGE_TOTAL_LIMIT"))
	if flbStorageTotalLimit == "" {
		flbStorageTotalLimit = defaultDiskQueueMB + "MB"
	}

	flbStorageSync := normalizeFLBStorageSync(os.Getenv("FLB_STORAGE_SYNC"))
	flbStorageMaxChunksUp := normalizePositiveEnvIntString("FLB_STORAGE_MAX_CHUNKS_UP")

	flbStoragePath := filepath.Join(filepath.Dir(flbTailDBPath), "storage")
	flbPushStoragePath := filepath.Join(filepath.Dir(flbTailDBPath), "push-storage")

	return telemetryTemplateConfig{
		mode:                      mode,
		pushEnabled:               pushEnabled,
		durableQueue:              durableQueue,
		otelQueueSize:             otelQueueSize,
		flbFlushSeconds:           flbFlushSeconds,
		flbOutputWorkers:          flbOutputWorkers,
		flbMemBufLimit:            flbMemBufLimit,
		flbTailDBPath:             flbTailDBPath,
		flbStorageBacklogMemLimit: flbStorageBacklogMemLimit,
		flbStorageTotalLimit:      flbStorageTotalLimit,
		flbStoragePath:            flbStoragePath,
		flbPushStoragePath:        flbPushStoragePath,
		flbStorageSync:            flbStorageSync,
		flbStorageMaxChunksUp:     flbStorageMaxChunksUp,
	}
}

func normalizeFLBStorageSync(raw string) string {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "", "normal":
		return "normal"
	case "full":
		return "full"
	default:
		logrus.WithField("flb_storage_sync", raw).Warn("[Telemetry] Unsupported FLB_STORAGE_SYNC, defaulting to normal")
		return "normal"
	}
}

func normalizePositiveEnvIntString(key string) string {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return ""
	}
	v, err := strconv.Atoi(raw)
	if err != nil || v <= 0 {
		logrus.WithField(strings.ToLower(key), raw).Warn("[Telemetry] Unsupported positive integer env value, omitting setting")
		return ""
	}
	return strconv.Itoa(v)
}

// ConfigGenerator generates OTel Collector and Fluent Bit configuration files
// from Go templates, writing them atomically to disk.
type ConfigGenerator struct {
	otelTemplate       *template.Template
	fbTemplate         *template.Template
	fbPushTemplate     *template.Template
	fbLiveTemplate     *template.Template
	otelConfigPath     string
	fbConfigPath       string
	fbPushConfigPath   string
	fbLiveConfigPath   string
	docker             dockerInspector
	logCollectionCache *logCollectionPlanCache
}

// NewConfigGenerator creates a ConfigGenerator by parsing embedded templates.
// OTel and Fluent Bit both use shared templates.
func NewConfigGenerator(docker dockerInspector) (*ConfigGenerator, error) {
	heraldName := os.Getenv("HERALD_NAME")
	otelTmplPath := otelEdgeTmpl
	fbTmplPath := fluentBitEdgeTmpl
	fbPushTmplPath := fluentBitPushEdgeTmpl
	fbLiveTmplPath := fluentBitLiveTmpl

	otelTmpl, err := template.ParseFS(templateFS, otelTmplPath)
	if err != nil {
		return nil, fmt.Errorf("failed to parse OTel template: %w", err)
	}

	fbTmpl, err := template.ParseFS(templateFS, fbTmplPath)
	if err != nil {
		return nil, fmt.Errorf("failed to parse Fluent Bit template: %w", err)
	}
	fbPushTmpl, err := template.ParseFS(templateFS, fbPushTmplPath)
	if err != nil {
		return nil, fmt.Errorf("failed to parse push Fluent Bit template: %w", err)
	}
	fbLiveTmpl, err := template.ParseFS(templateFS, fbLiveTmplPath)
	if err != nil {
		return nil, fmt.Errorf("failed to parse live Fluent Bit template: %w", err)
	}

	logrus.WithFields(logrus.Fields{
		"herald_name":   heraldName,
		"otel_template": otelTmplPath,
		"fb_template":   fbTmplPath,
		"fb_push":       fbPushTmplPath,
		"fb_live":       fbLiveTmplPath,
	}).Info("[ConfigGenerator] Templates selected")

	return &ConfigGenerator{
		otelTemplate:       otelTmpl,
		fbTemplate:         fbTmpl,
		fbPushTemplate:     fbPushTmpl,
		fbLiveTemplate:     fbLiveTmpl,
		otelConfigPath:     "/tmp/otel-edge.yaml",
		fbConfigPath:       "/tmp/fluent-bit.conf",
		fbPushConfigPath:   "/tmp/fluent-bit-push.conf",
		fbLiveConfigPath:   "/tmp/fluent-bit-live.conf",
		docker:             docker,
		logCollectionCache: newLogCollectionPlanCache(readMetaCacheTTL()),
	}, nil
}

// GenerateOTelConfig generates the OTel Collector config file.
func (g *ConfigGenerator) GenerateOTelConfig() error {
	cfg := readTelemetryTemplateConfig()
	data := otelTemplateData{
		PushMetricsEnabled:   cfg.pushEnabled,
		ScrapeMetricsEnabled: true,
		DurableQueue:         cfg.durableQueue,
		OTelQueueSize:        cfg.otelQueueSize,
	}

	var buf bytes.Buffer
	if err := g.otelTemplate.Execute(&buf, data); err != nil {
		return fmt.Errorf("failed to execute OTel template: %w", err)
	}

	if err := atomicWriteFile(g.otelConfigPath, buf.Bytes(), 0644); err != nil {
		return fmt.Errorf("failed to write OTel config: %w", err)
	}

	logrus.WithFields(logrus.Fields{
		"path":               g.otelConfigPath,
		"telemetry_mode":     cfg.mode,
		"push_metrics":       data.PushMetricsEnabled,
		"queue_mode_durable": data.DurableQueue,
		"otel_queue_size":    data.OTelQueueSize,
	}).Info("[ConfigGenerator] OTel config generated")

	return nil
}

// GeneratePushFluentBitConfig generates the stable Fluent Bit config that owns
// Docker Fluentd/HTTP push inputs. Monitoring changes must not reload it.
func (g *ConfigGenerator) GeneratePushFluentBitConfig() error {
	cfg := readTelemetryTemplateConfig()
	data := fluentBitTemplateData{
		PushLogsEnabled:           cfg.pushEnabled,
		DurableQueue:              cfg.durableQueue,
		FLBFlushSeconds:           cfg.flbFlushSeconds,
		FLBOutputWorkers:          cfg.flbOutputWorkers,
		FLBMemBufLimit:            cfg.flbMemBufLimit,
		FLBStorageBacklogMemLimit: cfg.flbStorageBacklogMemLimit,
		FLBStorageTotalLimit:      cfg.flbStorageTotalLimit,
		FLBStoragePath:            cfg.flbPushStoragePath,
		FLBStorageSync:            cfg.flbStorageSync,
		FLBStorageMaxChunksUp:     cfg.flbStorageMaxChunksUp,
	}

	var buf bytes.Buffer
	if err := g.fbPushTemplate.Execute(&buf, data); err != nil {
		return fmt.Errorf("failed to execute push Fluent Bit template: %w", err)
	}

	if err := atomicWriteFile(g.fbPushConfigPath, buf.Bytes(), 0644); err != nil {
		return fmt.Errorf("failed to write push Fluent Bit config: %w", err)
	}

	logrus.WithFields(logrus.Fields{
		"path":                          g.fbPushConfigPath,
		"push_logs":                     data.PushLogsEnabled,
		"queue_mode_durable":            data.DurableQueue,
		"flush_seconds":                 data.FLBFlushSeconds,
		"output_workers":                data.FLBOutputWorkers,
		"flb_mem_buf_limit":             data.FLBMemBufLimit,
		"flb_storage_path":              data.FLBStoragePath,
		"flb_storage_backlog_mem_limit": data.FLBStorageBacklogMemLimit,
		"flb_storage_total_limit":       data.FLBStorageTotalLimit,
		"flb_storage_sync":              data.FLBStorageSync,
		"flb_storage_max_chunks_up":     data.FLBStorageMaxChunksUp,
	}).Info("[ConfigGenerator] Push Fluent Bit config generated")

	return nil
}

// GenerateFluentBitConfig generates the Fluent Bit config file with
// per-container tail inputs for monitored containers.
func (g *ConfigGenerator) GenerateFluentBitConfig(plans []logCollectionPlan) error {
	cfg := readTelemetryTemplateConfig()
	tailContainers := make([]MonitoredContainer, 0, len(plans))
	for _, plan := range plans {
		if plan.SourceMode != logSourceTail {
			continue
		}
		name := plan.ContainerName
		if name == "" {
			name = plan.Key.Name
		}
		tailContainers = append(tailContainers, MonitoredContainer{
			Name:    name,
			Image:   plan.Image,
			LogPath: plan.LogPath,
		})
	}
	data := fluentBitTemplateData{
		MonitoredContainers:       tailContainers,
		HasTailInputs:             len(tailContainers) > 0,
		DurableQueue:              cfg.durableQueue,
		FLBFlushSeconds:           cfg.flbFlushSeconds,
		FLBOutputWorkers:          cfg.flbOutputWorkers,
		FLBMemBufLimit:            cfg.flbMemBufLimit,
		FLBTailDBPath:             cfg.flbTailDBPath,
		FLBStorageBacklogMemLimit: cfg.flbStorageBacklogMemLimit,
		FLBStorageTotalLimit:      cfg.flbStorageTotalLimit,
		FLBStoragePath:            cfg.flbStoragePath,
		FLBStorageSync:            cfg.flbStorageSync,
		FLBStorageMaxChunksUp:     cfg.flbStorageMaxChunksUp,
	}

	var buf bytes.Buffer
	if err := g.fbTemplate.Execute(&buf, data); err != nil {
		return fmt.Errorf("failed to execute Fluent Bit template: %w", err)
	}

	if err := atomicWriteFile(g.fbConfigPath, buf.Bytes(), 0644); err != nil {
		return fmt.Errorf("failed to write Fluent Bit config: %w", err)
	}

	logrus.WithFields(logrus.Fields{
		"path":               g.fbConfigPath,
		"monitored":          len(tailContainers),
		"queue_mode_durable": data.DurableQueue,
		"flush_seconds":      data.FLBFlushSeconds,
		"output_workers":     data.FLBOutputWorkers,
		"flb_tail_db":        data.FLBTailDBPath,
		"flb_storage_sync":   data.FLBStorageSync,
	}).Info("[ConfigGenerator] Fluent Bit config generated")

	return nil
}

type liveFluentBitConfig struct {
	flushSeconds  string
	outputWorkers int
	memBufLimit   string
	tailDBPath    string
	storagePath   string
	httpPort      int
	outputPort    int
	outputPath    string
}

func readLiveFluentBitConfig() liveFluentBitConfig {
	flushSeconds := strings.TrimSpace(os.Getenv("FLB_LIVE_FLUSH_SECONDS"))
	if flushSeconds == "" {
		flushSeconds = "0.2"
	}
	outputWorkers := parsePositiveEnvInt("FLB_LIVE_OUTPUT_WORKERS", 2)
	memBufLimit := strings.TrimSpace(os.Getenv("FLB_LIVE_MEM_BUF_LIMIT"))
	if memBufLimit == "" {
		memBufLimit = defaultFlbMemBufLimit
	}
	tailDBPath := strings.TrimSpace(os.Getenv("FLB_LIVE_TAIL_DB_PATH"))
	if tailDBPath == "" {
		tailDBPath = "/dev/shm/flb_live.db"
	}
	return liveFluentBitConfig{
		flushSeconds:  flushSeconds,
		outputWorkers: outputWorkers,
		memBufLimit:   memBufLimit,
		tailDBPath:    tailDBPath,
		storagePath:   filepath.Join(filepath.Dir(tailDBPath), "live-storage"),
		httpPort:      2021,
		outputPort:    localLiveLogIngestPort,
		outputPath:    localLiveLogIngestPath,
	}
}

func (g *ConfigGenerator) GenerateLiveFluentBitConfig(plans []logCollectionPlan) error {
	cfg := readLiveFluentBitConfig()
	tailContainers := make([]MonitoredContainer, 0, len(plans))
	for _, plan := range plans {
		if plan.SourceMode != logSourceTail {
			continue
		}
		name := plan.ContainerName
		if name == "" {
			name = plan.Key.Name
		}
		tailContainers = append(tailContainers, MonitoredContainer{
			Name:    name,
			Image:   plan.Image,
			LogPath: plan.LogPath,
		})
	}

	data := map[string]any{
		"Containers":    tailContainers,
		"HasTailInputs": len(tailContainers) > 0,
		"FlushSeconds":  cfg.flushSeconds,
		"OutputWorkers": cfg.outputWorkers,
		"MemBufLimit":   cfg.memBufLimit,
		"TailDBPath":    cfg.tailDBPath,
		"StoragePath":   cfg.storagePath,
		"HTTPPort":      cfg.httpPort,
		"OutputPort":    cfg.outputPort,
		"OutputPath":    cfg.outputPath,
	}

	var buf bytes.Buffer
	if err := g.fbLiveTemplate.Execute(&buf, data); err != nil {
		return fmt.Errorf("failed to execute live Fluent Bit template: %w", err)
	}
	if err := atomicWriteFile(g.fbLiveConfigPath, buf.Bytes(), 0644); err != nil {
		return fmt.Errorf("failed to write live Fluent Bit config: %w", err)
	}

	logrus.WithFields(logrus.Fields{
		"path":       g.fbLiveConfigPath,
		"containers": len(tailContainers),
		"http_port":  cfg.httpPort,
		"output":     cfg.outputPath,
		"tail_db":    cfg.tailDBPath,
	}).Info("[ConfigGenerator] Live-only Fluent Bit config generated")
	return nil
}
