.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash

DOCKER ?= docker
COMPOSE ?= $(DOCKER) compose
BUILDX ?= $(DOCKER) buildx
BUILDX_BUILDER ?= default
LOCAL_BUILD_ENV ?= BUILDX_BUILDER=default

DIND_COMPOSE_FILE ?= ops/dind/docker-compose.dind.yaml
CENTRAL_COMPOSE_FILE ?= ops/unicron/docker-compose.unicron.yaml
CENTRAL_ENV_FILE ?= ops/unicron/.env
CENTRAL_AUTH_TEST_MONGO_COMPOSE_FILE ?= ops/testing/docker-compose.central-auth-test-mongo.yml
CENTRAL_AUTH_TEST_MONGO_PORT ?= 27018
CENTRAL_AUTH_TEST_MONGO_ROOT_USERNAME ?= root
CENTRAL_AUTH_TEST_MONGO_ROOT_PASSWORD ?= password
CENTRAL_AUTH_TEST_MONGODB_DB_NAME ?= central_auth_test

REGISTRY ?= localhost:5000
TAG ?= latest
WAIT_TIMEOUT ?= 300
RELEASE_PLATFORMS ?= linux/amd64,linux/arm64

CENTRAL_ENV_ARG = $(if $(wildcard $(CENTRAL_ENV_FILE)),--env-file $(CENTRAL_ENV_FILE),)
CENTRAL_COMPOSE = $(LOCAL_BUILD_ENV) $(COMPOSE) -f $(CENTRAL_COMPOSE_FILE) $(CENTRAL_ENV_ARG)
CENTRAL_AUTH_TEST_MONGODB_URI ?= mongodb://$(CENTRAL_AUTH_TEST_MONGO_ROOT_USERNAME):$(CENTRAL_AUTH_TEST_MONGO_ROOT_PASSWORD)@127.0.0.1:$(CENTRAL_AUTH_TEST_MONGO_PORT)/?authSource=admin
CENTRAL_AUTH_TEST_MONGO_COMPOSE = $(LOCAL_BUILD_ENV) $(COMPOSE) -f $(CENTRAL_AUTH_TEST_MONGO_COMPOSE_FILE)
DIND_COMPOSE = $(LOCAL_BUILD_ENV) $(COMPOSE) -f $(DIND_COMPOSE_FILE)

OTEL_MIN_IMAGE ?= unicron-otel-min
OTEL_MIN_LOCAL_REF ?= $(OTEL_MIN_IMAGE):$(TAG)
OTEL_MIN_REMOTE_REF ?= logforge/unicron-otel-min:$(TAG)

FLUENT_BIT_MIN_IMAGE ?= unicron-fluent-bit-min
FLUENT_BIT_MIN_LOCAL_REF ?= $(FLUENT_BIT_MIN_IMAGE):$(TAG)
FLUENT_BIT_MIN_REMOTE_REF ?= logforge/unicron-fluent-bit-min:$(TAG)

GO_STREAMER_IMAGE ?= unicron-go-streamer
GO_STREAMER_LOCAL_REF ?= $(GO_STREAMER_IMAGE):$(TAG)
GO_STREAMER_REMOTE_REF ?= $(REGISTRY)/$(GO_STREAMER_IMAGE):$(TAG)
AGENT_REMOTE_REF ?= logforge/unicron-agent:$(TAG)

APPLIANCE_IMAGE ?= unicron-appliance
APPLIANCE_LOCAL_REF ?= $(APPLIANCE_IMAGE):$(TAG)
APPLIANCE_REMOTE_REF ?= logforge/unicron:$(TAG)
APPLIANCE_CONTAINER ?= unicron-appliance
APPLIANCE_DATA_VOLUME ?= unicron-data
APPLIANCE_ENV_FILE ?= ops/appliance/.env.local
APPLIANCE_FQDN ?= localhost
APPLIANCE_HTTP_PORT ?= 8080
APPLIANCE_HTTPS_PORT ?= 8444
APPLIANCE_MTLS_PORT ?= 9443
APPLIANCE_URL ?= https://localhost:$(APPLIANCE_HTTPS_PORT)/unicron
APPLIANCE_AGENT_IMAGE ?= logforge/unicron-agent:latest
APPLIANCE_UPDATE_IMAGE_REF ?= logforge/unicron:latest
APPLIANCE_NETWORK ?= unicron-network
APPLIANCE_NETWORK_ALIAS ?= unicron.central

