# Audit 2026-09-28 — `arch_devops` (Architecture · Code quality · Dependencies · Configuration · DevOps · Backup/DR · Secrets)

Auditor: read-only. No repository file was edited. The only DB activity was on the agent sandbox (:55432): I created and later dropped my own DB `ems_audit_arch_devops`. I did not touch :5432, :55433, the production server or GitHub workflows.
Tree: `Develop` @ `914a6571`, plus today's uncommitted work (98 modified, 27 untracked files; courses/assignments/labs/projects/registrar course_groups).

## 1. Scope & method (what was actually run)

| Check | Command / method | Result |
|---|---|---|
| Module cycle gate | `venv/bin/python scripts/module_deps.py --check` (+ report mode) | PASS: 0 static cycles, 0 core→apps |
| Public-API gate | `scripts/public_api_boundaries.py --check` | PASS: 0 private cross-app imports |
| Context-map gate | `scripts/context_map.py --check` | PASS: 60 files / 85 lines import `apps.registrar.models` directly (baseline, frozen) |
| Module size gate | `scripts/check_module_size.py --check` | PASS; grandfathered list is now **empty** (was 6 files >600) |
| Runtime (hidden) deps | own AST/regex probe over `apps.get_model()/import_module()` (`audit/arch_devops/runtime_deps.py`) | 13 hidden bidirectional app pairs (see AD-08) |
| Lint | `flake8 apps core config scripts --count`, `black --check`, `isort --check-only` | 0 / clean / clean (uncommitted work included) |
| TODO/FIXME/HACK/XXX | grep over apps/core/config/templates/static/docker/deploy scripts (excluding tests/migrations) | 1 hit (`_courses.html:38`, same as the previous audit) |
| Broad except | grep | 505 `except Exception/BaseException/bare` in prod code; 29 are `except Exception: pass` |
| Dependencies | `pip-audit -r <all pinned reqs> --no-deps --disable-pip` + `pip-audit` on the local venv freeze (141 pkgs) | **No known vulnerabilities**, both runs |
| `check --deploy` | `manage.py check --deploy --fail-level WARNING` with `config.settings.production`, `env -i`, dummy secrets, sqlite DSN, prod-default TLS vars | **0 issues, 0 silenced** |
| Settings drift | imported `config.settings.base` and `.production`/`.local` and diffed the UPPERCASE names | 22 real settings missing in prod/local (AD-04) |
| Compose | `docker compose -f docker-compose.prod.yml config --quiet`; YAML inventory of 23 services | valid; details in §3 |
| Infra tests | `pytest tests/test_deploy_preflight.py tests/test_infra_compose_config.py tests/test_infra_monitoring_config.py tests/test_proxy_trust_configuration.py tests/test_w2_deploy_rollback.py` (sandbox) | **94 passed** |
| Workflows | `actionlint` (1.7.12) | 0 errors, 3 shellcheck info/warnings |
| Secrets | `gitleaks detect` (8.30.1, repo config) on the history, and `--no-git` on a copy of tracked + untracked-not-ignored files | history: 7 hits, all on 2 local-only pre-purge branches; working tree: **0** |
| Restore runbook | reproduced the documented plain-dump restore on a toy sandbox DB (AD-02) | runbook is broken |
| Running local stack | `docker ps` (read-only) | agent Postgres published on 0.0.0.0 (AD-03) |

Not verified (remote or owner-only): production server state, GitHub `production` environment reviewers and branch protection, off-site storage, real RTO, and which secrets the prod `.env` holds.

## 2. Status of prior findings (2026-09-13 infra/backend audit + Codex)

