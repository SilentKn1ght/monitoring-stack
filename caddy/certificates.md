# Certificate renewal — operational notes

Everything here was verified on the running host. Do not "simplify" anything in
this file without re-testing the renewal path; two of these findings were silent
and only surfaced by forcing a real renewal.

## Current state

| Domain | CA | Challenge | Cert expires | Next renewal |
|---|---|---|---|---|
| `siteledger.duckdns.org` | Let's Encrypt (`YE1`) | DNS-01 DuckDNS | 2027-01-01 | 2026-12-01 |
| `siteledgerstaging.duckdns.org` | Let's Encrypt (`YE1`) | DNS-01 DuckDNS | 2026-11-25 | 2026-10-26 |
| `samstats.duckdns.org` | Let's Encrypt (`YE1`) | HTTP-01 webroot | 2027-01-01 | 2026-12-01 |

All three use **Let's Encrypt** deliberately. `siteledger` was originally on
ZeroSSL with no EAB credentials. ZeroSSL requires EAB for *new* account
registrations, so if the acme.sh account were ever lost, renewal would fail
permanently with no fallback. Let's Encrypt needs no EAB.

## FINDING 1 — `caddy reload` does NOT pick up a renewed certificate

This is the important one, and it was silently broken.

Caddy caches PEM certificates **by file path**. Re-applying the config with
`caddy reload` does **not** re-read the certificate files. Proven directly: the
staging certificate was copied over `fullchain.pem` and `caddy reload` was run —
Caddy kept serving the previous certificate.

The hook originally stored was:

```
docker exec caddy-migration-caddy-1 caddy reload ... || docker restart caddy-migration-caddy-1
```

`caddy reload` exits **0**, so the `||` fallback never ran. On every renewal the
cert file would be updated, the hook would report success, and Caddy would
quietly keep serving the **expired** certificate until someone noticed in a
browser. This is precisely the failure the monitoring was added to catch, and it
would have been invisible to it too, because `probe_ssl_earliest_cert_expiry`
reads the handshake Caddy actually performs.

**The stored hook for all three domains is now:**

```
docker restart caddy-migration-caddy-1
```

Verified working. Cost is a brief connection blip at renewal time, which is
acceptable roughly twice a year and vastly better than an expired certificate.
Caddy's shutdown is graceful, so in-flight requests finish.

## FINDING 2 — `--install-cert` without `--reloadcmd` wipes the stored hook

Running `--install-cert` without `--reloadcmd` **cleared** `Le_ReloadCmd` to
empty for `siteledger` during the CA switch. Always pass the reload command
explicitly, or re-set it afterwards:

```bash
HOOK='docker restart caddy-migration-caddy-1'
B64=$(printf '%s' "$HOOK" | base64 -w0)
python3 - "/home/deploy/.acme.sh/$DOMAIN.duckdns.org_ecc/$DOMAIN.duckdns.org.conf" \
  "__ACME_BASE64__START_${B64}__ACME_BASE64__END_"
```

## FINDING 3 — acme.sh 3.1.5 quirks

- `-D key=value` is **not supported**. DNS API credentials come from the
  environment (`export DuckDNS_Token=...`), which the script also persists into
  `account.conf`.
- `--issue` skips a domain that is not yet due **regardless of the requested
  CA**. Switching CAs therefore needs `--force`:

  ```bash
  export DuckDNS_Token="$(cat /opt/monitoring/secrets/duckdns.token)"
  acme.sh --issue --server letsencrypt -d siteledger.duckdns.org \
          --dns dns_duckdns --keylength ec-256 --force
  ```

## Verifying a renewal actually took effect

Do not trust the install output or the hook's exit code alone. Check the
**served** certificate:

```bash
echo | openssl s_client -connect 127.0.0.1:443 -servername siteledger.duckdns.org 2>/dev/null \
  | openssl x509 -noout -serial -issuer -enddate
```

The serial must differ from the previous one. Then confirm the strict monitor
agrees (it scrapes every 15s):

```bash
docker exec prometheus wget -qO- \
  'http://localhost:9090/api/v1/query?query=probe_ssl_earliest_cert_expiry%7Bjob%3D%22blackbox-tls%22%7D'
```

## Chain shape is correct — do not "fix" it

The Let's Encrypt chain is four certificates:

```
leaf -> YE1 -> Root YE -> ISRG Root X2 (cross-signed by ISRG Root X1)
```

`ISRG Root X2` is issued *by* `ISRG Root X1`, so it is an intermediate, not a
self-signed root. RFC 5246 forbids sending the self-signed root, and it is
correctly absent — `ISRG Root X1` is not in the file. This was briefly
misdiagnosed as "the root is being served"; it is not. `openssl verify` returns
`OK` and the strict `tls_strict` blackbox probe reports `probe_success=1`.

## HTTP-01 dependency (samstats only)

`samstats` is validated over HTTP-01 against `/opt/monitoring/caddy/acme-webroot`,
which Caddy serves on `:80` **without redirecting**. If Caddy is down when the
renewal fires, that renewal fails. The file is mounted read-only into Caddy;
acme.sh writes it from the host.

## DNS

`scripts/ddns-update.sh` runs every 5 minutes and pins all three records.
`samstats` uses HTTP-01, so nothing else keeps its record fresh. The DuckDNS token
lives in `secrets/duckdns.token` (0600, gitignored) rather than in the crontab.

## Not done: certbot

`certbot.timer` is disabled and inactive, but
`/etc/letsencrypt/renewal/siteledger.duckdns.org.conf` still exists with
`authenticator = standalone`. Re-enabling certbot would attempt HTTP-01 on port
80, which Caddy now owns. Its deploy hook also restarts nginx. Removing all of
this needs root.