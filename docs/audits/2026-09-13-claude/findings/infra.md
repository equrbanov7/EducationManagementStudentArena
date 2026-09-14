# İNFRASTRUKTUR · DEPLOY · CELERY · REDIS · ASGI/WS · MONİTORİNQ · BACKUP/DR · CI/CD — audit `infra`

Tarix: 2026-09-13 · Develop HEAD `7c5dc612` (audit_common `96016cff`-dən sonra 1 i18n commit) · Auditor: READ-ONLY, tracked fayl dəyişdirilməyib, real DB-yə qoşulma yoxdur, işləyən konteynerlər yalnız `docker ps/inspect/logs/exec <read-only>` ilə oxunub (restart/stop yoxdur).

Artefaktlar (bu qovluq): `notes_progress.md` (ara qeydlər), `running_pip_freeze.txt` (işləyən image `pip freeze`), `source_requirements.txt`, `test_ws_consumer_rls_nonsuper.py` (WS-RLS reproduksiya, sandbox `ems_audit_infra`), `test_alertmanager_webhook_direct_post.py` (webhook reproduksiya).

Baza: Codex 2026-09-12 hesabatı (`docs/audits/2026-09-12-codex/FINAL_REPORT_AZ.md`) — P0-01 (superuser DB rolu), P1-07 (image drift), P1-08 (TLS bayraqları), P2-08 (Redis maxmemory), Celery healthcheck-siz. HEAD-də artıq merge olunmuş düzəlişlər (yoxlandı, təkrar bildirilmir): Celery worker/heavy/beat healthcheck-ləri (`docker-compose.prod.yml:497-573`), `remote_deploy.sh` `worker_services_ready`/`preflight_django_deploy_check`/`verify_running_build_sha` (L385-482), `core/health_build_info.py` + `docker/build-info.sh`, Alertmanager Bearer `http_config.authorization` (`alertmanager.tmpl.yml`), `setuptools>=78.1.1` (`requirements/base.txt`, Dockerfile `pip install --upgrade pip setuptools wheel`), `tests/test_infra_compose_config.py` (10 test — sandbox-da PASS).

---

## 0. Metod və hüdudlar

- Mənbə: `docker-compose.prod.yml` (1024 sətir), `docker/Dockerfile.prod`, `docker/prod-entrypoint.sh`, `docker/release.sh`, `docker/build-info.sh`, `docker/nginx/nginx.conf`, `docker/prometheus/{prometheus,alerts}.yml`, `docker/alertmanager/alertmanager.tmpl.yml`, `docker/blackbox/blackbox.yml`, `docker/loki/loki-config.yml`, `docker/promtail/promtail-config.yml`, `docker/arp-agent/arp_agent.py`, `docker/postgres-init/10-create-app-role.sh`, `scripts/deploy/*.sh`, `.github/workflows/*.yml`, `config/{asgi,celery}.py`, `config/settings/{production.py,components/celery_cache.py}`, `apps/exams/tasks.py`, `apps/monitoring/{tasks,collectors,views}.py`, `apps/exams/consumers.py`, `apps/live_exam/consumers.py`, `core/{views,logging_filters,rls_pooling}.py`, `docs/operations/*.md`.
- İşləyən mühit: lokal macOS Docker Desktop-dakı «production-like» yığın (Codex-in də baxdığı). Uzaq `wcuserver` (10.0.2.42, self-hosted runner) əlçatan deyil → uzaq server barədə heç bir iddia yoxdur.
- Sandbox testləri: `postgres://emsarena_agent@127.0.0.1:55432/ems_audit_infra` (`--ds=config.settings.test`, `USE_REDIS=False`).
- Real backup faylları yalnız `ls -la` (ad/ölçü) ilə oxunub; restore məşqi data auditoru tərəfindən sintetik dump ilə edilib (`audit/data/FINDINGS.md §7`) — təkrar edilməyib.

---

## 1. Compose / Docker — PARTIAL

### 1.1 Servis cədvəli (`docker-compose.prod.yml`, mənbə HEAD)

| Servis | Image (pin) | restart | Healthcheck | Limits (cpu / mem) | User | Read-only mount-lar | Qeyd |
|---|---|---|---|---|---|---|---|
| postgres | `postgres:16-alpine` (teq) | unless-stopped | `pg_isready` 10s | — / 16384M | root (image defolt) | initdb `:ro` | `max_connections=250`, `shared_buffers=2GB`; WAL arxivi yoxdur |
| postgres-backup | `prodrigestivill/postgres-backup-local:16-alpine` (teq) | unless-stopped | `:8080` 5m | 0.5 / 256M | root | `./backups/postgres` **rw** | `@daily`, 7g/4h/3a |
| pgbouncer | `edoburu/pgbouncer:v1.25.1-p0` (teq) | unless-stopped | `pg_isready` ×2 10s | 1.0 / 512M | image defolt | — | `POOL_MODE=session`, pool 150+50, `DISCARD ALL` |
| redis | `redis:7-alpine` (teq) | unless-stopped | `redis-cli ping` 10s | 2.0 / 4096M | image defolt | — | `maxmemory 3gb noeviction`, AOF, `io-threads 4`, **parol argv-də** |
| arp-agent | `python:3.12-alpine` (teq) | unless-stopped | **YOX** | **YOX** | root | `./docker/arp-agent:ro` | `network_mode: host`, `172.18.0.1` sabit, **logging anchor YOX** |
| app | `emsarena-prod:latest` (build) | unless-stopped | HTTP `/ping/` 30s | — / 2048M | `appuser` (Dockerfile) | — | Daphne tək proses, `ASGI_THREADS=12`, `stop_grace_period` **yox** |
| celery_worker | eyni image | unless-stopped | `inspect ping -d celery@$HOSTNAME` 60s | 1.0 / 1024M | appuser | `./backups/postgres:ro` | `-Q celery -c 4` |
| celery_worker_heavy | eyni image | unless-stopped | eyni | — / 2048M | appuser | — | `-Q heavy -c 2` |
| celery_beat | eyni image | unless-stopped | schedule faylı `-mmin -10` | 0.25 / 256M | appuser | — | `/tmp/celerybeat-schedule` |
| postgres_exporter | `v0.17.1` | unless-stopped | `/metrics` 30s | 0.2 / 128M | image | — | `sslmode=disable` |
| node_exporter | `v1.9.1` | unless-stopped | **YOX** | 0.2 / 64M | image | `/:/host:ro` | `pid: host` |
| alertmanager | `v0.28.1` | unless-stopped | `/-/healthy` | 0.2 / 128M | image | tmpl `:ro` | `sed` ilə render; UI 127.0.0.1 |
| prometheus | `v3.8.0` | unless-stopped | `/-/healthy` | 0.5 / 512M | image | dir mount `:ro` | **`depends_on: app healthy`** |
| grafana | `12.3.0` | unless-stopped | `/api/health` | 0.5 / 256M | image | provisioning `:ro` | parol məcburi |
| cadvisor | `v0.60.5` | unless-stopped | **YOX** | 0.4 / 256M | **privileged** | `:ro` ×5 | |
| redis_exporter | `v1.66.0` | unless-stopped | **YOX** | 0.2 / 64M | image | — | |
| nginx_exporter | `1.3.0` | unless-stopped | **YOX** | 0.1 / 32M | image | — | |
| pgbouncer_exporter | `v0.10.2` | unless-stopped | **YOX** | 0.1 / 64M | image | — | |
| blackbox_exporter | `v0.25.0` | unless-stopped | **YOX** | 0.1 / 64M | image | cfg `:ro` | Host `10.0.2.42` git-də hard-code |
| loki | `3.1.1` | unless-stopped | `/ready` | 0.5 / 512M | image | cfg `:ro` | retention 336h |
| promtail | `3.1.1` | unless-stopped | **YOX** | 0.3 / 128M | image | docker.sock `:ro` | Promtail EOL (2026-03) |
| piston (profile) | `:latest` fallback | unless-stopped | node probe | 2.0 / 4096M | **privileged** | tmpfs | yalnız `--profile coding` |
| nginx | `nginx:1.27-alpine` (teq) | unless-stopped | **`nginx -t`** (konfiq sintaksisi, trafik yox) | 4.0 / 512M | image | conf/certs/static/media `:ro` | 80/443 |