| Prior ID | Item | Status | Evidence |
|---|---|---|---|
| infra P2-3 | No `stop_grace_period` | **FIXED** | compose: postgres 60s, app `${APP_STOP_GRACE_PERIOD:-130s}`, celery_worker 300s, heavy 900s |
| infra P2-4 | arp-agent gateway not pinned; no log anchor/limits/healthcheck | **FIXED** | `networks.emsarena-network.ipam` 172.18.0.0/16 gw .1; arp-agent has `logging`, 0.1 CPU/64M, `/mac?ip=` healthcheck |
| infra P2-5 | No rollback / SHA tag / pre-deploy dump | **FIXED** | `remote_deploy.sh:615-770` (`resolve_release_image`, `capture_previous_app_image`, `predeploy_database_backup` fail-closed, `rollback_to_previous_image`, `promote_release_image`); `tests/test_w2_deploy_rollback.py` passes |
| infra P2-9 | Prometheus depends on healthy app | **FIXED** | comment + depends_on only on exporters |
| infra P3-1/3/12/15/16 | nginx `nginx -t` healthcheck; Redis password in argv; Daphne without `--proxy-headers`; `safety || true`; deploy check at ERROR | **FIXED** | `stub_status` healthcheck; `docker/redis/redis.conf.tmpl` + entrypoint; `prod-entrypoint.sh --proxy-headers`; safety step removed; `DEPLOY_CHECK_FAIL_LEVEL` defaults to WARNING |
| infra P1-2 / Codex P1-07 | Running image drifted from source | **FIXED in process** (remote not verified) | CI deploy + `verify_running_build_sha` (`remote_deploy.sh:592`) |
| infra P2-7 | Backups: no off-site, no encryption, no media backup, no PITR, no real-size restore drill | **STILL OPEN**, raised to P1 → AD-01 | deployment.md:1031 «Off-site nüsxə hələ konfiqurasiya olunmayıb» |
| infra C2 | 6 exporters, promtail and cadvisor without healthcheck | **STILL OPEN** (7 services) → AD-13 | YAML inventory |
| infra P3-5/P3-6 | Mutable image tags; nginx 1.27, Promtail EOL, Loki 3.1.1 | **STILL OPEN** (owner-deferred) → AD-13 | compose images unchanged |
| infra C5/C7 | No `read_only`, `cap_drop`, `no-new-privileges` or `secrets:` | **STILL OPEN** → AD-13 | YAML inventory: none on any of 23 services |
| infra P3-7 | `.trivyignore` stale | **Justified / not a finding** | file documents a phantom pip-vendor manifest entry; review date 2026-12-15 |
| backend §1 | 6 grandfathered modules >600 lines | **FIXED** | `module_size_budget.json` budgets = {} |
| backend §1 | 23 modules at 590–600 lines ("cap hugging") | **STILL OPEN** (20 .py + 14 assets ≥590) → AD-17 | size probe |
| backend §1 | Dead `appeals/services/state_machine.py` | **STILL OPEN** → AD-16 | `assert_transition`/`can_transition` only re-exported in `apps/appeals/services/__init__.py:25` |
| backend §3 | 446 broad `except` | **REGRESSED (count)**: 505 now; 29 are silent `pass`, mostly best-effort cache/cleanup | grep |
| Arch score note | "0 cycles" | gate is correct for static imports, but runtime cycles are invisible → AD-08 (NEW) | probe |
| Codex P0-01 | Superuser DB role | Out of scope; commit `6e71c4f2` states prod app role is NOBYPASSRLS (remote not verified) | git log |

## 3. New / current findings

### AD-01 No off-site, encrypted or media backup: losing the single host loses all academic data
Severity: P1   Category: Backup/DR   Status: CONFIRMED (STILL OPEN from infra P2-7; raised to P1 because real data has been live since 2026-09-14: 8 443 users, plus mandatory evidence scans for score corrections)
Location: `docker-compose.prod.yml:239-272` (`postgres-backup` → `./backups/postgres` on the same host); `scripts/ops/db_backup.sh:20` (`/var/backups/emsarena/postgres`, also the same host); `docs/operations/deployment.md:918-926, 1031-1032`
Evidence:
```
# deployment.md:1031
**Off-site nüsxə hələ konfiqurasiya olunmayıb** (audit K-tapıntısı): `./backups/`
qovluğunu S3/B2-yə sync edən cron əlavə olunana qədər host itkisi = backup itkisi.
# media: only a manual `docker run … alpine tar czf` example (deployment.md:651-657); no schedule, no alert
# postgres command: no wal_level/archive_command → RPO = 24 h
```
How verified: read compose, scripts and docs. grep for `rclone|restic|borg|wal-g|pgbackrest|archive_command|off-site` across docs/scripts/docker/.github returns only docs and audit reports. There is no job or script.
Impact: a disk or host failure, ransomware or accidental `down -v` destroys the DB, every local dump and the `media_data` volume at once. That volume holds exam answer files, uploaded documents and correction scans. Media RPO is unbounded; DB RPO is 24 h even while the host survives. The dumps are plain gzip, so they are not encrypted at rest.
Root cause: backups were designed as "local first, off-site later"; the off-site step was never implemented.
Recommended fix: (1) host cron or systemd timer: `rclone sync` (or restic) of `./backups/postgres` and `/var/backups/emsarena` to an off-site bucket or university NAS, encrypted with `rclone crypt` or restic; (2) a nightly media snapshot of `media_data`, for example a restic sidecar with `:ro` mount, to the same target; (3) Prometheus freshness metrics for the off-site copy and the media backup (extend `collect_backup_age`); (4) optional PITR: `wal_level=replica` plus wal-g/pgBackRest sidecar.
Effort: Medium