.PHONY: \
	help \
	up \
	down \
	agent-down \
	dind-up \
	dind-down \
	rollout \
	rollout-edge \
	rollout-central \
	central-up \
	central-pki-init \
	central-down \
	central-destroy \
	central-migrate \
	central-auth-test-mongo-up \
	central-auth-test-mongo-down \
	central-auth-test-mongo-destroy \
	test-central-auth \
	build-otel-min \
	build-fluent-bit-min \
	build-go-streamer \
	build-central-backend \
	build-central-frontend \
	build-alert-engine \
	build-notifier \
	build-appliance \
	build-up \
	push-go-streamer \
	push-otel-min \
	push-fluent-bit-min \
	push-agent-bases \
	push-appliance \
	push-agent \
	push-logforge-images

help: ## Show rollout targets
	@echo "Usage: make <target>"
	@echo ""
	@awk -F':.*## ' '/^[a-zA-Z0-9._-]+:.*##/ { printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

up: push-go-streamer central-up ## Bring up the full development stack, publish go-streamer for DinD, and wait for readiness
	@echo ""
	@echo "Development stacks are up."

down: central-down agent-down dind-down ## Tear down development stacks, enrolled agents, and dind
	@echo ""
	@echo "Rollout teardown complete."

dind-up: ## Bring up the dind development stack and wait for readiness
	@echo ""
	@echo "Starting dind development stack..."
	@$(DIND_COMPOSE) up -d --build --wait --wait-timeout $(WAIT_TIMEOUT)

dind-down: ## Tear down the dind development stack
	@echo ""
	@echo "Stopping dind development stack..."
	@$(DIND_COMPOSE) down || true

agent-down: ## Stop/remove enrolled agent containers and agent volumes
	@echo ""
	@echo "Cleaning up enrolled agent containers..."
	@set -e; \
		AGENT_CONTAINERS=$$( \
			( $(DOCKER) ps -aq --filter "name=unicron-agent-" || true; \
			  $(DOCKER) ps -aq --filter "name=unicron-go-streamer" || true; \
			  $(DOCKER) ps -aq --filter "name=go-streamer" || true ) \
			| sort -u | tr '\n' ' ' \
		); \
		if [ -n "$$AGENT_CONTAINERS" ]; then \
			echo "Removing containers: $$AGENT_CONTAINERS"; \
			$(DOCKER) rm -f $$AGENT_CONTAINERS >/dev/null; \
		else \
			echo "No agent containers found."; \
		fi
	@echo "Cleaning up enrolled agent volumes..."
	@set -e; \
		AGENT_VOLUMES=$$($(DOCKER) volume ls -q | grep -E '^(unicron-agent-|unicron-go-streamer-)' || true); \
		if [ -n "$$AGENT_VOLUMES" ]; then \
			echo "$$AGENT_VOLUMES" | tr '\n' ' ' | sed 's/^/Removing volumes: /'; \
			echo "$$AGENT_VOLUMES" | xargs -r $(DOCKER) volume rm -f >/dev/null; \
		else \
			echo "No agent volumes found."; \
		fi

rollout: dind-up rollout-edge rollout-central ## Build the local LogForge Unicron image set and publish go-streamer
	@echo ""
	@echo "Rollout complete."

rollout-edge: build-otel-min build-fluent-bit-min push-go-streamer ## Build edge images and publish go-streamer
	@echo ""
	@echo "Edge rollout complete."

rollout-central: build-central-backend build-central-frontend build-alert-engine build-notifier ## Build central images locally
	@echo ""
	@echo "Central rollout complete."

