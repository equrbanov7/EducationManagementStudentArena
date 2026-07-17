# EMSArena — 5000 eyni-anlı istifadəçi üçün performans optimallaşdırması

_Tarix: 2026-07-17 · Server: wcuserver (80 core / 62 GiB) · k6 stress test + tam qat auditi_

## 1. Kök səbəb (sübut edilmiş)

Prod yavaşlığının (sayt/login/exam gec) səbəbi **dəmir yox, Docker resurs limitləridir**. Limitlər kiçik VPS üçün ölçülüb; 80-nüvəli serverdə app cəmi **6 nüvəyə** (4 replika × `APP_CPU_LIMIT=1.5`) həbs olunmuşdu.

**Sübut (yük altında ölçülmüş):**
- App konteynerləri CFS ilə period-ların **90–97%-də dondurulub** (`nr_throttled/nr_periods`), `throttled_usec` ~10 000 s.
- Host CPU **92% boş**, Postgres 1% CPU, DB tam sağlam.
- k6 login ladder (öncə): 50 VU-da p95 **39.7 s**, 100+ VU-da 60 s timeout, 89%-ə qədər fail.

## 2. Canlı düzəliş və nəticə (öncə → sonra)

`docker update --cpus=8` (4 app konteyneri, restartsız) tətbiq edildi:

| VUs | RPS öncə→sonra | p95 öncə→sonra | fail% öncə→sonra |
|----:|:--|:--|:--|
| 50 | 4.6 → **33.6** | 39.7s → **1.0s** | 0 → 0 |
| 100 | 3.8 → 32.8 | 60s → 8.6s | 15% → 0% |
| 200 | 13 → 28.5 | 60s → 15s | 77% → 0% |
| 500 | 7.4 → 25.2 | 60s → 37s | 67% → 0% |

Bir dəyişikliklə **7× throughput, 40× latency**. Qalan tavan (~25–33 RPS): 4 replika × 8 thread = **32 eyni-anlı sync slot** — 5000 üçün memarlıq genişlənməlidir (aşağı).

## 3. Repo-da edilmiş kalıcı dəyişikliklər (bu commit)

Hamısı `docker-compose.prod.yml` default-larıdır → **deploy edildikdə avtomatik tətbiq olunur, yeni serverdə də təkrarlanmır**, hamısı `.env` ilə override oluna bilər:

| Servis | Əvvəl | İndi (default) |
|---|---|---|
| app | 1.5 cpu / 1536M / 8 thread | **4.0 cpu / 2048M / 12 thread** |
| postgres | 2 cpu / 2G, stock config | **16 cpu / 16G** + tuning (shared_buffers 2G, effective_cache_size 6G, work_mem 16M, WAL/checkpoint) |
| redis | 0.5 cpu / 512M, maxmemory yox | **2 cpu / 4G** + `maxmemory 3gb` + `noeviction` + `io-threads 4` (OOM-kill → sessiya itkisinin qarşısını alır) |
| pgbouncer | 0.5 cpu, pool 40 | **1 cpu / 512M**, pool 150, reserve 50, max_client 2000 (POOL_MODE=session saxlanılıb — bax §5) |
| nginx | 0.5 cpu / 256M | **4 cpu / 512M** |
| replicas (`remote_deploy.sh`) | default 1 | **default 8** (app), 2 (celery) |
| app healthcheck | `/health/` (DB), timeout 5/10s, start 30s | `/ping/` (yüngül), timeout 18/20s, start 120s → yük altında saxta-unhealthy yox |

## 4. Bu 80-nüvəli server üçün .env (maksimum 5000 həcmi)

`.env` faylı `github-runner`-ə məxsusdur (root/sudo ilə redaktə et). Deploy defaultları da yaxşıdır, amma tam 5000 həcmi üçün:

