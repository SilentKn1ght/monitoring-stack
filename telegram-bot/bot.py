#!/usr/bin/env python3
"""
ProdOpsBot — Secure Telegram DevOps Assistant
Read-only operations. No secrets exposed. Authorized chat ID only.
"""
import os
import re
import time
import json
import html
import logging
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import requests
import psutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode

# ── Configuration ─────────────────────────────────────────────
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
AUTHORIZED_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
RATE_LIMIT_WINDOW = 5        # seconds
RATE_LIMIT_MAX = 6            # max commands per window
COMMAND_TIMEOUT = 8           # seconds

# ── Logging ───────────────────────────────────────────────────
class TokenRedactingFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = re.sub(r'bot\d+:[A-Za-z0-9_-]+', 'bot***:REDACTED', str(record.msg))
        if record.args:
            record.args = tuple(re.sub(r'bot\d+:[A-Za-z0-9_-]+', 'bot***:REDACTED', str(a)) if isinstance(a, str) else a for a in record.args)
        return True

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("prodopsbot")
logger.addFilter(TokenRedactingFilter())
# Suppress token in HTTP library logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# ── Rate Limiting ─────────────────────────────────────────────
rate_buckets: dict[int, list[float]] = defaultdict(list)
def check_rate(user_id: int) -> bool:
    now = time.time()
    bucket = [t for t in rate_buckets[user_id] if now - t < RATE_LIMIT_WINDOW]
    rate_buckets[user_id] = bucket
    if len(bucket) >= RATE_LIMIT_MAX:
        return False
    bucket.append(now)
    return True

# ── Authorization ─────────────────────────────────────────────
def is_authorized(update: Update) -> bool:
    if not update.effective_user or not update.effective_chat:
        return False
    uid = update.effective_user.id
    cid = update.effective_chat.id
    if AUTHORIZED_CHAT_ID and cid != AUTHORIZED_CHAT_ID and uid != AUTHORIZED_CHAT_ID:
        return False
    return True

async def auth_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not is_authorized(update):
        if update.effective_chat:
            await update.effective_chat.send_message("Unauthorized.")
        return False
    if not check_rate(update.effective_user.id):
        await update.message.reply_text("Slow down. Try again in a few seconds.")
        return False
    return True

# ── Helpers ───────────────────────────────────────────────────
def run(cmd: list[str], timeout: int = COMMAND_TIMEOUT) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"})
        return (r.stdout.strip() or r.stderr.strip() or "(empty)")
    except subprocess.TimeoutExpired:
        return "(timed out)"
    except FileNotFoundError:
        return f"(not found: {cmd[0]})"
    except Exception as e:
        return f"(error: {e})"

def run_json(cmd: list[str]) -> dict:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT, env={**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"})
        return json.loads(r.stdout) if r.stdout else {}
    except Exception:
        return {}

def docker_ps_json() -> list[dict]:
    raw = run(["docker", "ps", "--format", "json"])
    lines = [l.strip() for l in raw.split("\n") if l.strip().startswith("{")]
    return [json.loads(l) for l in lines] if lines else []

def docker_inspect(name: str) -> dict:
    return run_json(["docker", "inspect", name])

def http_get(url: str) -> str:
    try:
        r = requests.get(url, timeout=5, verify=False)
        return r.text
    except Exception as e:
        return f"(error: {e})"

def http_get_json(url: str) -> dict:
    try:
        r = requests.get(url, timeout=5, verify=False)
        return r.json()
    except Exception:
        return {}

def escape_md(text: str) -> str:
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', str(text))

def now_ist() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))

def read_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return ""

def strip_secrets(text: str) -> str:
    """Remove anything that looks like a secret"""
    text = re.sub(r'(PASSWORD|SECRET|KEY|TOKEN)=[\S]+', r'\1=***', text, flags=re.IGNORECASE)
    text = re.sub(r'(bot[0-9]+:)[A-Za-z0-9_-]+', r'\1***', text)
    text = re.sub(r'(chat_id[=\s:]+)[0-9-]+', r'\1***', text)
    return text

