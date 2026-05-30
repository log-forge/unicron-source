package main

import (
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"hash/fnv"
	"math/rand"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
)

// upstreamCommandHandler processes commands received from Central
type upstreamCommandHandler interface {
	HandleCentralCommand(env upstreamEnvelope)
}

type queueLane string

const (
	laneCritical  queueLane = "critical"
	laneTelemetry queueLane = "telemetry"

	defaultCriticalQueueSize        = 1024
	defaultTelemetryQueueSize       = 4096
	defaultCriticalEnqueueTimeoutMs = 5000
	minCriticalEnqueueTimeoutMs     = 100
	defaultWriteDeadline            = 10 * time.Second
	defaultReadDeadline             = 60 * time.Second
	defaultPingInterval             = (60 * time.Second * 9) / 10
	defaultReconnectJitterPercent   = 20
	dropLogInterval                 = 5 * time.Second
)

type outboundMessage struct {
	msgType string
	lane    queueLane
	payload []byte
}

type transportCounters struct {
	queuedCritical   uint64
	queuedTelemetry  uint64
	sentCritical     uint64
	sentTelemetry    uint64
	retriedCritical  uint64
	droppedCritical  uint64
	droppedTelemetry uint64
	droppedMarshal   uint64
	droppedQueueFull uint64
	droppedTimeout   uint64
	droppedWriteErr  uint64
}

type upstreamQueueConfig struct {
	criticalQueueSize        int
	telemetryQueueSize       int
	criticalEnqueueTimeoutMs int
}

func readUpstreamQueueConfig() upstreamQueueConfig {
	criticalQueueSize := parsePositiveEnvIntWithFallback(
		"UPSTREAM_CRITICAL_QUEUE_SIZE",
		defaultCriticalQueueSize,
	)
	telemetryQueueSize := parsePositiveEnvIntWithFallback(
		"UPSTREAM_TELEMETRY_QUEUE_SIZE",
		defaultTelemetryQueueSize,
	)
	criticalEnqueueTimeoutMs := parsePositiveEnvIntWithFallback(
		"UPSTREAM_CRITICAL_ENQUEUE_TIMEOUT_MS",
		defaultCriticalEnqueueTimeoutMs,
	)
	if criticalEnqueueTimeoutMs < minCriticalEnqueueTimeoutMs {
		criticalEnqueueTimeoutMs = minCriticalEnqueueTimeoutMs
	}

	return upstreamQueueConfig{
		criticalQueueSize:        criticalQueueSize,
		telemetryQueueSize:       telemetryQueueSize,
		criticalEnqueueTimeoutMs: criticalEnqueueTimeoutMs,
	}
}

func parsePositiveEnvIntWithFallback(key string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return fallback
	}
	return n
}

// upstreamClient maintains an outbound WebSocket connection to Central
type upstreamClient struct {
	url       string
	hostID    string
	conn      *websocket.Conn
	critical  chan outboundMessage
	telemetry chan outboundMessage
	reconnect chan struct{}
	handler   upstreamCommandHandler
	// mTLS certificate paths
	certPath string
	keyPath  string
	caPath   string
	// revocation tracking
	revoked bool

	criticalEnqueueTimeout time.Duration
	counters               transportCounters
	pendingMu              sync.Mutex
	pendingCritical        *outboundMessage
	rngMu                  sync.Mutex
	rng                    *rand.Rand
	dropLogMu              sync.Mutex
	lastDropLogByReason    map[string]time.Time
}

func newUpstreamClient(url, hostID, certPath, keyPath, caPath string) *upstreamClient {
	cfg := readUpstreamQueueConfig()
	timeout := time.Duration(cfg.criticalEnqueueTimeoutMs) * time.Millisecond

	return &upstreamClient{
		url:                    url,
		hostID:                 hostID,
		critical:               make(chan outboundMessage, cfg.criticalQueueSize),
		telemetry:              make(chan outboundMessage, cfg.telemetryQueueSize),
		reconnect:              make(chan struct{}, 1),
		certPath:               certPath,
		keyPath:                keyPath,
		caPath:                 caPath,
		criticalEnqueueTimeout: timeout,
		rng:                    rand.New(rand.NewSource(makeJitterSeed(hostID))),
		lastDropLogByReason:    map[string]time.Time{},
	}
}

func makeJitterSeed(hostID string) int64 {
	h := fnv.New64a()
	_, _ = h.Write([]byte(hostID))
	return int64(h.Sum64()) ^ time.Now().UnixNano()
}

