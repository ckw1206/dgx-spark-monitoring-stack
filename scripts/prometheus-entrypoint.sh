#!/bin/sh
# Substitute ${VAR} patterns from environment in the prometheus config template,
# then exec into the image's actual entrypoint (prometheus-main, a Go binary).
envsubst < /prometheus/prometheus.tpl.yml > /prometheus/prometheus.yml
exec /bin/prometheus-main "$@"