### AD-02 The documented DB restore/rollback procedure does not restore: it half-loads into the live DB and uses wrong service names
Severity: P1   Category: Backup/DR (runbook correctness)   Status: CONFIRMED (reproduced)
Location: `docs/operations/deployment.md:928-944` («Restore procedure (tested!)») and `:797-807` («Database rollback»)
Evidence:
```
docker compose -f docker-compose.prod.yml stop app celery-worker celery-beat        # :932 — services are celery_worker / celery_beat (+ celery_worker_heavy)
gunzip -c backups/postgres/daily/<dump-file>.sql.gz | \
  docker exec -i emsarena-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"       # restore INTO the existing DB
# sidecar dump options: POSTGRES_EXTRA_OPTS "-Z6 --blobs"  (no --clean / --if-exists)
```
Sandbox reproduction (toy DB on :55432, then dropped): I made a plain dump with the same options, then did a post-backup insert and `ALTER TABLE … ADD COLUMN`, then restored as documented:
```
ERROR: relation "t_pk" already exists / relation "t_nopk" already exists
ERROR: multiple primary keys for table "t_pk" are not allowed
ERROR: duplicate key value violates unique constraint "t_pk_pkey"
t_pk rows|3         ← the post-backup row survives; data NOT rolled back
t_nopk rows|4       ← PK-less table DUPLICATED (2 → 4)
newcol still exists|1  ← schema NOT rolled back
```
How verified: read the runbook, compose and the sidecar options, then ran the restore on the sandbox (commands in the section 1 table).
Impact: in a real incident (a failed migration, or a rollback after `remote_deploy.sh` tells the operator to "restore the pre-deploy dump"), following the runbook leaves the DB mixed. Tables with a PK keep the new data, tables without one get duplicate rows, and the schema stays ahead. The `stop` step fails on the unknown service names, so writers keep running during the restore. `psql` runs without `ON_ERROR_STOP`, so the operator sees a scroll of errors and "success". This turns a recoverable incident into data corruption. Only the fresh-host path in `:1034` (restore into an empty DB) is sound.
Root cause: the runbook assumes `pg_dump --clean`; the service names are from an older compose file; the procedure was never drilled end to end.
Recommended fix: rewrite both sections to restore into a **new** database (`createdb emsarena_restore_<ts>`, `psql -v ON_ERROR_STOP=1`, validate, then swap names with `ALTER DATABASE … RENAME` while writers are stopped), and use the correct service names (`app celery_worker celery_worker_heavy celery_beat`). Alternatively switch the sidecar to `-Fc` and use `pg_restore --clean --if-exists --single-transaction`. Add a scripted `scripts/ops/restore_drill.sh` that runs monthly against a scratch DB and records the timing (RTO).
Effort: Small (docs + script), Medium (scheduled drill)

### AD-03 Agent sandbox Postgres with production-copy databases is published on all interfaces with a repo-committed default password
Severity: P1   Category: Secrets / data exposure (developer host)   Status: CONFIRMED (the exposure is confirmed; database contents were not read)
Location: `docker-compose.agent.yml:15-18` — `POSTGRES_PASSWORD: ${AGENT_POSTGRES_PASSWORD:-<default committed>}`, `ports: "${AGENT_POSTGRES_PORT:-55432}:5432"` (no `127.0.0.1:` prefix); default also in `docs/operations/CLAUDE_POSTGRES_SANDBOX.md`
Evidence:
```
docker ps → emsarena-agent-postgres  0.0.0.0:55432->5432/tcp
pg_database (names/sizes only): ems_restore_a7d1p 3974 MB, ems_restore_final 3367 MB, ems_prodcopy 2802 MB,
  ems_mt_ui / ems_struct_27 / ems_courses_ui / ems_seed_test ≈2.8 GB each … (90 DBs)
socketfilterfw --getglobalstate → "Firewall is disabled. (State = 0)"
```
How verified: `docker ps`, a DB-name/size listing (no table reads), and the macOS firewall state. For comparison, the staging PG (`127.0.0.1:55433`) and the host proxies (`127.0.0.1:5432/6379`) are correctly bound to loopback.
Impact: the DB names suggest full copies of the production data set; contents were not inspected. That would include students' personal data and grades. Any device on the same Wi-Fi/LAN as the laptop can connect with the default credentials published in the repo. This bypasses every production control (RLS, network zone, TLS).
Root cause: the port mapping has no loopback bind, the password default is committed to the repo, and the host firewall is off.
Recommended fix: `ports: "127.0.0.1:${AGENT_POSTGRES_PORT:-55432}:5432"` (and the same for agent redis `56379`); require `AGENT_POSTGRES_PASSWORD` with `:?`; drop prodcopy/restore DBs that are no longer needed; enable the macOS firewall. Also `chmod 600` the 6 world-readable dumps under `backups/` (`find backups -perm -004` gives 6 files; they are gitignored and local).
Effort: Small

### AD-04 22 settings are silently dropped in production/local by the explicit `from .base import (…)` whitelist, so documented owner switches have no effect
Severity: P2   Category: Configuration   Status: CONFIRMED (import test)
Location: `config/settings/production.py:22-180` and `config/settings/local.py:15-151` (explicit name lists); consumers use `getattr(settings, NAME, default)`, for example `apps/ai_assistant/views.py:48`, `core/utils.py:107-128`, `apps/exams/services/final_center/pins.py:37,159-160`, `apps/exams/services/final_center/entry.py:63`
Evidence (env set to `AI_ASSISTANT_ENABLED=false AUTH_OTP_MAX_ATTEMPTS=2 FINAL_EXAM_PIN_MAX_FAILURES=3`):
```
production AI_ASSISTANT_ENABLED attr present: False | effective ai enabled: True | OTP max attempts: 5 | PIN max failures: 5
local      AI_ASSISTANT_ENABLED attr present: False | effective ai enabled: True | OTP max attempts: 5 | PIN max failures: 5
missing in production (defined in base components): AI_ASSISTANT_ENABLED, AI_ASSISTANT_RATE_LIMIT, AI_RATE_LIMIT,
AUTH_OTP_MAX_ATTEMPTS, AUTH_OTP_MAX_SENDS_PER_HOUR, AUTH_OTP_RESEND_COOLDOWN_SECONDS, AUTH_PENDING_SIGNUP_TTL_SECONDS,
FINAL_EXAM_ENTRY_RATE_PER_MINUTE, FINAL_EXAM_PIN_{EXPIRY_GRACE_MINUTES,LENGTH,LOCK_MINUTES,MAX_FAILURES,VISIBILITY_MINUTES},
FINAL_EXAM_REMINDER_DAYS, MONITORING_{PROMETHEUS,LOKI,ALERTMANAGER}_URL, MICROSOFT_CLARITY_{IMG,SCRIPT}_SRC, PUBLIC_SIGNUP_ENABLED …
```
How verified: imported both modules and diffed the UPPERCASE names; ran the env-override probe above.
Impact: `.env.production.example:186-188` documents `AI_ASSISTANT_ENABLED` ("Sahib açarı") and `AI_ASSISTANT_RATE_LIMIT`, and compose passes `AUTH_OTP_*`, `AI_*_RATE_LIMIT` and `MONITORING_*_URL`. None of them take effect. The owner cannot switch off the AI assistant (privacy) or tighten the OTP/PIN brute-force limits in production. `AI_ASSISTANT_ENABLED` is also missing from the compose `x-app-env`. Every new component setting has the same trap.
Root cause: the whitelist was probably introduced to satisfy flake8 F403/F405; nothing checks it for completeness.
Recommended fix: replace the list with `from .base import *  # noqa: F401,F403`, keeping the explicit overrides below, or generate it. Add a test that asserts `set(dir(base)) ⊆ set(dir(production))` for UPPERCASE names. Add `AI_ASSISTANT_ENABLED` to `x-app-env`.
Effort: Small

