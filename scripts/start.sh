#!/bin/sh
# Validate DGX_HOST before doing anything
if [ -z "$DGX_HOST" ]; then
    echo "ERROR: DGX_HOST environment variable is not set" >&2
    exit 1
fi

# Apply defaults
DGX_COLLECTOR_PORT="${DGX_COLLECTOR_PORT:-9273}"
DGX_SGLANG_PORT="${DGX_SGLANG_PORT:-8888}"

# Use awk to substitute template vars. Two patterns per variable:
# 1. ${VAR}       (no default suffix)
# 2. ${VAR:-def}  (with default suffix)
awk -v host="$DGX_HOST" \
    -v collector="$DGX_COLLECTOR_PORT" \
    -v sglang="$DGX_SGLANG_PORT" \
    '{
        gsub(/\$\{DGX_HOST\}/, host);
        gsub(/\$\{DGX_HOST:[^}]*\}/, host);
        gsub(/\$\{DGX_COLLECTOR_PORT\}/, collector);
        gsub(/\$\{DGX_COLLECTOR_PORT:[^}]*\}/, collector);
        gsub(/\$\{DGX_SGLANG_PORT\}/, sglang);
        gsub(/\$\{DGX_SGLANG_PORT:[^}]*\}/, sglang);
        print
    }' /prometheus/prometheus.tpl.yml > /prometheus/prometheus.yml

exec /bin/prometheus \
    --config.file=/prometheus/prometheus.yml \
    --web.enable-remote-write-receiver \
    --storage.tsdb.retention.time=60d \
    --storage.tsdb.wal-compression \
    --web.enable-lifecycle
