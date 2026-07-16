# ProdOpsBot — Telegram DevOps Assistant

## Overview

ProdOpsBot is a secure, read-only Telegram bot that lets you query and monitor the production server directly from Telegram. It extends the existing Alertmanager Telegram notification system using the same bot token.

## Security

- **Chat ID whitelisting:** Only the authorized Telegram chat ID can interact with the bot
- **Read-only:** All commands are read-only — no destructive operations
- **Rate limiting:** 6 commands per 5-second window per user
- **Secret redaction:** Bot token and sensitive values are never exposed in responses
- **No secrets:** `.env` values, passwords, tokens, and SSH keys are never accessible

## Available Commands

| Command | Description |
|---|---|
| `/start` | Welcome message with inline keyboard menu |
| `/help` | All commands with examples |
| `/status` | High-level health summary |
| `/health` | Full server-health.sh report |
| `/docker` | Container status: CPU, RAM, health |
| `/system` | CPU, RAM, Disk, Load, Uptime |
| `/network` | Open ports, Nginx response |
| `/backup` | Latest backup, size, retention |
| `/deploy` | Git SHA, image tags, rollback |
| `/logs <service>` | Tail 30 lines from any container |
| `/metrics` | Top CPU/RAM consumers |
| `/alerts` | Active Prometheus alerts |
| `/grafana` | Dashboard URL and status |
| `/db` | Database size, connections, tables |
| `/security` | UFW, Fail2Ban, SSH, SSL cert |
| `/services` | Per-service health status |
| `/version` | OS, Docker, Node, PG versions |
| `/today` | Daily summary |

### Conversational Mode

Type natural language queries without `/` prefix:

- `status` `cpu` `memory` `disk` `containers` `backups` `deploy`
- `alerts` `db` `security` `network` `metrics` `grafana`
- `services` `version` `today` `logs backend` `help`
- "how much disk is left" "is postgres healthy" "show backend logs"

### Inline Keyboards

The `/start` and `/status` commands present interactive inline keyboards for quick navigation between categories.

## Architecture

```
Telegram API
    ↕
telegram-bot container (monitoring network)
    ├── Docker socket (ro) → docker ps, docker exec, docker logs
    ├── /proc (rw) → CPU, RAM, Disk metrics
    ├── /etc/hostname → hostname
    ├── Prometheus API → scrape targets, alerts
    ├── /opt/siteledger (ro) → deploy state, certs, health script
    └── PostgreSQL (via docker exec) → DB stats
```

## Files

| File | Location |
|---|---|
| bot.py | `/opt/monitoring/telegram-bot/bot.py` |
| Dockerfile | `/opt/monitoring/telegram-bot/Dockerfile` |
| requirements.txt | `/opt/monitoring/telegram-bot/requirements.txt` |
| docker-compose.yml | `/opt/monitoring/docker-compose.yml` (telegram-bot service) |

## Dependencies

- `python-telegram-bot==21.10` — Telegram Bot API framework
- `requests==2.32.3` — HTTP client
- `psutil==6.1.1` — System metrics

## Container Details

- **Image:** `monitoring-telegram-bot` (built from Dockerfile)
- **User:** `botuser` (non-root, docker group GID 988)
- **Memory:** 128 MB limit
- **CPU:** 0.3 cores
- **Health check:** Telegram API getMe
- **Networks:** monitoring, app_internal
- **Restart:** unless-stopped

## Troubleshooting

| Issue | Solution |
|---|---|
| Bot not responding | Check `docker logs telegram-bot` |
| Unauthorized | Verify your Telegram chat ID matches TELEGRAM_CHAT_ID in .env |
| Permission denied (docker) | Verify docker group GID matches host (988) |
| Rate limited | Wait 5 seconds, then retry |
| Nginx checks failing | Verify bot is on app_internal network |
