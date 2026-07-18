# Production Security Hardening Report

**Server:** `vmi3410257` (84.46.248.57)  
**Date:** 10 July 2026  
**Scope:** SSH Configuration + Host Firewall (UFW)

---

## 1. Original Configuration (Before Changes)

### 1.1 SSH Effective Configuration (from `sshd -T`)

| Directive | Effective Value | Source |
|---|---|---|
| `PermitRootLogin` | `yes` (last wins: line 46 overrides line 11) | Conflicting lines: 11 and 46 |
| `PasswordAuthentication` | `no` | Correct |
| `PubkeyAuthentication` | `yes` | Correct |
| `X11Forwarding` | `yes` | Not needed on server |
| `AllowAgentForwarding` | `yes` | Not needed |
| `ClientAliveInterval` | `0` (disabled) | No idle timeout |
| `ClientAliveCountMax` | `3` | Default |
| `MaxAuthTries` | `6` | Default, too permissive |
| `LoginGraceTime` | `120` seconds | Default, generous |
| `PermitEmptyPasswords` | `no` | Correct |

### 1.2 Raw SSH Config Conflict

`/etc/ssh/sshd_config` had two conflicting `PermitRootLogin` directives:

```
Line 11: PermitRootLogin no
Line 16: Include /etc/ssh/sshd_config.d/*.conf
Line 46: PermitRootLogin yes     # ← Overrides line 11
```

The last occurrence wins in SSH config parsing, so root login was effectively permitted despite line 11 stating `no`.

### 1.3 Original UFW Rules

```
Status: active
Default: deny (incoming), allow (outgoing), deny (routed)

To                         Action      From
--                         ------      ----
[1] OpenSSH                ALLOW IN    Anywhere
[2] 80/tcp                 ALLOW IN    Anywhere
[3] 443/tcp                ALLOW IN    Anywhere
[4] 22/tcp                 ALLOW IN    Anywhere        # DUPLICATE of [1]
[5] OpenSSH (v6)           ALLOW IN    Anywhere (v6)
[6] 80/tcp (v6)            ALLOW IN    Anywhere (v6)
[7] 443/tcp (v6)           ALLOW IN    Anywhere (v6)
[8] 22/tcp (v6)            ALLOW IN    Anywhere (v6)   # DUPLICATE of [5]
```

---

## 2. Changes Made

### 2.1 SSH Configuration

| # | Change | File | Mechanism |
|---|---|---|---|
| 1 | Commented out conflicting `PermitRootLogin yes` on line 46 | `/etc/ssh/sshd_config` | `sed -i "46s/^PermitRootLogin yes/#PermitRootLogin yes # OBSOLETED by line 11/"` |
| 2 | Changed `X11Forwarding yes` → `X11Forwarding no` | `/etc/ssh/sshd_config` | `sed -i "s/^X11Forwarding yes/X11Forwarding no/"` |
| 3 | Set `LoginGraceTime 60` (was commented, default 120) | `/etc/ssh/sshd_config` | Uncommented and set via sed |
| 4 | Set `MaxAuthTries 3` (was commented, default 6) | `/etc/ssh/sshd_config` | Uncommented and set via sed |
| 5 | Set `AllowAgentForwarding no` (was commented, default yes) | `/etc/ssh/sshd_config` | Uncommented and set via sed |
| 6 | Set `ClientAliveInterval 300` (was commented, default 0) | `/etc/ssh/sshd_config` | Uncommented and set via sed |
| 7 | Set `ClientAliveCountMax 0` (was commented, default 3) | `/etc/ssh/sshd_config` | Uncommented and set via sed |
| 8 | Validated config with `sshd -t` (exit: 0) | — | Syntax check passed |
| 9 | Reloaded SSH with `systemctl reload ssh` (exit: 0) | — | Active sessions preserved |

### 2.2 UFW (Firewall)

| # | Change | Description |
|---|---|---|
| 1 | Deleted duplicate rule [4] `22/tcp` | Was duplicate of [1] `OpenSSH` (both allow SSH) |
| 2 | Deleted duplicate rule [7] `22/tcp (v6)` | Was duplicate of [4] `OpenSSH (v6)` |
| 3 | Confirmed no other changes needed | UFW was already properly configured |

---

## 3. Current Configuration (After Changes)

### 3.1 SSH Effective Configuration

