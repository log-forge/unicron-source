package main

import (
	"context"
	"fmt"
	"hash/fnv"
	"math/rand"
	"net/url"
	"os"
	"os/signal"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/events"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/client"
	"github.com/sirupsen/logrus"
)

type config struct {
	hostID                 string
	centralWSURL           string
	heartbeatInterval      time.Duration
	heartbeatJitterPercent int
	statsCacheTTL          time.Duration
	// mTLS bootstrap fields
	enrollToken       string
	agentName         string
	centralURL        string
	centralMTLSURL    string
	centralRootPrefix string
	caFingerprint     string
	certPath          string
	keyPath           string
	caPath            string
}

func loadConfig() config {
	hostID := os.Getenv("HOST_ID")
	if hostID == "" {
		h, err := os.Hostname()
		if err == nil {
			hostID = h
		} else {
			hostID = "unknown"
		}
	}

	rawCentralWSURL := strings.TrimSpace(os.Getenv("CENTRAL_WS_URL"))
	centralWSURL := rawCentralWSURL
	if centralWSURL == "" {
		centralWSURL = "wss://unicron-central:8443/unicron/api/agent/ws"
	}

	// Heartbeat interval (default 30s)
	heartbeatSeconds := 30
	if val := os.Getenv("HEARTBEAT_INTERVAL_SECONDS"); val != "" {
		if parsed, err := strconv.Atoi(val); err == nil && parsed > 0 {
			heartbeatSeconds = parsed
		}
	}
	heartbeatInterval := time.Duration(heartbeatSeconds) * time.Second
	heartbeatJitterPercent := 20
	if val := os.Getenv("HEARTBEAT_JITTER_PERCENT"); val != "" {
		if parsed, err := strconv.Atoi(val); err == nil && parsed >= 0 && parsed <= 80 {
			heartbeatJitterPercent = parsed
		}
	}

	// Stats cache TTL (default 60s)
	cacheTTLSeconds := 60
	if val := os.Getenv("STATS_CACHE_TTL_SECONDS"); val != "" {
		if parsed, err := strconv.Atoi(val); err == nil && parsed > 0 {
			cacheTTLSeconds = parsed
		}
	}
	statsCacheTTL := time.Duration(cacheTTLSeconds) * time.Second

	// mTLS bootstrap configuration
	enrollToken := os.Getenv("ENROLL_TOKEN")

	agentName := os.Getenv("AGENT_NAME")
	if agentName == "" {
		agentName = hostID // fallback to hostID for SPIFFE identity
	}

	rawCentralURL := strings.TrimSpace(os.Getenv("CENTRAL_URL"))
	centralURL := rawCentralURL
	if centralURL == "" {
		centralURL = "http://unicron-central:8000"
	}
	if strings.TrimSpace(os.Getenv("UNICRON_CENTRAL_FQDN")) == "" {
		for _, candidate := range []string{rawCentralURL, centralWSURL, centralURL} {
			if parsed, err := url.Parse(candidate); err == nil && parsed.Hostname() != "" {
				_ = os.Setenv("UNICRON_CENTRAL_FQDN", parsed.Hostname())
				break
			}
		}
	}

	caFingerprint := strings.TrimSpace(os.Getenv("CA_FINGERPRINT"))
	if caFingerprint == "" {
		fingerprintPath := strings.TrimSpace(os.Getenv("CA_FINGERPRINT_PATH"))
		if fingerprintPath == "" {
			fingerprintPath = "/ca/certs/root_ca_fingerprint.txt"
		}
		if raw, err := os.ReadFile(fingerprintPath); err == nil {
			caFingerprint = strings.TrimSpace(string(raw))
		}
	}

	centralMTLSURL := normalizeCentralMTLSBaseURL(os.Getenv("CENTRAL_MTLS_URL"))
	if centralMTLSURL == "" {
		// Derive from WebSocket URL: wss://host:port/... → https://host:port
		if parsed, err := url.Parse(centralWSURL); err == nil && parsed.Host != "" {
			centralMTLSURL = normalizeCentralMTLSBaseURL("https://" + parsed.Host)
		}
	}

	certPath := os.Getenv("CERT_PATH")
	if certPath == "" {
		certPath = "/agent-data/certs/agent.crt"
	}

	keyPath := os.Getenv("KEY_PATH")
	if keyPath == "" {
		keyPath = "/agent-data/certs/agent.key"
	}

	caPath := os.Getenv("CA_PATH")
	if caPath == "" {
		caPath = "/agent-data/certs/root_ca.crt"
	}

	centralRootPrefix := deriveCentralRootPrefix(centralURL, centralWSURL)

	return config{
		hostID:                 hostID,
		centralWSURL:           centralWSURL,
		heartbeatInterval:      heartbeatInterval,
		heartbeatJitterPercent: heartbeatJitterPercent,
		statsCacheTTL:          statsCacheTTL,
		enrollToken:            enrollToken,
		agentName:              agentName,
		centralURL:             centralURL,
		centralMTLSURL:         centralMTLSURL,
		centralRootPrefix:      centralRootPrefix,
		caFingerprint:          caFingerprint,
		certPath:               certPath,
		keyPath:                keyPath,
		caPath:                 caPath,
	}
}

