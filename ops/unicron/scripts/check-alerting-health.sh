#!/bin/bash

echo "=== Alerting Infrastructure Health Check ==="
echo ""

# Check Redis
echo "Redis:"
if redis-cli -h localhost ping 2>/dev/null | grep -q PONG; then
    echo "  Status: HEALTHY"
    echo "  Memory: $(redis-cli -h localhost info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')"
    echo "  Clients: $(redis-cli -h localhost info clients | grep connected_clients | cut -d: -f2 | tr -d '\r')"
else
    echo "  Status: UNHEALTHY"
fi
echo ""

# Check Streams
echo "Redis Streams:"
for stream in alerting:alerts alerting:notifications; do
    length=$(redis-cli -h localhost XLEN "$stream" 2>/dev/null || echo "0")
    echo "  $stream: $length messages"
done
echo ""

# Check PostgreSQL schemas
echo "PostgreSQL Schemas:"
for schema in alerting notifications; do
    if psql -h localhost -U unicron -d unicron_db -tAc \
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = '$schema'" 2>/dev/null | grep -q 1; then
        echo "  $schema: EXISTS"
    else
        echo "  $schema: MISSING"
    fi
done
echo ""

# Check PostgreSQL tables
echo "PostgreSQL Tables:"
echo "  alerting schema:"
psql -h localhost -U unicron -d unicron_db -tAc \
    "SELECT '    ' || table_name FROM information_schema.tables WHERE table_schema = 'alerting'" 2>/dev/null || echo "    (none)"
echo "  notifications schema:"
psql -h localhost -U unicron -d unicron_db -tAc \
    "SELECT '    ' || table_name FROM information_schema.tables WHERE table_schema = 'notifications'" 2>/dev/null || echo "    (none)"
echo ""

echo "=== Health Check Complete ==="