central-up: ## Bring up the central stack, run migrations, and wait for readiness
	@echo ""
	@$(MAKE) -f $(lastword $(MAKEFILE_LIST)) central-pki-init
	@echo "Starting central Postgres and waiting for readiness..."
	@$(CENTRAL_COMPOSE) up -d --wait --wait-timeout $(WAIT_TIMEOUT) postgres
	@echo "Building backend image for central migration..."
	@$(CENTRAL_COMPOSE) build backend
	@$(MAKE) -f $(lastword $(MAKEFILE_LIST)) central-migrate
	@echo "Starting central stack..."
	@$(CENTRAL_COMPOSE) up -d --build --remove-orphans --wait --wait-timeout $(WAIT_TIMEOUT)

central-pki-init: ## Explicitly initialize/validate central PKI material before runtime startup
	@echo ""
	@echo "Initializing central PKI material..."
	@$(CENTRAL_COMPOSE) --profile init run --rm stepca-init

central-down: ## Stop/remove central containers while preserving persistent volumes
	@echo ""
	@echo "Stopping central compose project and preserving persistent volumes..."
	@$(CENTRAL_COMPOSE) down --remove-orphans || true

central-destroy: ## Destructively remove central containers and persistent volumes
	@echo ""
	@echo "Destroying central compose project and persistent volumes..."
	@$(CENTRAL_COMPOSE) down -v --remove-orphans || true

central-migrate: ## Run central backend migrations
	@echo ""
	@echo "Running central backend migrations..."
	@$(CENTRAL_COMPOSE) run --rm --no-deps backend \
		python /app/backend/scripts/migrate_or_bootstrap.py

central-auth-test-mongo-up: ## Start disposable central-auth test Mongo and wait for readiness
	@echo ""
	@echo "Starting central-auth test Mongo on 127.0.0.1:$(CENTRAL_AUTH_TEST_MONGO_PORT)..."
	@CENTRAL_AUTH_TEST_MONGO_PORT="$(CENTRAL_AUTH_TEST_MONGO_PORT)" \
		CENTRAL_AUTH_TEST_MONGO_ROOT_USERNAME="$(CENTRAL_AUTH_TEST_MONGO_ROOT_USERNAME)" \
		CENTRAL_AUTH_TEST_MONGO_ROOT_PASSWORD="$(CENTRAL_AUTH_TEST_MONGO_ROOT_PASSWORD)" \
		CENTRAL_AUTH_TEST_MONGODB_DB_NAME="$(CENTRAL_AUTH_TEST_MONGODB_DB_NAME)" \
		$(CENTRAL_AUTH_TEST_MONGO_COMPOSE) up -d --wait --wait-timeout $(WAIT_TIMEOUT)

central-auth-test-mongo-down: ## Stop central-auth test Mongo while preserving its disposable volume
	@echo ""
	@echo "Stopping central-auth test Mongo..."
	@CENTRAL_AUTH_TEST_MONGO_PORT="$(CENTRAL_AUTH_TEST_MONGO_PORT)" \
		CENTRAL_AUTH_TEST_MONGO_ROOT_USERNAME="$(CENTRAL_AUTH_TEST_MONGO_ROOT_USERNAME)" \
		CENTRAL_AUTH_TEST_MONGO_ROOT_PASSWORD="$(CENTRAL_AUTH_TEST_MONGO_ROOT_PASSWORD)" \
		CENTRAL_AUTH_TEST_MONGODB_DB_NAME="$(CENTRAL_AUTH_TEST_MONGODB_DB_NAME)" \
		$(CENTRAL_AUTH_TEST_MONGO_COMPOSE) down --remove-orphans || true

