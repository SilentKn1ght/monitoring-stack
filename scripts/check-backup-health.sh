#!/bin/sh
# Backup Health Check — writes Prometheus textfile metrics
# Run via cron every 30 minutes

METRICS_DIR="/var/lib/node_exporter/textfile_collector"
PROM_FILE="${METRICS_DIR}/backup_health.prom"
TEMP_FILE="${PROM_FILE}.$$"

mkdir -p "${METRICS_DIR}"

# Check 1: Is backup container running?
BACKUP_RUNNING=0
if docker ps -q --filter "name=app-db-backup-1" 2>/dev/null | grep -q .; then
    BACKUP_RUNNING=1
fi

# Check 2: Is there a recent backup (< 30 hours)?
RECENT_BACKUP=0
RECENT_COUNT=$(docker run --rm -v app_db_backups:/backups alpine \
    find /backups -name "*.sql.gz" -mmin -1620 2>/dev/null | wc -l)
if [ "${RECENT_COUNT}" -gt 0 ]; then
    RECENT_BACKUP=1
fi

# Check 3: Is the latest backup valid (>0 bytes)?
LATEST_VALID=0
LATEST_FILE=$(docker run --rm -v app_db_backups:/backups alpine \
    sh -c 'ls -t /backups/*.sql.gz 2>/dev/null | head -1')
if [ -n "${LATEST_FILE}" ]; then
    LATEST_SIZE=$(docker run --rm -v app_db_backups:/backups alpine \
        stat -c%s "${LATEST_FILE}" 2>/dev/null || echo 0)
    if [ "${LATEST_SIZE}" -gt 100 ]; then
        LATEST_VALID=1
    fi
fi

cat > "${TEMP_FILE}" << EOF
# HELP backup_health Backup system health status (1=OK, 0=FAIL)
# TYPE backup_health gauge
backup_health{component="container_running"} ${BACKUP_RUNNING}
backup_health{component="recent_backup"} ${RECENT_BACKUP}
backup_health{component="latest_backup_valid"} ${LATEST_VALID}
EOF

mv "${TEMP_FILE}" "${PROM_FILE}"