Xülasə: 21 servis / 16 healthcheck; `read_only: true`, `cap_drop`, `security_opt: no-new-privileges`, `stop_grace_period`, `secrets:` — heç birində yoxdur. Yalnız `docker/Dockerfile.prod` base image digest ilə pin-lənib; qalan 18 image mutable teqdir (`postgres:16-alpine`, `redis:7-alpine`, `nginx:1.27-alpine`, `python:3.12-alpine` xüsusilə).

Yaddaş limitləri cəmi (defoltlar, `APP_REPLICAS=8`, `CELERY_REPLICAS=2`): postgres 16G + app 8×2G + redis 4G + heavy 2G + worker 2×1G + qalan ≈ 3.7G ≈ **44 GB**. Host ölçüsü heç bir sənəddə yoxdur (`deployment.md §2` yalnız Docker/Git versiyası). Limits > host RAM olduqda cgroups yox, host OOM-killer işə düşür (Redis `noeviction` 3g + Postgres 16G eyni anda).

### 1.2 Yoxlanılan maddələr

| # | Maddə | Nəticə | Sübut |
|---|---|---|---|
| C1 | Restart siyasəti | PASS | bütün servislər `unless-stopped` |
| C2 | Healthcheck hər servisdə | PARTIAL | 6 exporter + arp-agent + promtail yoxdur; nginx `nginx -t` real trafiki yoxlamır (`docker-compose.prod.yml:1010`) |
| C3 | app healthcheck dərinliyi | PARTIAL | test `/ping/` (DB yoxlanmır), şərh isə «/health/ DB-ni yoxlayır» deyir (`:395-405`); `c13716fd`-də qəsdən dəyişilib — şərh köhnə |
| C4 | Asılılıq sırası | PARTIAL | `prometheus.depends_on.app: service_healthy` (`:672`) → app qalxmayanda monitorinq də qalxmır (monitorinq izlədiyindən asılı olmamalıdır) |
| C5 | Non-root | PASS (app) / PARTIAL | app/celery `appuser` (`Dockerfile.prod:64-66,101`; işləyən konteynerdə `uid=999(appuser)` təsdiqləndi). cadvisor/piston `privileged`; nginx/postgres/redis image defoltu |
| C6 | Read-only mount-lar | PASS | konfiq/cert/static/media `:ro`; media yalnız app/celery-də rw |
| C7 | Sirlər | PARTIAL | hamısı env (`docker inspect` ilə oxunur); Redis parolu `--requirepass` argv-də → `ps`/`docker inspect .Config.Cmd`-də açıq (işləyən konteynerdə təsdiqləndi — dəyər bu sənədə yazılmayıb); Docker `secrets:` istifadə olunmur |
| C8 | Logging driver limiti | PASS / 1 istisna | `x-logging` json-file 10m×3 hər yerdə; **arp-agent** anchor-suz (`:351-361`) → limitsiz log |
| C9 | Image pinning | PARTIAL | yalnız Python base digest; qalanlar teq |
| C10 | Migrasiya release addımında | PASS | `remote_deploy.sh:504` `compose run --rm app release.sh` (owner rolu, `MIGRATION_DATABASE_URL`) sonra replikalar `RUN_RELEASE_ON_START=false` |
| C11 | Static/media volume | PASS | `static_data`, `media_data` named volume; nginx `:ro`; `CompressedManifestStaticFilesStorage` (`production.py:385`) → `immutable 30d` təhlükəsizdir |
| C12 | nginx TLS/HSTS/gzip | PASS/PARTIAL | TLSv1.2/1.3, http2, gzip (BREACH qeydi düzgün); HSTS Django-dan (`SECURE_HSTS_SECONDS=31536000`, `production.py:380`) — nginx-in birbaşa verdiyi `/static/`, `/media/post_images/` cavablarında HSTS/`X-Content-Type-Options` yoxdur (P3) |
| C13 | `client_max_body_size` vs upload | PASS | 64M ≥ `DATA_UPLOAD_MAX_MEMORY_SIZE` 50M (`components/exam.py:47`), cavab faylı 5M |
| C14 | Proxy timeout vs uzun imtahan | PASS | `proxy_read_timeout 900s` = `DAPHNE_HTTP_TIMEOUT 900`; `application-close-timeout 120` |
| C15 | WebSocket upgrade | PASS | `map $http_upgrade` + `Connection $connection_upgrade` (`nginx.conf:36-39,180-182`) |
| C16 | PgBouncer rejimi vs Django | PASS | `POOL_MODE=session` + `SERVER_RESET_QUERY=DISCARD ALL` + `RLS_TRANSACTION_SCOPED=False` + `CONN_MAX_AGE=0` — uyğun (session GUC RLS). Pool hesabı: app 8×12 thread=96 + celery 4×2+2+1 = 107 < 150 pool; owner cütü ayrıca 200 → nəzəri 400 > `max_connections 250` (yalnız `APP_DATABASE_USER` fərqli olanda, praktikdə owner cütü az işlənir) — P3 |
| C17 | Daphne | PARTIAL | tək proses/replika, `--proxy-headers` **yox** (`prod-entrypoint.sh:26-31`) → WS `scope["client"]` = nginx IP (`live_exam/consumers.py:44-49` fallback rate-limit identity), HTTP tərəfdə `core/utils.py:181` XFF-dən oxuyur (nginx overwrite edir) → HTTP təhlükəsiz |
| C18 | Gunicorn yoxdur | NOT APPLICABLE | dizayn qərarı: Daphne HTTP+WS, replika ilə miqyas |
| C19 | `stop_grace_period` | FAIL (P2) | heç bir servisdə yoxdur → Docker defolt 10s SIGKILL; Daphne `application-close-timeout 120`, heavy OCR task 900s — deploy zamanı davam edən imtahan təqdimi/WS/OCR kəsilir |
| C20 | arp-agent gateway sabiti | FAIL (P2) | `ARP_AGENT_BIND 172.18.0.1` + `EXAM_ARP_AGENT_URL http://172.18.0.1:8953` sabit, amma `networks.emsarena-network` IPAM subnet/gateway pin-lənməyib (`:1017-1019`). Lokal host-da 5 istifadəçi şəbəkəsi var; `emsarena_emsarena-network` təsadüfən 172.18.0.0/16-dır. Başqa sıra ilə yaradılsa agent bind edə bilmir (restart loop) və `resolve_client_mac` fail-closed (`exam_center_gate.py:59-61`) → **imtahan mərkəzi qapısı bütün tələbələri rədd edir** |
| C21 | `.dockerignore` | PASS | `docker/nginx/certs/`, `.env*`, `backups/`, `media/` image-ə düşmür; `docker/nginx/certs/origin.key` git-də izlənmir (`.gitignore:*.key`), fayl `0600` |
| C22 | `docker compose config` | PASS | `--quiet` xətasız |

---

## 2. Celery — PARTIAL