### AD-05 The deployed image is not the CI-scanned image, and the server build reuses a frozen apt layer, so OS patches never reach production
Severity: P2   Category: DevOps / supply chain   Status: CONFIRMED (read); runtime effect on the server not verified
Location: `scripts/deploy/remote_deploy.sh:801` (`docker compose … build` on the prod host); `docker-compose.prod.yml:39-52` (`x-app-build.args` has no `APT_SECURITY_REFRESH`); `docker/Dockerfile.prod:21,49` (`ARG APT_SECURITY_REFRESH=manual` … `apt-get upgrade`); CI passes `APT_SECURITY_REFRESH=${{ github.run_id }}` (`_container-scan.yml:46`, `_docker-build.yml:46`)
Evidence:
```
CI:     builds emsarena-prod:ci (push: false) → Trivy gate exit-code 1 on fixable HIGH/CRITICAL
Server: docker compose build  → ARG APT_SECURITY_REFRESH=manual (constant) + digest-pinned base
        → `apt-get upgrade` layer is a cache hit on every deploy
```
How verified: read the workflow, the compose file, the Dockerfile and the deploy script.
Impact: the Trivy gate certifies an artifact that is never deployed. The production image is rebuilt on the exam server, using its CPU during a deploy. Its Debian packages stay at whatever version the first server build fetched, and transitive pip packages also float (AD-06). CI green therefore does not imply that production is patched.
Root cause: no registry and no build-once/promote flow.
Recommended fix: short term, pass `APT_SECURITY_REFRESH: ${APT_SECURITY_REFRESH:-manual}` in `x-app-build.args` and export `APT_SECURITY_REFRESH=$(date +%G%V)` (weekly) or `$BUILD_GIT_SHA` in `remote_deploy.sh`. Proper fix: push the CI-built, Trivy-scanned image to GHCR (private) tagged with the SHA, and have `remote_deploy.sh` `docker pull` that exact digest instead of building.
Effort: Small (short term) / Medium (registry)

### AD-06 No lock file: 73 of 141 installed packages, including Celery's runtime stack, are unpinned transitive dependencies
Severity: P2   Category: Dependencies / reproducibility   Status: CONFIRMED
Location: `requirements/base.txt`, `requirements/production.txt` (only `==` for direct deps, no hashes/constraints); `docker/Dockerfile.prod:77-78`
Evidence: local venv (`pip freeze`) compared with every pinned requirement. Unpinned examples: `amqp, billiard, kombu, vine, click*` (Celery runtime), `boto3, botocore, s3transfer, jmespath`, `google-api-core, grpcio, protobuf, pydantic`, `et_xmlfile, httplib2, tqdm`. pip itself warns: "users are encouraged to fully hash their pinned dependencies".
How verified: set difference over the normalised names; `pip-audit` on both lists reported no known vulnerabilities today.
Impact: two builds of the same commit can resolve different Celery/kombu or grpc versions. CI (`requirements/test.txt`, fresh resolve), the server (cached resolve from its first build) and a new host can all differ. A breaking kombu release would arrive silently on a rebuild.
Root cause: hand-maintained requirements with no compile step.
Recommended fix: `pip-compile --generate-hashes` (or `uv pip compile`) into `requirements/*.lock`; install with `--require-hashes` in the Dockerfile and CI; point Dependabot at the `.in` files.
Effort: Medium

