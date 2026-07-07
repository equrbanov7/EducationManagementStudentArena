# EMSArena — server ops scripts

Reusable, self-documenting scripts for the production host (`wcuserver`), so the
setup is reproducible and we don't have to re-derive it. All are idempotent.

## Files
| Script | Purpose |
|---|---|
| `db_backup.sh` | Timestamped `pg_dump` → `/var/backups/emsarena/postgres` (outside the app dir, deploy-proof), gzip + integrity check + age retention. |
| `systemd/emsarena-db-backup.{service,timer}` | Run `db_backup.sh` **every night at 02:00** (with catch-up). |
| `server_hardening.sh` | fail2ban + ufw (22/80/443) + docker log-rotation + SSH hardening (root off, X11 off). |
| `test_alert.sh` | Fire a test alert through Alertmanager to verify email delivery. |

## Install the nightly backup (systemd timer)
```bash
sudo install -m 0755 scripts/ops/db_backup.sh /usr/local/sbin/emsarena-db-backup.sh
sudo cp scripts/ops/systemd/emsarena-db-backup.service /etc/systemd/system/
sudo cp scripts/ops/systemd/emsarena-db-backup.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now emsarena-db-backup.timer
sudo systemctl start emsarena-db-backup.service   # run one now
systemctl list-timers emsarena-db-backup.timer    # verify next run
```
Backups: `/var/backups/emsarena/postgres/emsarena_db-YYYYmmdd-HHMMSS.sql.gz`
(+ `emsarena_db-latest.sql.gz` symlink). Log: `/var/log/emsarena-backup.log`.

## Restore a backup
```bash
LATEST=/var/backups/emsarena/postgres/emsarena_db-latest.sql.gz
gunzip -c "$LATEST" | docker exec -i emsarena-postgres \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

## Harden a fresh host
```bash
sudo scripts/ops/server_hardening.sh
# then, from a NEW terminal, confirm SSH still works before closing.
```

## Notes / follow-ups
- **Off-site backups:** these all live on the same host. If the host is lost,
  the backups go with it. Add an off-site copy (S3 or another server) when a
  target is available — extend `db_backup.sh` with an upload step.
- **Alert email (Brevo):** delivery works but Brevo sometimes returns
  `525 Unauthorized IP address` on the first attempt (succeeds on retry). Add
  the host's public egress IP to Brevo → Senders & IP → Authorized IPs.
- **SSH key-only:** password auth is still on (protected by fail2ban, LAN-only).
  Add your public key to `~/.ssh/authorized_keys`, verify key login, then set
  `PasswordAuthentication no` in the hardening drop-in and reload sshd.
