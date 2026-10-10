#!/bin/sh
# Replace ${VAR} patterns in prometheus.tpl.yml using sed + env
tmpl="/prometheus/prometheus.tpl.yml"
out="/prometheus/prometheus.yml"

# sed with env var expansion - sed 's|\${VAR}|'"$VAR"'|g'
sed \
    -e "s|\${DGX_HOST}|${DGX_HOST}|g" \
    -e "s|\${DGX_COLLECTOR_PORT}|${DGX_COLLECTOR_PORT}|g" \
    -e "s|\${DGX_SGLANG_PORT}|${DGX_SGLANG_PORT}|g" \
    "$tmpl" > "$out"

exec /bin/prometheus "$@"