### AD-07 The release path skips the coverage gate, Python 3.11 tests and PR review: promotion is a direct push to `main`
Severity: P2   Category: CI/CD gating   Status: CONFIRMED (repo side); branch protection not verified
Location: `.github/workflows/ci.yml:64-66` (`unit-tests-311` runs only on `pull_request || workflow_dispatch`, and it is the only job with `coverage: true` and `--cov-fail-under=68`, `_unit-tests.yml:29-32,195-197`); `ci.yml:74-85` (3.12 shards run with `coverage: false`); `scripts/git/promote_release.sh:67-83` (`merge` + `push HEAD:main`)
Evidence:
```
origin/main: 0fd56b1d Promotion: Staging → main … / 4a057d0f Promotion: Staging → main … / 631defb9 Promotion: Staging → main …
ci-success: unit-tests-311 "skipped" is accepted ( != success && != skipped → fail )
```
How verified: read the workflows and the promotion script; `git log origin/main`.
Impact: every production deploy (push to `main`) runs with no coverage floor and no 3.11 run (the 3.11 lint job stays). No second pair of eyes is required. Coverage can erode unnoticed.
Root cause: sharding removed coverage from the 3.12 path (CI sharding, 2026-09-21), and promotion bypasses PRs.
Recommended fix: combine the shard `.coverage` files (`coverage combine` in a follow-up job) and enforce `--fail-under` on push to `main`; or open the Staging→main promotion as a PR with required checks and branch protection. Keep the rule that deploys need `ci-success`.
Effort: Small–Medium

### AD-08 The module-cycle gate reports 0 cycles, but 13 app pairs are coupled both ways through `apps.get_model()` runtime imports
Severity: P2   Category: Architecture / coupling   Status: CONFIRMED (static probe; production code only, tests and migrations excluded)
Location (examples): `apps/organizations/group_split.py:147`, `apps/organizations/group_students.py:90,140` (organizations→registrar, 19 sites) against registrar→organizations (static plus 71 `get_model` sites); `apps/registrar/services.py:340,364`, `apps/registrar/journal_topics.py:75` (registrar→courses) against courses→registrar (static); `apps/registrar/exam_attempt_history.py:53`, `apps/registrar/schedule.py:338` (registrar→exams); `apps/registrar/plan_hours.py:93`, `schedule_editor.py:141` (registrar→workload); `apps/syllabus/assessment_formula.py:93` (syllabus→registrar); `apps/courses/signals.py:60-61` (courses→assignments/projects); `apps/exams/services/retention.py:37-38` (exams→appeals); `apps/exams/constants.py:130` (exams→live_exam); `apps/notifications/services/events.py:413` (notifications→courses); `apps/registrar/exam_eligibility.py:245` (registrar→legacy_import)
Evidence: `module_deps.py` docstring: "AST adi absolute importları yoxlayır; runtime hook-lar ayrıca dizayn review tələb edir". Probe output: 29 (a→b runtime) edges where b→a also exists.
How verified: probe script `audit/arch_devops/runtime_deps.py`.
Impact: the "0 cycles / microservice-ready e_journal" claim (MICROSERVICE_READINESS, context_map) overstates the isolation. `registrar` and `organizations` are one mutually dependent unit, and extracting e-journal would break at runtime rather than at import time. `get_model` also hides these edges from IDEs and refactors.
Root cause: `apps.get_model` has been used as a cycle-breaker instead of inverting the dependency (signals or public facades).
Recommended fix: extend `module_deps.py` to count `apps.get_model("<app>", …)` and `import_module("apps.<app>…")` edges, with a separate baseline so they can only shrink. Route the organizations→registrar group operations through `apps.registrar.public`, and courses→assignments/projects through a signal or registry owned by the receiving apps.
Effort: Small (gate) / Large (untangling)

### AD-09 `accounts` is a UI god-app that aggregates other contexts' screens
Severity: P3   Category: Architecture / separation of concerns   Status: CONFIRMED
Location: `apps/accounts/` — 67 530 prod LOC (46 983 in views), 330 prod modules, depends on 17 of 25 apps (`module_deps` report); `apps/accounts/views/{exam_score_entry,exam_score_import,journal_close,kollokvium_windows,schedule_editor,schedule_manage,registrar_catalog,…}.py`, `views/profile/_sections/` (54 section modules)
Evidence: `context_map.py`: 16 accounts files import registrar **journal** models directly (for example `apps/accounts/views/exam_score_entry.py:48`, `forms/journal_close.py:11`).
How verified: LOC count per app, module_deps and context_map output.
Impact: identity/tenant code and journal, exam-score and schedule UI change together. Most cross-context coupling flows through accounts, which is also the largest review and merge-conflict surface (parallel agents plus Codex share the tree).
Recommended fix: keep the "kabinet" shell in accounts but move each domain section (views, templates, forms) into its owning app behind a section-registry hook; keep `context_map` ratcheting down.
Effort: Large (incremental)

### AD-10 `USE_X_FORWARDED_HOST/PORT=True`, but nginx never sets or overwrites `X-Forwarded-Host`
Severity: P3   Category: Configuration / proxy trust   Status: CONFIRMED (read); exploit impact is limited by ALLOWED_HOSTS
Location: `config/settings/production.py:351-352`; `docker/nginx/nginx.conf:163-170, 289-294` (sets Host, X-Real-IP, XFF, X-Forwarded-Proto, X-EMS-Zone; **no** `X-Forwarded-Host`/`X-Forwarded-Port`)
Evidence: grep for `Forwarded-Host` in `docker/`: only `prometheus.yml:41`, which sends it deliberately.
How verified: read both files; `tests/test_proxy_trust_configuration.py` covers XFF/Proto only.
Impact: a client-supplied `X-Forwarded-Host` passes through nginx and becomes `request.get_host()`, restricted to any ALLOWED_HOSTS value (`.env.production.example:14` contains `localhost,127.0.0.1`). It sidesteps nginx's `$ems_reject_host` 444 policy at the Django layer. `build_absolute_uri` output (emails, QR codes, redirects) can be steered to `localhost`, which gives broken links rather than a hijack.
Recommended fix: in every proxied location add `proxy_set_header X-Forwarded-Host $host;` and `proxy_set_header X-Forwarded-Port $server_port;`, or set `USE_X_FORWARDED_HOST=False`, since nginx already passes `Host $host`. Extend `test_proxy_trust_configuration.py`.
Effort: Small

