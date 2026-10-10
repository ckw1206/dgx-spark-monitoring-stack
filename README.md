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
cp .env .env.local   # override defaults in .env.local (git-ignored)
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
| `PROMETHEUS_MEMORY_LIMIT` | `24g` | Prometheus memory limit |
| `PROMETHEUS_DATA_DIR` | `/data/prometheus_data` | Prometheus TSDB data dir |
| `DGX_HOST` | `192.168.1.100` | DGX Spark host IP (collector endpoint) |
| `GRAFANA_VERSION` | `latest` | Grafana image tag |
| `GRAFANA_MEMORY_LIMIT` | `4g` | Grafana memory limit |
| `GRAFANA_DATA_DIR` | `/data/grafana_data` | Grafana data dir |
| `GRAFANA_PORT` | `3000` | Host port for Grafana UI |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin username |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana admin password |

### Prometheus Config

- Config: `conf_prom/prometheus.yml`

### Grafana Provisioning

Dashboards are auto-loaded from `conf_grafana/provisioning/dashboards/`. Drop additional JSON dashboards there.

The included **DGX Spark dashboard** (GPU & Unified Memory for GB10) requires the collector running on the DGX host.

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