```bash
APP_REPLICAS=12            # 12 × 12 thread = 144 eyni-anlı sync slot
APP_CPU_LIMIT=4.0
ASGI_THREADS=12
CELERY_REPLICAS=2
CELERY_WORKER_CONCURRENCY=4
POSTGRES_CPU_LIMIT=16
POSTGRES_MEM_LIMIT=20480M
POSTGRES_SHARED_BUFFERS=15GB
POSTGRES_EFFECTIVE_CACHE_SIZE=40GB
POSTGRES_WORK_MEM=32MB
POSTGRES_MAX_CONNECTIONS=400
PGBOUNCER_DEFAULT_POOL_SIZE=200
PGBOUNCER_CPU_LIMIT=1.0
REDIS_CPU_LIMIT=2.0
REDIS_MEM_LIMIT=4096M
NGINX_CPU_LIMIT=4.0
```

**Deploy:** normal CD (main-ə merge) VƏ YA serverdə:
`cd ~/EducationManagementStudentArena && sudo docker compose -f docker-compose.prod.yml up -d`
(app tier qısa recreate olur; `.env` dəyişiklikləri və yeni limitlər tətbiq olunur).

## 5. Əsl 5000 həlli: pgbouncer transaction pooling (P0)

Session rejimində tavan ≈ pool ölçüsü (~300 eyni-anlı DB sorğusu). Sinxron imtahan-başlanğıcı bunu keçir. **Transaction pooling** tavanı qaldırır və kodda **artıq hazırdır** (`RLS_TRANSACTION_SCOPED` bayrağı, default OFF: SET LOCAL, worker/celery/channels sarğısı, testlər, CI gate).

**Amma aktivləşdirməzdən əvvəl 1 P0 kod boşluğu düzəlməlidir:**
- `apps/organizations/middleware.py:119–234` — üzvlük həlli view-dən (atomic-dən) əvvəl `bypass_rls()` (session `SET`) işlədir. Transaction rejimində bu (a) org həllini pozur, (b) **tenant-lər arası data sızması** yaradır (P0 təhlükəsizlik).
- **Fix:** həmin blok bayraq aktivdirsə `with transaction.atomic():` içinə alınmalı (helper-lər `in_atomic_block`-u avtomatik görüb SET LOCAL-a keçir).
- Sonra: real pgbouncer (transaction mode) ilə staging validasiya + iki-tenant login-yolu təkrar-istifadə testi (CI gate direct-Postgres olduğu üçün bunu tutmur).
- Aktivləşdir: `PGBOUNCER_POOL_MODE=transaction` + `RLS_TRANSACTION_SCOPED=1`. Rollback ani: hər ikisini geri qaytar.

Detallar: `docs/performance/FAZA2_3B_TRANSACTION_POOLING.md`.

## 6. k6 stress test alətləri (`k6/`)

- `run-ladder.sh <scenario> <VU_ENV> <label>` — 50→1000 ladder, per-pillə JSON + markdown + server yükü.
- `login-load-test.js`, `dashboard-navigation-test.js`, `full-exam-flow-test.js`, `mixed-realistic-load-test.js`, `final-exam-center-test.js`.
- **Yeni:** `websocket-load-test.js` (canlı proctor WS: `/ws/exams/supervision/<attempt_id>/`), `herd-submit-test.js` (deadline eyni-anlı submit), `exam-day-5000-test.js` (login+dashboard+exam+autosave qarışıq, ramping-vus).
- Hədəf: `BASE_URL=https://10.0.2.42 K6_INSECURE_SKIP_TLS_VERIFY=true K6_USERS_FILE=$(pwd)/k6/data/stress-users.json`.
- Test istifadəçiləri: `seed_stress_test --students 1000` → `stress_student_001..1000` / `StressTest2026!`. Student login: `/accounts/login/telebe/`.

## 7. Deploy-dan SONRA təkrar edilməli testlər (server qayıdanda)