### AD-11 Purged secrets still live in local refs; GitHub `refs/pull/*` purge is pending
Severity: P3   Category: Secrets   Status: CONFIRMED (local); remote not verified
Location: local branches `claude/exciting-blackburn-03c35c` and `claude/modest-kare-9694a1` (worktrees in `.claude/worktrees/`) plus the pre-rewrite mirror `~/Developer/EMSArena-history-backup-2026-09-27.git` (mode 0700). Gitleaks hits: `.env` (commit `b09cb19d`), `.claude/launch.json` (`864e47e4`), `scripts/qa_live/query_profile.py`, `docs/ROL_MATRISI.md`, `docs/audits/2026-09-02/REHEARSAL_FRESH_2026_09_03.md` (rule `ems-postgres-dsn-password`)
Evidence: `git for-each-ref --contains b09cb19d` → only these 2 local heads; no `origin/*` ref contains it. The working tree scan found 0. Hash comparison (values not printed): the local `.env` `SECRET_KEY`, `POSTGRES_PASSWORD`, `DATABASE_URL`, `REDIS_URL` and `PGADMIN_PASSWORD` all **differ** from the purged-history values.
Impact: an accidental `git push --all` from this checkout, or pushing either worktree branch, re-publishes the purged history. Whether production secrets were rotated after the purge cannot be verified from here.
Recommended fix: delete the two stale worktrees/branches (`git worktree remove`, `git branch -D`) after confirming nothing is needed from them; keep the mirror offline or encrypted; follow up the GitHub Support ticket (`backups/github_support_request_2026-09-27.md`); record the prod rotation date in `docs/security/SECURITY_SECRET_ROTATION.md`, whose status still reads 2026-05-24 "TƏCİLİ".
Effort: Small

### AD-12 Deploy mechanics: rsync happens before preflight, configs are not rolled back, drift failure does not roll back, and the recreate is not rolling
Severity: P3   Category: DevOps / deploy safety   Status: CONFIRMED (read)
Location: `.github/workflows/ci.yml:297-299` (`rsync -a --delete … "$APP_DIR/"` then `remote_deploy.sh`); `scripts/deploy/remote_deploy.sh:608-611` (`verify_running_build_sha` → `exit 1`, no rollback); `:809-811` (`up -d --scale app=8` recreates all replicas together); `rollback_to_previous_image` only swaps `APP_IMAGE`
Impact: if a preflight fails (env, DNS, TLS, check --deploy), the live directory already holds the new `docker/nginx/nginx.conf`, `prometheus/alerts.yml` and compose file. The next container restart or host reboot runs new configs against the old image. After a rollback, bind-mounted configs stay at the failed release. An image-drift failure leaves the unverified release serving traffic. The simultaneous recreate means a short 502 window on every deploy.
Recommended fix: rsync into `releases/<sha>/` and switch a `current` symlink only after a successful deploy; call `rollback_to_previous_image` on a drift mismatch; recreate app replicas in two halves (or `--no-deps` per replica) behind nginx.
Effort: Medium

### AD-13 Container hardening, image pinning and health coverage are unchanged since the last audit
Severity: P3   Category: DevOps   Status: STILL OPEN (prior C2/C5/C7/P3-5/P3-6)
Location: `docker-compose.prod.yml` (23 services)
Evidence: YAML inventory: no service has `read_only`, `cap_drop`, `security_opt: no-new-privileges` or `secrets:`. `privileged: true` on cadvisor and piston (profile). No healthcheck on node_exporter, cadvisor, redis/nginx/pgbouncer/blackbox exporters or promtail. Only `Dockerfile.prod` is digest-pinned; `postgres:16-alpine`, `redis:7-alpine`, `nginx:1.27-alpine` (1.27 mainline, superseded) and `python:3.12-alpine` (arp-agent) are mutable tags. `grafana/promtail:3.1.1` is EOL (Alloy replaces it) per vendor notice (not verified today). `.github/dependabot.yml` has no `docker` ecosystem.
Recommended fix: add `security_opt: [no-new-privileges:true]` and `cap_drop: [ALL]` (plus minimal `cap_add`) to app, celery, exporters and nginx; `read_only: true` with tmpfs for exporters; digest-pin the base images and add a Dependabot `docker` entry; add trivial healthchecks for the exporters; plan nginx 1.28 and the Promtail→Alloy change.
Effort: Medium