func (u *upstreamClient) jitterDuration(base time.Duration, percent int) time.Duration {
	if base <= 0 || percent <= 0 {
		return 0
	}
	maxDelta := int64(base) * int64(percent) / 100
	if maxDelta <= 0 {
		return 0
	}

	u.rngMu.Lock()
	delta := u.rng.Int63n(maxDelta*2+1) - maxDelta
	u.rngMu.Unlock()

	return time.Duration(delta)
}

// buildTLSConfig constructs TLS config for the mTLS WebSocket connection.
// Returns nil if certificate materials are not available yet.
func (u *upstreamClient) buildTLSConfig() *tls.Config {
	if u.certPath == "" {
		return nil
	}
	if _, err := os.Stat(u.certPath); os.IsNotExist(err) {
		return nil
	}

	// Load client certificate and private key
	cert, err := tls.LoadX509KeyPair(u.certPath, u.keyPath)
	if err != nil {
		logrus.WithError(err).WithFields(logrus.Fields{
			"cert_path": u.certPath,
			"key_path":  u.keyPath,
		}).Warn("[mTLS] Failed to load client certificate")
		return nil
	}

	// Load CA certificate
	caCert, err := os.ReadFile(u.caPath)
	if err != nil {
		logrus.WithError(err).WithField("ca_path", u.caPath).Warn("[mTLS] Failed to load CA certificate")
		return nil
	}

	caCertPool := x509.NewCertPool()
	if !caCertPool.AppendCertsFromPEM(caCert) {
		logrus.WithField("ca_path", u.caPath).Warn("[mTLS] Failed to parse CA certificate")
		return nil
	}

	return &tls.Config{
		Certificates: []tls.Certificate{cert},
		RootCAs:      caCertPool,
	}
}

func (u *upstreamClient) run() {
	backoff := time.Second
	maxBackoff := 30 * time.Second

	logrus.WithFields(logrus.Fields{
		"critical_queue_size":           cap(u.critical),
		"telemetry_queue_size":          cap(u.telemetry),
		"critical_enqueue_timeout_msec": int(u.criticalEnqueueTimeout / time.Millisecond),
		"critical_policy":               "bounded_wait_then_drop",
		"telemetry_policy":              "drop_new_when_queue_full",
		"reconnect_jitter_percent":      defaultReconnectJitterPercent,
	}).Info("upstream transport policy initialized")

	for {
		// Check if agent was revoked - stop reconnect loop and let manager flow finish.
		if u.revoked {
			logrus.Warn("[mTLS] Agent revoked by Central (close code 1008); stopping upstream reconnect loop")
			return
		}

		// Build TLS config for mTLS (if certs available)
		tlsConfig := u.buildTLSConfig()

		if tlsConfig == nil {
			logrus.WithField("url", u.url).Warn("[mTLS] Client certificate not ready; cannot connect to Central yet")
			time.Sleep(backoff)
			if backoff < maxBackoff {
				backoff *= 2
				if backoff > maxBackoff {
					backoff = maxBackoff
				}
			}
			continue
		}

		dialer := &websocket.Dialer{
			TLSClientConfig:  tlsConfig,
			HandshakeTimeout: 10 * time.Second,
		}
		logrus.WithField("url", u.url).Info("[mTLS] Connecting with client certificate")
		c, _, err := dialer.Dial(u.url, nil)

		if err != nil {
			logrus.WithError(err).WithField("url", u.url).Warn("upstream dial failed")

			// Exponential backoff with jitter to avoid synchronized reconnect storms.
			sleepFor := backoff + u.jitterDuration(backoff, defaultReconnectJitterPercent)
			if sleepFor < 100*time.Millisecond {
				sleepFor = 100 * time.Millisecond
			}
			time.Sleep(sleepFor)

			if backoff < maxBackoff {
				backoff *= 2
				if backoff > maxBackoff {
					backoff = maxBackoff
				}
			}
			continue
		}

		u.conn = c
		logrus.Info("upstream connected to Central")
		backoff = time.Second

		done := make(chan struct{})
		go u.writePump(done)
		u.readPump(done)
		<-done
		u.conn = nil

		// Check for revocation after readPump returns
		if u.revoked {
			logrus.Warn("[mTLS] Agent revoked by Central (close code 1008); stopping upstream reconnect loop")
			return
		}

		logrus.WithFields(u.transportCounterFields()).Info("upstream transport counters snapshot")
		logrus.Info("upstream disconnected; will reconnect")
	}
}