1. `login` ladder (deploy sonrası) — 96–144 slot ilə tavanı təsdiqlə.
2. `dashboard` ladder (əvvəlki run şəbəkə qopması ilə pozuldu — təkrar).
3. `exam-day-5000-test.js` (dedik imtahan yaradılıb `K6_TEST_EXAM_SLUG` verildikdən sonra, `K6_CONFIRM_DESTRUCTIVE_EXAM_FLOW=true`).
4. `websocket-load-test.js K6_PROFILE=ws-1000` — canlı proctor WS həcmi.
5. Autosave yükü (exam-flow) — imtahan günü ~170–500 write/s.

## 8. Prioritetləşmə

- **P0 (dəmər/tətbiq):** ✅ CPU limitləri (canlı + repo default). Deploy et → 8 replika × 12 thread.
- **P0 (əsl 5000):** transaction pooling + middleware atomic() fix (§5).
- **P1:** postgres/redis/pgbouncer/nginx limitləri (repo default ✅), healthcheck (✅), .env tuning (§4).
- **P2:** hot-path kod auditi — tamamlandı (aşağı §9-10).

## 9. Kod/settings/migration — TƏTBİQ olundu (bu sessiya, `manage.py check` + `sqlmigrate` ilə doğrulanmış)

| Dəyişiklik | Fayl | Təsir |
|---|---|---|
| **PASSWORD_HASHERS** = PBKDF2 600k (Django 5.2 default 1M idi) | `core/hashers.py` + `config/settings/production.py` | Kütləvi login CPU **-40%**; köhnə hash-lar işləyir, avtomatik re-hash. (Argon2 daha yaxşı — argon2-cffi + rebuild lazım.) |
| **Redis cache socket timeout** (2s) + pool bound | `config/settings/components/celery_cache.py` | Redis yavaşlayanda sonsuz hang YOX (sessiya/lock/rate-limit hamısı bu alias-dadır) — fail-fast. **Qeyd:** built-in RedisCache kiçik-hərfli redis-py kwarg-ları istəyir. |
| **CHANNEL_LAYERS** capacity=1500, expiry=20 | `celery_cache.py` | 5000 WS proctor fan-out buferi + köhnə event-lərin təmizlənməsi |
| **EXAM_START_GLOBAL 12→200, PER_EXAM 6→100** | `exam.py` + `docker-compose.prod.yml` | Eyni-anlı imtahan başlanğıcı: 12 yerinə 200 tələbə eyni anda start edə bilir (pool 150-yə uyğun) |
| **Migration 0057**: 4 ExamAttempt indeksi | `apps/exams/migrations/0057_*` + `apps/exams/domain/attempts.py` | 60s Celery sweep-lər (partial idx) + canlı proctor monitor (`exam,started_at`) + flagged (`exam,-violation_count`) — bütün cədvəl taraması aradan qalxır |

## 10. Backlog — DƏQİQ düzəlişlər (sınanmış rollout lazım; server bu sessiyada offline idi)

**P0:**
- **RLS predicate `::text` cast** (`apps/organizations/migrations/0003_rls_policies.py:39`): `organization_id::text = ...` HƏR sorğunun org filtrində UUID indeksini yararsız edir (seq scan). Fix: policy-ləri `organization_id = NULLIF(current_setting('app.current_org_id',true),'')::uuid` ilə yenidən yarat. **Ən böyük DB qazancı** — amma təhlükəsizlik migrasiyası, sınaqla.
- **Exam-start FAIL-FAST** (`apps/exams/services/attempts.py:124-176`): bloklananda `sleep`-lə 30s sync thread tutur. Fix: dərhal 503 + client-side retry (jitter) qaytar, thread-i tutma.
- **Login `UPPER() iexact`** (`apps/accounts/backends.py:26`): `Q(username__iexact) | Q(email__iexact)` unique b-tree indeksini işlətmir. Fix: `CREATE INDEX CONCURRENTLY ... (UPPER(username))` + email (functional indekslər, migrasiya).
- **ASGI per-consumer `ThreadSensitiveContext`** (`apps/exams/consumers.py`): WS DB çağırışları bir thread-ə serializasiya olur. Fix: hər consumer öz `ThreadSensitiveContext()`-i ilə (HTTP yolu artıq belədir).
- **Çatışmayan indekslər**: `ExamRoomComputer(organization,mac_address)` + `(organization,is_active)` (`final_center.py:260`); `Membership(user,organization,is_active)` (`organizations/models.py:555`).

