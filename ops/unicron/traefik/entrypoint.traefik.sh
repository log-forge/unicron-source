#!/bin/sh
set -e

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [TRAEFIK-ENTRY] $1"
}

log "Starting Traefik entrypoint script..."

TEMPLATE_FILE="/etc/traefik/traefik-config.template.yaml"
CONFIG_FILE="/etc/traefik/shared/traefik-config.yaml"

if [ -f "$TEMPLATE_FILE" ]; then
    HOSTS_RULE=""
    EXPOSE_VICTORIA_UI="${TRAEFIK_EXPOSE_VICTORIA_UI:-false}"
    if [ -n "$TRAEFIK_ROUTER_HOSTS" ]; then
        for host in $(echo "$TRAEFIK_ROUTER_HOSTS" | tr ',' ' '); do
            [ -z "$host" ] && continue
            if [ -z "$HOSTS_RULE" ]; then
                HOSTS_RULE="Host(\`$host\`)"
            else
                HOSTS_RULE="$HOSTS_RULE || Host(\`$host\`)"
            fi
        done
    fi
    # Use awk to avoid shell interpreting backticks in Host(`...`) and to
    # conditionally inject dev-only telemetry UI routers.
    awk -v repl="$HOSTS_RULE" -v expose_victoria_ui="$EXPOSE_VICTORIA_UI" '
        function prefixed_rule(path) {
            if (repl == "") {
                return "PathPrefix(`" path "`)"
            }
            return "(" repl ") && PathPrefix(`" path "`)"
        }

        function emit_victoria_ui() {
            print "    # Victoria VMUI routers (dev-only)"
            print "    victoria-metrics-vmui:"
            print "      rule: \047" prefixed_rule("/unicron/victoria-metrics") "\047"
            print "      entryPoints: [\047websecure\047]"
            print "      service: victoria-metrics-service@file"
            print "      middlewares:"
            print "        - unicron-strip@file"
            print "        - victoria-metrics-strip@file"
            print "      tls:"
            print "        options: default"
            print "      priority: 40"
            print ""
            print "    victoria-logs-vmui:"
            print "      rule: \047" prefixed_rule("/unicron/victoria-logs") "\047"
            print "      entryPoints: [\047websecure\047]"
            print "      service: victoria-logs-service@file"
            print "      middlewares:"
            print "        - unicron-strip@file"
            print "        - victoria-logs-strip@file"
            print "      tls:"
            print "        options: default"
            print "      priority: 35"
        }

        {
            gsub("{{HOSTS_OR_RULES}}", repl)

            if (index($0, "{{VICTORIA_UI_ROUTERS}}") > 0) {
                if (tolower(expose_victoria_ui) == "true" || expose_victoria_ui == "1" || tolower(expose_victoria_ui) == "yes") {
                    emit_victoria_ui()
                } else {
                    print "    # Victoria VMUI routers disabled."
                }
                next
            }

            print
        }
    ' "$TEMPLATE_FILE" > "$CONFIG_FILE"
    log "Processed Traefik config template and created $CONFIG_FILE"
    log "Victoria vendor UIs enabled: $EXPOSE_VICTORIA_UI"
    # Normalize ownership & permissions so step-ca (uid 1000) can touch the file via hook
    chown 1000:0 "$CONFIG_FILE" 2>/dev/null || log "Non-fatal: chown 1000:0 $CONFIG_FILE failed"
    chmod 664 "$CONFIG_FILE" 2>/dev/null || log "Non-fatal: chmod 664 $CONFIG_FILE failed"
else
    log "Warning: Template file $TEMPLATE_FILE not found"
fi

log "Starting Traefik with entrypoint script..."
exec /entrypoint.sh "$@"