```
logingracetime 60           # Reduced from 120s
maxauthtries 3              # Reduced from 6
clientaliveinterval 300     # Enabled (was disabled)
clientalivecountmax 0       # Immediate disconnect after timeout
permitrootlogin no          # Fixed (was conflicting yes)
pubkeyauthentication yes    # Unchanged
passwordauthentication no   # Unchanged
x11forwarding no            # Disabled (was yes)
allowagentforwarding no     # Disabled (was yes)
permitemptypasswords no     # Unchanged
```

### 3.2 Final UFW Rules

```
Status: active
Default: deny (incoming), allow (outgoing), deny (routed)

To                         Action      From
--                         ------      ----
[1] OpenSSH                ALLOW IN    Anywhere
[2] 80/tcp                 ALLOW IN    Anywhere
[3] 443/tcp                ALLOW IN    Anywhere
[4] OpenSSH (v6)           ALLOW IN    Anywhere (v6)
[5] 80/tcp (v6)            ALLOW IN    Anywhere (v6)
[6] 443/tcp (v6)           ALLOW IN    Anywhere (v6)
```

### 3.3 Listening Ports

| Port | Service | Public | Required | Source |
|---|---|---|---|---|
| 22/tcp | SSH (sshd) | ✅ | ✅ | Host |
| 80/tcp | HTTP (Nginx/Docker) | ✅ | ✅ | Docker proxy |
| 443/tcp | HTTPS (Nginx/Docker) | ✅ | ✅ | Docker proxy |
| 53/udp | systemd-resolved | ❌ (127.0.0.53) | ✅ | Host |
| 36023/tcp | VS Code Server | ❌ (127.0.0.1) | ✅ | Host |

---

## 4. Security Improvements

| Category | Before | After | Impact |
|---|---|---|---|
| Root SSH access | Effectively permitted (config conflict) | Blocked | Eliminates root brute-force vector |
| X11 Forwarding | Enabled | Disabled | Removes unnecessary network exposure |
| Agent Forwarding | Enabled | Disabled | Prevents credential forwarding attacks |
| Auth attempts | 6 per connection | 3 per connection | Reduces brute-force window |
| Login grace period | 120 seconds | 60 seconds | Reduces slow-attack window |
| Idle timeout | None (infinite) | 5 minutes auto-disconnect | Frees up sessions, reduces exposure |
| Firewall rules | Duplicate entries | Clean, deduplicated | Clearer audit trail |
| Config consistency | Conflicting directives | Single authoritative value | Prevents future misconfiguration |

---

## 5. Verification Results

### 5.1 SSH

| Check | Result |
|---|---|
| `sshd -t` (config validation) | ✅ Passed (exit 0) |
| `systemctl reload ssh` | ✅ Applied without error |
| New SSH connection | ✅ Established successfully |
| `PermitRootLogin` effective | ✅ `no` |
| `PasswordAuthentication` effective | ✅ `no` |
| `X11Forwarding` effective | ✅ `no` |
| `MaxAuthTries` effective | ✅ `3` |

### 5.2 Firewall

| Check | Result |
|---|---|
| UFW active | ✅ Yes |
| SSH accessible | ✅ Port 22 |
| HTTP accessible | ✅ Port 80 |
| HTTPS accessible | ✅ Port 443 |
| Duplicate rules removed | ✅ Clean ruleset |

### 5.3 Docker Applications

| Container | Status | Health |
|---|---|---|
| `app-nginx-1` | Running | ✅ Healthy |
| `app-backend-1` | Running | ✅ Healthy |
| `app-db-1` | Running | ✅ Healthy |
| `app-db-backup-1` | Running | ✅ Healthy |
| `trading-bot` | Running | ✅ Healthy |

### 5.4 Application Endpoints

| Endpoint | Method | Result |
|---|---|---|
| `http://127.0.0.1/` | GET | ✅ 301 (redirects to HTTPS) |
| `https://127.0.0.1/` | GET | ✅ 200 (serves SPA) |
| `https://127.0.0.1/api/health` | GET | ✅ `{"status":"ok","db":"connected"}` |

### 5.5 Network Connectivity

| Destination | Type | Result |
|---|---|---|
| GitHub Container Registry | Outbound HTTPS | ✅ Reachable |
| Telegram API | Outbound DNS/HTTPS | ✅ Reachable |
| Google.com | DNS resolution | ✅ Resolved |
| Docker bridge networking | Internal | ✅ All containers communicating |

