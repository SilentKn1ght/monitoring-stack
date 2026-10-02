#!/bin/bash
# Rollback: restore app-nginx-1 as the ingress for siteledger.duckdns.org.
#
# Safe to run at any time. Restores the exact pre-migration state:
#   - Caddy stopped
#   - nginx host ports returned to 80/443
#   - nginx started and healthy
#
# Usage: bash rollback.sh [--dry-run]

set -u
DRY="${1:-}"
CADDY_DIR=/home/deploy/caddy-migration
SL_DIR=/opt/siteledger/app
ENV="$SL_DIR/.env"

say() { printf '\n== %s\n' "$*"; }

say "PRE-CHECKS"
echo "  caddy:  $(docker inspect caddy-migration-caddy-1 --format '{{.State.Status}}' 2>/dev/null || echo absent)"
echo "  nginx:  $(docker inspect app-nginx-1 --format '{{.State.Status}}' 2>/dev/null || echo absent)"
echo "  nginx image cached: $(docker image inspect $(docker inspect app-nginx-1 --format '{{.Image}}' 2>/dev/null) >/dev/null 2>&1 && echo yes || echo NO)"
echo "  current production: siteledger -> $(curl -sk -o /dev/null -w '%{http_code}' --resolve siteledger.duckdns.org:443:127.0.0.1 https://siteledger.duckdns.org/ 2>/dev/null)"

if [ "$DRY" = "--dry-run" ]; then
  say "DRY RUN â€” no changes will be made"
  echo "  would: stop caddy -> set HOST_PORT 80/443 -> recreate+start nginx -> verify"
  exit 0
fi

say "STEP 1 â€” stop Caddy (releases 80/443)"
cd "$CADDY_DIR"
docker compose -p caddy-migration -f docker-compose.prod.yml stop caddy 2>&1 | tail -2

say "STEP 2 â€” restore nginx host ports to 80/443"
cd "$SL_DIR"
sed -i 's/^HOST_PORT_HTTP=.*/HOST_PORT_HTTP=80/'   "$ENV"
sed -i 's/^HOST_PORT_HTTPS=.*/HOST_PORT_HTTPS=443/' "$ENV"
grep -E '^HOST_PORT' "$ENV" | sed 's/^/  /'

say "STEP 3 â€” confirm 80/443 are free before starting nginx"
for i in $(seq 1 10); do
  ss -lntH 2>/dev/null | grep -qE ':(80|443)\b' || break
  sleep 2
done
if ss -lntH 2>/dev/null | grep -qE ':(80|443)\b'; then
  echo "  ABORT: 80/443 still bound by:"; ss -lntH | grep -E ':(80|443)\b'
  exit 1
fi
echo "  PASS free"

say "STEP 4 â€” recreate and start nginx on 80/443"
docker compose -p app -f docker-compose.prod.yml up -d --no-deps nginx 2>&1 | tail -3
sleep 10
docker inspect app-nginx-1 --format '  app-nginx-1 {{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{end}} ports={{range $k,$v := .NetworkSettings.Ports}}{{$k}}={{range $v}}{{.HostIp}}:{{.HostPort}} {{end}}{{end}}'

say "STEP 5 â€” VERIFY"
f=0
chk() { if [ "$2" = "$3" ]; then echo "  PASS  $1 -> $3"; else echo "  FAIL  $1 got=$3 want=$2"; f=1; fi; }
chk "80/443 owner" "nginx" "$(docker inspect app-nginx-1 --format '{{range $k,$v := .NetworkSettings.Ports}}{{if eq $k "80/tcp"}}nginx{{end}}{{end}}')"
chk "production SPA" "200" "$(curl -sk -o /dev/null -w '%{http_code}' --resolve siteledger.duckdns.org:443:127.0.0.1 https://siteledger.duckdns.org/)"
chk "SPA deep link" "200" "$(curl -sk -o /dev/null -w '%{http_code}' --resolve siteledger.duckdns.org:443:127.0.0.1 https://siteledger.duckdns.org/x/y/z)"
chk "api health" "200" "$(curl -sk -o /dev/null -w '%{http_code}' --resolve siteledger.duckdns.org:443:127.0.0.1 https://siteledger.duckdns.org/api/health)"
chk "staging" "200" "$(curl -sk -o /dev/null -w '%{http_code}' --resolve siteledgerstaging.duckdns.org:443:127.0.0.1 https://siteledgerstaging.duckdns.org/)"
chk "grafana" "200" "$(curl -sk -o /dev/null -w '%{http_code}' --resolve siteledger.duckdns.org:443:127.0.0.1 https://siteledger.duckdns.org/grafana/api/health)"
chk "http->https redirect" "301" "$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: siteledger.duckdns.org' http://127.0.0.1/)"

say "RESULT"
[ "$f" -eq 0 ] && echo "  ROLLBACK COMPLETE â€” nginx is the ingress again." \
              || echo "  ROLLBACK INCOMPLETE â€” investigate before declaring success."
echo
echo "To return to Caddy later:"
echo "  bash $CADDY_DIR/rollback-to-caddy.sh"