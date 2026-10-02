# Caddy Migration Parity Checklist

Every row is measured against `app-nginx-1`'s **effective** configuration, which
is `/tmp/nginx.conf` â€” generated at container start by `nginx-entrypoint.sh` via
`envsubst`. The stock `/etc/nginx/nginx.conf` and `/etc/nginx/conf.d/default.conf`
in the image are **inert**; editing them changes nothing.

## Staging parity â€” measured

Source of truth: `/etc/nginx/certs/vhosts/staging.conf`.

| # | Behaviour | nginx | Caddy (test) | Result |
|---|---|---|---|---|
| 1 | HTTPS listener | `443 ssl`, http2 | `8443`, http2 | âœ… |
| 2 | SNI / hostname | `siteledgerstaging.duckdns.org` | same | âœ… |
| 3 | TLS protocols | `TLSv1.2 TLSv1.3` | Caddy default (TLS 1.2+1.3) | âš  verify at cutover |
| 4 | `ssl_prefer_server_ciphers` | `on` | n/a (Caddy has no equivalent) | âš  judgement call |
| 5 | HTTP â†’ HTTPS | implied | `301` | âœ… |
| 6 | `GET /` (SPA) | `200` 1946 b | `200` 1946 b | âœ… byte-identical |
| 7 | `GET /deep/spa/route` | `200` (SPA fallback upstream) | `200` | âœ… |
| 8 | `GET /api/health` | `200` | `200` | âœ… |
| 9 | `GET /api/<unknown>` | `404` | `404` | âœ… |
| 10 | `/` and `/api/` upstream | `staging-frontend:80` | `staging-frontend:80` | âœ… |
| 11 | `X-Forwarded-Proto` | `https` | `https` | âœ… |
| 12 | `X-Forwarded-For` | `$proxy_add_x_forwarded_for` | forwarded | âœ… |
| 13 | `client_max_body_size 12m` | enforced | `request_body { max_size 12MB }` | âœ… supported in 2.10 |
| 14 | HSTS | `max-age=31536000; includeSubDomains` | identical | âœ… exact |
| 15 | `X-Content-Type-Options` | `nosniff` | identical | âœ… exact |
| 16 | `X-Frame-Options` | `DENY` | identical | âœ… exact |
| 17 | `Referrer-Policy` | `strict-origin-when-cross-origin` | identical | âœ… exact |
| 18 | `server` header | `server: nginx` | suppressed | âœ… better |
| 19 | API rate limit 30r/s burst 50 | `limit_req api_limit` | **none** | âŒ **GAP** |
| 20 | Login rate limit 5r/m | *not on staging* | n/a | n/a staging |

## Production parity â€” NOT yet built

Source of truth: `/tmp/nginx.conf` + `/etc/nginx/app-locations.conf`.
**Nothing in this section has been implemented or tested.** Do not treat it as ready.

| # | Behaviour | nginx | Status |
|---|---|---|---|
| P1 | HTTP â†’ HTTPS `301` | `return 301 https://$host$request_uri` | â˜ |
| P2 | HTTPS default vhost `server_name _` | yes | â˜ |
| P3 | SPA `try_files $uri $uri/ /index.html` | yes | â˜ |
| P4 | `/api/` â†’ `backend:3000` | yes | â˜ |
| P5 | `/api/auth/login` â†’ `backend:3000` | nested location | â˜ |
| P6 | API rate limit `30r/s burst 50 nodelay` | `limit_req api_limit` | âŒ gap |
| P7 | Login rate limit `5r/m burst 3 nodelay` | `limit_req login_limit` | âŒ gap â€” **highest risk** |
| P8 | WebSocket upgrade `/api/` | `Upgrade`/`Connection: upgrade` | â˜ Caddy automatic |
| P9 | `proxy_read_timeout` / `proxy_send_timeout` | `60s` | â˜ |
| P10 | `client_max_body_size 12m` | `12m` | â˜ |
| P11 | `server_tokens off` | yes | â˜ Caddy omits by default |
| P12 | gzip + types + `min_length 256` | yes | â˜ Caddy default differs |
| P13 | 7 security headers | HSTS + 6 others | â˜ |
| P14 | `/grafana/` â†’ `grafana:3000` | yes | â˜ |
| P15 | `/grafana/api/live/` (WebSocket) | yes | â˜ Caddy automatic |
| P16 | `X-Forwarded-Port 443` on Grafana | yes | â˜ |
| P17 | TLS: `TLSv1.2/1.3`, prefer ciphers on, `SSL:10m` cache | yes | â˜ |