**P1:**
- **nginx**: (a) `set $emsarena_app`+variable `proxy_pass` → static `upstream {server app:8000; keepalive 64;}` (hər sorğuda yeni TCP handshake-i aradan qaldırır; CI konfiqi artıq belədir); (b) `Connection "upgrade"` hardcoded → `map $http_upgrade $connection_upgrade` (plain HTTP-ni pozur + keepalive-i bloklayır); (c) `nginx-main.conf` mount et — `worker_processes 8` (NGINX_CPU_LIMIT-ə uyğun, 80 yerinə) + `worker_connections 16384` + `worker_rlimit_nofile 65536`; (d) `APP_REPLICAS` 20-24 (5000 WS-i ~200/replika-ya yay).
- **RequestQueueMiddleware** (`core/middleware.py:157`): autosave-i 8-slotluq global semaphore-a salır + 3 Redis round-trip. Fix: `/exams/` prefiksini `REQUEST_QUEUE_EXCLUDED_PATH_PREFIXES`-ə əlavə et (autosave idempotent upsert-dir).
- **AUTHENTICATION_BACKENDS** (`security.py:148`): ölü `ModelBackend` (hər uğursuz login-də əlavə sorğu) sil.
- **bump_autosave_revision** (`_helpers.py:124`): `F()+1`-dən sonra `refresh_from_db` (əlavə SELECT) → sətir kilidlidir, Python-da increment et.
- **/exams/assigned N+1** (`lists.py:302`): hər kart üçün `attempts_left_for`+`can_user_start` yenidən sorğu — annotate/batch.
- **Celery**: ağır işləri (`run_text_extraction_job`, AI, export) ayrı `heavy` queue-ya route et; `CELERY_TASK_IGNORE_RESULT=True` (noeviction altında result backend şişməsin).

**P2:** M2M `.set()` → `add/remove` diff; `prefetch("files")` yalnız written/coding exam üçün; final-state poll `refresh_from_db` şərti; cache dogpile jitter (`core/cache.py`); TLS session cache 50m + `gzip_comp_level 4`; WS client heartbeat < `proxy_read_timeout 900s` təsdiqlə.

_Transaction pooling (§5) tətbiq olunanda P1 pgbouncer sizing + middleware `atomic()` fix birlikdə gəlməlidir._

## 11. Frontend / Reporting / Media auditi (backlog — dəqiq düzəlişlər)

**Frontend / static / şablon:**
- **P0** N+1: `_build_exam_items` (`apps/exams/views/student/lists.py:302`) hər kart üçün `attempts_left_for()` çağırır (COUNT + grant + stale-expiry), halbuki `_annotate_exam_list_base` (lists.py:266) həmin sayları SQL-də hesablayıb. Fix: annotasiya sahələrindən arifmetika (`max_attempts + extra_grant - finished_count`); `attempts_left_for`-u yalnız tək-imtahan start axınında saxla. _(2 agent müstəqil təsdiqlədi.)_
- **P1** `/jsi18n/` (`config/urls.py:62`) hər səhifədə cache-siz, tam middleware stack-dən keçir. Fix: `cache_page` + `cache_control` — **DİQQƏT: dilə görə Vary et** (yoxsa dil qarışar).
- **P2**: navbar `notif_count` iki dəfə sorğulanır; heç yerdə `{% cache %}` fragment yoxdur (navbar 440 sətir hər request render); hot səhifələr ~28-40 bundle-olunmamış CSS/JS; FontAwesome tam yüklənir (inline SVG varkən); WhiteNoiseMiddleware nginx-first-də ölüdür.

