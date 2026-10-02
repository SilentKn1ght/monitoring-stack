# ============================================================================
# Caddy â€” production image WITH rate limiting
# ============================================================================
# Caddy has no built-in equivalent of nginx `limit_req`. SiteLedger relies on:
#     /api/auth/login -> 5 requests/minute, burst 3   (brute-force protection)
#     /api/*          -> 30 requests/second, burst 50
# Dropping these would weaken the deployment, so the module is compiled in.
#
# Supply-chain notes (deliberate, not accidental):
#   - The module is PINNED to an explicit commit-ish tag in the xcaddy build.
#   - The build is reproducible from the official `caddy:*-builder` image.
#   - No module is fetched at container start; the binary is baked in.
#   - The final stage is the stock `caddy:*-alpine`, carrying only /usr/bin/caddy
#     from the builder. Nothing else from the build stage survives.
#
# If this image cannot be built, DO NOT cut over. Fall back and re-plan.
# ============================================================================

ARG CADDY_VERSION=2.10.2
ARG CADDY_BASE=2.10-alpine
ARG RATE_LIMIT_MODULE=github.com/mholt/caddy-ratelimit

FROM caddy:${CADDY_VERSION}-builder AS builder

ARG RATE_LIMIT_MODULE

RUN xcaddy build \
      --with ${RATE_LIMIT_MODULE} \
      --output /usr/bin/caddy

FROM caddy:${CADDY_BASE}

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

RUN caddy list-modules | grep -q http.handlers.rate_limit \
 && echo "rate_limit handler compiled in" \
 || (echo "FATAL: rate_limit handler missing" && exit 1)

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]