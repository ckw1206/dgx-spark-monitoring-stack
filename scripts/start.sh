#!/bin/sh
# Substitute ${VAR} patterns in prometheus.tpl.yml using sed,
# then start prometheus. No external tools needed (uses only sh + sed).
sed -e "s/\${DGX_HOST}/${DGX_HOST}/g" \
    -e "s/\${DGX_COLLECTOR_PORT}/${DGX_COLLECTOR_PORT:-9273}/g" \
    -e "s/\${DGX_SGLANG_PORT}/${DGX_SGLANG_PORT:-8888}/g" \
    /prometheus/prometheus.tpl.yml > /prometheus/prometheus.yml

exec /bin/prometheus \
    --config.file=/prometheus/prometheus.yml \
    --web.enable-remote-write-receiver \
    --storage.tsdb.retention.time=60d \
    --storage.tsdb.wal-compression \
    --web.enable-lifecycle
