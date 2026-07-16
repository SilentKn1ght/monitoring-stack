#!/usr/bin/env python3
"""Generate custom Grafana dashboard JSONs with correct datasource UIDs."""
import json
import os

DS_PROM = "${DS_PROMETHEUS}"
DS_LOKI = "${DS_LOKI}"
UID_PROM = "prometheus"
UID_LOKI = "loki"
HOST = "vmi3410257"
OUT = "/opt/monitoring/grafana/dashboards"


def hostname_var():
    return {"name": "hostname", "type": "constant", "query": HOST,
            "current": {"text": HOST, "value": HOST}}


def build_infrastructure():
    return {
        "title": "Infrastructure Overview",
        "uid": "infrastructure-overview",
        "tags": ["infrastructure", "docker", "vps"],
        "timezone": "browser",
        "schemaVersion": 38,
        "version": 1,
        "time": {"from": "now-24h", "to": "now"},
        "refresh": "30s",
        "panels": [
            {
                "id": 1, "title": "CPU Usage", "type": "gauge",
                "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "(1 - avg(node_cpu_seconds_total{mode=\"idle\"}) / avg(node_cpu_seconds_total)) * 100", "legendFormat": "CPU", "refId": "A", "instant": True}],
                "fieldConfig": {"defaults": {"unit": "percent", "thresholds": {"steps": [
                    {"color": "red", "value": None}, {"color": "yellow", "value": 80}, {"color": "green", "value": 95}]}}, "overrides": []},
            },
            {
                "id": 2, "title": "Memory Usage", "type": "gauge",
                "gridPos": {"h": 8, "w": 6, "x": 6, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100", "legendFormat": "RAM", "refId": "A", "instant": True}],
                "fieldConfig": {"defaults": {"unit": "percent", "thresholds": {"steps": [
                    {"color": "red", "value": None}, {"color": "yellow", "value": 80}, {"color": "green", "value": 95}]}}, "overrides": []},
            },
            {
                "id": 3, "title": "Disk Usage", "type": "gauge",
                "gridPos": {"h": 8, "w": 6, "x": 12, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "(1 - (node_filesystem_avail_bytes{mountpoint=\"/\",fstype!~\"tmpfs|overlay|squashfs\"} / node_filesystem_size_bytes{mountpoint=\"/\",fstype!~\"tmpfs|overlay|squashfs\"})) * 100", "legendFormat": "Disk", "refId": "A", "instant": True}],
                "fieldConfig": {"defaults": {"unit": "percent", "thresholds": {"steps": [
                    {"color": "red", "value": None}, {"color": "yellow", "value": 80}, {"color": "green", "value": 95}]}}, "overrides": []},
            },
            {
                "id": 4, "title": "System Load", "type": "stat",
                "gridPos": {"h": 8, "w": 6, "x": 18, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "node_load15", "legendFormat": "15m", "refId": "A", "instant": True}],
                "fieldConfig": {"defaults": {"unit": "none", "thresholds": {"steps": [
                    {"color": "green", "value": None}, {"color": "yellow", "value": 2}, {"color": "red", "value": 4}]}}, "overrides": []},
            },
            {
                "id": 5, "title": "CPU Usage (24h)", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "(1 - (avg by(instance)(rate(node_cpu_seconds_total{mode=\"idle\"}[$__rate_interval])))) * 100", "legendFormat": "CPU", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "percent"},
                    "overrides": [{"matcher": {"id": "byName", "options": "CPU"}, "properties": [{"id": "custom.lineStyle", "value": {"fill": "solid"}}]}]},
            },
            {
                "id": 6, "title": "Memory Usage (24h)", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100", "legendFormat": "RAM", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "percent"},
                    "overrides": [{"matcher": {"id": "byName", "options": "RAM"}, "properties": [{"id": "custom.lineStyle", "value": {"fill": "solid"}}]}]},
            },
            {
                "id": 7, "title": "Disk I/O (24h)", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "rate(node_disk_io_time_seconds_total[5m])", "legendFormat": "{{device}}", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "percentunit"},
                    "overrides": []},
            },
            {
                "id": 8, "title": "Network Traffic (24h)", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 16},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [
                    {"expr": "rate(node_network_receive_bytes_total{device!=\"lo\"}[$__rate_interval])", "legendFormat": "RX {{device}}", "refId": "A"},
                    {"expr": "rate(node_network_transmit_bytes_total{device!=\"lo\"}[$__rate_interval])", "legendFormat": "TX {{device}}", "refId": "B"},
                ],
                "fieldConfig": {"defaults": {"unit": "Bps"},
                    "overrides": []},
            },
            {
                "id": 9, "title": "Container Health", "type": "table",
                "gridPos": {"h": 8, "w": 24, "x": 0, "y": 24},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "time() - container_last_seen", "legendFormat": "{{name}}", "refId": "A", "format": "table", "instant": True}],
                "fieldConfig": {"defaults": {"unit": "s"}},
            },
        ],
        "templating": {"list": [hostname_var()]},
    }