func makeHeartbeatSeed(hostID string) int64 {
	h := fnv.New64a()
	_, _ = h.Write([]byte(hostID))
	return int64(h.Sum64()) ^ time.Now().UnixNano()
}

func jitteredHeartbeatInterval(base time.Duration, percent int, rng *rand.Rand) time.Duration {
	if base <= 0 {
		return time.Second
	}
	if percent <= 0 {
		return base
	}
	maxDelta := int64(base) * int64(percent) / 100
	if maxDelta <= 0 {
		return base
	}
	delta := rng.Int63n(maxDelta*2+1) - maxDelta
	next := base + time.Duration(delta)
	if next < time.Second {
		return time.Second
	}
	return next
}

func main() {
	// Normalize telemetry queue defaults early so template rendering and
	// child process env inheritance are consistent across run modes.
	ensureTelemetryQueueEnvDefaults()
	cfg := loadConfig()
	telemetryMode := resolveTelemetryMode()
	telemetryQueueMode := resolveTelemetryQueueMode()

	logrus.SetFormatter(&logrus.JSONFormatter{})
	logrus.SetLevel(logrus.InfoLevel)

	logrus.WithFields(logrus.Fields{
		"host_id":              cfg.hostID,
		"central_ws":           cfg.centralWSURL,
		"heartbeat":            cfg.heartbeatInterval,
		"heartbeat_jitter_pct": cfg.heartbeatJitterPercent,
		"telemetry_mode":       telemetryMode,
		"telemetry_queue_mode": telemetryQueueMode,
	}).Info("unicron go-streamer agent starting")

	// Create Docker client
	cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		logrus.WithError(err).Fatal("failed to create docker client")
	}
	defer cli.Close()

	// Log negotiated Docker API/server details for runtime compatibility visibility.
	ctx := context.Background()
	if serverVersion, err := cli.ServerVersion(ctx); err != nil {
		logrus.WithError(err).Warn("failed to query Docker server version")
	} else {
		logrus.WithFields(logrus.Fields{
			"docker_server_version":  serverVersion.Version,
			"docker_api_version":     serverVersion.APIVersion,
			"docker_min_api_version": serverVersion.MinAPIVersion,
			"docker_client_api":      cli.ClientVersion(),
		}).Info("docker api negotiation complete")
	}

	// Create manager
	mgr := newManager(cli, cfg.hostID)

	hasCertificate := prepareAgentCertificate(cfg, 1*time.Hour)

	// Register herald with Central (creates the DB row via mTLS POST).
	// Must happen after bootstrap so we have a certificate, and before
	// WebSocket connect so the herald row exists for inventory persistence.
	if hasCertificate {
		cpuCount := mgr.hostCPUCount
		if cpuCount <= 0 {
			cpuCount = runtime.NumCPU()
		}
		registerAgentWithCentral(cfg, 1*time.Hour, cpuCount)
	}

	// Start certificate renewal loop if certificate exists
	if hasCertificate {
		renewalCfg := renewalConfigFromRuntime(cfg, 1*time.Hour)
		go startAgentRenewalLoop(renewalCfg)
	}

	// Log auth mode based on certificate availability
	if hasCertificate {
		logrus.WithField("cert_path", cfg.certPath).Info("[Auth] Using mTLS mode (client certificate)")
		// Warn if cert files exist but URL is not wss://
		if !strings.HasPrefix(cfg.centralWSURL, "wss://") {
			logrus.WithFields(logrus.Fields{
				"url":       cfg.centralWSURL,
				"cert_path": cfg.certPath,
			}).Warn("[Auth] mTLS certificates found but CENTRAL_WS_URL uses ws:// - connection will NOT be encrypted. Set CENTRAL_WS_URL to wss:// for mTLS.")
		}
	} else {
		logrus.Warn("[Auth] No client certificate available yet; agent WebSocket is mTLS-only and will wait for enrollment/bootstrap")
	}

	// Create upstream WebSocket client to Central
	up := newUpstreamClient(cfg.centralWSURL, cfg.hostID, cfg.certPath, cfg.keyPath, cfg.caPath)
	go up.run()
	mgr.up = up
	up.registerCommandHandler(mgr)

	// Initialize stats streaming components
	statsCache := NewStatsCache(cfg.statsCacheTTL)
	streamManager := NewStreamManager(statsCache, cli, cfg.hostID, up)
	mgr.streamManager = streamManager

	// Start cache cleanup routine
	go func() {
		ticker := time.NewTicker(cfg.statsCacheTTL)
		defer ticker.Stop()
		for range ticker.C {
			statsCache.CleanStaleStats()
		}
	}()

	// Initialize TelemetryManager (OTel + Fluent Bit pipeline)
	telemetryMgr, err := NewTelemetryManager(cli, up, cfg.hostID)
	if err != nil {
		logrus.WithError(err).Fatal("failed to create telemetry manager")
	}
	mgr.telemetryMgr = telemetryMgr
	go telemetryMgr.Start()

	logrus.WithFields(logrus.Fields{
		"heartbeat_interval": cfg.heartbeatInterval,
		"stats_cache_ttl":    cfg.statsCacheTTL,
	}).Info("[Streaming] Initialized streaming architecture")

	// Initial container discovery and stream startup
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		conts, err := cli.ContainerList(ctx, container.ListOptions{All: false})
		if err != nil {
			logrus.WithError(err).Warn("[Discovery] Failed to list running containers")
			return
		}

		logrus.WithField("count", len(conts)).Info("[Discovery] Discovered running containers")

		for _, c := range conts {
			name := c.ID
			if len(c.Names) > 0 {
				name = strings.TrimPrefix(c.Names[0], "/")
			}
			if !streamManager.HasStream(c.ID) {
				if err := streamManager.StartStream(context.Background(), c.ID, name, c.Image); err != nil {
					logrus.WithError(err).WithField("container", name).Warn("[Discovery] Failed to start stream")
				}
			}
		}
	}()

	// Send full container inventory on startup
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		conts, err := cli.ContainerList(ctx, container.ListOptions{All: true})
		if err != nil {
			logrus.WithError(err).Warn("[Inventory] Failed to list containers")
			return
		}

		items := make([]map[string]any, 0, len(conts))
		for _, c := range conts {
			name := ""
			if len(c.Names) > 0 {
				name = strings.TrimPrefix(c.Names[0], "/")
			}

			item := map[string]any{
				"container_id": c.ID,
				"name":         name,
				"image":        c.Image,
				"status":       c.State,
				"labels":       c.Labels,
				"ports":        c.Ports,
				"started_at":   "",
			}

			// Inspect for additional details
			inspectCtx, inspectCancel := context.WithTimeout(context.Background(), 2*time.Second)
			inspect, inspectErr := cli.ContainerInspect(inspectCtx, c.ID)
			inspectCancel()

			if inspectErr == nil {
				if inspect.State != nil {
					item["started_at"] = inspect.State.StartedAt
				}
				if inspect.NetworkSettings != nil {
					item["networks"] = inspect.NetworkSettings.Networks
				}
				if inspect.Mounts != nil {
					item["mounts"] = inspect.Mounts
				}
				if inspect.Config != nil && inspect.Config.Env != nil {
					item["environment"] = inspect.Config.Env
				}
			}

			items = append(items, item)
		}

		payload := map[string]any{
			"host_id":    cfg.hostID,
			"containers": items,
			"timestamp":  time.Now().Unix(),
		}
		up.sendInventory(payload)
		logrus.WithField("count", len(items)).Info("[Inventory] Initial inventory sent")
	}()

	// Docker event stream for container state changes
	go func() {
		logrus.Info("[Events] Starting Docker event stream subscription")

		eventFilters := filters.NewArgs()
		eventFilters.Add("type", "container")
		eventFilters.Add("event", "start")
		eventFilters.Add("event", "stop")
		eventFilters.Add("event", "die")
		eventFilters.Add("event", "restart")
		eventFilters.Add("event", "pause")
		eventFilters.Add("event", "unpause")
		eventFilters.Add("event", "kill")
		eventFilters.Add("event", "destroy")
		eventFilters.Add("event", "health_status")

		for {
			ctx := context.Background()
			eventChan, errChan := cli.Events(ctx, events.ListOptions{
				Filters: eventFilters,
			})

			logrus.Info("[Events] Docker event stream connected")

			for {
				select {
				case event := <-eventChan:
					containerID := event.Actor.ID
					containerName := event.Actor.Attributes["name"]
					eventAction := event.Action

					logrus.WithFields(logrus.Fields{
						"container": containerName,
						"event":     eventAction,
					}).Debug("[Events] Container event received")

					// Inspect container for full state
					inspectCtx, inspectCancel := context.WithTimeout(context.Background(), 2*time.Second)
					inspect, err := cli.ContainerInspect(inspectCtx, containerID)
					inspectCancel()

					// Stream lifecycle management
					if eventAction == "start" && err == nil {
						if !streamManager.HasStream(containerID) {
							image := inspect.Config.Image
							if startErr := streamManager.StartStream(context.Background(), containerID, containerName, image); startErr != nil {
								logrus.WithError(startErr).WithField("container", containerName).Warn("[Events] Failed to start stream")
							}
						}
					}
					if eventAction == "die" || eventAction == "stop" || eventAction == "kill" || eventAction == "destroy" {
						streamManager.StopStream(containerID)
					}

					if err != nil {
						// Container removed - send minimal event
						if eventAction == "die" || eventAction == "stop" || eventAction == "kill" || eventAction == "destroy" {
							state := "exited"
							if eventAction == "destroy" {
								state = "removed"
							}

							// Extract exit code from Docker event attributes (available on die/stop events)
							exitCodeStr := event.Actor.Attributes["exitCode"]
							var exitCode *int
							if exitCodeStr != "" {
								if code, err := strconv.Atoi(exitCodeStr); err == nil {
									exitCode = &code
								}
							}

							up.sendContainerEvent(map[string]any{
								"container_id": containerID,
								"name":         containerName,
								"action":       eventAction,
								"status":       state,
								"image":        "",
								"timestamp":    event.Time,
								"exit_code":    exitCode,
							})
						}
						continue
					}

					// Build event payload with full container metadata (like LogForge)
					name := containerName
					if name == "" && len(inspect.Name) > 0 {
						name = strings.TrimPrefix(inspect.Name, "/")
					}

					containerData := map[string]any{
						"container_id": containerID,
						"name":         name,
						"action":       eventAction,
						"status":       inspect.State.Status,
						"image":        inspect.Config.Image,
						"timestamp":    event.Time,
					}

					// Add exit code for crash classification
					if inspect.State != nil {
						containerData["exit_code"] = inspect.State.ExitCode
					}

					// Add health check data if present
					if inspect.State != nil && inspect.State.Health != nil {
						containerData["has_health_check"] = true
						containerData["health_status"] = inspect.State.Health.Status
					} else {
						containerData["has_health_check"] = false
					}

					// Add labels and compose info for stack filtering
					if inspect.Config != nil && len(inspect.Config.Labels) > 0 {
						containerData["labels"] = inspect.Config.Labels
						if stack, ok := inspect.Config.Labels["com.docker.compose.project"]; ok && stack != "" {
							containerData["compose_stack"] = stack
						} else if stack, ok := inspect.Config.Labels["com.docker.stack.namespace"]; ok && stack != "" {
							containerData["compose_stack"] = stack
						}
						if service, ok := inspect.Config.Labels["com.docker.compose.service"]; ok && service != "" {
							containerData["compose_service"] = service
						}
					}

					// Add ports if exposed
					if inspect.NetworkSettings != nil && len(inspect.NetworkSettings.Ports) > 0 {
						ports := []map[string]any{}
						for port, bindings := range inspect.NetworkSettings.Ports {
							portParts := strings.Split(string(port), "/")
							privatePort := 0
							portType := "tcp"
							if len(portParts) >= 1 {
								fmt.Sscanf(portParts[0], "%d", &privatePort)
							}
							if len(portParts) >= 2 {
								portType = portParts[1]
							}
							for _, binding := range bindings {
								publicPort := 0
								fmt.Sscanf(binding.HostPort, "%d", &publicPort)
								ports = append(ports, map[string]any{
									"PrivatePort": privatePort,
									"PublicPort":  publicPort,
									"Type":        portType,
									"IP":          binding.HostIP,
								})
							}
							if len(bindings) == 0 {
								ports = append(ports, map[string]any{
									"PrivatePort": privatePort,
									"Type":        portType,
								})
							}
						}
						containerData["ports"] = ports
					}

					// Add networks
					if inspect.NetworkSettings != nil && len(inspect.NetworkSettings.Networks) > 0 {
						networks := map[string]any{}
						for netName, netConfig := range inspect.NetworkSettings.Networks {
							networks[netName] = map[string]any{
								"IPAddress": netConfig.IPAddress,
								"Gateway":   netConfig.Gateway,
							}
						}
						containerData["networks"] = networks
					}

					// Add mounts
					if len(inspect.Mounts) > 0 {
						mounts := []map[string]any{}
						for _, mount := range inspect.Mounts {
							mounts = append(mounts, map[string]any{
								"Type":        string(mount.Type),
								"Source":      mount.Source,
								"Destination": mount.Destination,
								"Mode":        mount.Mode,
							})
						}
						containerData["mounts"] = mounts
					}

					// Add started_at timestamp
					if inspect.State != nil && inspect.State.StartedAt != "" {
						containerData["started_at"] = inspect.State.StartedAt
					}

					up.sendContainerEvent(containerData)

					logrus.WithFields(logrus.Fields{
						"container": name,
						"action":    eventAction,
						"status":    inspect.State.Status,
					}).Info("[Events] Container event sent to Central")

				case err := <-errChan:
					logrus.WithError(err).Warn("[Events] Docker event stream error, reconnecting...")
					time.Sleep(2 * time.Second)
					goto reconnect
				}
			}

		reconnect:
			logrus.Info("[Events] Reconnecting to Docker event stream...")
			time.Sleep(1 * time.Second)
		}
	}()

	// Heartbeat loop
	go func() {
		rng := rand.New(rand.NewSource(makeHeartbeatSeed(cfg.hostID)))
		// Spread initial heartbeat send across the interval to avoid sync bursts.
		if cfg.heartbeatInterval > 0 {
			initialSpread := time.Duration(rng.Int63n(int64(cfg.heartbeatInterval)))
			time.Sleep(initialSpread)
		}
		for {
			up.sendHeartbeat()
			logrus.Debug("[Heartbeat] Sent heartbeat to Central")
			time.Sleep(jitteredHeartbeatInterval(cfg.heartbeatInterval, cfg.heartbeatJitterPercent, rng))
		}
	}()

	logrus.Info("unicron go-streamer agent running (press Ctrl+C to stop)")

	// Graceful shutdown handler
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGTERM, syscall.SIGINT)
	go func() {
		<-sigChan
		logrus.Info("Received shutdown signal, stopping telemetry manager...")
		telemetryMgr.Stop()
		os.Exit(0)
	}()

	// Block forever - agent runs until stopped
	select {}
}