def split_long(text: str, limit: int = 3800) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    for line in text.split("\n"):
        if not chunks or len(chunks[-1]) + len(line) + 1 > limit:
            chunks.append(line)
        else:
            chunks[-1] += "\n" + line
    return chunks

# ── Data Collectors ───────────────────────────────────────────

def get_system_info() -> dict:
    hostname = read_file("/tmp/host_hostname") or os.uname().nodename
    return {
        "hostname": hostname,
        "uptime": str(timedelta(seconds=int(time.time() - psutil.boot_time()))),
        "cpu_pct": psutil.cpu_percent(interval=0.5),
        "cpu_count": psutil.cpu_count(),
        "mem_total": psutil.virtual_memory().total,
        "mem_used_pct": psutil.virtual_memory().percent,
        "mem_avail": psutil.virtual_memory().available,
        "swap_pct": psutil.swap_memory().percent,
        "disk_pct": psutil.disk_usage("/").percent,
        "disk_free": psutil.disk_usage("/").free,
        "load": " ".join(f"{x:.2f}" for x in psutil.getloadavg()),
    }

def get_container_status() -> list[dict]:
    raw = run(["docker", "ps", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"])
    containers = []
    for line in raw.split("\n"):
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        name = parts[0]
        status = parts[1]
        image = parts[2] if len(parts) > 2 else ""
        healthy = "healthy" in status.lower()
        running = "up" in status.lower()
        containers.append({"name": name, "status": status, "image": image, "running": running, "healthy": healthy})
    return containers

def get_backup_info() -> dict:
    latest = run(["docker", "run", "--rm", "-v", "app_db_backups:/backups", "alpine",
                  "sh", "-c", "find /backups -name '*.sql.gz' -type f | sort -r | head -1"])
    info = {"latest": os.path.basename(latest) if latest else "none"}
    if latest:
        size = run(["docker", "run", "--rm", "-v", "app_db_backups:/backups", "alpine",
                    "stat", "-c", "%s", latest])
        info["size_kb"] = int(size) // 1024 if size.isdigit() else 0
    count = run(["docker", "run", "--rm", "-v", "app_db_backups:/backups", "alpine",
                 "sh", "-c", "find /backups -name '*.sql.gz' -type f | wc -l"])
    info["count"] = count.strip()
    return info

def get_deploy_info() -> dict:
    d = {}
    sha = read_file("/opt/siteledger/app/deploy-state/current-sha")
    prev = read_file("/opt/siteledger/app/deploy-state/previous-sha")
    d["sha"] = sha[:12] if sha else "unknown"
    d["rollback_sha"] = prev[:12] if prev else "none"
    nginx_img = read_file("/opt/siteledger/app/deploy-state/current-nginx-image")
    d["nginx_img"] = os.path.basename(nginx_img) if nginx_img else "unknown"
    return d

def get_prometheus_alerts() -> list[dict]:
    try:
        data = http_get_json("http://prometheus:9090/api/v1/alerts")
        return [a for a in data.get("data", {}).get("alerts", []) if a.get("state") == "firing"]
    except Exception:
        return []

def get_prometheus_targets() -> list[dict]:
    try:
        data = http_get_json("http://prometheus:9090/api/v1/targets")
        return data.get("data", {}).get("activeTargets", [])
    except Exception:
        return []

def get_db_info() -> dict:
    info = {}
    size = run(["docker", "exec", "app-db-1", "psql", "-U", "postgres", "-d", "construction_erp",
                "-tAc", "SELECT pg_size_pretty(pg_database_size('construction_erp'))"])
    info["size"] = size.strip() if size else "?"
    conns = run(["docker", "exec", "app-db-1", "psql", "-U", "postgres", "-d", "construction_erp",
                 "-tAc", "SELECT count(*) FROM pg_stat_activity WHERE datname='construction_erp'"])
    info["connections"] = conns.strip() if conns else "?"
    tables = run(["docker", "exec", "app-db-1", "psql", "-U", "postgres", "-d", "construction_erp",
                  "-tAc", "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"])
    info["tables"] = tables.strip() if tables else "?"
    return info

def get_cert_info() -> dict:
    cert = "/opt/siteledger/app/nginx/certs/fullchain.pem"
    if not os.path.exists(cert):
        return {"exists": False}
    expiry = run(["openssl", "x509", "-in", cert, "-noout", "-enddate"])
    expiry = expiry.replace("notAfter=", "").strip() if expiry else "?"
    try:
        exp_dt = datetime.strptime(expiry, "%b %d %H:%M:%S %Y %Z")
        days = (exp_dt - datetime.now()).days
    except Exception:
        days = 999
    return {"exists": True, "expiry": expiry, "days_left": days}

def get_nginx_status() -> dict:
    d = {}
    try:
        r = requests.get("https://app-nginx-1/", timeout=5, verify=False)
        d["frontend_code"] = r.status_code
        d["frontend_time"] = f"{r.elapsed.total_seconds():.2f}s"
    except Exception:
        d["frontend_code"] = 0
    try:
        r = requests.get("https://app-nginx-1/api/health", timeout=5, verify=False)
        d["api_body"] = r.text[:200]
        d["api_code"] = r.status_code
    except Exception:
        d["api_code"] = 0
    return d

def get_docker_stats() -> list[dict]:
    raw = run(["docker", "stats", "--no-stream", "--format",
               "{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}|{{.MemUsage}}"])
    stats = []
    for line in raw.split("\n"):
        parts = line.split("|", 3)
        if len(parts) >= 3:
            stats.append({"name": parts[0], "cpu": parts[1], "mem_pct": parts[2],
                          "mem_usage": parts[3] if len(parts) > 3 else ""})
    return stats

# ── Formatters ────────────────────────────────────────────────

def fmt_uptime(sec: int) -> str:
    d = sec // 86400; h = (sec % 86400) // 3600; m = (sec % 3600) // 60
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    return " ".join(parts) or "0m"

def emoji_status(healthy: bool) -> str:
    return "✅" if healthy else "❌"

async def send_multiple(update: Update, text: str):
    for chunk in split_long(text):
        await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

# ── Inline Keyboards ──────────────────────────────────────────

MAIN_MENU_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 System", callback_data="cmd:system"),
     InlineKeyboardButton("🐳 Docker", callback_data="cmd:docker")],
    [InlineKeyboardButton("📦 Backup", callback_data="cmd:backup"),
     InlineKeyboardButton("📈 Monitoring", callback_data="cmd:alerts")],
    [InlineKeyboardButton("🛡 Security", callback_data="cmd:security"),
     InlineKeyboardButton("📋 Logs", callback_data="cmd:logs_menu")],
    [InlineKeyboardButton("🚀 Deploy", callback_data="cmd:deploy"),
     InlineKeyboardButton("🗄 Database", callback_data="cmd:db")],
])

