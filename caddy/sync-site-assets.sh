#!/usr/bin/env bash
# ============================================================================
# sync-site-assets.sh â€” keep Caddy's copy of the SiteLedger SPA current
# ============================================================================
# SiteLedger's production frontend is baked into the siteledger-nginx image
# (`COPY frontend/dist /usr/share/nginx/html`). Caddy serves those files from
# ./site-assets, so the copy must be refreshed whenever SiteLedger deploys a
# new image tag or the SPA will reference hashed asset filenames that do not
# exist locally -> blank page.
#
# Idempotent, and safe to run from cron: it copies only when the source
# index.html differs from the destination.
#
# Caddy reads files from disk per request, so no Caddy restart is needed.
#
# Usage:
#   ./sync-site-assets.sh            # sync if drifted
#   ./sync-site-assets.sh --check    # report only, never copy (exit 1 if drifted)
#   ./sync-site-assets.sh --force    # copy unconditionally
# ============================================================================
set -euo pipefail

SRC_CONTAINER="app-nginx-1"
SRC_PATH="/usr/share/nginx/html"
DEST="$(cd "$(dirname "$0")" && pwd)/site-assets"
MODE="${1:-sync}"

log() { printf '[%s] %s\n' "$(date -Iseconds)" "$*"; }

source_hash() { docker exec "$SRC_CONTAINER" sha256sum "$SRC_PATH/index.html" 2>/dev/null | awk '{print $1}'; }
dest_hash()  { sha256sum "$DEST/index.html" 2>/dev/null | awk '{print $1}'; }

if ! docker inspect "$SRC_CONTAINER" >/dev/null 2>&1; then
  log "ERROR: container $SRC_CONTAINER not found. Cannot sync."
  exit 2
fi

SRC="$(source_hash || true)"
DST="$(dest_hash || true)"

if [ -z "$SRC" ]; then
  log "ERROR: could not read $SRC_PATH/index.html from $SRC_CONTAINER"
  exit 2
fi

if [ "$SRC" = "$DST" ] && [ "$MODE" != "--force" ]; then
  log "in sync (index.html ${SRC:0:12}) â€” nothing to do"
  exit 0
fi

if [ "$MODE" = "--check" ]; then
  log "DRIFT DETECTED: source=${SRC:0:12} dest=${DST:0:12}"
  log "run: $0 --force"
  exit 1
fi

log "syncing assets: source=${SRC:0:12} dest=${DST:0:12}"
TMP="$(mktemp -d "${DEST}.new.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

docker cp "$SRC_CONTAINER:$SRC_PATH/." "$TMP"/ >/dev/null 2>&1

if [ -z "$(dest_hash_of() { sha256sum "$1/index.html" 2>/dev/null | awk '{print $1}'; }; dest_hash_of "$TMP")" ]; then
  log "ERROR: copied tree has no index.html â€” aborting, existing copy untouched"
  exit 1
fi

# Atomic-ish swap: replace contents rather than the directory inode, because
# the directory is bind-mounted into a running container.
find "$DEST" -mindepth 1 -delete
cp -a "$TMP"/. "$DEST"/

NEW="$(dest_hash)"
if [ "$NEW" != "$SRC" ]; then
  log "ERROR: post-sync hash mismatch ($NEW != $SRC)"
  exit 1
fi

log "sync complete: index.html ${NEW:0:12}, $(ls "$DEST/assets" 2>/dev/null | wc -l) asset files"
log "no Caddy restart required (file_server reads from disk)"
exit 0