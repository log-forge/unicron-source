package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestGenerateOTelConfigIncludesLogsPipelineAndContainerKeyTransform(t *testing.T) {
	t.Setenv("HERALD_NAME", "edge-a")
	t.Setenv("TELEMETRY_MODE", "hybrid")
	t.Setenv("TELEMETRY_QUEUE_MODE", "durable")
	t.Setenv("OTEL_SENDING_QUEUE_SIZE", "1234")

	gen, err := NewConfigGenerator(nil)
	if err != nil {
		t.Fatalf("NewConfigGenerator failed: %v", err)
	}

	tmpDir := t.TempDir()
	gen.otelConfigPath = filepath.Join(tmpDir, "otel-edge.yaml")

	if err := gen.GenerateOTelConfig(); err != nil {
		t.Fatalf("GenerateOTelConfig failed: %v", err)
	}

	data, err := os.ReadFile(gen.otelConfigPath)
	if err != nil {
		t.Fatalf("ReadFile failed: %v", err)
	}
	text := string(data)

	if !strings.Contains(text, "transform/container_key:") {
		t.Fatalf("expected transform/container_key in config, got:\n%s", text)
	}
	if !strings.Contains(text, "logs:") {
		t.Fatalf("expected logs pipeline in config, got:\n%s", text)
	}
	if !strings.Contains(text, "receivers: [otlp]") {
		t.Fatalf("expected logs pipeline to receive from otlp, got:\n%s", text)
	}
	if !strings.Contains(text, "endpoint: ${CENTRAL_MTLS_URL}/unicron/otel") {
		t.Fatalf("expected shared template endpoint in config, got:\n%s", text)
	}
}

func TestGenerateFluentBitConfigsSplitPushAndTailPipelines(t *testing.T) {
	t.Setenv("TELEMETRY_MODE", "hybrid")
	t.Setenv("TELEMETRY_QUEUE_MODE", "durable")
	t.Setenv("FLB_STORAGE_SYNC", "full")
	t.Setenv("FLB_STORAGE_MAX_CHUNKS_UP", "64")
	t.Setenv("FLB_STORAGE_TOTAL_LIMIT", "128MB")
	t.Setenv("FLB_STORAGE_BACKLOG_MEM_LIMIT", "32MB")
	t.Setenv("FLB_MEM_BUF_LIMIT", "16MB")

	gen, err := NewConfigGenerator(nil)
	if err != nil {
		t.Fatalf("NewConfigGenerator failed: %v", err)
	}

	tmpDir := t.TempDir()
	gen.fbPushConfigPath = filepath.Join(tmpDir, "fluent-bit-push.conf")
	gen.fbConfigPath = filepath.Join(tmpDir, "fluent-bit-tail.conf")

	if err := gen.GeneratePushFluentBitConfig(); err != nil {
		t.Fatalf("GeneratePushFluentBitConfig failed: %v", err)
	}
	if err := gen.GenerateFluentBitConfig([]logCollectionPlan{{
		Key:           ContainerKey{Name: "web", Image: "example/app:v1"},
		ContainerName: "web",
		Image:         "example/app:v1",
		LogPath:       "/var/lib/docker/containers/web/web-json.log",
		SourceMode:    logSourceTail,
	}}); err != nil {
		t.Fatalf("GenerateFluentBitConfig failed: %v", err)
	}

	pushData, err := os.ReadFile(gen.fbPushConfigPath)
	if err != nil {
		t.Fatalf("ReadFile push failed: %v", err)
	}
	pushText := string(pushData)
	for _, want := range []string{
		"HTTP_Port     2022",
		"Name          forward",
		"Port          24224",
		"Name          http",
		"Port          9880",
		"Mem_Buf_Limit 16MB",
		"storage.type  filesystem",
		"storage.path  /tmp/flb/push-storage",
		"storage.sync  full",
		"storage.backlog.mem_limit 32MB",
		"storage.max_chunks_up 64",
		"storage.total_limit_size 128MB",
		"Retry_Limit          False",
	} {
		if !strings.Contains(pushText, want) {
			t.Fatalf("expected push config to contain %q, got:\n%s", want, pushText)
		}
	}
	if strings.Contains(pushText, "Name              tail") {
		t.Fatalf("push config must not contain tail inputs, got:\n%s", pushText)
	}

	tailData, err := os.ReadFile(gen.fbConfigPath)
	if err != nil {
		t.Fatalf("ReadFile tail failed: %v", err)
	}
	tailText := string(tailData)
	for _, want := range []string{
		"HTTP_Port     2020",
		"Name              tail",
		"Path              /var/lib/docker/containers/web/web-json.log",
		"storage.path  /tmp/flb/storage",
		"storage.sync  full",
		"storage.max_chunks_up 64",
	} {
		if !strings.Contains(tailText, want) {
			t.Fatalf("expected tail config to contain %q, got:\n%s", want, tailText)
		}
	}
	for _, forbidden := range []string{"Name          forward", "Port          24224", "Port          9880"} {
		if strings.Contains(tailText, forbidden) {
			t.Fatalf("tail config must not contain %q, got:\n%s", forbidden, tailText)
		}
	}
}

func TestReadTelemetryTemplateConfigDefaultsInvalidStorageSync(t *testing.T) {
	t.Setenv("FLB_STORAGE_SYNC", "sometimes")
	t.Setenv("FLB_STORAGE_MAX_CHUNKS_UP", "never")

	cfg := readTelemetryTemplateConfig()
	if cfg.flbStorageSync != "normal" {
		t.Fatalf("expected invalid FLB_STORAGE_SYNC to default to normal, got %q", cfg.flbStorageSync)
	}
	if cfg.flbStorageMaxChunksUp != "" {
		t.Fatalf("expected invalid FLB_STORAGE_MAX_CHUNKS_UP to be omitted, got %q", cfg.flbStorageMaxChunksUp)
	}
}

func TestGenerateLiveFluentBitConfigAvoidsUnsupportedTailOptions(t *testing.T) {
	gen, err := NewConfigGenerator(nil)
	if err != nil {
		t.Fatalf("NewConfigGenerator failed: %v", err)
	}

	tmpDir := t.TempDir()
	gen.fbLiveConfigPath = filepath.Join(tmpDir, "fluent-bit-live.conf")

	err = gen.GenerateLiveFluentBitConfig([]logCollectionPlan{{
		Key:           ContainerKey{Name: "web", Image: "example/app:v1"},
		ContainerName: "web",
		LogPath:       "/var/lib/docker/containers/web/web-json.log",
		SourceMode:    logSourceTail,
	}})
	if err != nil {
		t.Fatalf("GenerateLiveFluentBitConfig failed: %v", err)
	}

	data, err := os.ReadFile(gen.fbLiveConfigPath)
	if err != nil {
		t.Fatalf("ReadFile failed: %v", err)
	}
	text := string(data)
	if !strings.Contains(text, "Read_from_Head                    false") {
		t.Fatalf("expected Read_from_Head in live config, got:\n%s", text)
	}
	if strings.Contains(text, "Read_Newly_Discovered_Files_From_Head") {
		t.Fatalf("unexpected unsupported tail option in live config:\n%s", text)
	}
}