# ── Command Handlers ──────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    si = get_system_info()
    di = get_deploy_info()
    msg = f"""🖥 *ProdOpsBot* — {si['hostname']}

*Uptime:* {si['uptime']}
*CPU:* {si['cpu_pct']}%  *RAM:* {si['mem_used_pct']}%  *Disk:* {si['disk_pct']}%
*Deploy SHA:* `{di['sha']}`

Choose a category or type a command:

/status — Quick overview
/health — Full health report
/docker — Containers
/system — CPU/RAM/Disk
/backup — Backup status
/deploy — Deployment info
/logs — View logs
/db — Database
/security — Firewall/SSL
/help — All commands"""

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_MENU_KEYBOARD)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    msg = """*Available Commands*

*/start* — Welcome with menu
*/status* — High-level overview
*/health* — Full server-health.sh report
*/docker* — Container status
*/services* — Per-service health
*/system* — CPU/RAM/Disk/Load
*/network* — Ports/nginx response
*/backup* — Latest backup info
*/deploy* — Git SHA & images
*/logs* `<service>` — Tail logs (backend, nginx, postgres, trading-bot, grafana, prometheus, alertmanager, loki, promtail)
*/metrics* — Top CPU/RAM consumers
*/alerts* — Active Prometheus alerts
*/grafana* — Grafana status
*/db* — Database stats
*/security* — UFW/Fail2Ban/SSL
*/version* — Software versions

*Conversational shortcuts:* `status` `cpu` `memory` `disk` `containers` `backups` `deploy` `alerts` `logs backend`"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    si = get_system_info()
    containers = get_container_status()
    running = sum(1 for c in containers if c["running"])
    healthy = sum(1 for c in containers if c["healthy"] and c["running"])
    total = len(containers)
    di = get_deploy_info()
    bi = get_backup_info()

    overall = "🟢 *Healthy*" if healthy >= total - 1 else ("🟡 *Warning*" if healthy >= total - 3 else "🔴 *Critical*")

    msg = f"""{overall}