def build_siteledger():
    return {
        "title": "SiteLedger Application",
        "uid": "siteledger-overview",
        "tags": ["siteledger", "nestjs"],
        "timezone": "browser",
        "schemaVersion": 38,
        "version": 1,
        "time": {"from": "now-6h", "to": "now"},
        "refresh": "30s",
        "panels": [
            {
                "id": 1, "title": "API Health", "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "probe_success{instance=\"$instance\"}", "legendFormat": "", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "none", "thresholds": {"steps": [
                    {"color": "red", "value": None}, {"color": "green", "value": 1}]}}},
            },
            {
                "id": 2, "title": "API Latency", "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 6, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "probe_duration_seconds{instance=\"$instance\"}", "legendFormat": "", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "s", "thresholds": {"steps": [
                    {"color": "green", "value": None}, {"color": "yellow", "value": 1}, {"color": "red", "value": 5}]}}},
            },
            {
                "id": 3, "title": "Uptime", "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 12, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "time() - process_start_time_seconds{service=\"siteledger\"}", "legendFormat": "", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "s"}},
            },
            {
                "id": 4, "title": "DB Connections", "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 18, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "pg_stat_database_numbackends{datname=\"$database\"}", "legendFormat": "", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "short"}},
            },
            {
                "id": 5, "title": "HTTP Request Rate", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 6},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "rate(http_requests_total{service=\"siteledger\"}[$__rate_interval])", "legendFormat": "{{method}} {{route}}", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "reqps"}},
            },
            {
                "id": 6, "title": "HTTP Request Duration (p95)", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 6},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{service=\"siteledger\"}[$__rate_interval])) by (le, route))", "legendFormat": "{{route}}", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "s"}},
            },
            {
                "id": 7, "title": "Database Query Rate", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 14},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "rate(prisma_query_count_total{service=\"siteledger\"}[$__rate_interval])", "legendFormat": "queries/s", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "reqps"}},
            },
            {
                "id": 8, "title": "Auth Activity", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 14},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [
                    {"expr": "rate(auth_logins_total{service=\"siteledger\"}[$__rate_interval])", "legendFormat": "logins", "refId": "A"},
                    {"expr": "rate(auth_login_failures_total{service=\"siteledger\"}[$__rate_interval])", "legendFormat": "failures", "refId": "B"},
                ],
                "fieldConfig": {"defaults": {"unit": "reqps"}},
            },
        ],
        "templating": {"list": [
            hostname_var(),
            {"name": "instance", "type": "query", "datasource": {"type": "prometheus", "uid": UID_PROM},
             "query": "label_values(probe_success{job=~\"blackbox.*\"}, instance)", "multi": False, "includeAll": False,
             "current": {"text": "https://app-nginx-1/api/health", "value": "https://app-nginx-1/api/health"}},
            {"name": "database", "type": "query", "datasource": {"type": "prometheus", "uid": UID_PROM},
             "query": "label_values(pg_stat_database_numbackends, datname)", "multi": False, "includeAll": False,
             "current": {"text": "construction_erp", "value": "construction_erp"}},
        ]},
    }