Konfiq (`config/settings/components/celery_cache.py`): broker/result Redis DB 2, JSON, `TIME_LIMIT 300/SOFT 240`, `ACKS_LATE=True`, `PREFETCH_MULTIPLIER=1`, `RESULT_EXPIRES=3600`, `TRACK_STARTED`. Növbələr: `celery` (defolt) + `heavy` (3 route). `autodiscover_tasks` (`config/celery.py`). Global `autoretry_for`/`max_retries`/`reject_on_worker_lost` yoxdur.

### 2.1 Task cədvəli (11 task; `apps/exams/tasks.py`, `apps/monitoring/tasks.py`)

| Task | Növbə / cədvəl | time_limit | Retry | Idempotent? | Atomic / RLS | Qeyd |
|---|---|---|---|---|---|---|
| `exams.expire_stale_resumed_attempts` | celery / 60s | 300/240 | yox | **qismən** — sətir kilidi yoxdur | `rls_worker_atomic()+bypass_rls()` | `sweep_expired_resume_windows` (`supervision/actions.py:252`) |
| `exams.expire_overdue_attempts` | celery / 60s | 300/240 | yox | **qismən** (P2-6) | eyni | `sweep_overdue_attempts` (`services/attempts.py:199-224`): `.iterator()` + `expire_if_time_limit_reached()` → `mark_finished()` kor `save(update_fields=[status,...])` (`domain/attempts.py:350-367`); tələbə tərəfi `select_for_update(of=self)` ilə kilidləyir (`views/student/attempts.py:319`), sweep kilidləmir → «submitted» → «expired» last-writer-wins + ikiqat `schedule_journal_sync` |
| `exams.notify_upcoming_final_exams` | celery / 3600s | 300/240 | yox | bəli (`reminder_stage`) | eyni | |
| `exams.reap_stuck_extraction_jobs` | celery / 300s | 300/240 | yox | bəli (`UPDATE ... WHERE status=PROCESSING AND started_at<cutoff`) | eyni | lease 1200 > heavy 900 ✔ |
| `exams.purge_expired_import_stashes` | celery / 3600s | 300/240 | yox | bəli | eyni | |
| `exams.auto_close_daily_room_sessions` | celery / crontab 22:00 Baku | 300/240 | yox | bəli (state maşını) | eyni | |
| `exams.run_text_extraction_job` | heavy | 900/840 | yox (CAS + reaper) | bəli — `PENDING→PROCESSING` CAS (`tasks.py:180-191`) | claim/yazma bloku `rls_worker_atomic+bypass`; OCR bayırda | `SoftTimeLimitExceeded` `except Exception` ilə FAILED-ə düşür ✔ |
| `exams.run_ai_generation_job` | heavy | 900/840 | yox (CAS) | bəli | eyni | Gemini çağırışı transaction xaricində ✔ |
| `exams.run_export_job` | heavy | 900/840 | yox (CAS) | bəli | **bütün export `rls_worker_atomic` içində** (flag on olsa uzun tranzaksiya) | |
| `monitoring.collect_celery_stats` | celery / 60s | 300/240 | ignore_result | bəli (cache) | DB yox | yalnız `celery` növbəsini ölçür (§5) |
| `monitoring.collect_backup_age` | celery / 900s | 300/240 | ignore_result | bəli | DB yox | `/backups` ro mount |

Yoxlamalar:
- Worker giriş qapısı (`core/rls_pooling.py:86-110`): 11/11 task `rls_worker_atomic()` istifadə edir; DB yazan 9-u `bypass_rls()` ilə (qlobal sweep-lər — tenant hər sətrin öz `organization`-ına yazılır). Flag off → no-op (mövcud session rejimi). PASS.
- `acks_late` + Redis broker visibility_timeout defolt 3600 > 900 ✔; worker OOM → redelivery → CAS «artıq PROCESSING» → toxunmur → reaper 20 dəq sonra FAILED. Təhlükəsiz (təkrar yox, amma iş də itir — qəbul edilə bilər).
- Dead-letter yoxdur (Redis broker); uğursuz task yalnız `TextExtractionJob.status=FAILED` + log. PARTIAL (P3).
- Beat: `--schedule /tmp/...` (`PersistentScheduler`), tək instans — `container_name` sabit olduğu üçün ikinci beat qalxa bilmir ✔.
- 60s sweep-lər `.iterator()` ilə bütün `draft/in_progress` cəhdləri gəzir (org filtri yox) → böyük gündə (min cəhd) 240s soft limitə yaxınlaşa bilər; overlap qorunması (cache lock) yoxdur → concurrency 4 ilə iki sweep paralel işləyə bilər. P3.
- İşləyən stack (lokal): 1 node `celery@585731e2344a`, `max-concurrency 2`, `prefetch_count 8` (mənbə: multiplier 1), yalnız `celery` növbəsi (image 2026-07-06, heavy növbəsi 2026-07-18-də gəlib), `LLEN celery=0 heavy=0`, `exams.expire_stale_resumed_attempts` 3 972 icra. Mənbədəki heavy routing bu image-də olmadığı üçün daxili ziddiyyət yoxdur; amma mənbə deploy olunanda `celery_worker_heavy` mütləq qalxmalıdır (deploy skripti `worker_services_ready` ilə gözləyir ✔).

---

## 3. Redis — PARTIAL

| DB | İstifadə | Konfiq mənbəyi | TTL siyasəti | Qeyd |
|---|---|---|---|---|
| 0 | Channels layer (`channels_redis`) | `REDIS_URL` (`celery_cache.py:14,18-27`) | `expiry 20s`, `capacity 1500` | WS fan-out |
| 1 | Django cache (session `cached_db`, ratelimit, exam-start lock, request-queue, monitorinq statistikası) | `_redis_url_with_db(...,1)` | çağıran təyin edir; `socket_timeout 2s`, `max_connections 100` | `KEY_PREFIX` yoxdur (tək-tenant deploy, qəbul) |
| 2 | Celery broker + result backend | `_redis_url_with_db(...,2)` | `RESULT_EXPIRES 3600` | işləyən: 972 açar (`celery-task-meta-*`, 969-u TTL-li) |
| 12 | **naməlum** — mənbədə istifadə yoxdur | — | 2 açar, TTL yox | lokal alət qalığı; prod-da yoxlanmalı (P3) |

- Yaddaş siyasəti: mənbə `maxmemory 3gb noeviction` (`docker-compose.prod.yml:311-317`) + limit 4096M — `test_redis_maxmemory_default_is_below_container_memory_limit` PASS. **İşləyən:** `maxmemory 0`, `io-threads 1`, konteyner limiti 512 MiB (`docker inspect`), `used_memory 2.18M`, `mem_fragmentation_ratio 5.73`, `evicted_keys 0`, `rejected_connections 0`, `connected_clients 17`, `blocked_clients 1` (Celery BRPOP). → **P2-08 açıq** (Codex ilə eyni; owner-only recreate).
- `noeviction` + broker eyni instansda: cache (DB1) ratelimit/sessiya açarları limitə çatanda **yazma xətası** verir → `cached_db` sessiya DB-yə düşür, ratelimit fail-open? (NOT TESTED); broker qorunur. Alternativ: cache üçün ayrıca instans/`volatile-lru` — dizayn qərarı, P3 tövsiyə.
- Parol: `--requirepass` argv (§1 C7) — `ps`, `docker inspect`, crash dump-larda görünür. P3 (yalnız host daxili). Fix: `redis.conf` şablonu + `REDISCLI_AUTH` (artıq var) və ya ACL faylı.
- TLS yoxdur (daxili bridge) — qəbul. Persistence: AOF + RDB (`save 3600 1 300 100 60 10000`), `aof_last_write_status ok`. PASS.
- Həssas məlumat: sessiya (`cached_db` → DB1, AOF diskə yazılır), imtahan-start kilidləri, ratelimit sayğacları. OTP DB-də hash-lənir (`accounts/services/auth.py:220`), cache-də deyil. PASS.
- Tenant toqquşması: cache açarları globaldır, amma deploy tək-tenant (WCU); Channels qrupları `exam_supervision_<attempt_id>`, `staff_group(session_id)`, `live_<pin>_*` — hamısı qlobal-unikal PK/PIN (`LiveSession.pin unique=True`, `live_exam/models.py:42`). PASS.