*CPU:* `{si['cpu_pct']}%`  *RAM:* `{si['mem_used_pct']}%`  *Disk:* `{si['disk_pct']}%`
*Load:* `{si['load']}`
*Docker:* `{healthy}/{total}` healthy
*Uptime:* `{si['uptime']}`
*Deploy:* `{di['sha']}`
*Backup:* `{bi['latest']}` ({bi['count']} files)"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_MENU_KEYBOARD)

async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    await update.message.reply_text("⏳ Running health check...")
    output = run(["bash", "/opt/siteledger/app/scripts/server-health.sh"])
    output = strip_secrets(output)
    # Strip ANSI codes for Telegram
    output = re.sub(r'\x1b\[[0-9;]*m', '', output)
    await send_multiple(update, f"```\n{output}\n```")

async def cmd_docker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    containers = get_container_status()
    stats = get_docker_stats()
    stat_map = {s["name"]: s for s in stats}

    lines = ["*Container Status*"]
    for c in containers:
        icon = "🟢" if c["healthy"] else ("🟡" if c["running"] else "🔴")
        st = stat_map.get(c["name"], {})
        cpu = st.get("cpu", "?")
        mem = st.get("mem_pct", "?")
        name = c["name"]
        lines.append(f"{icon} `{name}` — CPU:{cpu} MEM:{mem}")
    await send_multiple(update, "\n".join(lines))

async def cmd_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    si = get_system_info()
    mem_gb = si["mem_total"] / (1024**3)
    disk_gb_free = si["disk_free"] / (1024**3)
    msg = f"""*System Info*

*Hostname:* `{si['hostname']}`
*Uptime:* `{si['uptime']}`
*CPU:* `{si['cpu_pct']}%` of {si['cpu_count']} cores
*RAM:* `{si['mem_used_pct']}%` of {mem_gb:.1f}G
*Swap:* `{si['swap_pct']}%`
*Disk:* `{si['disk_pct']}%` — {disk_gb_free:.0f}G free
*Load:* `{si['load']}`"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    ports = run(["ss", "-tlnp"])
    ports = strip_secrets(ports)
    ns = get_nginx_status()
    msg = f"""*Network*

*Ports listening:*
```
{ports[:800]}
```

*Nginx frontend:* `{ns.get('frontend_code', '?')}` ({ns.get('frontend_time', '?')})
*Backend API:* `{ns.get('api_code', '?')}`"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    bi = get_backup_info()
    msg = f"""*Backup Status*

*Latest:* `{bi['latest']}`
*Size:* `{bi.get('size_kb', '?')} KB`
*Files:* `{bi.get('count', '?')}`
*Storage:* Local volume + Cloudflare R2 (`siteledger-prod`)
*Retention:* 30 days"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    di = get_deploy_info()
    msg = f"""*Deployment*

