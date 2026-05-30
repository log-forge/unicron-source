#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS_DIR="$(dirname "$SCRIPT_DIR")"

cd "$OPS_DIR"

# Check if network exists
docker network inspect unicron-network >/dev/null 2>&1 || \
    docker network create unicron-network

# Start alerting infrastructure
echo "Starting alerting infrastructure..."
docker compose \
    -f docker-compose.unicron.yaml \
    -f docker-compose.alerting.yml \
    up -d redis

# Wait for Redis to be healthy
echo "Waiting for Redis..."
until docker exec unicron-redis redis-cli ping 2>/dev/null | grep -q PONG; do
    sleep 1
done

echo "Redis is ready!"

# Run database migrations if postgres is running
if docker ps --format '{{.Names}}' | grep -q unicron-postgres; then
    echo "Running database migrations..."
    docker exec unicron-backend alembic upgrade head || true
fi

echo "Alerting infrastructure ready!"
echo ""
echo "Redis: redis://localhost:6379"
echo "Redis Commander (dev): http://localhost:8081"
