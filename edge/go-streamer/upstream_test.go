package main

import (
	"math/rand"
	"sync/atomic"
	"testing"
	"time"
)

func newTestUpstreamClient(criticalCap int, telemetryCap int, timeout time.Duration) *upstreamClient {
	return &upstreamClient{
		hostID:                 "test-host",
		critical:               make(chan outboundMessage, criticalCap),
		telemetry:              make(chan outboundMessage, telemetryCap),
		criticalEnqueueTimeout: timeout,
		rng:                    rand.New(rand.NewSource(1)),
		lastDropLogByReason:    map[string]time.Time{},
	}
}

func TestLaneForMessageType(t *testing.T) {
	if got := laneForMessageType("monitoring_toggle_ack"); got != laneCritical {
		t.Fatalf("expected critical lane for control messages, got %s", got)
	}
	if got := laneForMessageType("stats"); got != laneTelemetry {
		t.Fatalf("expected telemetry lane for stats, got %s", got)
	}
	if got := laneForMessageType("logs_output"); got != laneTelemetry {
		t.Fatalf("expected telemetry lane for logs_output, got %s", got)
	}
	if got := laneForMessageType("fast_logs_frame"); got != laneTelemetry {
		t.Fatalf("expected telemetry lane for fast_logs_frame, got %s", got)
	}
	if got := laneForMessageType("log_collection_state_changed"); got != laneCritical {
		t.Fatalf("expected critical lane for log_collection_state_changed, got %s", got)
	}
}

func TestCriticalQueueTimeoutIsExplicitlyCounted(t *testing.T) {
	client := newTestUpstreamClient(1, 1, 20*time.Millisecond)
	client.critical <- outboundMessage{msgType: "inventory", lane: laneCritical, payload: []byte("held")}

	start := time.Now()
	ok := client.enqueue(outboundMessage{msgType: "heartbeat", lane: laneCritical, payload: []byte("x")})
	elapsed := time.Since(start)

	if ok {
		t.Fatalf("expected enqueue to fail on full critical queue")
	}
	if elapsed < 15*time.Millisecond {
		t.Fatalf("expected enqueue to wait for timeout window, elapsed=%s", elapsed)
	}
	if got := atomic.LoadUint64(&client.counters.droppedTimeout); got == 0 {
		t.Fatalf("expected droppedTimeout counter to increment")
	}
}

func TestTelemetryQueueFullDropsImmediately(t *testing.T) {
	client := newTestUpstreamClient(1, 1, 20*time.Millisecond)
	client.telemetry <- outboundMessage{msgType: "stats", lane: laneTelemetry, payload: []byte("held")}

	ok := client.enqueue(outboundMessage{msgType: "stats", lane: laneTelemetry, payload: []byte("x")})
	if ok {
		t.Fatalf("expected telemetry enqueue to fail when queue is full")
	}
	if got := atomic.LoadUint64(&client.counters.droppedQueueFull); got == 0 {
		t.Fatalf("expected droppedQueueFull counter to increment")
	}
}

func TestPendingCriticalRoundTrip(t *testing.T) {
	client := newTestUpstreamClient(1, 1, 20*time.Millisecond)
	msg := outboundMessage{msgType: "monitoring_toggle_ack", lane: laneCritical, payload: []byte("payload")}
	client.enqueueCriticalPending(msg)

	got, ok := client.takePendingCritical()
	if !ok {
		t.Fatalf("expected pending critical message to be available")
	}
	if got.msgType != msg.msgType {
		t.Fatalf("expected msgType %q, got %q", msg.msgType, got.msgType)
	}
	if _, ok := client.takePendingCritical(); ok {
		t.Fatalf("expected pending critical message to be consumed")
	}
}