central-auth-test-mongo-destroy: ## Destructively remove central-auth test Mongo and its disposable volume
	@echo ""
	@echo "Destroying central-auth test Mongo and volume..."
	@CENTRAL_AUTH_TEST_MONGO_PORT="$(CENTRAL_AUTH_TEST_MONGO_PORT)" \
		CENTRAL_AUTH_TEST_MONGO_ROOT_USERNAME="$(CENTRAL_AUTH_TEST_MONGO_ROOT_USERNAME)" \
		CENTRAL_AUTH_TEST_MONGO_ROOT_PASSWORD="$(CENTRAL_AUTH_TEST_MONGO_ROOT_PASSWORD)" \
		CENTRAL_AUTH_TEST_MONGODB_DB_NAME="$(CENTRAL_AUTH_TEST_MONGODB_DB_NAME)" \
		$(CENTRAL_AUTH_TEST_MONGO_COMPOSE) down -v --remove-orphans || true

test-central-auth: central-auth-test-mongo-up ## Run central-auth unit and integration tests against disposable Mongo
	@echo ""
	@echo "Running central-auth tests against $(CENTRAL_AUTH_TEST_MONGODB_URI)"
	@CENTRAL_AUTH_TEST_MONGODB_URI="$(CENTRAL_AUTH_TEST_MONGODB_URI)" \
		CENTRAL_AUTH_TEST_MONGODB_DB_NAME="$(CENTRAL_AUTH_TEST_MONGODB_DB_NAME)" \
		npm --prefix central/auth run test:all

define docker_build_only
	@echo ""
	@echo "==> Building $(1)"
	@$(LOCAL_BUILD_ENV) $(DOCKER) build $(2) -t $(3) -f $(4) $(5)
endef

define docker_tag_push
	@echo "==> Tagging $(1) as $(2)"
	@$(DOCKER) tag $(1) $(2)
	@echo "==> Pushing $(2)"
	@$(DOCKER) push $(2)
endef

define docker_buildx_push
	@echo ""
	@echo "==> Building and pushing $(1) for $(RELEASE_PLATFORMS)"
	@$(BUILDX) build \
		--builder $(BUILDX_BUILDER) \
		--platform $(RELEASE_PLATFORMS) \
		$(2) \
		-t $(3) \
		-f $(4) \
		--push \
		$(5)
endef

define docker_build_tag_push
	$(call docker_build_only,$(1),$(2),$(3),$(4),$(5))
	$(call docker_tag_push,$(3),$(6))
endef

define compose_build_only
	@echo ""
	@echo "==> Building $(1) from compose"
	@$(2) build $(1)
endef

build-otel-min: ## Build the local unicron-otel-min image
	$(call docker_build_only,otel-min,,$(OTEL_MIN_LOCAL_REF),edge/otel-min/Dockerfile,edge/otel-min)

build-fluent-bit-min: ## Build the local unicron-fluent-bit-min image
	$(call docker_build_only,fluent-bit-min,,$(FLUENT_BIT_MIN_LOCAL_REF),edge/fluent-bit-min/Dockerfile,edge/fluent-bit-min)

build-go-streamer: build-otel-min build-fluent-bit-min ## Build the local unicron-go-streamer image
	$(call docker_build_only,go-streamer,--build-arg OTEL_MIN_IMAGE=$(OTEL_MIN_LOCAL_REF) --build-arg FLUENT_BIT_MIN_IMAGE=$(FLUENT_BIT_MIN_LOCAL_REF),$(GO_STREAMER_LOCAL_REF),edge/go-streamer/Dockerfile,edge/go-streamer)

push-go-streamer: dind-up build-go-streamer ## Build and push unicron-go-streamer
	$(call docker_tag_push,$(GO_STREAMER_LOCAL_REF),$(GO_STREAMER_REMOTE_REF))

push-otel-min: ## Build and push the public OTel base image for release platforms
	$(call docker_buildx_push,otel-min,,$(OTEL_MIN_REMOTE_REF),edge/otel-min/Dockerfile,edge/otel-min)

push-fluent-bit-min: ## Build and push the public Fluent Bit base image for release platforms
	$(call docker_buildx_push,fluent-bit-min,,$(FLUENT_BIT_MIN_REMOTE_REF),edge/fluent-bit-min/Dockerfile,edge/fluent-bit-min)

push-agent-bases: push-otel-min push-fluent-bit-min ## Build and push public multi-arch agent base images

