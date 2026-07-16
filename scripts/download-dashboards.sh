#!/bin/sh
# Download Grafana dashboards from grafana.com
# Run this script on first deployment to populate dashboards
set -e

DASHBOARD_DIR="/opt/monitoring/grafana/dashboards"

# Dashboard IDs and names (name:id format)
DASHBOARDS="
NodeExporter:1860
DockerContainers:11580
DockerEngine:10566
cAdvisor:14282
PostgreSQL:9628
Loki:13639
Prometheus:3662
Grafana:1860
Nginx:12744
BlackboxExporter:7587
DiskAndFilesystem:2639
"

# Grafana API base URL
GRAFANA_API="https://grafana.com/api/dashboards"

for entry in $DASHBOARDS; do
  NAME=$(echo "$entry" | cut -d: -f1)
  ID=$(echo "$entry" | cut -d: -f2)
  OUTPUT="${DASHBOARD_DIR}/${NAME}.json"

  if [ -f "$OUTPUT" ]; then
    echo "Dashboard $NAME already exists, skipping"
    continue
  fi

  echo "Downloading dashboard: $NAME (ID: $ID)..."
  wget -q -O "$OUTPUT" "${GRAFANA_API}/${ID}/revisions/latest/download" || \
    echo "Failed to download dashboard $NAME"
done

echo "Dashboard download complete"
echo "Run: docker compose restart grafana"
