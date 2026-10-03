#!/usr/bin/env bash
# ============================================================================
# ddns-update.sh — keep DuckDNS A records pointing at this host
# ============================================================================
# Why this exists: samstats.duckdns.org and siteledger.duckdns.org are served by
# Caddy with certificates validated over HTTP-01. HTTP-01 needs DNS to already
# point here and never touches it, so nothing else keeps those records fresh.
# Only siteledgerstaging had a crontab updater, which left the production
# hostname and the Control Center unprotected against a DuckDNS reset.
#
# acme.sh's DNS-01 challenge for siteledger also updates its own record, but
# only during a renewal, so a record can rot for weeks between renewals.
#
# The API token is read from secrets/duckdns.token (mode 0600, and `secrets/` is
# in .gitignore) rather than being placed in the crontab, where it is visible to
# anyone who can run `crontab -l`. The pre-existing siteledgerstaging entry still
# has its token inline and should be migrated separately.
#
# Usage: ddns-update.sh [domain ...]
#   with no arguments, updates every domain in DUCKDNS_DOMAINS.
#
# DuckDNS responds OK / KI on success and KO when the token is rejected, so the
# token is distinguishable from a network failure.
# ============================================================================
set -uo pipefail

SECRETS_DIR="$(cd "$(dirname "$0")/.." && pwd)/secrets"
TOKEN_FILE="${SECRETS_DIR}/duckdns.token"
LOG="${SECRETS_DIR}/../logs/ddns-update.log"

mkdir -p "$(dirname "$LOG")" 2>/dev/null || true

log() { printf '%s %s\n' "$(date -Iseconds)" "$*" >>"$LOG" 2>/dev/null || true; }

if [ ! -r "$TOKEN_FILE" ]; then
  log "FATAL: token file unreadable: $TOKEN_FILE"
  echo "ddns-update: token file unreadable: $TOKEN_FILE" >&2
  exit 2
fi

TOKEN=$(tr -d '[:space:]' <"$TOKEN_FILE")
if [ -z "$TOKEN" ]; then
  log "FATAL: token file empty"
  exit 2
fi

# Domains to keep pinned. samstats and siteledger are the ones that were
# missing; siteledgerstaging is included so one script owns all three.
DEFAULT_DOMAINS="samstats siteledger siteledgerstaging"

DOMAINS="${*:-${DUCKDNS_DOMAINS:-$DEFAULT_DOMAINS}}"

# Re-detect the egress address each run so a VPS migration self-heals.
IP=$(curl -s --max-time 10 https://api.ipify.org 2>/dev/null || true)
if [ -z "$IP" ]; then
  # Fall back to the address this host believes it has.
  IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
fi
if [ -z "$IP" ]; then
  log "FATAL: could not determine public IPv4"
  echo "ddns-update: could not determine public IPv4" >&2
  exit 3
fi

rc=0
for domain in $DOMAINS; do
  resp=$(curl -s --max-time 15 \
    "https://www.duckdns.org/update?domains=${domain}&token=${TOKEN}&ip=${IP}" 2>/dev/null || true)
  case "$resp" in
    OK|KI) log "ok      ${domain} -> ${IP} (${resp})" ;;
    KO)     log "REJECT  ${domain} - token refused by DuckDNS"; rc=1 ;;
    *)      log "error   ${domain} -> ${IP}: ${resp:-no response}"; rc=1 ;;
  esac
  printf '%-24s %s -> %s\n' "$domain" "${resp:-no-response}" "$IP"
done

exit $rc