### AD-14 CI supply chain: actions pinned by tag, unverified binary download, shell-interpolated inputs on the prod runner
Severity: P3   Category: CI/CD security   Status: CONFIRMED (read)
Location: all workflows use `@vN` tags (e.g. `aquasecurity/trivy-action@v0.35.0`, `orgoro/coverage@v3.2`, `docker/build-push-action@v6`), and `actions/checkout` mixes `@v4` (6×) and `@v6` (12×); `_secret-scan.yml` downloads gitleaks 8.24.3 via `curl | tar` with no checksum; `seed-database.yml:48,64` interpolate `${{ github.event.inputs.asset_id / expected_users }}` directly in `run:` on the self-hosted prod runner
Impact: a tag-hijacked third-party action runs with the job's token. trivy-action tags were reportedly force-pushed in a 2026 incident (from memory; not checked). Input injection needs write access, so the risk is low.
Recommended fix: pin third-party actions by commit SHA (Dependabot keeps them updated); verify the gitleaks tarball `sha256`; pass inputs through `env:` as `prod-exam-ops.yml` already does.
Effort: Small

### AD-15 Dependency currency and licensing notes
Severity: P3   Category: Dependencies   Status: PLAUSIBLE (knowledge-based, Not verified online beyond pip-audit)
Evidence / location: `requirements/base.txt`: `google-generativeai==0.8.6` (Google has deprecated this SDK in favour of `google-genai`; used by `apps/exams/services/ai_summary.py`, `ai_question_generation.py`). `PyMuPDF==1.24.14` (Nov 2024; AGPL-3.0 or commercial licence, so network-use obligations need owner/legal review). `whitenoise==6.5.0` and `tzdata==2025.2` are old. Dependabot branches waiting on origin: `cryptography-50.0.1`, `pypdf-6.16.2`, `requests-2.34.2`, `pytest-django-4.14.0`, `pytest-asyncio-1.4.0`. CI `pip-audit` audits `requirements/base.txt` only, not `production.txt` (sentry-sdk, psycopg2).
Result today: `pip-audit` found **no known vulnerabilities** in the pinned set or in the 141-package venv.
Recommended fix: migrate to `google-genai`; merge the pending Dependabot bumps after CI passes; run `pip-audit -r requirements/production.txt` in `_security.yml`; get the owner's decision on the PyMuPDF licence.
Effort: Small–Medium

### AD-16 Dead code and repository clutter
Severity: P3   Category: Code quality   Status: CONFIRMED
Location: `apps/appeals/services/state_machine.py` (only re-exported, no consumer; prior finding still open); `docker/Dockerfile` and `docker/entrypoint.sh` (referenced nowhere in compose, workflows or docs); `remote_deploy.sh:260 legacy_deploy` (DEPLOY_MODE=legacy, unused path); empty tracked `text.md`; 114 dated one-off `scripts/i18n_*.py`; `scripts/prod_ops/exam_day_probe{,2,3}.py`. Today's deletions (edit_course.*, course_panel_tabs.js, lab_section.js, …) left **no dangling references** (grep checked).
Recommended fix: delete or archive (`scripts/archive/i18n/`); either wire the appeals state machine into `recompute_appeal_status` or remove it.
Effort: Small

### AD-17 Many modules sit just under the 600-line cap
Severity: P3   Category: Maintainability   Status: STILL OPEN (improved: 0 grandfathered)
Evidence: 20 `.py` and 14 asset files have 590–600 lines; 8 are exactly 600 (`apps/registrar/views.py`, `apps/organizations/models.py`, `apps/accounts/academic_records.py`, `apps/exams/views/student/coding.py`, `legacy_import/services/{rehearsal,field}_contracts.py`, `exams/templates/exams/student/exam_result.html`, `exams/static/exams/css/create_question_bank.css`). Recent commits split files purely to satisfy the limit (e.g. `5e0c1002` "jd2.css 600 sətir limiti").
Recommended fix: add a "warn at 550" report to `check_module_size.py` and split along responsibilities, not at the line count.
Effort: Medium

### AD-18 Settings-loading order and legacy settings
Severity: P3   Category: Configuration   Status: CONFIRMED (read)
Location: `config/settings/base.py` `exec`-includes components that read `os.getenv` at import, before `production.py:237` / `local.py:202` call `load_dotenv`. `production.py` still sets `SECURE_BROWSER_XSS_FILTER` (a no-op since Django 4) and `STATICFILES_STORAGE` (ignored since Django 5.1; `STORAGES` is authoritative). The monitoring collector opens a Redis connection at app start-up (observed during `check --deploy`: "Monitorinq kollektoru qeydə alınmadı: … Connection refused").
Impact: a host-side `manage.py` run that relies on `.env` (rather than process env) gets base defaults for component settings, for example `REDIS_URL` → 127.0.0.1. There is no effect inside containers, where compose injects the env.
Recommended fix: call `load_dotenv` at the top of `base.py`; remove the dead settings; make the collector registration lazy.
Effort: Small

### AD-19 No staging environment
Severity: P3   Category: DevOps   Status: CONFIRMED
Evidence: the `Staging` branch only triggers CI; there is no staging deploy job. `docker-compose.staging.yml` is a local inspection Postgres only. The `_prod-smoke`/`_e2e-smoke` compose stacks in CI are the only pre-production runtime gate.
Recommended fix: a lightweight staging on the server (separate compose project, anonymised or seed data) that `Staging` deploys to automatically, and gate `main` promotion on it.
Effort: Medium

## 4. Scores (0–100)

