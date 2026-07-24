# Monitoring Stack

Production observability platform for SiteLedger (Construction ERP), Trading Bot, and VPS infrastructure.

## Architecture

| Component | Version | Role |
|-----------|---------|------|
| Grafana | 11.6.1 | Dashboard & visualization |
| Prometheus | 2.55.0 | Metrics storage & alerting |
| Loki | 3.4.2 | Log aggregation |
| Promtail | 3.4.2 | Log collection |
| Alertmanager | 0.28.0 | Alert routing & notification |
| Node Exporter | 1.8.1 | Host metrics |
| cAdvisor | 0.49.2 | Container metrics (root only) |
| PostgreSQL Exporter | 0.16.0 | Database metrics |
| Blackbox Exporter | 0.25.0 | External endpoint probes |

## Dashboard Structure

```
📁 Operations (daily use)
├── Executive Overview       — Overall system health, landing page
├── SiteLedger Operations    — API performance, business metrics
├── Trading Bot Operations   — Execution status, P&L tracking
├── Infrastructure           — Host CPU/memory/disk/network
└── Logs & Incidents         — Error tracking, log viewer

📁 Platform (maintenance)
├── Monitoring Stack         — Prometheus, Loki, Alertmanager health
└── Docker & Containers      — Container resource monitoring

📁 Debug (troubleshooting)
├── Node Exporter            — Detailed host metrics
├── PostgreSQL               — Database internals
└── Blackbox                 — External probe details
```

## Datasources

| Name | Type | URL |
|------|------|-----|
| Prometheus | prometheus | http://prometheus:9090 |
| Loki | loki | http://loki:3100 |

Both are provisioned automatically from `grafana/provisioning/datasources/`.

## Key Metrics by Dashboard

### Executive Overview
- `probe_success{instance="https://app-nginx-1/api/health"}` — SiteLedger API health
- `bot_running` — Trading Bot status
- `pg_up` — PostgreSQL status
- `instance:node_cpu_utilization:rate5m * 100` — CPU gauge
- `count(ALERTS{alertstate="firing"})` — Active alert count
- `{job="docker"} |= "error"` — Recent error logs

### SiteLedger Operations
- `http_requests_total{service="siteledger"}` — HTTP request count
- `http_request_duration_seconds_bucket{service="siteledger"}` — Request latency histogram
- `auth_active_sessions{service="siteledger"}` — Active auth sessions
- `prisma_query_count_total{service="siteledger"}` — Database query rate
- `business_attendance_total{service="siteledger"}` — Attendance events
- `process_start_time_seconds{service="siteledger"}` — Process uptime

### Trading Bot Operations
- `bot_running` — Bot status
- `bot_last_heartbeat_timestamp_seconds` — Time since last heartbeat
- `trading_pnl_daily/weekly/monthly/total` — P&L tracking
- `trading_open_positions` — Open positions
- `trading_drawdown_percent` — Maximum drawdown
- `trades_orders_total` — Order counts (labels: type, status)
- `trades_signals_total` — Signal counts (labels: direction)

### Infrastructure
- `node_cpu_seconds_total` — CPU utilization
- `node_memory_Mem*_bytes` — Memory breakdown
- `node_filesystem_*_bytes` — Disk usage
- `node_network_*_bytes_total` — Network traffic
- `node_disk_*_bytes_total` — Disk I/O
- `node_load*` — System load
- `node_vmstat_oom_kill` — OOM events
- `node_pressure_*` — Pressure stall indicators
- `predict_linear(node_filesystem_avail_bytes[...], ...)` — Disk forecast

### Monitoring Stack
- `up` — Target health
- `scrape_duration_seconds` — Scrape durations
- `prometheus_tsdb_*` — TSDB storage metrics
- `alertmanager_alerts` — Alert states
- `alertmanager_notifications_*` — Notification status
- `loki_distributor_*` — Loki ingestion rates

## Provisioning

Dashboards and datasources are provisioned automatically from files:

```
grafana/
├── dashboards/
│   ├── Operations/
│   ├── Platform/
│   └── Debug/
└── provisioning/
    ├── dashboards/dashboards.yml    — Dashboard provider config
    └── datasources/datasources.yml  — Prometheus + Loki config
```

Grafana scans these directories on startup and every 60 seconds (`updateIntervalSeconds: 60`).

Folders are created automatically from the subdirectory structure (`foldersFromFilesStructure: true`).

## Deployment