---

## 4. ASGI / WebSocket — FAIL (1×P1 latent)

`config/asgi.py`: `ProtocolTypeRouter{http, websocket: AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(...)))}` — origin + session auth qapısı ✔. 5 marşrut.

| Consumer | URL | Auth on connect | Authz | Qrup | Inbound validasiya / limit | RLS konteksti | Nəticə |
|---|---|---|---|---|---|---|---|
| `ExamSupervisionConsumer` | `ws/exams/supervision/<attempt_id>/` | `is_authenticated` → 4401 | sahib / müəllif / superadmin (`bypass_rls` altında `values("user_id","exam__author_id")`) | `exam_supervision_<id>` | inbound yoxdur (read-only) | **`bypass_rls()`** ✔ | PASS |
| `FinalExamRoomConsumer` | `ws/exams/final/room/<session_id>/` | 4401 | `can_supervise_session_ws` | `staff_group(session_id)` | yalnız `ping` | **YOX** — `ExamRoomSession.objects...first()` (`consumers.py:141-145`) | **FAIL** |
| `FinalExamWaitConsumer` | `ws/exams/final/wait/<ticket_id>/` | 4401 + entry-session uyğunluğu | bilet sahibi + status/state | `ticket_group`, `students_group` | `MIN_MESSAGE_INTERVAL 3s`, yalnız `heartbeat`/`ready` | **YOX** — `_authorize`, `_mark_connected_db`, `_heartbeat`, `_set_ready`, `_mark_disconnected` (`:197-334`) | **FAIL** |
| `LiveLobbyConsumer` | `ws/live/<pin>/lobby/` | PIN/host token (`LiveSessionSocketAuthMixin`) | PIN-scoped | `live_<pin>_lobby` | connect rate-limit (`record_rate_limit_hit`, 4429) | `rls_worker_atomic()`; helper `bypass_rls()` | PASS |
| `LivePlayConsumer` | `ws/live/<pin>/play/` | eyni | host/player ayrı qruplar | `live_<pin>_play_{host,players}` | mesaj + cavab rate-limit, `type=="answer"` yoxlaması | `rls_worker_atomic()+bypass_rls()` (`:343-357`) | PASS |

**Reproduksiya** (`test_ws_consumer_rls_nonsuper.py`, sandbox, 124 s): superuser test bağlantısında hər 3 consumer icazə verir; sonra `CREATE ROLE ... NOSUPERUSER NOBYPASSRLS` + `GRANT ... ALL TABLES` + `SET SESSION AUTHORIZATION` + `app.bypass_rls=off`, `app.current_org_id=''` (WS scope-da heç bir middleware tenant GUC-u qoymur):

```
RESULTS under NOBYPASSRLS role: {'supervision_consumer_with_bypass': True,
                                 'final_room_consumer': False,
                                 'final_wait_consumer': None}
```

Yəni Codex P0-01-in düzəlişi (`APP_DATABASE_USER` NOBYPASSRLS rolu, `docker-compose.prod.yml:70-72`, `scripts/provision-app-db-role.sh`) tətbiq olunan kimi final imtahan mərkəzinin **bütün nəzarətçi monitorları və tələbə gözləmə soketləri 4403 ilə rədd olunacaq**, `FinalExamTicket.objects.filter(pk).update(...)` presence yazıları səssizcə 0 sətir toxunacaq. Mövcud superuser rolunda görünmür → P0-01 rollout-un **gizli blokeri**. Bax §9 P1-1.

Digər: disconnect/reconnect — `reconnect_count` + `last_seen_at` (`:244-256`) ✔; backpressure — channel layer `capacity 1500 / expiry 20` ✔; `AsyncJsonWebsocketConsumer.receive_json` defoltu no-op (supervision) ✔; Daphne `--proxy-headers` yoxdur (§1 C17) → `LiveLobby/Play` connect rate-limit fallback-i (`_get_scope_ip`) bütün müştəriləri nginx IP-si altında birləşdirir — yalnız token/istifadəçi olmayanda (P3).

---

## 5. Monitorinq / alert — PARTIAL (işləyən stack-də FAIL)

- Prometheus (`docker/prometheus/prometheus.yml`): 11 scrape job (app via `nginx:80/metrics/`, postgres, node, cadvisor, redis, nginx, pgbouncer, alertmanager, loki, blackbox ×3 endpoint, prometheus). **App scrape tək hədəf `nginx:80`** → `APP_REPLICAS=8` olanda hər scrape nginx round-robin ilə fərqli replikaya düşür; hər replikanın öz `PROMETHEUS_MULTIPROC_DIR` registry-si var → eyni seriya altında 8 müstəqil sayğac qarışır (`rate()` counter-reset kimi görür, `High5xxRate`/`HighLatencyP95`/`ExamAttemptServerErrors` səhv hesablanır). P2. Fix: `dns_sd_configs: [{names: [app], type: A, port: 8000}]` (Compose DNS `app` bütün replika IP-lərini qaytarır — nginx də eyni mexanizmi işlədir).
- Alert qaydaları (`alerts.yml`): 31 qayda / 8 qrup — TargetDown, PostgresDown, High5xxRate, HighLatencyP95, ExamAttemptServerErrors, PgConnectionsHigh(>170), disk/inode/mem/cpu/load/swap, ContainerDown/RestartLoop/OOM/MemNearLimit, RedisDown/MemoryHigh/Evicted/Blocked, NginxDown, EndpointProbeFailed/Slow, TlsCertExpiring(30g)/Critical(7g), CeleryWorkersDown, CeleryBeatStale, CeleryQueueBacklog(>200), BackupTooOld(>26h). Metrik adları mənbədə mövcuddur (`core/metrics.py:52-62`, `apps/monitoring/collectors.py:90-115`) ✔.
- **Monitorinq boşluqları:**
  1. Alertmanager-in öz çatdırılma uğursuzluğu (`alertmanager_notifications_failed_total`) izlənmir → müşahidə olunan «525 Unauthorized IP» halı səssiz qalır. Deadman/Watchdog (həmişə yanan alert + xarici heartbeat) yoxdur.
  2. `emsarena_celery_queue_length` yalnız `celery` növbəsini ölçür (`collectors.py:52`) → **heavy** (OCR/AI/export) backlog-u və heavy worker ölümü (`workers_online` ümumi say) görünmür.
  3. PgBouncer `cl_waiting`/pool doyması, Postgres deadlock/uzun tranzaksiya/lock gözləməsi, DB ölçüsü artımı — qayda yoxdur.
  4. Redis AOF/RDB uğursuzluğu (`redis_aof_last_bgrewrite_status`) — yoxdur.
  5. E-poçt/OTP göndərmə uğursuzluğu, WS bağlantı sayı/channel-layer drop — metrik yoxdur.
  6. `CeleryQueueBacklog` `for 10m` — imtahan günü 60s sweep-lər üçün gecdir (P3).
