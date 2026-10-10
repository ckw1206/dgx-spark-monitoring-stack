#!/bin/sh
envsubst < /prometheus/prometheus.tpl.yml > /prometheus/prometheus.yml
exec /bin/prometheus-main "$@"