push-agent: push-agent-bases ## Build and push the public LogForge Unicron agent image for release platforms
	$(call docker_buildx_push,agent,--build-arg OTEL_MIN_IMAGE=$(OTEL_MIN_REMOTE_REF) --build-arg FLUENT_BIT_MIN_IMAGE=$(FLUENT_BIT_MIN_REMOTE_REF),$(AGENT_REMOTE_REF),edge/go-streamer/Dockerfile,edge/go-streamer)

build-central-backend: ## Build unicron-backend locally using compose
	$(call compose_build_only,backend,$(CENTRAL_COMPOSE))

build-central-frontend: ## Build unicron-frontend locally using compose
	$(call compose_build_only,frontend,$(CENTRAL_COMPOSE))

build-alert-engine: ## Build unicron-alert-engine locally using compose
	$(call compose_build_only,alert-engine,$(CENTRAL_COMPOSE))

build-notifier: ## Build unicron-notifier locally using compose
	$(call compose_build_only,notifier,$(CENTRAL_COMPOSE))

build-appliance: ## Build the single-image greenfield appliance
	$(call docker_build_only,appliance,,$(APPLIANCE_LOCAL_REF),ops/appliance/Dockerfile,.)

push-appliance: ## Build and push the public LogForge Unicron appliance image for release platforms
	$(call docker_buildx_push,appliance,,$(APPLIANCE_REMOTE_REF),ops/appliance/Dockerfile,.)

push-logforge-images: push-appliance push-agent ## Build and push public LogForge Unicron release images