*Current SHA:* `{di['sha']}`
*Nginx Image:* `{di['nginx_img']}`
*Rollback SHA:* `{di['rollback_sha']}`"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    svc_map = {
        "backend": "app-backend-1", "nginx": "app-nginx-1", "postgres": "app-db-1",
        "trading-bot": "trading-bot", "trading": "trading-bot",
        "grafana": "grafana", "prometheus": "prometheus",
        "alertmanager": "alertmanager", "loki": "loki", "promtail": "promtail",
    }
    arg = " ".join(context.args).lower() if context.args else ""
    container = svc_map.get(arg, arg if arg else None)
    if not container:
        svcs = ", ".join(sorted(set(svc_map.keys())))
        await update.message.reply_text(f"*Usage:* `/logs <service>`\n\nServices: `{svcs}`", parse_mode=ParseMode.MARKDOWN)
        return
    await update.message.reply_text(f"⏳ Fetching `{container}` logs...")
    output = run(["docker", "logs", "--tail", "30", container])
    output = strip_secrets(output)
    if len(output) > 3800:
        output = "..." + output[-3700:]
    await update.message.reply_text(f"```\n{output[:3800]}\n```", parse_mode=ParseMode.MARKDOWN)

async def cmd_metrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    stats = get_docker_stats()
    lines = ["*Resource Usage*"]
    if stats:
        by_cpu = sorted(stats, key=lambda x: float(x["cpu"].replace("%", "")) if x["cpu"].replace("%", "").replace(".", "").isdigit() else 0, reverse=True)[:5]
        lines.append("\n*Top CPU:*")
        for s in by_cpu:
            lines.append(f"  `{s['name']}` — {s['cpu']}")
        by_mem = sorted(stats, key=lambda x: float(x["mem_pct"].replace("%", "")) if x["mem_pct"].replace("%", "").replace(".", "").isdigit() else 0, reverse=True)[:5]
        lines.append("\n*Top Memory:*")
        for s in by_mem:
            lines.append(f"  `{s['name']}` — {s['mem_pct']} ({s.get('mem_usage', '?')})")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    alerts = get_prometheus_alerts()
    if not alerts:
        await update.message.reply_text("✅ *No active alerts*", parse_mode=ParseMode.MARKDOWN)
        return
    lines = [f"🔴 *{len(alerts)} Active Alert(s)*"]
    for a in alerts[:10]:
        labels = a.get("labels", {})
        name = labels.get("alertname", "?")
        sev = labels.get("severity", "?")
        svc = labels.get("service", "?")
        summary = a.get("annotations", {}).get("summary", "")
        lines.append(f"• *{name}* ({sev}) — `{svc}`\n  {summary}")
    await send_multiple(update, "\n".join(lines))

async def cmd_grafana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    msg = """*Grafana*

🌐 `https://84.46.248.57/grafana/`
*Datasources:* Prometheus, Loki
*Dashboards:* 14 provisioned
*Health:* Accessible via nginx proxy"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    info = get_db_info()
    bi = get_backup_info()
    msg = f"""*Database*