- Alertmanager (`alertmanager.tmpl.yml`): e-poçt (Brevo SMTP, `smtp_require_tls`) + app webhook (Bearer ✔, `max_alerts 20`, `send_resolved`); `group_by alertname`, critical `repeat 1h`; inhibit TargetDown→job. `sed` render `|` ayırıcısı ilə — SMTP parolunda `|`/`&`/`\` konfiqi pozar (P3).
- **Webhook çatmır (reproduksiya `test_alertmanager_webhook_direct_post.py`):** Alertmanager `http://app:8000/api/superadmin/monitoring/alertmanager-webhook/`-a `Host: app:8000`, XFP-siz POST edir. `.env.production.example`/`deployment.md:84` `ALLOWED_HOSTS=10.0.2.42,localhost,127.0.0.1` + `SECURE_SSL_REDIRECT=True` (P1-08 tələbi) ilə: **400** (DisallowedHost); `app` əlavə etsək **301** → `https://app:8000/...` (Alertmanager redirect izləmir, 3xx = uğursuz); yalnız `app`+https → 200. Yəni düzgün konfiqurasiya olunmuş prod-da Monitorinq Mərkəzinin insident webhook-u heç vaxt işləmir. CI `prod-smoke` `INSECURE_TRANSPORT_OK=1` ilə bunu maskalayır. P2. Fix: `nginx.conf`-da `/metrics/` naxışı ilə daxili `location = /api/superadmin/monitoring/alertmanager-webhook/ { allow 172.16.0.0/12; deny all; proxy_set_header Host localhost; proxy_set_header X-Forwarded-Proto https; ... }` və template URL → `http://nginx/api/...`.
- Blackbox: `Host: 10.0.2.42` git-də hard-code (`blackbox.yml`), `insecure_skip_verify` (LAN self-signed) — mühit dəyəri repoda (P3).
- Grafana: 1 dashboard (`emsarena-overview.json`), datasource provisioning ✔, sign-up off, parol məcburi ✔.
- Health endpoint-ləri: `/ping/` (liveness, DB-siz), `/health/` (DB + Redis, 200/207/503, 2s cache, **anonim**: `build.sha`, Django/Python versiyası, uptime — informasiya sızması, P3; nginx-də məhdudlaşdırılmır). `/metrics/` nginx `allow 10.0.0.0/8` → **kampus LAN-ındakı hər tələbə kompüteri** (`FINAL_EXAM_ALLOWED_IPS=10.0.0.0/19`) `METRICS_ALLOW_ANONYMOUS=true` ilə metrikləri oxuya bilir (yol/status sayğacları, worker sayı) — P3 (LAN daxili), fix: `allow 172.16.0.0/12` (yalnız docker) + `deny all`.
- Loglar: Django JSON (`core/logging_filters.py` — `SensitiveDataFilter` e-poçt/telefon/token/parol maskalama, `RequestIdFilter`), `RequestIdMiddleware` → nginx `req_id=$upstream_http_x_request_id` korrelyasiya ✔. Loki 14 gün retention, Promtail docker_sd ✔ (Promtail EOL 2026-03 → Alloy-a keçid, P3). nginx access log sorğu sətrini xam yazır (Django maskalaması ora çatmır) — PII riski axtarış parametrlərində (P3).
- **İşləyən lokal stack (2026-09-13, `docker ps`):** `emsarena-prometheus`, `emsarena-alertmanager`, `emsarena-nginx` — üçü də **Exited (127)** 2026-09-07 22:23:20Z-dən bəri, `restart=unless-stopped` olsa da qalxmayıb (Docker Desktop restart-ında bind-mount/inode). Yəni lokal «prod-like» yığında **5+ gündür edge və monitorinq işləmir**; yalnız grafana/postgres-exporter/node-exporter/backup ayaqdadır. Alertmanager-in son logları (07.09): e-poçt çatdırılması **`525 5.7.1 Unauthorized IP address`** (Brevo göndərici IP icazəsi yoxdur) + `smtp-relay.brevo.com` DNS timeout — **alert kanalı faktiki işləmir**; işləyən alertmanager `cmd`-də `__WEBHOOK_TOKEN__` sed-i yoxdur (köhnə compose). cadvisor/loki/promtail/redis_exporter/nginx_exporter/pgbouncer_exporter/blackbox/arp-agent/celery_worker_heavy heç yaradılmayıb.

---

## 6. Backup / DR — PARTIAL (real ölçü restore NOT TESTED)

| Maddə | Vəziyyət | Sübut |
|---|---|---|
| Servis | `postgres-backup` (`prodrigestivill/postgres-backup-local:16-alpine`), `pg_dump -Z6 --blobs`, `@daily`, saxlama 7g/4h/3a, healthcheck `:8080` (son backup uğursuz → unhealthy → TargetDown/ContainerDown) | `docker-compose.prod.yml:208-250` |
| Təzəlik alerti | `BackupTooOld > 26h` (`emsarena_backup_age_seconds`, worker `/backups:ro`, 15 dəq) | `alerts.yml`, `collectors.py:115` |
| İşləyən lokal | healthy; `/backups` bind → **başqa checkout** (`/Users/elvin/Desktop/Programming Folders/EMSArena/EMSArena/backups/postgres`, 3.3 GB): daily `20260908/09/12/13` (10, 11 **yoxdur** — laptop yatıb; serverdə bu problem yoxdur), weekly `202637`, monthly `202609`, hard-link (nlink 4) ✔; hər biri ≈708 MB, mode **0644**, şifrələnməmiş, plain gzip | `ls -la`, `docker inspect Mounts`, `docker logs` («SQL backup created successfully» 13.09 12:34Z) |
| Off-site | **YOX** — sənəd rclone cron nümunəsi verir (`deployment.md:604-605`), «hələ konfiqurasiya olunmayıb» (`:711-712`) | doc |
| Şifrələmə | YOX (dump və `backups/` qovluğu açıq) | compose/doc |
| Media backup | yalnız əl ilə `tar` nümunəsi (`deployment.md:357-361`), cədvəl/alert yoxdur → imtahan cavab faylları, sənədlər, avatar RPO = ∞ | doc |
| PITR / WAL arxivi | YOX (`wal_level`/`archive_command` yoxdur) → RPO = 24 saat (qiymət/imtahan yazıları üçün böyük) | compose `:171-197` |
| Restore proseduru | `deployment.md §12` + «Backup RESTORE runbook» (`:680-712`) — `gunzip -c | psql` yeni DB-yə, sonra `migrate`/smoke; deploy öncəsi `pg_dump` tövsiyəsi (`:479-483`) amma **deploy skripti backup almır** | doc, `remote_deploy.sh` |
| Restore məşqi | Sintetik: data auditoru (`audit/data/FINDINGS.md §7`) — 172 cədvəl/283 miqrasiya/142 siyasət paritet PASS, 2 s; yeganə xəbərdarlıq `transaction_timeout` (pg_dump 17 klient / PG16). **Real ölçü (2.46 GB SQL, 4 M lessonmark) — NOT TESTED**; Codex `backup-integrity.json` gzip PASS, restore NOT TESTED. Repo `backups/postgres/emsarena_db_20260908_0228.dump` (custom, 710 MB) QA klonunu qurub → real data ilə 1 dəfə `pg_restore` faktiki edilib, amma runbook `psql` yolunu təsvir edir | — |
| Miqrasiya geri qaytarma | `deployment.md §8`: `migrate <app> <name>` + image teqi ilə geri — amma CI image-i SHA ilə teqləmir (§7), `RUN_RELEASE_ON_START` defolt true köhnə image-də irəli migrate edir (geri yox) | doc, `remote_deploy.sh:502-507` |
| Postgres data | named volume `postgres_data` (host disk); host itkisi = backup itkisi (off-site yox) | compose |

Qiymət: mexanizm və təzəlik alerti var; off-site/şifrələmə/media/PITR yoxdur; real ölçüdə bərpa müddəti (RTO) ölçülməyib.

