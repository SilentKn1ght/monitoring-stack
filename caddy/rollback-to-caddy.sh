#!/bin/bash
# Return to Caddy as the ingress (inverse of rollback.sh).
set -u
CADDY_DIR=/opt/monitoring/caddy
SL_DIR=/opt/siteledger/app
ENV="$SL_DIR/.env"

say() { printf '\n== %s\n' "$*"; }

say "STEP 1 â€” refresh SiteLedger SPA assets"
bash "$CADDY_DIR/sync-site-assets.sh" 2>&1 | tail -2

say "STEP 2 â€” stop nginx (release 80/443)"
cd "$SL_DIR"
docker compose -p app -f docker-compose.prod.yml stop nginx 2>&1 | tail -2

say "STEP 3 â€” move nginx to loopback-ish high ports"
sed -i 's/^HOST_PORT_HTTP=.*/HOST_PORT_HTTP=18080/'   "$ENV"
sed -i 's/^HOST_PORT_HTTPS=.*/HOST_PORT_HTTPS=18443/' "$ENV"

say "STEP 4 â€” wait for ports"
for i in $(seq 1 10); do
  ss -lntH 2>/dev/null | grep -qE ':(80|443)\b' || break
  sleep 2
done
ss -lntH 2>/dev/null | grep -E ':(80|443)\b' && { echo "ABORT: still bound"; exit 1; }
echo "  PASS free"

say "STEP 5 â€” start Caddy, then restart nginx on its new ports"
cd "$CADDY_DIR"
docker compose -p caddy-migration -f docker-compose.prod.yml up -d 2>&1 | tail -2
sleep 8
cd "$SL_DIR"
docker compose -p app -f docker-compose.prod.yml up -d --no-deps nginx 2>&1 | tail -2

say "STEP 6 â€” VERIFY"
f=0
chk() { if [ "$2" = "$3" ]; then echo "  PASS  $1 -> $3"; else echo "  FAIL  $1 got=$3 want=$2"; f=1; fi; }
chk "caddy running" "running" "$(docker inspect caddy-migration-caddy-1 --format '{{.State.Status}}')"
chk "production SPA" "200" "$(curl -sk -o /dev/null -w '%{http_code}' --resolve siteledger.duckdns.org:443:127.0.0.1 https://siteledger.duckdns.org/)"
chk "api health" "200" "$(curl -sk -o /dev/null -w '%{http_code}' --resolve siteledger.duckdns.org:443:127.0.0.1 https://siteledger.duckdns.org/api/health)"
chk "staging" "200" "$(curl -sk -o /dev/null -w '%{http_code}' --resolve siteledgerstaging.duckdns.org:443:127.0.0.1 https://siteledgerstaging.duckdns.org/)"
chk "grafana" "200" "$(curl -sk -o /dev/null -w '%{http_code}' --resolve siteledger.duckdns.org:443:127.0.0.1 https://siteledger.duckdns.org/grafana/api/health)"

say "RESULT"
[ "$f" -eq 0 ] && echo "  CADDY IS THE INGRESS AGAIN." || echo "  INCOMPLETE â€” investigate."