### 5.6 Container Restarts

**No container restarts occurred.** SSH reload and UFW changes do not affect containers.

---

## 6. Monitoring Readiness

### 6.1 Preparation for Future Monitoring Stack

The following conditions are already satisfied for a future monitoring deployment:

| Requirement | Status | Notes |
|---|---|---|
| Port 9090 (Prometheus) free | ✅ | Not listening |
| Port 3100 (Loki) free | ✅ | Not listening |
| Port 9100 (Node Exporter) free | ✅ | Not listening |
| Port 3000 (Grafana) free | ✅ | Backend uses 3000 internally, no host port |
| DOCKER-USER chain available | ✅ | Empty, ready for rules |
| Internal Docker networking | ✅ | Bridge networks work correctly |
| UFW default deny policy | ✅ | Already enforcing |
| Outbound DNS/HTTPS | ✅ | Works for monitoring components |

### 6.2 Firewall Design for Monitoring

When deploying monitoring:

1. **Create a new bridge network** (e.g., `172.20.0.0/16`) for monitoring stack
2. **Expose Grafana through Nginx** (add a `/monitoring/` location or subdomain)
3. **No UFW rules needed** for internal monitoring traffic — Docker bridge networking handles it
4. **Use DOCKER-USER chain** if host-level filtering is needed for monitoring traffic
5. **Node Exporter** should run with `network_mode: host` to access host metrics
6. **cAdvisor** needs access to `/var/run/docker.sock` and host cgroups

### 6.3 Port Exposure Strategy

| Port | Service | Public | Via |
|---|---|---|---|
| 3000 | Grafana | ✅ (eventually) | Nginx reverse proxy |
| 9090 | Prometheus | ❌ | Internal only |
| 3100 | Loki | ❌ | Internal only |
| 9100 | Node Exporter | ❌ | Internal only |
| 8080 | cAdvisor | ❌ | Internal only |
| 9187 | PG Exporter | ❌ | Internal only |
| 9115 | Blackbox Exporter | ❌ | Internal only |

---

## 7. SSH Hardening Summary

### Before vs After

| Directive | Before | After |
|---|---|---|
| `PermitRootLogin` | `yes` (conflict) | `no` |
| `PasswordAuthentication` | `no` | `no` ✅ |
| `PubkeyAuthentication` | `yes` | `yes` ✅ |
| `X11Forwarding` | `yes` | `no` |
| `AllowAgentForwarding` | `yes` | `no` |
| `ClientAliveInterval` | `0` (off) | `300` (5 min) |
| `ClientAliveCountMax` | `3` | `0` (immediate) |
| `MaxAuthTries` | `6` | `3` |
| `LoginGraceTime` | `120` | `60` |
| `PermitEmptyPasswords` | `no` | `no` ✅ |
| `UsePAM` | `yes` | `yes` ✅ |

### Active SSH Users

Only `deploy` has shell access. Two Ed25519 keys authorized:
- `contabo-siteledger` (operator)
- `github-actions-siteledger-deploy` (CI/CD)

---

## 8. Rollback Procedure

If rollback is needed:

### SSH

```bash
# Restore from backup
sudo cp /etc/ssh/sshd_config.backup /etc/ssh/sshd_config
sudo sshd -t
sudo systemctl reload ssh
```

### UFW (if issues arise)

```bash
# Disable UFW temporarily
sudo ufw disable
# Re-enable with original rules
sudo ufw enable
```

### Emergency Access

If SSH is locked out, use the VPS provider's console (VNC/IPMI) to access the machine directly:
1. Connect via VPS provider web console
2. Login as `deploy` or `root`
3. Run rollback commands above

---

## 9. Open Ports: Before vs After

| Port | Before | After | Change |
|---|---|---|---|
| 22/tcp (SSH) | ✅ Open | ✅ Open | Unchanged |
| 80/tcp (HTTP) | ✅ Open | ✅ Open | Unchanged |
| 443/tcp (HTTPS) | ✅ Open | ✅ Open | Unchanged |
| 53/udp (DNS local) | ✅ Local | ✅ Local | Unchanged |
| 36023/tcp (VS Code) | ✅ Local | ✅ Local | Unchanged |
| Duplicate SSH rules | ❌ Present | ✅ Removed | Cleaned |

**No ports were opened or closed.** Only duplicate firewall rules were removed.
