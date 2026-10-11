# Prometheus + Grafana Docker Compose

Monitoring stack with Prometheus (scrape/remote-write) and Grafana OSS (visualization).

## Quick Start

```bash
# 1. Deploy the collector on the DGX Spark host
scp collector/dgx_collector.py collector/dgx-collector.service root@<dgx-host>:
ssh root@<dgx-host>
  cp dgx_collector.py /opt/
  cp dgx-collector.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now dgx-collector
  curl http://localhost:9273/metrics   # verify

# 2. Start the monitoring stack
cp .env.example .env   # edit .env to set DGX_HOST, LITELLM_HOST and other vars
docker compose up -d
```

Then open Grafana at http://localhost:3000 (admin / admin).

## Services

| Service    | Port | Notes                          |
|------------|------|--------------------------------|
| Prometheus | —    | Internal only (docker network) |
| Grafana    | 3000 | Exposed on `${GRAFANA_PORT:-3000}` |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_MEMORY_LIMIT` | `4g` | Prometheus memory limit |
| `PROMETHEUS_DATA_DIR` | `/data/prometheus_data` | Prometheus TSDB data dir |
| `DGX_HOST` | — (**required**) | DGX Spark host IP; Prometheus refuses to start if empty |
| `DGX_COLLECTOR_PORT` | `9273` | `dgx_collector.py` metrics port |
| `DGX_SGLANG_PORT` | `8888` | SGLang `/metrics` port |
| `LITELLM_HOST` | — (**required**) | LiteLLM proxy host IP; Prometheus refuses to start if empty |
| `LITELLM_METRICS_PORT` | `4001` | LiteLLM dedicated metrics port |
| `GRAFANA_VERSION` | `latest` | Grafana image tag (dashboards need ≥ 12) |
| `GRAFANA_MEMORY_LIMIT` | `4g` | Grafana memory limit |
| `GRAFANA_DATA_DIR` | `/data/grafana_data` | Grafana data dir |
| `GRAFANA_PORT` | `3000` | Host port for Grafana UI |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin username |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana admin password |

### Prometheus Config

- Config template: `conf_prom/prometheus.tpl.yml`. `scripts/start.sh` renders it inside the container at start, substituting any `${VAR}` / `${VAR:-default}` from the environment, so real IPs never land in the repo. New variables must also be passed through in `docker-compose.yml`.
- Scrape jobs: `dgx-spark` (collector, `${DGX_HOST}:${DGX_COLLECTOR_PORT}`), `dgx-spark-sglang` (SGLang, `${DGX_HOST}:${DGX_SGLANG_PORT}`), `litellm-dedicated` (`${LITELLM_HOST}:${LITELLM_METRICS_PORT}`).

### Grafana Provisioning

Dashboards are auto-loaded from `conf_grafana/provisioning/dashboards/`. Drop additional JSON dashboards there.

| Dashboard | URL | Data source |
|-----------|-----|-------------|
| DGX Spark Overview | `/d/dgx-spark-overview` | DGX collector (GPU, unified memory, CPU) |
| SGLang Inference Server | `/d/sglang-inference-server` | SGLang `/metrics` |
| LiteLLM Overview | `/d/litellm-overview` | LiteLLM proxy `/metrics` + DGX collector |

Dashboards tagged `gpu` link to each other from the top bar.

Dashboards are Grafana v2-schema resources. When adding one exported from the UI: wrap the spec as `{"apiVersion": "dashboard.grafana.app/v2", "kind": "Dashboard", "metadata": {"name": "<uid>"}, "spec": {...}}`, and set the datasource variable's `current` to `Prometheus` instead of an instance-specific UID.

## DGX Spark Collector

The collector runs **on the DGX Spark host directly** (not in Docker), as it needs raw GPU telemetry via `nvidia-smi` and `/proc` files from the host.

> Collector source: https://github.com/shahizat/dgx-spark-dashboard (MIT)

### Systemd install

```bash
# On the DGX Spark host
sudo cp dgx-collector.service /etc/systemd/system/
sudo cp dgx_collector.py /opt/
sudo systemctl daemon-reload
sudo systemctl enable --now dgx-collector
```

Verify: `curl http://localhost:9273/metrics`

### Manual run

```bash
cd collector
python3 dgx_collector.py
# listens on 0.0.0.0:9273/metrics
```

No Python dependencies — stdlib only. Set `DGX_HOST` in `.env` to the DGX Spark's IP so Prometheus can reach it.

## Data Persistence

```bash
sudo mkdir -p /data/prometheus_data /data/grafana_data
sudo chown 472 /data/grafana_data   # grafana container user
```