build-up: build-appliance ## Build and run the single-image appliance, then print the local URL
	@set -e; \
		if [ ! -s "$(APPLIANCE_ENV_FILE)" ]; then \
			command -v openssl >/dev/null 2>&1 || { echo "openssl is required to generate $(APPLIANCE_ENV_FILE)" >&2; exit 1; }; \
			mkdir -p "$$(dirname "$(APPLIANCE_ENV_FILE)")"; \
			{ \
				printf 'UNICRON_CENTRAL_FQDN=%s\n' "$(APPLIANCE_FQDN)"; \
				printf 'POSTGRES_PASSWORD=%s\n' "$$(openssl rand -hex 24)"; \
				printf 'CENTRAL_AUTH_SECRET=%s\n' "$$(openssl rand -hex 32)"; \
				printf 'CENTRAL_ADMIN_USERNAME=%s\n' "admin"; \
				printf 'CENTRAL_ADMIN_RECOVERY_OVERRIDE=%s\n' "false"; \
				printf 'REMOTE_AGENT_IMAGE=%s\n' "$(APPLIANCE_AGENT_IMAGE)"; \
				printf 'UNICRON_UPDATE_IMAGE_REF=%s\n' "$(APPLIANCE_UPDATE_IMAGE_REF)"; \
				printf 'INTERNAL_API_SECRET=%s\n' "$$(openssl rand -hex 32)"; \
				printf 'CSRF_COOKIE_SECRET=%s\n' "$$(openssl rand -hex 32)"; \
				printf 'CSRF_SECRET=%s\n' "$$(openssl rand -hex 32)"; \
				printf 'STEP_CA_PASSWORD=%s\n' "$$(openssl rand -hex 24)"; \
				printf 'STEP_CA_PROVISIONER_PASSWORD=%s\n' "$$(openssl rand -hex 24)"; \
				printf 'STEP_CA_RA_PASSWORD=%s\n' "$$(openssl rand -hex 24)"; \
			} > "$(APPLIANCE_ENV_FILE)"; \
			chmod 0600 "$(APPLIANCE_ENV_FILE)"; \
			echo "Generated $(APPLIANCE_ENV_FILE)"; \
		else \
			echo "Using existing $(APPLIANCE_ENV_FILE)"; \
			if ! grep -q '^CENTRAL_ADMIN_RECOVERY_OVERRIDE=' "$(APPLIANCE_ENV_FILE)"; then \
				printf 'CENTRAL_ADMIN_RECOVERY_OVERRIDE=%s\n' "false" >> "$(APPLIANCE_ENV_FILE)"; \
				echo "Added CENTRAL_ADMIN_RECOVERY_OVERRIDE to $(APPLIANCE_ENV_FILE)"; \
			fi; \
			if ! grep -q '^REMOTE_AGENT_IMAGE=' "$(APPLIANCE_ENV_FILE)"; then \
				printf 'REMOTE_AGENT_IMAGE=%s\n' "$(APPLIANCE_AGENT_IMAGE)" >> "$(APPLIANCE_ENV_FILE)"; \
				echo "Added REMOTE_AGENT_IMAGE to $(APPLIANCE_ENV_FILE)"; \
			fi; \
			if ! grep -q '^UNICRON_UPDATE_IMAGE_REF=' "$(APPLIANCE_ENV_FILE)"; then \
				printf 'UNICRON_UPDATE_IMAGE_REF=%s\n' "$(APPLIANCE_UPDATE_IMAGE_REF)" >> "$(APPLIANCE_ENV_FILE)"; \
				echo "Added UNICRON_UPDATE_IMAGE_REF to $(APPLIANCE_ENV_FILE)"; \
			fi; \
		fi
	@set -e; \
		username="$$(sed -n 's/^CENTRAL_ADMIN_USERNAME=//p' "$(APPLIANCE_ENV_FILE)" | tail -n 1)"; \
		configured_password="$$(sed -n 's/^CENTRAL_ADMIN_PASSWORD=//p' "$(APPLIANCE_ENV_FILE)" | tail -n 1)"; \
		recovery_override="$$(sed -n 's/^CENTRAL_ADMIN_RECOVERY_OVERRIDE=//p' "$(APPLIANCE_ENV_FILE)" | tail -n 1)"; \
		if [ -z "$$username" ]; then username="admin"; fi; \
		if [ -z "$$recovery_override" ]; then recovery_override="false"; fi; \
		recovery_override="$$(printf '%s' "$$recovery_override" | tr '[:upper:]' '[:lower:]')"; \
		recovery_override_enabled="false"; \
		case "$$recovery_override" in true|1|yes|on) recovery_override_enabled="true";; esac; \
		admin_password="$$configured_password"; \
		admin_password_source="configured"; \
		admin_env_args=(); \
		if [ "$$recovery_override_enabled" = "true" ] && [ -z "$$configured_password" ]; then \
			admin_password_source="missing-recovery"; \
			echo "Warning: CENTRAL_ADMIN_RECOVERY_OVERRIDE=$$recovery_override but CENTRAL_ADMIN_PASSWORD is not set; startup will fail until CENTRAL_ADMIN_PASSWORD is configured." >&2; \
		elif [ -z "$$configured_password" ]; then \
			command -v openssl >/dev/null 2>&1 || { echo "openssl is required to generate the initial admin password" >&2; exit 1; }; \
			admin_password="Unicron-$$(openssl rand -base64 18)-A1!"; \
			admin_password_source="generated"; \
			admin_env_args=(-e "CENTRAL_ADMIN_PASSWORD=$$admin_password"); \
		fi; \
		if ! $(DOCKER) network inspect "$(APPLIANCE_NETWORK)" >/dev/null 2>&1; then \
			echo "Creating Docker network $(APPLIANCE_NETWORK)"; \
			$(DOCKER) network create "$(APPLIANCE_NETWORK)" >/dev/null; \
		fi; \
		if $(DOCKER) ps -a --format '{{.Names}}' | grep -qx "$(APPLIANCE_CONTAINER)"; then \
			echo "Replacing existing container $(APPLIANCE_CONTAINER)"; \
			$(DOCKER) rm -f "$(APPLIANCE_CONTAINER)" >/dev/null; \
		fi; \
		$(DOCKER) run -d \
			--name "$(APPLIANCE_CONTAINER)" \
			--read-only \
			--tmpfs /tmp:rw,nosuid,nodev,mode=1777,size=256m \
			--tmpfs /run:rw,nosuid,nodev,mode=755,size=64m \
			--tmpfs /run/pyinstaller:rw,nosuid,nodev,exec,mode=1777,size=256m \
			--cap-drop ALL \
			--cap-add CHOWN \
			--cap-add DAC_OVERRIDE \
			--cap-add FOWNER \
			--cap-add KILL \
			--cap-add SETGID \
			--cap-add SETUID \
			--cap-add NET_BIND_SERVICE \
			--security-opt no-new-privileges:true \
			--add-host unicron-stepca:127.0.0.1 \
			--add-host unicron-stepca-ra:127.0.0.1 \
			--add-host unicron.central:127.0.0.1 \
			--add-host "$(APPLIANCE_FQDN):127.0.0.1" \
			--env-file "$(APPLIANCE_ENV_FILE)" \
			"$${admin_env_args[@]}" \
			--network "$(APPLIANCE_NETWORK)" \
			--network-alias "$(APPLIANCE_NETWORK_ALIAS)" \
			-p "$(APPLIANCE_HTTP_PORT):80" \
			-p "$(APPLIANCE_HTTPS_PORT):443" \
			-p "$(APPLIANCE_MTLS_PORT):8443" \
			-e UNICRON_PUBLIC_CENTRAL_PORT="$(APPLIANCE_HTTPS_PORT)" \
			-e UNICRON_PUBLIC_CENTRAL_MTLS_PORT="$(APPLIANCE_MTLS_PORT)" \
			-e UNICRON_APPLIANCE_CONTAINER_NAME="$(APPLIANCE_CONTAINER)" \
			-e TMPDIR=/run/pyinstaller \
			-v "$(APPLIANCE_DATA_VOLUME):/var/lib/unicron" \
			-v /var/run/docker.sock:/var/run/docker.sock \
			"$(APPLIANCE_LOCAL_REF)" >/dev/null; \
		for attempt in 1 2 3 4 5 6 7 8; do \
			status="$$( $(DOCKER) inspect -f '{{.State.Status}}' "$(APPLIANCE_CONTAINER)" 2>/dev/null || true )"; \
			if [ "$$status" = "exited" ] || [ "$$status" = "dead" ]; then \
				exit_code="$$( $(DOCKER) inspect -f '{{.State.ExitCode}}' "$(APPLIANCE_CONTAINER)" 2>/dev/null || echo unknown )"; \
				echo "Appliance container $(APPLIANCE_CONTAINER) exited during startup with exit code $$exit_code." >&2; \
				echo "Recent appliance logs:" >&2; \
				$(DOCKER) logs --tail 120 "$(APPLIANCE_CONTAINER)" >&2 || true; \
				exit 1; \
			fi; \
			sleep 1; \
		done; \
		echo ""; \
		echo "Appliance is starting in container $(APPLIANCE_CONTAINER)."; \
		echo "Open: $(APPLIANCE_URL)"; \
		echo "Admin username: $$username"; \
		if [ "$$admin_password_source" = "missing-recovery" ]; then \
			echo "Admin password: not configured"; \
			echo "Recovery override: enabled; set CENTRAL_ADMIN_PASSWORD before starting recovery."; \
		elif [ "$$recovery_override_enabled" = "true" ]; then \
			echo "Admin password: $$admin_password"; \
			echo "Recovery override: enabled; configured password will reset the existing local admin during startup."; \
		elif [ "$$admin_password_source" = "generated" ]; then \
			echo "Admin password: $$admin_password"; \
			echo "Recovery override: disabled; this password initializes a new admin only and will not reset an existing admin."; \
		else \
			echo "Admin password: $$admin_password"; \
			echo "Recovery override: disabled; configured password applies only to first initialization and will not reset an existing admin."; \
		fi; \
		echo "Logs: $(DOCKER) logs -f $(APPLIANCE_CONTAINER)"; \
		echo "Stop: $(DOCKER) stop $(APPLIANCE_CONTAINER)"; \
		echo "Local TLS uses the appliance-generated CA, so your browser may show a certificate warning."
