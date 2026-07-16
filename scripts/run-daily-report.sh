#!/bin/sh
# Wrapper to run daily report inside the monitoring Docker network
# Runs at 11:00 AM IST daily (cron: 30 11 * * *)
cd /opt/monitoring

# Load telegram tokens from .env
TELEGRAM_BOT_TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" .env | cut -d= -f2-)
TELEGRAM_CHAT_ID=$(grep "^TELEGRAM_CHAT_ID=" .env | cut -d= -f2-)

# Pre-compute container metrics via Docker CLI
CONTAINER_COUNT=$(docker ps -q 2>/dev/null | wc -l)
CONTAINER_RESTARTS=$(docker ps -q 2>/dev/null | xargs -I{} docker inspect {} --format "{{.RestartCount}}" 2>/dev/null | paste -sd+ | bc 2>/dev/null || echo 0)
BACKUP_ALIVE=$(docker ps -q --filter "name=app-db-backup-1" 2>/dev/null | wc -l)

docker run --rm --network monitoring \
  -e PROMETHEUS_URL="http://prometheus:9090" \
  -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  -e TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
  -e CONTAINER_COUNT="$CONTAINER_COUNT" \
  -e CONTAINER_RESTARTS="$CONTAINER_RESTARTS" \
  -e BACKUP_ALIVE="$BACKUP_ALIVE" \
  -v /opt/monitoring/scripts/daily-report.py:/report.py:ro \
  -e TZ=Asia/Kolkata \
  python:3.11-alpine \
  python3 /report.py