---

## 7. CI/CD — PASS (deploy rollback PARTIAL)

| Qapı | Workflow | Bloklayır? | Qeyd |
|---|---|---|---|
| Lint | `_lint.yml` (3.11) | bəli (hər şey `needs: lint`) | |
| Unit 3.11 / 3.12 | `_unit-tests.yml` ×2 | bəli | Postgres+Redis servisləri, `-n 4` xdist, `--cov-fail-under=68`, pytest-timeout |
| RLS txn-pool | `_rls-txn-pool.yml` | bəli | `-m postgres` + `RLS_TRANSACTION_SCOPED=True` |
| Build | `_build.yml` | bəli | `collectstatic`, **`makemigrations --check --dry-run`** (`:92`), `migrate` |
| Security | `_security.yml` | bəli | pip-audit (fail), safety (`\|\| true` — advisory), bandit, `check --deploy --fail-level WARNING` |
| Secret scan | `_secret-scan.yml` | bəli | gitleaks |
| Docker build | `_docker-build.yml` | bəli | `emsarena-prod:ci` |
| Container scan | `_container-scan.yml` | bəli | Trivy HIGH/CRITICAL fixable `exit-code 1`, `.trivyignore` 2 giriş (**«Yenidən baxış: 2026-08-15» keçib**; `CVE-2025-47273` setuptools artıq image-də ≥78.1.1 → ignore köhnəlib, P3) |
| Prod smoke | `_prod-smoke.yml` | bəli | tam compose stack, `/ping/`+`/health/`, `INSECURE_TRANSPORT_OK=1` (düz HTTP) |
| E2E smoke | `_e2e-smoke.yml` | bəli | Playwright |
| CodeQL | `codeql.yml` | ayrı | |
| `ci-success` | `ci.yml:139-237` | fail-closed (cancelled/skipped ≠ success) ✔ | |
| `deploy-production` | `ci.yml:240-267` | `push main` + `ci-success`, `environment: production`, self-hosted, `concurrency production-deploy` | `rsync -a --delete --exclude-from rsync-excludes.txt` (`.env*`, `media/`, `backups/`, certs, `.git` qorunur ✔) → `remote_deploy.sh` |

Deploy axını (`remote_deploy.sh docker_deploy`, L484-547): DNS/TLS preflight → `build` → `up postgres redis pgbouncer` → `check --deploy` (ERROR səviyyə, W-lar yalnız çap) → `release.sh` (migrate owner rolu + collectstatic) → `up -d --scale app=8 --scale celery_worker=2` → app+worker health gözləmə (300s) → nginx reload/recreate → Prometheus SIGHUP → Alertmanager recreate → `/ping/`+`/health/` → `build.sha` uyğunluğu. ✔ Sağlam qapılar.

Boşluqlar:
- **Rollback yolu yoxdur** — `APP_IMAGE` defolt `emsarena-prod:latest`, `build` `latest`-i üstündən yazır; əvvəlki image yalnız dangling ID kimi qalır. Sənəd (`deployment.md §8`) «SHA ilə teqləyin» deyir, skript etmir. `up -d` bütün 8 replikanı eyni anda yeni image ilə recreate edir (rolling deyil); sağlamlıq gözləməsi uğursuz olsa köhnə konteynerlər artıq gedib → **downtime + əl ilə rebuild**. P2.
- Deploy öncəsi avtomatik DB backup yoxdur (sənəd tövsiyə edir). P2 (miqrasiya-ağır release-də).
- Frontend build addımı yoxdur — bundler yoxdur (vanilla JS/CSS, whitenoise manifest) → NOT APPLICABLE ✔.
- Coverage 68 % qapısı (Codex: statement 83 % SQLite ölçüsü) — aşağıdır, amma var. Flaky/skip sayı: uzaq run-lar əlçatan deyil → NOT TESTED.
- `env-update.yml`: `workflow_dispatch` ilə prod `.env` dəyişikliyi (dəyərlər run logunda görünür — sənəd xəbərdarlıq edir), `.env.bak.*` 10 nüsxə saxlanır (sirlər); `environment: production` qorunması GitHub tərəfində konfiqurasiya olunubsa qəbul edilə bilər — NOT TESTED (uzaq). `prod-exam-ops.yml`: ağ-siyahılı skriptlər, `manage.py shell < stdin`, dry-run defolt ✔.

---

## 8. Dependency / versiya drift — FAIL (işləyən image, P1-07 təsdiq və genişlənib)

İşləyən `emsarena-prod:latest` (ID `3cd9f2c510a6`, **build 2026-07-06 03:02 +04**, 1.45 GB, `build-info.json` yoxdur) vs mənbə `requirements/{base,production}.txt` (56 pin; `running_pip_freeze.txt` 88 paket):

| Paket | Mənbə | İşləyən | Risk |
|---|---|---|---|
| Django | 5.2.17 (PYSEC-2026-3717 + 2090/2091/2092) | **5.2.15** | təhlükəsizlik |
| sqlparse | 0.6.0 (PYSEC-2026-3696..3699) | **0.5.4** | təhlükəsizlik |
| pypdf | 6.16.1 (CVE-2026-84309/84310/84311) | **6.13.3** | təhlükəsizlik (PDF import) |
| cryptography | 50.0.0 | 49.0.0 | |
| pyOpenSSL | 26.4.0 | 26.3.0 | |
| pillow | 12.3.0 | 12.2.0 | |
| pyasn1 | 0.6.4 | 0.6.3 | |
| PyMySQL | 1.2.0 | yoxdur | legacy adapter |
| setuptools | ≥78.1.1 | 83.0.0 ✔ | |
| celery/redis/channels/daphne/psycopg2/Twisted | 5.5.2/7.1.0/4.3.2/4.2.2/2.9.9/26.4.0 | eyni ✔ | |

Runtime: Python 3.12.13 (EOL 2028-10), Django 5.2 LTS (2028-04), Postgres 16.x alpine (EOL 2028-11), Redis 7.4.8 (7.4 dəstəklənir), PgBouncer 1.25.1, nginx **1.27-alpine** (1.27 mainline 2025-04-dən yenilənmir; lokal image 2025-04-16 → alpine paket CVE-ləri; `1.28-alpine`-a keçid, P3), Prometheus 3.8.0, Alertmanager 0.28.1, Grafana 12.3.0, Loki/Promtail 3.1.1 (Promtail EOL, Loki 3.5+ mövcuddur, P3), cadvisor 0.60.5, postgres-exporter 0.17.1. Codex-in «5.2.15 vs 5.2.17» tapıntısı **69 günlük** image drift-inin bir simptomudur; işləyən compose də köhnədir (healthcheck-siz celery, `maxmemory 0`, `cpus 1.5`/`mem 1.5G` app, 1 replika, heavy worker yoxdur, alertmanager token sed-i yoxdur, 9 servis yaradılmayıb).

---

## 9. Tapıntılar (P0–P3) — minimal repo-side fix ilə

### P0 — yoxdur (bu sahədə). Codex P0-01 (superuser DB rolu) açıq qalır — owner-only rollout; P1-1 onun blokeridir.

### P1

**P1-1 · Final-center WS consumer-ləri NOBYPASSRLS rolu altında 0 sətir görür (latent, P0-01 rollout blokeri)** — FAIL, reproduksiya `test_ws_consumer_rls_nonsuper.py`.
`apps/exams/consumers.py` `FinalExamRoomConsumer._can_supervise` (L138-145), `FinalExamWaitConsumer._authorize` (L197-222), `_mark_connected_db` (L224-243), `_mark_disconnected` (L256-265), `_heartbeat` (L283-300), `_set_ready` (L303-314) — WS scope-da tenant GUC yoxdur, `bypass_rls()` çağırılmır. Fix: hər `@database_sync_to_async` gövdəsini `ExamSupervisionConsumer` və `live_exam/consumers.py:343` naxışı ilə `with rls_worker_atomic(), bypass_rls():` içinə al (autorizasiya artıq `student=user` / `can_supervise_session_ws` ilə kodda təmin olunur); reproduksiya testini `apps/exams/tests/test_final_center_consumers.py`-ə (postgres marker, probe rol) daşı.