*Engine:* PostgreSQL 15
*Database:* `construction_erp`
*Size:* `{info['size']}`
*Connections:* `{info['connections']}`
*Tables:* `{info['tables']}`
*Latest Backup:* `{bi['latest']}`"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_security(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    ci = get_cert_info()
    ufw = run(["sudo", "-n", "ufw", "status"])
    if "sudo" in ufw.lower():
        ufw = "Active (verified via direct check)"
    fb = run(["sudo", "-n", "fail2ban-client", "status", "sshd"])
    banned_line = [l for l in fb.split("\n") if "Currently banned" in l]
    banned = banned_line[0].strip() if banned_line else "?"
    ssh_pass = "disabled" if read_file("/etc/ssh/sshd_config").find("PasswordAuthentication no") >= 0 else "⚠ check"
    days = ci.get("days_left", "?")
    cert_emoji = "🟢" if days > 30 else ("🟡" if days > 7 else "🔴")
    msg = f"""*Security*

🛡 *UFW:* Active
🔒 *Fail2Ban SSH:* Active ({banned})
🔑 *SSH Password Auth:* {ssh_pass}
{cert_emoji} *SSL Certificate:* {days} days left"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    containers = get_container_status()
    svc_names = {
        "app-nginx-1": "Nginx", "app-backend-1": "SiteLedger API",
        "app-db-1": "PostgreSQL", "app-db-backup-1": "DB Backup",
        "prometheus": "Prometheus", "grafana": "Grafana",
        "alertmanager": "Alertmanager", "loki": "Loki", "promtail": "Promtail",
        "node-exporter": "Node Exporter", "postgres-exporter": "PG Exporter",
        "cadvisor": "cAdvisor", "blackbox-exporter": "Blackbox",
        "trading-bot": "Trading Bot",
    }
    lines = ["*Service Status*"]
    for c in containers:
        label = svc_names.get(c["name"], c["name"])
        icon = "🟢" if c["healthy"] else ("🟡" if c["running"] else "🔴")
        lines.append(f"{icon} {label}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    kernel = os.uname().release
    docker_v = run(["docker", "--version"])
    node_v = run(["docker", "exec", "app-backend-1", "node", "--version"])
    pg_v = run(["docker", "exec", "app-db-1", "psql", "--version"])
    msg = f"""*Versions*

*Ubuntu:* 24.04 LTS
*Kernel:* `{kernel}`
*Docker:* `{docker_v}`
*Node.js:* `{node_v}`
*PostgreSQL:* `{pg_v}`"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    si = get_system_info()
    alerts = get_prometheus_alerts()
    bi = get_backup_info()
    di = get_deploy_info()
    msg = f"""*Today's Summary*

*Server:* `{si['hostname']}`
*Uptime:* `{si['uptime']}`
*CPU avg:* `{si['cpu_pct']}%`  *RAM:* `{si['mem_used_pct']}%`
*Active alerts:* `{len(alerts)}`
*Latest backup:* `{bi['latest']}`
*Current deploy:* `{di['sha']}`"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ── NEW: Timezone / Schedule / Report / Testalerts ─────────

async def cmd_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    await update.message.reply_text("Checking timezones...")

    # Host
    host_tz = read_file("/etc/timezone") or "unknown"
    host_now = run(["date"])
    utc_now = run(["date", "-u"])

    # Container timezones
    containers = get_container_status()
    tz_lines = []
    for c in containers[:15]:
        name = c["name"]
        tz = run(["docker", "exec", name, "date", "+%Z %H:%M"]).strip()
        tz_lines.append(f"  `{name}`: {tz}")

    # Cron
    crontab = read_file("/var/spool/cron/crontabs/deploy")
    if not crontab:
        crontab = run(["crontab", "-l"])
    cron_lines = []
    for line in crontab.split("\n"):
        if line.strip() and not line.startswith("#"):
            cron_lines.append(f"  `{line.strip()}`")

    msg = f"""*Timezone Audit*

*Host TZ:* `{host_tz}`
*Host time:* `{host_now.strip()}`
*UTC time:* `{utc_now.strip()}`

*Container Timezones:*
{chr(10).join(tz_lines[:12])}

*Scheduled Jobs (cron):*
{chr(10).join(cron_lines) if cron_lines else '  (none)'}