Note P13: **production sends 7 headers, staging sends 4.** The staging Caddyfile
reproduces 4 on purpose. Production must add `Permissions-Policy`,
`Cross-Origin-Resource-Policy`, `Cross-Origin-Opener-Policy`,
`X-Permitted-Cross-Domain-Policies`.

## Rate limiting â€” the one real blocker

**Requirement.** nginx enforces, per client IP:

```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m   rate=30r/s;
limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;
# /api/auth/login -> login_limit burst 3 nodelay
# /api/*          -> api_limit    burst 50 nodelay
```

`login_limit` is brute-force protection on a login endpoint. Losing it silently
would be a real security regression, so **this blocks cutover.**

**Options, with honest trade-offs:**

| Option | Rate limiting | Cost / risk |
|---|---|---|
| A. Custom Caddy image with a rate-limit module (`caddy-ratelimit` via `xcaddy`) | Yes | Requires a third-party plugin. Supply-chain risk, maintenance risk, and it must be rebuilt when Caddy patches. Needs pinned module versions. |
| B. Move rate limiting into the application (SiteLedger backend) | Yes, better | Changes application code â€” explicitly out of scope for this migration, and SiteLedger's code is not to be modified. |
| C. Caddy â†’ nginx â†’ app (keep nginx as an inner rate-limiting hop) | Yes | Keeps nginx alive, so the migration does not actually retire it. Defeats the goal; adds a hop. |
| D. External limiter (Cloudflare or similar) in front | Yes | Adds a third party and a DNS/proxy dependency. Cloudflare is not currently in front of this host. |
| E. Accept the loss | No | **Not acceptable** for the login limiter. |

**Recommendation:** option A, with a pinned `xcaddy` build and a documented
upgrade procedure â€” or B if SiteLedger's owners prefer application-level limits.
This needs an explicit decision before cutover; it is not an implementation detail.

## Certificate model (recommended)

Current state, verified:

| Domain | ACME owner | Installs to | Reload |
|---|---|---|---|
| `siteledger.duckdns.org` | **acme.sh** (DNS-01, DuckDNS) | `/opt/siteledger/app/nginx/certs/{fullchain,privkey}.pem` via `Le_Real*Path` | `docker restart app-nginx-1` |
| `siteledgerstaging.duckdns.org` | **acme.sh** (DNS-01, DuckDNS) | `.../certs/staging-{fullchain,privkey}.pem` | `docker exec app-nginx-1 nginx -s reload \|\| true` |

Next renewals: **2026-10-26** (prod) and **2026-10-26** (staging). Certs expire
2026-11-08 and 2026-11-25. Renewal is **working and automated** â€” my earlier
audit claim that it was broken was wrong; it was based on the stub
`deploy/nginx.sh`, which is not the mechanism in use.

**Dormant second system:** `certbot.timer` is active (2Ã—/day) and
`/etc/letsencrypt/renewal/siteledger.duckdns.org.conf` configures
`authenticator = standalone`, `http-01`, on the **Let's Encrypt** directory â€”
for a domain currently served by a **ZeroSSL** cert from acme.sh. Its
`live/`, `archive/` and `accounts/` directories are root-only and were empty of
renewable lineage when inspected. A deploy hook
(`/etc/letsencrypt/renewal-hooks/deploy/copy-to-siteledger.sh`) would copy from
`/etc/letsencrypt/live/...` and reload nginx.

