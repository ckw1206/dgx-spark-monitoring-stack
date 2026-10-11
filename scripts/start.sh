#!/bin/sh
# Validate required hosts before doing anything
for v in DGX_HOST LITELLM_HOST; do
    if [ -z "$(printenv "$v")" ]; then
        echo "ERROR: $v environment variable is not set" >&2
        exit 1
    fi
done

# Render the template: replace ${VAR} and ${VAR:-default} with the env value
# (or the default when unset/empty). Rendered inside the container so the
# repo never holds real IPs.
awk '{
    while (match($0, /\$\{[A-Za-z_][A-Za-z0-9_]*(:-[^}]*)?\}/)) {
        tok = substr($0, RSTART + 2, RLENGTH - 3); name = tok; def = ""
        if ((i = index(tok, ":-")) > 0) { name = substr(tok, 1, i - 1); def = substr(tok, i + 2) }
        val = (ENVIRON[name] != "") ? ENVIRON[name] : def
        $0 = substr($0, 1, RSTART - 1) val substr($0, RSTART + RLENGTH)
    }
    print
}' /prometheus/prometheus.tpl.yml > /prometheus/prometheus.yml

exec /bin/prometheus \
    --config.file=/prometheus/prometheus.yml \
    --web.enable-remote-write-receiver \
    --storage.tsdb.retention.time=60d \
    --storage.tsdb.wal-compression \
    --web.enable-lifecycle