**P1-2 · İşləyən image/compose 69 gün geridədir; məlum CVE-li Django/sqlparse/pypdf serve olunur** — FAIL (Codex P1-07 təsdiqləndi, `pip freeze` diff §8). Repo-side: heç nə (mənbə düzgündür); owner-only: §10-1. Əlavə repo-side qoruma: `alerts.yml`-ə `ImageAgeHigh` (health `build.built_at` → gauge) — P3 tövsiyə.

**P1-3 · Alert kanalı faktiki işləmir (lokal prod-like stack sübutu)** — FAIL. Alertmanager logu 2026-09-07: `525 5.7.1 Unauthorized IP address` (Brevo IP ağ siyahısı) + DNS timeout; sonra alertmanager/prometheus/nginx `Exited (127)` 5+ gün, heç kim bilməyib (self-monitoring yoxdur). Repo-side fix: `docker/prometheus/alerts.yml`-ə `AlertmanagerNotificationsFailing: increase(alertmanager_notifications_failed_total[15m]) > 0` (critical) + `Watchdog: vector(1)` (həmişə yanan; receiver — xarici heartbeat/e-poçt «hələ sağam»); `docs/operations/SISTEM_MONITORINQI.md`-də Brevo «authorised IP» addımı. Owner-only: §10-2.

### P2

**P2-1 · Alertmanager → app webhook düzgün prod konfiqində 400/301 alır** — FAIL (reproduksiya `test_alertmanager_webhook_direct_post.py`). Fix: `docker/nginx/nginx.conf`-da `location = /api/superadmin/monitoring/alertmanager-webhook/` (allow `172.16.0.0/12`, `Host localhost`, `X-Forwarded-Proto https`, `/metrics/` bloku kimi) + `docker/alertmanager/alertmanager.tmpl.yml` `url: http://nginx/api/superadmin/monitoring/alertmanager-webhook/`; `_prod-smoke.yml`-də `INSECURE_TRANSPORT_OK` olmadan bu yolu yoxlayan addım.

**P2-2 · Prometheus app scrape-i tək `nginx:80` hədəfi ilə 8 replikanı qarışdırır** — FAIL. Fix: `prometheus.yml` `emsarena-app` job → `dns_sd_configs: [{names: ["app"], type: A, port: 8000}]`; app konteynerləri `/metrics/`-i redirect-siz versin deyə `SECURE_REDIRECT_EXEMPT=[r"^metrics/$"]` (`production.py`) və ya Prometheus `http_headers: {X-Forwarded-Proto: https}`; nginx `/metrics/` bloku qala bilər.

**P2-3 · `stop_grace_period` yoxdur → deploy/restart-da 10 s sonra SIGKILL** — FAIL. Fix: `docker-compose.prod.yml` `app: stop_grace_period: 130s` (≥ `DAPHNE_APPLICATION_CLOSE_TIMEOUT`), `celery_worker: 300s`, `celery_worker_heavy: 900s` (warm shutdown), `postgres: 60s`; `tests/test_infra_compose_config.py`-ə invariant.

**P2-4 · arp-agent gateway ünvanı pin-lənməyib → imtahan qapısı fail-closed** — FAIL. Fix: `networks.emsarena-network.ipam.config: [{subnet: 172.18.0.0/16, gateway: 172.18.0.1}]` (mövcud host bu subnet-dədir → recreate-də dəyişmir); arp-agent-ə `logging: *default-logging`, `deploy.resources.limits` (0.1 / 32M), healthcheck (`/healthz` endpoint əlavə et).

**P2-5 · Deploy rollback yolu / SHA teqi yoxdur** — FAIL. Fix: `remote_deploy.sh` `resolve_build_git_sha`-dan sonra `export APP_IMAGE="emsarena-prod:${BUILD_GIT_SHA}"` (compose `build` bu teqlə), uğurlu health-dən sonra `docker tag ... emsarena-prod:latest`; uğursuzluqda `APP_IMAGE=<əvvəlki>` ilə `up -d`; `docs/operations/deployment.md §8` yenilə. Əlavə: `release.sh`-dan əvvəl `docker compose exec -T postgres-backup /backup.sh` — deploy-öncəsi dump.

**P2-6 · `sweep_overdue_attempts` kilidsiz kor yazı (Celery idempotentlik)** — FAIL (kod oxunuşu; exams auditoru ilə kəsişir). Fix: `apps/exams/services/attempts.py:199-224` — hər cəhd üçün `with transaction.atomic(): attempt = ExamAttempt.objects.select_for_update(of=("self",), skip_locked=True).filter(pk=..., status__in=["draft","in_progress"]).first()` və ya `mark_finished`-i şərti `UPDATE ... WHERE status IN (...)` ilə CAS et; eyni naxış `sweep_expired_resume_windows`.

**P2-7 · Backup: off-site yox, şifrələmə yox, media backup yox, PITR yox, real-ölçü restore NOT TESTED** — PARTIAL (data auditoru ilə eyni; Codex açıq). Repo-side minimal: `docker-compose.prod.yml` `postgres-backup`-a `BACKUP_ON_START=TRUE`; docs-da off-site cron məcburi checklist maddəsi; media üçün ikinci sidecar `tar` cədvəli və `collect_media_backup_age`. Owner-only: §10-3.

**P2-8 · Heavy növbəsi/worker monitorinqsiz** — FAIL. Fix: `apps/monitoring/collectors.py:50-56` `llen("heavy")` də ölç, `emsarena_celery_queue_length{queue="celery|heavy"}`; `workers_online` node adı ilə → `CeleryHeavyWorkerDown` qaydası.

**P2-9 · Prometheus `depends_on: app: service_healthy`** — FAIL (dizayn). Fix: `docker-compose.prod.yml:670-674` app asılılığını sil (yalnız `postgres_exporter`); TargetDown onsuz da app-i tutur.

**P2-10 · Redis işləyən konfiq drift-i (`maxmemory 0`, 512 MiB limit, io-threads 1)** — Codex P2-08 açıq, owner-only §10-1.

### P3