**Latent risk:** if anyone restores a certbot lineage, the next `certbot.timer`
run attempts HTTP-01 **standalone on port 80**, which `app-nginx-1` owns. That
either fails or disrupts production ingress.

**Recommended target model â€” one owner per domain:**

```
ONE domain
    â†“
ONE ACME owner            (acme.sh today; Caddy after cutover â€” pick one, not both)
    â†“
ONE certificate path      (Caddy: its own storage, no copy into nginx's directory)
    â†“
controlled reload         (`caddy reload` / SIGUSR1, never `docker restart`)
```

Actions before cutover:
1. Disable or purge the certbot lineage for `siteledger.duckdns.org`.
2. Do not enable Caddy ACME while acme.sh still renews the same domain.
3. Change acme.sh's prod `Le_ReloadCmd` from `docker restart app-nginx-1` to
   `nginx -s reload` â€” a hard restart causes avoidable connection drops.
4. Give Caddy the DuckDNS API token via an env file with `0600`, never inline.

## Sam Control Center â€” prepared, not yet routable

Not deployed (no container, no listener on 8081/8001). When it lands:

```caddyfile
sam.<duckdns-domain> {
    # Frontend: same-origin SPA + API on one origin.
    handle {
        reverse_proxy sam-control-center:8080
    }
}
```

Caddy reaches `sam-backend` **directly on `monitoring`** at `sam-backend:8000`
â€” verified. No new published port is required.

Rules to hold:

- Sam's own password + TOTP + HttpOnly cookie auth stays enforced. Caddy adds no
  auth and no bypass.
- Only `/api/control-center/` and `/api/observability/` are proxied. Sam's legacy
  `X-User-Id`-only chat routes are **not** exposed publicly.
- `sam-postgres` (5432) and `sam-redis` (6379) stay on
  `project-sam_project_sam_internal`, which Caddy does not join. Verified: Caddy
  cannot resolve `postgres` or `redis`.
- The observability API is read-only `GET`; Caddy must not add write verbs.
- 8080/8001/8000 stay unpublished.

## OpenConstructionERP â€” design only

Currently `0.0.0.0:8090`, plain HTTP, **no proxy**. Target:

```
Internet :443 â†’ Caddy â†’ openerp-app-1:8080   (on openerp_default)
```

Requires: a hostname (do not invent one), a certificate, and joining
`openerp_default`. On success, remove the `0.0.0.0:8090` publish from
`/opt/openerp/docker-compose.yml` so the app is no longer directly reachable.
**Not actioned.** SiteLedger is not currently used for this, so there is no
existing hostname to reuse.

## Final topology (target)

```
                        Caddy  (only public 80/443)
                          â”‚
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        â”‚                 â”‚                  â”‚                   â”‚
 app_internal      app_staging-internal   monitoring      openerp_default
        â”‚                 â”‚                  â”‚                   â”‚
 app-backend-1     staging-frontend    grafana, prometheus   openerp-app-1
 grafana           staging-backend     alertmanager, loki
 âš  app-db-1                           sam-backend
                                       telegram-bot
```

Not joined, deliberately: `project-sam_project_sam_internal` (Postgres, Redis),
`trading-bot_default`. Caddy reaches HTTP endpoints only, never databases.

## Cutover gate

Do not touch 80/443 until **all** of these are true:

- [ ] Production parity rows P1â€“P17 implemented and tested
- [ ] **Rate-limiting decision made and implemented** (P6, P7)
- [ ] Certbot lineage disabled so only one ACME owner exists
- [ ] Caddy certificate issuance proven on a test hostname
- [ ] `app-db-1` reachable-from-Caddy risk reviewed
- [ ] Rollback rehearsed on the test instance
- [ ] Maintenance window agreed