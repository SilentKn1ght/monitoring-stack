#!/usr/bin/env python3
"""Daily infrastructure report sent to Telegram at 11:00 IST."""

import os, sys, json, urllib.request, urllib.parse, datetime

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

PROMETHEUS = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TZ_OFFSET = datetime.timedelta(hours=5, minutes=30)

# Pre-computed by wrapper script
CONTAINER_COUNT = os.environ.get("CONTAINER_COUNT", "N/A")
CONTAINER_RESTARTS = os.environ.get("CONTAINER_RESTARTS", "N/A")
BACKUP_ALIVE = os.environ.get("BACKUP_ALIVE", "N/A")


def promql(query):
    url = PROMETHEUS + "/api/v1/query?query=" + urllib.parse.quote(query)
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url), timeout=3)
        data = json.loads(resp.read())
        if data["status"] == "success" and data["data"]["result"]:
            return data["data"]["result"]
    except Exception:
        pass
    return []


def first_value(results):
    for r in results or []:
        try:
            return float(r["value"][1])
        except Exception:
            pass
    return None


def fmt_bytes(b):
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return "%s %s" % (str(round(float(b), 1)), u)
        b = float(b) / 1024.0
    return "%s PB" % str(round(float(b), 1))


def fmt_pct(v):
    return "%s%%" % str(round(float(v), 1)) if v is not None else "N/A"


def n(expr, formatter=str):
    r = first_value(promql(expr))
    return formatter(r) if r is not None else "N/A"


def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set", file=sys.stderr)
        return False
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    payload = json.dumps({
        "chat_id": int(CHAT_ID),
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    try:
        resp = urllib.request.urlopen(
            urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}),
            timeout=8,
        )
        print("Telegram: OK" if json.loads(resp.read()).get("ok") else "Telegram: FAILED")
        return True
    except Exception as e:
        print("Telegram send failed: " + str(e), file=sys.stderr)
        return False


def build_report():
    now = datetime.datetime.now(datetime.timezone.utc) + TZ_OFFSET
    date_str = now.strftime("%d %B %Y, %I:%M %p IST")

    cpu = n('100 - (avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)', fmt_pct)
    ram = n("(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100", fmt_pct)
    disk = n("(1 - (node_filesystem_avail_bytes{mountpoint='/'} / node_filesystem_size_bytes{mountpoint='/'})) * 100", fmt_pct)
    uptime = n("(time() - node_boot_time_seconds{instance=~'node-exporter:9100'})",
               lambda v: str(int(v / 86400)) + "d " + str(int((v % 86400) / 3600)) + "h")
    siteledger = n("probe_success{instance='https://app-nginx-1/api/health'}", lambda v: "OK" if v == 1 else "DOWN")
    trading = n("up{service='trading-bot'}", lambda v: "OK" if v == 1 else "DOWN")
    db_size = n("pg_database_size_bytes{datname='construction_erp'}", fmt_bytes)
    db_conn = n("pg_stat_database_numbackends{datname='construction_erp'}", int)
    ssldays = n("(probe_ssl_earliest_cert_expiry{instance='https://app-nginx-1/'} - time()) / 86400",
                lambda v: str(int(v)) + " days" if v and v > 0 else "N/A")

    prom_up = len(promql("up == 1"))
    prom_down = len(promql("up == 0"))

    return "Daily Infrastructure Report\n" + date_str + "\n\n" + \
        "Host -\n" + \
        "CPU:    " + str(cpu) + "\n" + \
        "RAM:    " + str(ram) + "\n" + \
        "Disk:   " + str(disk) + "\n" + \
        "Uptime: " + str(uptime) + "\n\n" + \
        "Containers -\n" + \
        "Running: " + str(CONTAINER_COUNT) + " | Restarts (total): " + str(CONTAINER_RESTARTS) + "\n\n" + \
        "Applications -\n" + \
        "SiteLedger:  " + str(siteledger) + "\n" + \
        "Trading Bot: " + str(trading) + "\n\n" + \
        "Database -\n" + \
        "Size:  " + str(db_size) + "\n" + \
        "Connections: " + str(db_conn) + "\n\n" + \
        "Prometheus -\n" + \
        "Targets: " + str(prom_up) + " UP / " + str(prom_down) + " DOWN\n\n" + \
        "SSL -\n" + \
        "Expires: " + str(ssldays) + "\n\n" + \
        "Backups -\n" + \
        "DB backup: " + ("Running" if str(BACKUP_ALIVE).strip() == "1" else "N/A") + "\n\n" + \
        "Generated automatically at 11:00 IST"


if __name__ == "__main__":
    report = build_report()
    print(report)
    send_telegram(report)