| Area | Score | One-line justification |
|---|---|---|
| Architecture | **77** | Clean modular monolith with 4 green ratchet gates, public facades and 0 private imports; but 13 hidden runtime bidirectional app pairs (organizations↔registrar), and `accounts` is a 67k-LOC hub depending on 17 apps |
| Code Quality | **80** | flake8/black/isort clean including today's work, 1 TODO, 0 grandfathered god-files, no dangling refs after today's deletions; 505 broad excepts (29 silent), dead appeals state machine, 114 one-off scripts |
| Maintainability | **74** | Size cap enforced but 34 files hug 600; settings whitelist silently drops 22 settings; `accounts` aggregation and runtime cycles raise the change cost |
| DevOps | **72** (prior 66) | Big gains: SHA-tagged images, auto-rollback, fail-closed pre-deploy dump, grace periods, IPAM pin, worker healthchecks, 94 infra tests green; still builds on the prod host (≠ scanned image, frozen apt layer), unpinned transitive deps, no coverage gate or PR on the release path, no staging, no container hardening, sandbox DB exposed on the LAN |
| Backup / Recovery | **45** | Daily sidecar (7/4/3), second systemd dump, freshness alert, pre-deploy dump, one real-size `pg_restore` done (2026-09-14 seed); but no off-site, no encryption, no media backup, no PITR, no recorded RTO, and the documented restore/rollback runbook corrupts data (reproduced) |
| Configuration | **74** | `check --deploy` 0 issues and 0 silenced; fail-closed SECRET_KEY/ALLOWED_HOSTS/TLS/2FA; JSON logs with masking; but 22 base settings dropped in prod (owner kill switches ignored), X-Forwarded-Host trusted without an nginx overwrite, dotenv loaded after components |

## 5. Prioritised remediation (arch_devops)

| # | Priority | Action | Dependency | Risk of change | Effort | Benefit |
|---|---|---|---|---|---|---|
| 1 | P1 | Fix the restore/rollback runbook (restore into a new DB, `ON_ERROR_STOP`, correct service names) and add `scripts/ops/restore_drill.sh`; run one real-size drill and record the RTO (AD-02) | none | Docs only | S | Makes recovery actually possible |
| 2 | P1 | Off-site encrypted copy of DB dumps plus scheduled media backup, each with a freshness alert (AD-01) | Owner: bucket/NAS + credentials | Low (read-only mounts) | M | Host loss no longer means total data loss |
| 3 | P1 | Bind the agent PG/Redis to 127.0.0.1, require the password, drop unneeded prodcopy DBs, enable the macOS firewall, chmod 600 local dumps (AD-03) | none | Low | S | Closes LAN PII exposure |
| 4 | P2 | `from .base import *` in production/local plus a parity test; add `AI_ASSISTANT_ENABLED` to `x-app-env` (AD-04) | none | Low; run the settings tests | S | Owner switches and OTP/PIN limits work |
| 5 | P2 | Pass `APT_SECURITY_REFRESH` in the server build now; later, a GHCR build-once/pull-by-digest flow (AD-05) | GHCR token for the private repo | Medium for the registry step | S/M | Production gets patched, and the scanned image is the deployed one |
| 6 | P2 | Hash-locked requirements (`pip-compile --generate-hashes`) with `--require-hashes` (AD-06) | #5 recommended | Medium (resolver drift once) | M | Reproducible builds |
| 7 | P2 | Coverage combine and fail-under on push to `main`, or a PR-based promotion with branch protection (AD-07) | none | Low | S | Restores the quality gate on releases |
| 8 | P2 | Extend `module_deps.py` to count `get_model`/`import_module` edges with a shrink-only baseline; start with organizations↔registrar (AD-08) | none | Low (gate), High (refactor) | S/L | Real isolation for e-journal extraction |
| 9 | P3 | nginx `X-Forwarded-Host/Port` overwrite (AD-10); SHA-pin actions, checksum gitleaks, env-pass inputs (AD-14) | none | Low | S | Proxy trust and supply chain |
| 10 | P3 | Release-dir symlink deploy, rollback on drift, two-phase replica recreate (AD-12) | none | Medium | M | Safer, zero-downtime deploys |
| 11 | P3 | Hardening (`no-new-privileges`, `cap_drop`, `read_only`), digest pins plus Dependabot `docker`, exporter healthchecks, nginx 1.28 / Alloy (AD-13) | Stack test window outside exam days | Medium | M | Smaller blast radius, patched images |
| 12 | P3 | Remove stale pre-purge branches/worktrees, follow up the GitHub Support purge, document prod secret rotation (AD-11) | GitHub Support | Low | S | Stops the purged history from reappearing |
| 13 | P3 | Migrate to `google-genai`, merge pending Dependabot bumps, `pip-audit` on production.txt, owner decision on the PyMuPDF licence (AD-15) | none | Low–Medium | S/M | Supported SDKs, licence clarity |
| 14 | P3 | Clean-up: dead files, i18n script archive, appeals state machine, 550-line early warning, `load_dotenv` order, deprecated settings (AD-16/17/18) | none | Low | S | Lower maintenance noise |
| 15 | P3 | Staging environment gating `main` (AD-19); gradual extraction of domain sections from `accounts` (AD-09) | Server capacity | Medium | M/L | Pre-prod verification, clearer boundaries |

Counts: P0 0 · P1 3 · P2 5 · P3 11. Artefacts: `audit/arch_devops/` (module_deps/public_api/context_map/module_size outputs, `runtime_deps.py`, `pip_audit_*.txt`, `check_deploy.txt`, `gitleaks_*.json` (redacted), `venv_freeze.txt`).
