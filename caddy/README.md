# Caddy â€” VPS Ingress (Sam VPS)

**Status: LIVE. Caddy is the production ingress on `0.0.0.0:80` and `:443`.**

It replaced `app-nginx-1` as the reverse proxy for SiteLedger production, SiteLedger
staging, and Grafana. `app-nginx-1` is still running on `127.0.0.1`-equivalent high
ports (`18080`/`18443`) and is fully intact, so rollback is a script away.

## Location

Canonical home is `caddy/` in the **monitoring-stack** repository, deployed to
`/opt/monitoring/caddy`.

It started at `/home/deploy/caddy-migration` because `/opt` was root-owned at the
time, then moved here once it was clear this is VPS ingress infrastructure and
belongs with the rest of the stack.

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Test instance. Loopback ports only. Networks declared `external` (joined, never created). |
| `Caddyfile` | Staging-only parity config. HTTP 8080 / HTTPS 8443 inside the container. |
| `certs/site.crt`, `certs/site.key` | **Self-signed test certificate.** Generated locally with `openssl`, no ACME contact. Not a production certificate. |
| `migration-checklist.md` | Parity checklist + rate-limiting decision record. This becomes the cutover acceptance test. |
| `rollback.md` | Exact cutover and rollback commands. |

## Test topology

```
Internet
   â”‚  80 / 443
   â–¼
app-nginx-1  (production, UNTOUCHED)
   â”œâ”€â”€ /                     SiteLedger prod SPA
   â”œâ”€â”€ /api/                 â†’ backend:3000
   â””â”€â”€ /grafana/             â†’ grafana:3000

127.0.0.1:8081  â”€â”€â–º  caddy-migration-test :8080   HTTP  â†’ 301 redirect
127.0.0.1:8082  â”€â”€â–º  caddy-migration-test :8443   HTTPS â†’ staging SPA + /api
```

Both test ports are bound to `127.0.0.1` only and were verified **not reachable
from outside the host**.

Note: `8443` is the port *inside* the container. From the host, use `8082`.

## Networks

Caddy joins three **existing** networks and creates none:

| Network | Why | Reaches |
|---|---|---|
| `app_staging-internal` | staging parity test | `siteledger-staging-frontend` |
| `app_internal` | production parity (later) | `app-backend-1`, `grafana`, `app-db-1` âš  |
| `monitoring` | Sam + Grafana later | `sam-backend`, `grafana`, `prometheus`, `alertmanager` |

Deliberately **not** joined: `project-sam_project_sam_internal`.
Verified â€” Caddy cannot resolve `postgres` or `redis`, so it has no network path
to any database. `app-db-1` is reachable because `app_internal` carries it; that
is inherited from `app-nginx-1`'s membership and should be reviewed before
cutover (see checklist).

## Running

```bash
cd /home/deploy/caddy-migration

docker compose up -d          # start (loopback only)
docker compose ps
docker compose logs -f

# validate config without starting anything
docker run --rm \
  -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -v "$PWD/certs:/certs:ro" \
  caddy:2.10-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

docker compose down           # stop and remove
```

## Testing the test instance

```bash
# HTTP -> HTTPS redirect
curl -sI -H 'Host: siteledgerstaging.duckdns.org' http://127.0.0.1:8081/ | head -1

# staging SPA through Caddy (self-signed cert, hence -k)
curl -sk --resolve siteledgerstaging.duckdns.org:8082:127.0.0.1 \
  https://siteledgerstaging.duckdns.org:8082/ | head -5

# header parity vs production nginx
curl -skI --resolve siteledgerstaging.duckdns.org:443:127.0.0.1 \
  https://siteledgerstaging.duckdns.org/ | grep -iE 'HTTP/|strict-transport|x-frame|x-content|referrer'
curl -skI --resolve siteledgerstaging.duckdns.org:8082:127.0.0.1 \
  https://siteledgerstaging.duckdns.org:8082/ | grep -iE 'HTTP/|strict-transport|x-frame|x-content|referrer'
```

## What this instance deliberately does NOT do

- Bind `80` or `443`.
- Run ACME. `auto_https off` plus an explicit certificate file means **zero**
  contact with Let's Encrypt, ZeroSSL or DuckDNS.
- Expose the Caddy admin API (`admin off`, and port 2019 is not published).
- Modify any existing container, network, volume, certificate, or firewall rule.
- Touch SiteLedger, OpenConstructionERP, Sam, or monitoring configuration.