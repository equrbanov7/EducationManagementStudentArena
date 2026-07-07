#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMSArena — server hardening (idempotent, re-runnable)
#
# Reproduces the baseline hardening applied to the production host so a new
# server (or a rebuild) can be brought to the same state with one command:
#   sudo scripts/ops/server_hardening.sh
#
# Applies: fail2ban (SSH), ufw (22/80/443), docker log-rotation default,
# SSH hardening drop-in (root login off, X11 off). Password SSH auth is left
# ENABLED on purpose — flip it off only after key-based access is verified
# (see README), otherwise you can lock yourself out.
#
# LAN_CIDR is whitelisted in fail2ban so ops hosts are never auto-banned.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo/root." >&2; exit 1; }

LAN_CIDR="${LAN_CIDR:-10.0.0.0/19}"

echo "==> fail2ban"
DEBIAN_FRONTEND=noninteractive apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq fail2ban
cat > /etc/fail2ban/jail.local <<EOF
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1 ${LAN_CIDR}
bantime = 1h
findtime = 10m
maxretry = 5
backend = systemd

[sshd]
enabled = true
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "==> ufw (allow 22/80/443 BEFORE enable)"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw default deny incoming
ufw default allow outgoing
yes | ufw enable

echo "==> docker log rotation default"
mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
EOF
  echo "   wrote /etc/docker/daemon.json (takes effect on next docker restart)"
else
  echo "   /etc/docker/daemon.json already exists — left untouched"
fi

echo "==> SSH hardening drop-in (root off, X11 off; password auth kept)"
cat > /etc/ssh/sshd_config.d/99-emsarena-hardening.conf <<'EOF'
# EMSArena hardening. Password auth intentionally kept ON until key-only
# access is verified (see scripts/ops/README.md). Then set:
#   PasswordAuthentication no
PermitRootLogin no
X11Forwarding no
EOF
if sshd -t; then
  systemctl reload ssh
  echo "   sshd config valid — reloaded"
else
  echo "   sshd config INVALID — NOT reloaded; fix before continuing" >&2
  exit 1
fi

echo "==> done. Verify from a NEW session that SSH still works before closing this one."