1. Commit and push to main
2. GitHub Actions deploys automatically (or SSH and pull manually)
3. Restart Grafana to reload dashboards:
   ```bash
   docker compose restart grafana
   ```

## Adding a Dashboard

1. Create a JSON file in the appropriate folder under `grafana/dashboards/`
2. Assign a unique `uid`
3. Use `"prometheus"` or `"loki"` as the datasource UID
4. Set `"schemaVersion": 38`
5. Validate JSON: `python3 -c "import json; json.load(open('file.json'))"`
6. Commit, push, deploy
7. Verify in Grafana after provisioning cycle

## Backup & Restore

### Grafana Database
```bash
# Backup
docker exec grafana sqlite3 /var/lib/grafana/grafana.db ".backup '/tmp/grafana-$(date +%Y%m%d).db'"
docker cp grafana:/tmp/grafana-*.db ./backups/

# Restore
docker cp ./backups/grafana-20260101.db grafana:/var/lib/grafana/grafana.db
docker exec grafana chown 472:472 /var/lib/grafana/grafana.db
docker compose restart grafana
```

### Provisioning files are the source of truth
Dashboard configurations in `grafana/dashboards/` are the primary backup. Grafana re-imports them automatically.

## Troubleshooting

### Dashboard shows "No Data"
1. Open panel query in Prometheus Explore (shift+click)
2. Check if metric exists: `http://localhost:9090/api/v1/label/__name__/values`
3. Check if labels match: verify label names and values
4. Verify datasource is healthy in Grafana

### Datasource errors
1. Check `docker compose logs grafana` for provisioning errors
2. Verify Prometheus/Loki are running
3. Check network connectivity between containers (same `monitoring` network)

### Provisioning not updating
1. Check `updateIntervalSeconds` (60s default)
2. Restart Grafana: `docker compose restart grafana`
3. Check Grafana logs for provisioning errors

### Missing metrics
1. Verify exporter is scraped: Prometheus Targets page
2. Check exporter metrics endpoint: `curl http://exporter:port/metrics`
3. Verify scrape config in `prometheus/prometheus.yml`

## Known Limitations

1. **cAdvisor per-container metrics**: Due to a cAdvisor overlay2 detection issue, only root container metrics are available. Per-container CPU/memory/network from cAdvisor are unavailable. Container metrics use `process_*` from application targets instead.

2. **Trading Bot broker_api metrics**: `broker_api_duration_seconds` histogram is defined in source code but not producing data in production. The deployed container image may need rebuilding.

3. **Grafana password**: The admin password in the environment variable may diverge from the database password after first start. Reset via `docker exec grafana grafana cli admin reset-admin-password <newpass>`.

4. **Missing Trading Bot metrics**: See `trading_bot_instrumentation.md` for recommended additions.

## Required Application Instrumentation

### SiteLedger (backend)
The NestJS backend at `/api/metrics` must expose:

| Metric | Type | Required |
|--------|------|----------|
| `http_requests_total` | Counter | Yes |
| `http_request_duration_seconds_bucket` | Histogram | Yes |
| `auth_active_sessions` | Gauge | Yes |
| `prisma_query_count_total` | Counter | Yes |
| `business_attendance_total` | Counter | Yes |
| `process_start_time_seconds` | Gauge | Auto (from prom-client) |

### Trading Bot
The Python bot at `:8000/metrics` must expose:

| Metric | Type | Required |
|--------|------|----------|
| `bot_running` | Gauge | Yes |
| `bot_uptime_seconds` | Gauge | Yes |
| `bot_last_heartbeat_timestamp_seconds` | Gauge | Yes |
| `bot_heartbeat_total` | Counter | Yes |
| `trades_orders_total` | Counter (type, status) | Yes |
| `trades_signals_total` | Counter (direction) | Yes |
| `trading_pnl_daily/weekly/monthly/total` | Gauge | Yes |
| `trading_open_positions` | Gauge | Yes |
| `trading_drawdown_percent` | Gauge | Yes |

## Instrumentation Roadmap

### High Priority
- Add `trading_portfolio_value` (Gauge) to trading bot
- Add `trading_last_execution_timestamp_seconds` (Gauge) to trading bot
- Add `bot_config_version` (Gauge) to trading bot

### Medium Priority
- Add `trading_execution_duration_seconds` (Histogram) to trading bot
- Add `siteledger_active_users` (Gauge) to backend
- Add `siteledger_projects_*` (Counters) to backend

### Low Priority
- Add `broker_connected` (Gauge) to trading bot
- Add `trading_win_rate` (Gauge) to trading bot