func (u *upstreamClient) writePump(done chan struct{}) {
	ticker := time.NewTicker(defaultPingInterval)
	defer func() {
		ticker.Stop()
		close(done)
	}()

	for {
		if pending, ok := u.takePendingCritical(); ok {
			if !u.writeOne(*pending) {
				return
			}
			continue
		}

		// Strict priority: if critical queue has data, send it before telemetry.
		select {
		case msg := <-u.critical:
			if !u.writeOne(msg) {
				return
			}
			continue
		default:
		}

		select {
		case msg := <-u.critical:
			if !u.writeOne(msg) {
				return
			}
		case msg := <-u.telemetry:
			if !u.writeOne(msg) {
				return
			}
		case <-ticker.C:
			if u.conn == nil {
				continue
			}
			u.conn.SetWriteDeadline(time.Now().Add(defaultWriteDeadline))
			if err := u.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

func (u *upstreamClient) writeOne(msg outboundMessage) bool {
	if u.conn == nil {
		if msg.lane == laneCritical {
			u.enqueueCriticalPending(msg)
			atomic.AddUint64(&u.counters.retriedCritical, 1)
			return false
		}
		u.recordDrop(msg, "conn_unavailable")
		return false
	}

	u.conn.SetWriteDeadline(time.Now().Add(defaultWriteDeadline))
	if err := u.conn.WriteMessage(websocket.TextMessage, msg.payload); err != nil {
		atomic.AddUint64(&u.counters.droppedWriteErr, 1)
		if msg.lane == laneCritical {
			u.enqueueCriticalPending(msg)
			atomic.AddUint64(&u.counters.retriedCritical, 1)
		} else {
			u.recordDrop(msg, "write_failure")
		}
		_ = u.conn.Close()
		return false
	}

	if msg.lane == laneCritical {
		atomic.AddUint64(&u.counters.sentCritical, 1)
	} else {
		atomic.AddUint64(&u.counters.sentTelemetry, 1)
	}
	return true
}

func (u *upstreamClient) enqueueCriticalPending(msg outboundMessage) {
	u.pendingMu.Lock()
	defer u.pendingMu.Unlock()
	u.pendingCritical = &msg
}

func (u *upstreamClient) takePendingCritical() (*outboundMessage, bool) {
	u.pendingMu.Lock()
	defer u.pendingMu.Unlock()
	if u.pendingCritical == nil {
		return nil, false
	}
	msg := *u.pendingCritical
	u.pendingCritical = nil
	return &msg, true
}

func (u *upstreamClient) readPump(done chan struct{}) {
	defer func() {
		if u.conn != nil {
			u.conn.Close()
		}
	}()

	u.conn.SetReadDeadline(time.Now().Add(defaultReadDeadline))
	u.conn.SetPongHandler(func(string) error {
		u.conn.SetReadDeadline(time.Now().Add(defaultReadDeadline))
		return nil
	})

	for {
		_, data, err := u.conn.ReadMessage()
		if err != nil {
			// Check if this is a WebSocket close error with code 1008 (Policy Violation / Revocation)
			if closeErr, ok := err.(*websocket.CloseError); ok {
				if closeErr.Code == 1008 {
					logrus.WithField("code", closeErr.Code).Error("[mTLS] Agent revoked by Central (close code 1008)")
					u.revoked = true
					return
				}
			}
			// For other errors (network, other close codes), continue normal reconnect flow
			return
		}
		var env upstreamEnvelope
		if err := json.Unmarshal(data, &env); err != nil {
			continue
		}
		if u.handler != nil {
			u.handler.HandleCentralCommand(env)
		}
	}
}

func (u *upstreamClient) registerCommandHandler(h upstreamCommandHandler) {
	u.handler = h
}

// upstreamEnvelope is the message envelope for all agent-to-Central communication
type upstreamEnvelope struct {
	Type   string          `json:"type"` // "inventory" | "container_event" | "heartbeat" | "metrics" | "stats"
	HostID string          `json:"host_id"`
	Data   json.RawMessage `json:"data"`
}

func laneForMessageType(messageType string) queueLane {
	switch messageType {
	case "stats", "metrics", "exec_output", "logs_output", "fast_logs_frame", "fast_logs_error":
		return laneTelemetry
	case "log_collection_state_changed":
		return laneCritical
	default:
		return laneCritical
	}
}

func (u *upstreamClient) recordDrop(msg outboundMessage, reason string) {
	if msg.lane == laneCritical {
		atomic.AddUint64(&u.counters.droppedCritical, 1)
	} else {
		atomic.AddUint64(&u.counters.droppedTelemetry, 1)
	}
	switch reason {
	case "marshal_error":
		atomic.AddUint64(&u.counters.droppedMarshal, 1)
	case "queue_full":
		atomic.AddUint64(&u.counters.droppedQueueFull, 1)
	case "enqueue_timeout":
		atomic.AddUint64(&u.counters.droppedTimeout, 1)
	case "write_failure":
		atomic.AddUint64(&u.counters.droppedWriteErr, 1)
	}

	now := time.Now()
	shouldLog := false
	u.dropLogMu.Lock()
	last, ok := u.lastDropLogByReason[reason]
	if !ok || now.Sub(last) >= dropLogInterval {
		u.lastDropLogByReason[reason] = now
		shouldLog = true
	}
	u.dropLogMu.Unlock()

	if shouldLog {
		logrus.WithFields(logrus.Fields{
			"type":                msg.msgType,
			"lane":                msg.lane,
			"reason":              reason,
			"critical_queue_len":  len(u.critical),
			"telemetry_queue_len": len(u.telemetry),
		}).Warn("upstream transport drop")
	}
}

func (u *upstreamClient) transportCounterFields() logrus.Fields {
	return logrus.Fields{
		"queued_critical":    atomic.LoadUint64(&u.counters.queuedCritical),
		"queued_telemetry":   atomic.LoadUint64(&u.counters.queuedTelemetry),
		"sent_critical":      atomic.LoadUint64(&u.counters.sentCritical),
		"sent_telemetry":     atomic.LoadUint64(&u.counters.sentTelemetry),
		"retried_critical":   atomic.LoadUint64(&u.counters.retriedCritical),
		"dropped_critical":   atomic.LoadUint64(&u.counters.droppedCritical),
		"dropped_telemetry":  atomic.LoadUint64(&u.counters.droppedTelemetry),
		"dropped_marshal":    atomic.LoadUint64(&u.counters.droppedMarshal),
		"dropped_queue_full": atomic.LoadUint64(&u.counters.droppedQueueFull),
		"dropped_timeout":    atomic.LoadUint64(&u.counters.droppedTimeout),
		"dropped_write_err":  atomic.LoadUint64(&u.counters.droppedWriteErr),
	}
}

func (u *upstreamClient) enqueue(msg outboundMessage) bool {
	switch msg.lane {
	case laneCritical:
		timer := time.NewTimer(u.criticalEnqueueTimeout)
		defer timer.Stop()
		select {
		case u.critical <- msg:
			atomic.AddUint64(&u.counters.queuedCritical, 1)
			return true
		case <-timer.C:
			u.recordDrop(msg, "enqueue_timeout")
			return false
		}
	case laneTelemetry:
		select {
		case u.telemetry <- msg:
			atomic.AddUint64(&u.counters.queuedTelemetry, 1)
			return true
		default:
			u.recordDrop(msg, "queue_full")
			return false
		}
	default:
		u.recordDrop(msg, "unknown_lane")
		return false
	}
}

func (u *upstreamClient) enqueueEnvelope(
	messageType string,
	hostID string,
	payload any,
	lane queueLane,
) {
	b, err := json.Marshal(payload)
	if err != nil {
		msg := outboundMessage{msgType: messageType, lane: lane}
		u.recordDrop(msg, "marshal_error")
		return
	}
	env := upstreamEnvelope{Type: messageType, HostID: hostID, Data: b}
	wire, err := json.Marshal(env)
	if err != nil {
		msg := outboundMessage{msgType: messageType, lane: lane}
		u.recordDrop(msg, "marshal_error")
		return
	}

	_ = u.enqueue(outboundMessage{
		msgType: messageType,
		lane:    lane,
		payload: wire,
	})
}

func (u *upstreamClient) sendInventory(payload map[string]any) {
	u.enqueueEnvelope("inventory", u.hostID, payload, laneCritical)
}

func (u *upstreamClient) sendContainerEvent(payload map[string]any) {
	u.enqueueEnvelope("container_event", u.hostID, payload, laneCritical)
}

func (u *upstreamClient) sendHeartbeat() {
	payload := map[string]any{"timestamp": time.Now().Unix()}
	u.enqueueEnvelope("heartbeat", u.hostID, payload, laneCritical)
}

func (u *upstreamClient) sendMetrics(frame metricsFrame) {
	u.enqueueEnvelope("metrics", frame.HostID, frame, laneTelemetry)
}

func (u *upstreamClient) sendStats(payload map[string]any) {
	u.enqueueEnvelope("stats", u.hostID, payload, laneTelemetry)
}

func (u *upstreamClient) sendEnvelope(env upstreamEnvelope) {
	env.HostID = u.hostID
	wire, err := json.Marshal(env)
	if err != nil {
		msg := outboundMessage{
			msgType: env.Type,
			lane:    laneForMessageType(env.Type),
		}
		u.recordDrop(msg, "marshal_error")
		return
	}
	_ = u.enqueue(outboundMessage{
		msgType: env.Type,
		lane:    laneForMessageType(env.Type),
		payload: wire,
	})
}
