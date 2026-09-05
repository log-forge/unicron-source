# LogForge Unicron

LogForge Unicron is Open Source code from
https://github.com/log-forge/logforge for a local-first observability appliance
for Docker hosts and container fleets. It packages a web UI, Central API, local
admin auth, agent enrollment, telemetry ingest, alert evaluation, and
notifications into a standalone deployment.

## Quick Start

Run the standalone appliance:

```sh
docker compose -f deploy/standalone/docker-compose.yml up -d
```

Open:

```text
https://localhost/unicron
```

If `CENTRAL_ADMIN_PASSWORD` is unset, the auth service generates a first-boot
administrator password and logs it once:

```sh
docker logs unicron-appliance | grep -E "Local admin first-boot generated administrator credential|generatedPassword"
```

To validate a local appliance image:

```sh
docker build -f ops/appliance/Dockerfile -t unicron-appliance:latest .

UNICRON_IMAGE=unicron-appliance:latest \
UNICRON_HTTP_PORT=8080 \
UNICRON_HTTPS_PORT=8444 \
UNICRON_MTLS_PORT=9443 \
docker compose -f deploy/standalone/docker-compose.yml up -d
```

## What Is Included

- Single-image appliance runtime for standalone deployment.
- Local administrator auth with explicit recovery mode.
- Central backend, React frontend, alert engine, notifier API, and notifier worker.
- Postgres, Redis, Step CA/RA, Traefik, VictoriaMetrics, VictoriaLogs,
  and OTel collector inside the appliance.
- Automatic migration of Central Auth data from older MongoDB-backed appliance volumes.
- Agent enrollment through tokens and mTLS identity.
- Browser and API ingress under `/unicron`.
- Agent mTLS and OTLP ingress on port `8443`.

## Repository Map

- `deploy/standalone/`: standalone Compose artifact.
- `ops/appliance/`: appliance Dockerfile, manager, templates, and tests.
- `central/unicron/backend/`: Central FastAPI backend.
- `central/unicron/frontend/`: React Router frontend.
- `central/auth/`: local administrator auth service.
- `edge/go-streamer/`: remote agent.
- `services/alert-engine/`: alert rules and evaluation service.
- `services/notifier/`: notification API and worker.
- `libs/unicron_shared/`: shared Python models and enums.

## Development

### Upgrading Multi-container Auth

Compose retains `unicron-central-auth-mongo-data` and imports the existing login
before creating a new administrator. Keep the old `CENTRAL_AUTH_MONGO_ROOT_USERNAME`,
`CENTRAL_AUTH_MONGO_ROOT_PASSWORD`, and `CENTRAL_AUTH_MONGODB_DB_NAME` settings.
Back up both databases before upgrading. Missing legacy users, missing passwords,
or conflicting PostgreSQL and MongoDB accounts stop startup rather than replacing
the login. Restore the missing data or correct the connection settings before retrying.

Fresh installs never start MongoDB. After migration, restarting the legacy helper
leaves it idle; it no longer needs a MongoDB-compatible CPU. The first migration
of an old database still requires a compatible CPU. Keep the new
`unicron-central-auth-migration` volume with PostgreSQL when backing up or restoring.

### Local Checks

Useful commands:

```sh
make build-appliance
make build-up
make central-up
make central-down
make dind-up
make dind-down
```

Common focused checks:

```sh
docker compose -f deploy/standalone/docker-compose.yml config
npm --prefix central/unicron/frontend run typecheck
TMPDIR=/tmp npm --prefix central/unicron/frontend test
npm --prefix central/auth run typecheck
make test-central-auth
(cd ops/appliance/manager && go test ./...)
(cd edge/go-streamer && go test ./...)
(cd central/unicron/backend && poetry run python -m unittest tests.test_security_hardening tests.test_origin_policy tests.test_appliance_update)
```

Test the production multi-container auth wiring with isolated containers and
volumes (including real legacy password migration and failure cases):

```sh
docker build -f central/auth/Dockerfile -t unicron-central-auth:local-test .
python3 ops/testing/test-central-auth-compose.py unicron-central-auth:local-test
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md).

## License

LogForge Unicron is Open Source. See [LICENSE](LICENSE).