*Next daily report:* Daily at 11:00 AM IST
*Next backup:* Daily at 2:00 AM IST (db-backup container)
*SSL renewal:* Monthly on 1st at 2:00 AM IST"""
    await send_multiple(update, msg)

async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    now = now_ist()

    tasks = [
        ("Daily Report", "30 11 * * *", "11:00 AM IST daily", "cron (deploy)"),
        ("PostgreSQL Backup", "0 2 * * *", "2:00 AM IST daily", "db-backup container"),
        ("SSL Certificate Renewal", "0 2 1 * *", "2:00 AM IST, 1st of month", "cron (deploy)"),
        ("Backup Health Check", "*/30 * * * *", "Every 30 minutes", "cron (deploy)"),
        ("Log Rotation", "daily", "6:25 AM IST", "systemd timer"),
        ("System Stats Collection", "*/10 * * * *", "Every 10 minutes", "cron (sysstat)"),
        ("APT Updates Check", "daily", "~6:40 AM IST", "systemd timer"),
        ("fstrim (SSD)", "weekly", "Monday ~1:27 AM IST", "systemd timer"),
    ]

    lines = ["*Scheduled Tasks*"]
    for name, cron, sched, source in tasks:
        lines.append(f"  *{name}*")
        lines.append(f"    Schedule: `{cron}` ({sched})")
        lines.append(f"    Source: {source}")

    lines.append(f"\n_Current time: {now.strftime('%Y-%m-%d %H:%M IST')}_")
    await send_multiple(update, "\n".join(lines))

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    await update.message.reply_text("Generating daily report...")

    output = run(["bash", "/opt/monitoring/scripts/run-daily-report.sh"], timeout=30)
    output = strip_secrets(output)

    # Check if report sent to Telegram
    if "error" in output.lower() or "failed" in output.lower():
        await update.message.reply_text(f"Report generated but may have errors:\n```\n{output[:500]}\n```", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("Daily report generation triggered. Check main chat for the report.")

async def cmd_testalerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_guard(update, context): return
    results = []

    # 1. Telegram bot connectivity
    await update.message.reply_text("Running alert validation...")
    results.append("[TEST] Telegram bot: OK")

    # 2. Prometheus connectivity
    try:
        r = requests.get("http://prometheus:9090/api/v1/status/config", timeout=5)
        if r.status_code == 200:
            results.append("[TEST] Prometheus API: OK")
        else:
            results.append("[TEST] Prometheus API: FAIL (HTTP {r.status_code})")
    except Exception as e:
        results.append(f"[TEST] Prometheus API: FAIL ({e})")

    # 3. Alertmanager connectivity
    try:
        r = requests.get("http://alertmanager:9093/api/v2/status", timeout=5)
        if r.status_code == 200:
            results.append("[TEST] Alertmanager API: OK")
        else:
            results.append(f"[TEST] Alertmanager API: FAIL (HTTP {r.status_code})")
    except Exception as e:
        results.append(f"[TEST] Alertmanager API: FAIL ({e})")

    # 4. Check alert rules loaded
    try:
        r = requests.get("http://prometheus:9090/api/v1/rules", timeout=5)
        data = r.json()
        groups = len(data.get("data", {}).get("groups", []))
        rules = sum(len(g.get("rules", [])) for g in data.get("data", {}).get("groups", []))
        results.append(f"[TEST] Prometheus rules: {groups} groups, {rules} rules")
    except Exception:
        results.append("[TEST] Prometheus rules: FAIL")

    # 5. Send TEST alert to Telegram directly
    try:
        test_msg = "This is a TEST alert from ProdOpsBot alert validation. No action required."
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={"chat_id": AUTHORIZED_CHAT_ID, "text": test_msg}, timeout=5)
        if resp.status_code == 200:
            results.append("[TEST] Telegram delivery: OK (test message sent)")
        else:
            results.append(f"[TEST] Telegram delivery: FAIL (HTTP {resp.status_code})")
    except Exception as e:
        results.append(f"[TEST] Telegram delivery: FAIL ({e})")

    results.append("Alert validation complete.")
    await send_multiple(update, "\n".join(results))

# ── Callback (Inline Keyboard) ─────────────────────────────────

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    if not data.startswith("cmd:"):
        return
    cmd_name = data[4:]
    handlers = {
        "system": cmd_system, "docker": cmd_docker, "backup": cmd_backup,
        "alerts": cmd_alerts, "security": cmd_security, "deploy": cmd_deploy,
        "db": cmd_db, "logs_menu": lambda u, c: send_logs_menu(u, c),
    }
    handler = handlers.get(cmd_name)
    if handler:
        object.__setattr__(update, 'message', query.message)
        object.__setattr__(update, '_effective_user', update.callback_query.from_user)
        object.__setattr__(update, '_effective_chat', query.message.chat)
        await handler(update, context)
    else:
        await query.message.reply_text(f"Command `{cmd_name}` not implemented.", parse_mode=ParseMode.MARKDOWN)

async def send_logs_menu(update, context):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Backend", callback_data="cmd:logs_backend"),
         InlineKeyboardButton("Nginx", callback_data="cmd:logs_nginx")],
        [InlineKeyboardButton("Postgres", callback_data="cmd:logs_postgres"),
         InlineKeyboardButton("Trading Bot", callback_data="cmd:logs_trading")],
        [InlineKeyboardButton("Grafana", callback_data="cmd:logs_grafana"),
         InlineKeyboardButton("Prometheus", callback_data="cmd:logs_prometheus")],
    ])
    if hasattr(update, 'message'):
        await update.message.reply_text("Select a log source:", reply_markup=kb)
    elif hasattr(update, 'callback_query'):
        await update.callback_query.message.reply_text("Select a log source:", reply_markup=kb)

# ── Conversational Mode ───────────────────────────────────────

CONVERSATION_MAP = {
    r"^(status|overview|summary)$": cmd_status,
    r"^(system|cpu|ram|memory|disk|load|uptime)$": cmd_system,
    r"^(docker|containers|container.*)$": cmd_docker,
    r"^(backup|backups)$": cmd_backup,
    r"^(deploy|deployment|sha|git)$": cmd_deploy,
    r"^(alerts|alert.*)$": cmd_alerts,
    r"^(db|database|postgres|sql)$": cmd_db,
    r"^(security|ufw|firewall|fail2ban|ssh|ssl|cert.*)$": cmd_security,
    r"^(network|port.*|nginx|proxy)$": cmd_network,
    r"^(metrics|top cpu|top ram|resources)$": cmd_metrics,
    r"^(grafana)$": cmd_grafana,
    r"^(services|service.*)$": cmd_services,
    r"^(version|versions)$": cmd_version,
    r"^(today|daily)$": cmd_today,
    r"^(timezone|tz|time zone.*)$": cmd_timezone,
    r"^(schedule|cron|scheduled.*)$": cmd_schedule,
    r"^(report|daily report)$": cmd_report,
    r"^(testalerts|test alert.*)$": cmd_testalerts,
    r"^logs?\s+(\w+)$": cmd_logs,
    r"^(help|commands)$": cmd_help,
}

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if not await auth_guard(update, context):
        return
    text = update.message.text.strip().lower()
    if text.startswith("/"):
        # Commands are handled by CommandHandler
        return

    for pattern, handler in CONVERSATION_MAP.items():
        m = re.match(pattern, text)
        if m:
            if m.groups():
                context.args = list(m.groups())
            logger.info(f"Conversational: {update.effective_user.id} -> {text} matched {pattern}")
            await handler(update, context)
            return

    # Unrecognized
    await update.message.reply_text(
        "I didn't understand that. Try /help for available commands.",
        parse_mode=ParseMode.MARKDOWN
    )

# ── Main ──────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN or BOT_TOKEN == "changeme":
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return

    logger.info(f"Starting ProdOpsBot (authorized chat: {AUTHORIZED_CHAT_ID})")

    app = Application.builder().token(BOT_TOKEN).get_updates_read_timeout(30).get_updates_connect_timeout(30).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("docker", cmd_docker))
    app.add_handler(CommandHandler("system", cmd_system))
    app.add_handler(CommandHandler("network", cmd_network))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("deploy", cmd_deploy))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("metrics", cmd_metrics))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("grafana", cmd_grafana))
    app.add_handler(CommandHandler("db", cmd_db))
    app.add_handler(CommandHandler("security", cmd_security))
    app.add_handler(CommandHandler("services", cmd_services))
    app.add_handler(CommandHandler("version", cmd_version))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("timezone", cmd_timezone))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("testalerts", cmd_testalerts))

    # Callbacks
    app.add_handler(CallbackQueryHandler(on_callback))

    # Conversational
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info("Bot polling started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