def build_trading_bot():
    return {
        "title": "Trading Bot",
        "uid": "trading-bot-overview",
        "tags": ["trading", "bot"],
        "timezone": "browser",
        "schemaVersion": 38,
        "version": 1,
        "time": {"from": "now-24h", "to": "now"},
        "refresh": "30s",
        "panels": [
            {
                "id": 1, "title": "Bot Status", "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "bot_running{service=\"trading-bot\"}", "legendFormat": "", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "none", "thresholds": {"steps": [
                    {"color": "red", "value": None}, {"color": "green", "value": 1}]}}},
            },
            {
                "id": 2, "title": "Last Heartbeat", "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 6, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "time() - bot_last_heartbeat_timestamp_seconds{service=\"trading-bot\"}", "legendFormat": "", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "s"}},
            },
            {
                "id": 3, "title": "Orders Today", "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 12, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "increase(trades_orders_total{service=\"trading-bot\"}[24h])", "legendFormat": "", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "short"}},
            },
            {
                "id": 4, "title": "PnL (Daily)", "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 18, "y": 0},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "trading_pnl_daily{service=\"trading-bot\"}", "legendFormat": "", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "currencyINR"}},
            },
            {
                "id": 5, "title": "PnL (30d)", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 6},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [
                    {"expr": "trading_pnl_daily{service=\"trading-bot\"}", "legendFormat": "Daily", "refId": "A"},
                ],
                "fieldConfig": {"defaults": {"unit": "currencyINR"}},
            },
            {
                "id": 6, "title": "Broker API Latency", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 6},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [{"expr": "rate(broker_api_duration_seconds_sum{service=\"trading-bot\"}[$__rate_interval]) / rate(broker_api_duration_seconds_count{service=\"trading-bot\"}[$__rate_interval])", "legendFormat": "avg latency", "refId": "A"}],
                "fieldConfig": {"defaults": {"unit": "s"}},
            },
            {
                "id": 7, "title": "Risk Metrics", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 14},
                "datasource": {"type": "prometheus", "uid": UID_PROM},
                "targets": [
                    {"expr": "trading_open_positions{service=\"trading-bot\"}", "legendFormat": "Open Positions", "refId": "A"},
                    {"expr": "trading_drawdown_percent{service=\"trading-bot\"}", "legendFormat": "Drawdown %", "refId": "B"},
                ],
                "fieldConfig": {"defaults": {"unit": "none"}},
            },
        ],
        "templating": {"list": [hostname_var()]},
    }


def build_logs():
    return {
        "title": "Logs Overview",
        "uid": "logs-overview",
        "tags": ["logs", "loki"],
        "timezone": "browser",
        "schemaVersion": 38,
        "version": 1,
        "time": {"from": "now-24h", "to": "now"},
        "refresh": "30s",
        "panels": [
            {
                "id": 1, "title": "Error Logs (24h)", "type": "logs",
                "gridPos": {"h": 10, "w": 24, "x": 0, "y": 0},
                "datasource": {"type": "loki", "uid": UID_LOKI},
                "targets": [{"expr": "{job=\"docker\"} |= \"error\"", "refId": "A"}],
            },
            {
                "id": 2, "title": "Application Errors", "type": "timeseries",
                "gridPos": {"h": 8, "w": 8, "x": 0, "y": 10},
                "datasource": {"type": "loki", "uid": UID_LOKI},
                "targets": [{"expr": "sum by(compose_service) (rate({job=\"docker\", compose_service=\"backend\"} |= \"error\" [$__rate_interval]))", "legendFormat": "{{compose_service}}", "refId": "A"}],
            },
            {
                "id": 3, "title": "Auth Failures", "type": "timeseries",
                "gridPos": {"h": 8, "w": 8, "x": 8, "y": 10},
                "datasource": {"type": "loki", "uid": UID_LOKI},
                "targets": [{"expr": "rate({job=\"auth\"} |= \"Failed password\" [$__rate_interval])", "legendFormat": "failures", "refId": "A"}],
            },
            {
                "id": 4, "title": "Nginx Errors", "type": "timeseries",
                "gridPos": {"h": 8, "w": 8, "x": 16, "y": 10},
                "datasource": {"type": "loki", "uid": UID_LOKI},
                "targets": [{"expr": "rate({job=\"docker\", compose_service=\"nginx\"} |= \"error\" [$__rate_interval])", "legendFormat": "errors", "refId": "A"}],
            },
        ],
        "templating": {"list": [hostname_var()]},
    }


def main():
    dashboards = [
        ("Infrastructure.json", build_infrastructure()),
        ("SiteLedger.json", build_siteledger()),
        ("TradingBot.json", build_trading_bot()),
        ("Logs.json", build_logs()),
    ]
    for name, data in dashboards:
        path = os.path.join(OUT, name)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Created: {name}")

if __name__ == "__main__":
    main()