- P3-1 · nginx healthcheck `nginx -t` → `wget -qO- http://127.0.0.1:8081/stub_status` (real dinləmə).
- P3-2 · app healthcheck şərhi (`:395-405`) `/ping/` reallığına uyğunlaşdırılsın.
- P3-3 · Redis parolu argv-də → `docker/redis/redis.conf` şablonu (`requirepass` env-dən entrypoint-də render) və ya ACL faylı.
- P3-4 · `/health/` anonim `build.sha`/versiya sızması → nginx `allow` siyahısı; `/metrics/` `allow 10.0.0.0/8` → yalnız `172.16.0.0/12`.
- P3-5 · Image teqləri digest-ə pin (`postgres`, `redis`, `nginx`, `python:3.12-alpine`, exporterlər) — Renovate/Dependabot `docker`.
- P3-6 · nginx `1.27-alpine` → `1.28-alpine`; Promtail → Alloy; Loki 3.1.1 → 3.5.x.
- P3-7 · `.trivyignore` baxış tarixi (2026-08-15) keçib; `CVE-2025-47273` girişi artıq lazımsız → sil.
- P3-8 · Alertmanager `sed` render: `|`/`&` ehtiva edən SMTP parolu konfiqi pozur → `envsubst` və ya `smtp_auth_password_file`.
- P3-9 · Blackbox `Host: 10.0.2.42` git-də → `HEALTHCHECK_HOST` env ilə render.
- P3-10 · Host ölçüsü/limit cəmi (≈44 GB) sənədləşdirilsin; `.env.production.example`-da host RAM-a görə defoltlar.
- P3-11 · nginx `/static/`, `/media/post_images/` cavablarında `X-Content-Type-Options nosniff` + HSTS (`add_header ... always`).
- P3-12 · Daphne `--proxy-headers` (nginx XFF-i overwrite edir → təhlükəsiz) → WS `scope["client"]` real IP.
- P3-13 · Redis DB 12-də 2 TTL-siz açar (mənbədə istifadə yoxdur) — prod-da `INFO keyspace` ilə yoxla.
- P3-14 · 60 s sweep-lər üçün overlap kilidi (`cache.add("lock:sweep_overdue", ttl=55)`); `CeleryQueueBacklog for 10m` → `2m`.
- P3-15 · `safety check ... || true` advisory; pip-audit onsuz da bloklayır → `safety` addımını sil (yanıltıcı yaşıl).
- P3-16 · Deploy `check --deploy` W-ları yalnız çap edir (`DEPLOY_CHECK_FAIL_LEVEL=ERROR`); CI eyni yoxlamanı WARNING ilə bloklayır → prod hostda da `WARNING`.
- P3-17 · nginx access log sorğu sətri (PII axtarış parametrləri) → `$request_method $uri`.
- P3-18 · PgBouncer pool hesabı: `APP_DATABASE_USER` ≠ owner olanda iki cüt × 200 > `max_connections 250` → owner cütü üçün ayrıca kiçik pool / `POSTGRES_MAX_CONNECTIONS 400`.

---

## 10. Owner-only ops addımları (repo dəyişikliyi deyil)

1. **Image/compose rollout (P1-2, P2-10, Codex P1-07/P2-08):** `main`-ə push → `deploy-production` (və ya serverdə `bash scripts/deploy/remote_deploy.sh`). Deploy sonrası `curl -k https://127.0.0.1/health/ | jq .build.sha` = HEAD; `docker compose ps` — `celery_worker_heavy`, `cadvisor`, `loki`, `promtail`, exporterlər, `arp-agent` mövcud; `docker exec emsarena-redis redis-cli CONFIG GET maxmemory` = 3221225472. İmtahan günündən kənarda, `.env`-də `INSECURE_TRANSPORT_OK` olmadan.
2. **Alert kanalı (P1-3):** Brevo panelində serverin çıxış IP-sini «Authorised IPs»-ə əlavə et (və ya SMTP relay-i dəyiş); `docker compose exec alertmanager amtool alert add test severity=critical` ilə e-poçtun çatdığını təsdiqlə; `alertmanager_notifications_failed_total` 0 olduğunu Prometheus-da gör. Lokal Docker Desktop yığınında exited (127) prometheus/alertmanager/nginx-i `docker compose up -d` ilə recreate et (bu audit toxunmayıb).
3. **Backup/DR (P2-7):** off-site `rclone` cron (`deployment.md:604`) + şifrələmə (`rclone crypt` / `gpg --symmetric`); media volume üçün həftəlik `tar` + eyni off-site; **real ölçüdə restore məşqi** ayrı host/VM-də: `gunzip -c daily/latest | psql` → `migrate --check` → `/health/` → 1 tələbə/1 müəllim smoke; RTO-nu runbook-a yaz. PITR istənirsə `wal_level=replica` + `archive_command` (wal-g/pgbackrest sidecar).
4. **P0-01 rollout:** yalnız §9 P1-1 düzəlişi merge olduqdan SONRA (`scripts/provision-app-db-role.sh` → `.env` `APP_DATABASE_USER/PASSWORD` → `EMS_DB_ROLE_ENFORCE=error` → staging klonunda final-center WS + `-m postgres` testləri).
5. GitHub `production` environment-ində required reviewers (env-update/prod-exam-ops workflow-ları üçün) — yoxlanmalı (uzaq, NOT TESTED).

---

## 11. Ballar və xülasə

| Sahə | Bal | Əsaslandırma |
|---|---|---|
| DevOps | **62** | Compose zəngin (21 servis, log rotasiyası, limitlər, healthcheck 16/21, non-root app, ro mount-lar, `.dockerignore`), amma stop_grace/IPAM/secrets/digest pinning yoxdur; işləyən yığın mənbədən 69 gün geridir |
| Deployment | **55** | Güclü qapılar (check --deploy, release ayrı, health + build-sha doğrulaması) — rollback/SHA teq/deploy-öncəsi backup yoxdur, bütün replikalar eyni anda recreate |
| Reliability | **58** | restart siyasəti, healthcheck-lər, CAS+reaper job-lar ✔; arp-agent gateway sabiti (imtahan qapısı fail-closed), 10 s SIGKILL, lokal stack-də 3 kritik konteyner 5+ gün exited (127) və qalxmayıb |
| Celery | **70** | Növbə ayrımı, acks_late+prefetch 1, CAS claim, lease reaper, worker-atomic gate 11/11; sweep kor yazı (P2-6), retry/DLQ yoxdur, heavy növbəsi monitorinqsiz |
| Redis | **64** | DB ayrımı, AOF+RDB, noeviction (broker-safe), timeout-lar, OTP cache-də deyil; işləyən drift (maxmemory 0), parol argv-də, cache/broker eyni instans |
| WebSocket/Realtime | **52** | Origin+auth+authz, rate-limit, qrup adlandırması təmiz; **final-center consumer-ləri NOBYPASSRLS rolunda tamamilə qırılır** (reproduksiya edildi) — P0-01 düzəlişinin gizli blokeri |
| Monitoring | **48** | 31 alert qaydası, 11 exporter, blackbox/TLS expiry, backup-age — amma webhook prod konfiqində çatmır (repro), 8 replika tək hədəfdə qarışır, self-monitoring/deadman yoxdur, işləyən yığında alert e-poçtu «525 Unauthorized IP» və prometheus/alertmanager 5 gün exited |
| Logging | **74** | JSON + request-id + PII maskalama + nginx korrelyasiya + Loki 14 gün ✔; nginx xam query-string, Promtail EOL |
| Documentation | **66** | `deployment.md` (13 bölmə + restore runbook), `SISTEM_MONITORINQI.md`, `PROD_DB_ROLE_CHECKLIST.md`, compose şərhləri yüksək keyfiyyətli; host ölçüsü, real rollback, Brevo IP tələbi, alert kanalının test qaydası yoxdur; bəzi şərhlər köhnəlib (`/ping/` vs `/health/`) |

**Ümumi infra balı: 60/100.** Mənbə (HEAD) tərəfi yaxşı dizayn olunub və Codex remediation-ları düzgün merge olunub; balı aşağı salan (1) işləyən mühitin mənbədən 69 gün geri olması və orada alert/edge/monitorinq konteynerlərinin faktiki işləməməsi, (2) P0-01 rollout-u üçün gizli WS-RLS blokeri, (3) alert kanalının (e-poçt + webhook) real çatdırılmasının heç bir şəraitdə sübut olunmamasıdır.

**Saylar:** P0 0 · P1 3 · P2 10 · P3 18. NOT TESTED: real ölçüdə restore/RTO, uzaq `wcuserver` vəziyyəti, GitHub environment qorunması, uzaq CI run-larının flaky/skip sayı, Redis limitə çatanda ratelimit/session fail-open davranışı, broker failover.
