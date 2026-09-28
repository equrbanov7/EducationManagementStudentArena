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
| `restore_drill.sh` | Restore a dump into a **new scratch DB** (`ON_ERROR_STOP`, single transaction), sanity counts, prints the restore time (RTO), drops the scratch DB (`--keep` for the real restore swap). Audit 2026-09-28 AD-02. |
| `offsite_backup.sh` | Nightly **off-site, encrypted** copy (restic) of both dump dirs + the `media_data` volume (read-only), retention, Prometheus textfile metric. Audit 2026-09-28 AD-01. |
| `systemd/emsarena-offsite-backup.{service,timer}` | Run `offsite_backup.sh` every night at 03:30. Config: `/etc/emsarena/offsite-backup.env` (template `offsite-backup.env.example`). |

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
Never pipe a dump into the live `$POSTGRES_DB` — the dumps have no `--clean`,
so that half-loads (duplicates, schema not rolled back; audit 2026-09-28 AD-02).
Restore into a NEW database, check it, then swap names while the writers are
stopped — full procedure: `docs/operations/deployment.md` §12 «Restore procedure».
```bash
# drill / first step of a real restore (the live DB is never touched)
scripts/ops/restore_drill.sh /var/backups/emsarena/postgres/emsarena_db-latest.sql.gz
scripts/ops/restore_drill.sh --keep --db emsarena_restore_$(date +%Y%m%d_%H%M) <dump>
```

## Install the off-site backup (restic, encrypted)
See `docs/operations/deployment.md` §12 «Off-site copy» (password file,
`/etc/emsarena/offsite-backup.env`, `init`, timer). Until it is configured the
`OffsiteBackupStale` alert fires.

## Harden a fresh host
```bash
sudo scripts/ops/server_hardening.sh
# then, from a NEW terminal, confirm SSH still works before closing.
```

## Notes / follow-ups
- **Off-site backups:** `offsite_backup.sh` (restic) is the off-host copy of the
  dumps and media; it needs an owner-provided target (bucket/NAS) — see above.
- **Alert email (Brevo):** delivery works but Brevo sometimes returns
  `525 Unauthorized IP address` on the first attempt (succeeds on retry). Add
  the host's public egress IP to Brevo → Senders & IP → Authorized IPs.
- **SSH key-only:** password auth is still on (protected by fail2ban, LAN-only).
  Add your public key to `~/.ssh/authorized_keys`, verify key login, then set
  `PasswordAuthentication no` in the hardening drop-in and reload sshd.