**Reporting / statistika / jurnal:**
- **P0** Canlı monitor snapshot (`supervision/monitor.py:227`, `exam_live_monitor_poll_api`) hər poll-da COUNT DISTINCT JOIN yenidən hesablanır — proctorlar durmadan poll edir. Fix: Redis-də 3-5s cache (exam_id,date) VƏ YA answer-save-də materialized counter.
- **P1** appeals GROUP BY tələsi (`appeals/views/teacher/endpoints.py:144`): `.order_by()` təmizlənməlidir annotate-dən əvvəl (sibling statistics.py-də artıq düzəlib) — yaddaşdakı Meta.ordering tələsi.
- **P1** `teacher_exam_statistics` (`statistics.py:149`) tam attempt siyahısını materializə edir → DB `.aggregate()` + qısa cache.
- **P2** admin `list_select_related` (ExamAttempt/Answer/Coding); statistika selektorlarında Python loop → `TruncMonth`/`Avg` DB aggregate.

**Media / PDF-OCR / export:**
- **P0** Protected media FileField axtarışları indekssiz (`core/media_views.py:100`) — `db_index=True` / `CREATE INDEX CONCURRENTLY` (examanswerfile.file, paint_image, submission-lar).
- **P0** Protected media cache tam söndürülüb (`media_views.py:421`, nginx:124) — dəyişməz məzmun (question_media, exam_uploads) hər dəfə Django auth-dan keçir. Fix: immutable prefikslərə `private, max-age=86400, immutable`.
- **P0** AI qiymətləndirmə (`ai_grading.py:364`) request içində SİNXRON xarici API çağırışı (base64 payload). Fix: mövcud `TextExtractionJob`/Celery pattern-inə keçir + poll.
- **P1** Sinxron toplu Excel export (`exam_center/statistics.py:214`) async pattern-dən kənar → `export_registry` + `EXPORT_SYNC_MAX_ROWS` həddi. Base64 dublikat saxlama (`utils.py:72` `paint_data_url`) yazı baytlarını ikiqat edir → sil.

## 12. Audit əhatəsi — TAM (10 istiqamət)

| # | İstiqamət | Status |
|---|---|---|
| 1 | Docker resurs planı (bütün servislər) | ✅ audit + **tətbiq** |
| 2 | Django settings / per-request pipeline | ✅ audit + **tətbiq (P0-lar)** |
| 3 | nginx konfiqurasiyası | ✅ audit (backlog) |
| 4 | Hot-path kod N+1/query (login/exam/autosave/final) | ✅ audit (backlog) |
| 5 | ASGI / daphne / channels / WebSocket | ✅ audit (backlog) |
| 6 | DB sxem / indekslər | ✅ audit + **tətbiq (ExamAttempt mig 0057)** |
| 7 | Celery / periodic / cache | ✅ audit (backlog) |
| 8 | pgbouncer / RLS transaction pooling | ✅ audit (yol + P0 fix) |
| 9 | Frontend / static / şablon | ✅ audit (backlog) |
| 10 | Reporting / statistika / jurnal / media-OCR-export | ✅ audit (backlog) |

## 13. Sonrakı tətbiqlər (batch 2)

- **Migration 0058 + 0024**: `ExamRoomComputer(organization,mac_address)` + `(organization,is_active)` (final-giriş MAC gate P0) və `Membership(user,organization,is_active)` (per-request üzvlük həlli) indeksləri. ✅ tətbiq + doğrulandı.
- **⚠️ N+1 (`lists.py:302`) blind DÜZƏLDİLMƏDİ**: memory `attempt_limit_and_live_monitoring` — *"attempts_left_for grant-aware həqiqət mənbəyidir, xam saylardan yenidən hesablama"*. Annotasiya grant məntiqini (əlavə qrant, reset və s.) TAM güzgüləyib testlə təsdiqlənməlidir; sadə arifmetika səhv nəticə verər. Test + server ilə gedəcək.
