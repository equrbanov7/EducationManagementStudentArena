# Codex üçün yenidən-audit tapşırığı — 2026-07-11 düzəlişlərinin verifikasiyası + performans

**Bu sənəd Codex-ə verilir.** Məqsəd: 2026-07-11 tam auditindən sonra edilən
düzəlişlərin **həqiqətən işlədiyini müstəqil təsdiqləmək**, açıq qalan
tapıntıların statusunu yoxlamaq və **performansı ölçmək** (əvvəlki auditdə
sübut yox idi).

- Əsas audit: [EMSArena_End_to_End_Audit_AZ_2026-07-11.md](./EMSArena_End_to_End_Audit_AZ_2026-07-11.md)
- Nə düzəldildi (iddia): [FIX_REPORT_2026-07-11.md](./FIX_REPORT_2026-07-11.md)
- Prinsip: **iddiaya inanma, koddan və icradan yoxla.** Hər "HƏLL EDİLDİ" üçün
  regresiya/istismar ssenarisi qur; keçmirsə açıq say.

---

## A. Düzəldiyi iddia edilən tapıntıları TƏSDİQLƏ

Hər biri üçün: (1) düzəlişin kodda olduğunu gör, (2) müsbət test yaz/işə sal,
(3) **bypass cəhdi** et — köhnə hücum hələ də işləyirsə düzəliş natamamdır.

| ID | İddia | Verifikasiya nöqtəsi | Bypass cəhdi |
|---|---|---|---|
| EXAM-P0-01 | Non-superuser app DB rolu | `apps/organizations/checks.py`, `scripts/provision-app-db-role.sh`, compose `DATABASE_URL`/`MIGRATION_DATABASE_URL` | **Prod-da faktiki qoşulan rol hələ superuser ola bilər** — `SELECT current_user, rolsuper, rolbypassrls`. Server addımı atılmayıbsa tapıntı AÇIQ qalır. |
| EXAM-P0-02 | 14 exam cədvəlinə RLS | migration `organizations/0017`; `apps/organizations/tests/test_rls.py::TestRLSExamGapTables` | Non-superuser rol + tenant B kontekstində tenant A-nın `codingsubmission`/`examstudentpin`/`supervisionincident` sətrini oxu/dəyiş — 0 sətir olmalı. |
| EXAM-P0-03 | Seçim snapshot-u (qismən) | `ExamAnswer.selected_option_ids_snapshot` (mig 0045), `result_calculation.py` | Variantı delete/recreate et → keçmiş bal dəyişməməli. **Qeyd:** sual mətni/media/variant mətni HƏLƏ dondurulmayıb — bunu açıq say. |
| EXAM-P0-04 | Manual grading trust | `_attempt_views.py`, `_answer_max_points` | POST-a `max_points_*=100000` və `score=99999` göndər → `ExamQuestion.points` dəyişməməli, bal snapshot-max-a clamp olmalı. `ai_grade_answer`-ə də `max_points` göndər. |
| EXAM-P0-05 | Nəticə/cavab release kilidi | `views/student/results.py::_exam_answers_release_locked` | `end_datetime` gələcəkdə ikən nəticə səhifəsində düzgün variant/verdikt/ideal cavab görünməməli. Reload, fərqli tələbə, `?` parametr manipulyasiyası ilə cəhd et. |
| EXAM-P1-02/03 | Archive/delete + public exclusion | `domain/access_policy.py` | Arxiv/soft-deleted imtahana birbaşa start URL; public imtahanda excluded user; aktiv cəhdi olan excluded user davam. Hamısı bloklu olmalı. |
| EXAM-P1-10 | Supervision incident payload | `views/teacher/supervision/monitor.py::log_incident_api` | 100 ardıcıl POST → 429; nested/5000-simvol metadata → sanitizasiya; naməlum event_type → 400. |
| EXAM-P1-12 | Live late-join | `live_exam/views/player/join.py` | Sessiya `question`/`finished` state-də ikən YENİ oyunçu join → 403; mövcud oyunçu reconnect → 200. |
| EXAM-P1-13 | Coding final idempotency | mig `exams/0046` partial unique + `coding_submit` row lock | Eyni attempt-ə paralel/təkrar submit → yalnız 1 `is_final=True` sətir. Postgres-də `\d+ exams_codingsubmission` ilə partial unique index-i təsdiqlə. |
| PROXY-P0 | Nginx XFF hardening (CF yoxdur) | `docker/nginx/nginx.conf` | Origin-ə birbaşa `X-Forwarded-For: 1.2.3.4` göndər → Django `get_client_ip` bunu QƏBUL ETMƏMƏLİ (nginx overwrite edir). Rate-limit/allowlist spoof cəhdi. |
| CI-P1 | docker/scan/smoke/E2E blocking | `.github/workflows/ci.yml` ci-success | Job-lardan biri fail olanda `ci-success`-in də fail olduğunu (deploy getmədiyini) təsdiqlə. |

**Regresiya bazası (təkrar işə sal):**
```
# SQLite (E2E xaric) — gözlənilən: ~2831 passed
DATABASE_URL="sqlite:///$PWD/tmp.db" pytest --ignore=tests/e2e --no-migrations -m "not postgres"
# Postgres RLS (real Postgres 16 konteyner) — gözlənilən: 40 passed
DATABASE_URL=postgres://…/… pytest apps/organizations/tests/test_rls.py -m postgres
# Migration qrafı təmizliyi
python manage.py makemigrations --check --dry-run
```

---

## B. Açıq qalan tapıntıların statusunu TƏSDİQLƏ (hələ düzəlməyib)

Bunlar bilərəkdən bu dalğada edilmədi — hələ də açıq olduğunu təsdiqlə və
riski yenidən qiymətləndir:

**Exam:** EXAM-P1-01 (formal state machine yox), P1-04 (per-question timer
client-only), P1-05 (disabled field payload-dan düşür), P1-06 (autosave server
OCC yox), P1-07 (draft plaintext localStorage), P1-08 (PIN lifecycle:
expiry/revoke/one-use yox), P1-09 (ümumi access code plaintext), P1-11 (client
telemetry proctoring zəif), P1-15 (import crash lease/retry), P1-16 (3s sonra
sync OCR/AI fallback), P1-17 (dil variant parity validatoru yox), P1-18 (appeal
reviewer independence yox), P1-19 (hard delete CASCADE), P1-20 (exam business
SLI/monitorinq yox).

**EXAM-P0-03 qalan hissəsi:** delivered sual mətni + media hash + variant
mətni/sırası snapshot-u və nəticə render-inin tarixi vəziyyətdən aparılması.

**Layihə-wide:** RLS coverage HƏLƏ natamamdır — `accounts_userprofile`,
`ai_assistant_aiassistantlog`, `audit_auditlog`, `labs_*`,
`projects_projectsubmission` policy-siz qalıb (yalnız exam cədvəlləri
bağlandı). Həmçinin: immutable image promotion + rollback yox; assignment/
project/lab concurrency + grade clamp invariantları yox; audit log append-only/
tamper-evident deyil; off-site backup + restore drill yox; privacy/retention
schedule yox; JS/a11y/query-budget keyfiyyət gate-ləri yox.

---

## C. PERFORMANS — ölç, təxmin etmə (əvvəlki auditdə sübut yox idi)

Əsas boşluq: `docs/performance/FAZA4_BASELINE_RESULTS.md` boşdur, k6 ssenariləri
default 1 VU-dur, `scripts/stress_exam_capacity.sh` yalnız `/ping`+`/health`
vurur. Aşağıdakıları FAKTİKİ ölçü ilə doldur:

### C.1. Yük testi (HTTP + WebSocket)
- Real imtahan yolunu yüklə: PIN giriş → attempt start → question fetch →
  autosave → submit → result. Yalnız health endpoint yox.
- Profil: 100 VU × 30 dəq (steady), 500 VU × 15 dəq, 1000 VU qısa spike, 1 saat soak.
- WebSocket: supervision + live + final-center üçün 1000 paralel bağlantı,
  reconnect storm, Redis pub/sub gecikməsi.
- Hesabla: p50/p95/p99 latency, error rate, throughput, DB connection sayı,
  PgBouncer pool doyması, Redis latency, Celery queue lag, **data-loss
  invariantı** (autosave/submit itkisi olmamalı).

### C.2. Query-budget / N+1 (audit N+1 riski qeyd etmişdi)
- `assertNumQueries` və ya django-debug-toolbar/silk ilə ölç:
  - `exam_result` səhifəsi (indi selected_option_ids_snapshot oxuyur),
  - `teacher_view_attempt` / grading səhifəsi,
  - registrar `compute_final_result` offering list-i (audit N+1 şübhəsi),
  - accounts dashboard hub.
- Yeni əlavələrin regresiya yaratmadığını təsdiqlə: RLS migration 0017-nin
  subquery policy-ləri (coding/incident/M2M) SELECT planına EXPLAIN ANALYZE ilə
  bax — seq scan yox, index istifadə olunurmu?

### C.3. Yeni düzəlişlərin performans təsiri
- **RLS gap policy-ləri (0017):** hər tenant sorğusuna əlavə subquery gəlir —
  `codingsubmission`, `supervisionincident`, join cədvəllərində EXPLAIN ilə
  overhead-i ölç.
- **Coding partial unique index (0046):** submit yolunda əlavə index write.
- **selected_option_ids_snapshot (0045):** autosave-də əlavə JSONField write;
  result hesablamada JSON parse.
- **Supervision rate-limit:** hər incident-də əlavə cache round-trip.

### C.4. Coding sandbox (prod-da disabled, amma aktivləşdirmə üçün)
- Global executor semaphore, queue depth, memory/backpressure limiti ölç;
  audit "output limitsiz yığılır" (P1-14) demişdi — worker memory exhaustion
  ssenarisini yoxla.

**Nəticə formatı:** `docs/performance/FAZA4_BASELINE_RESULTS.md`-ı ölçülmüş
rəqəmlərlə doldur (VU, p95/p99, error rate, DB/Redis/queue metrikaları,
EXPLAIN çıxışları). "500 VU collapse" kimi sənədləşdirilmiş iddiaları faktiki
ölçü ilə təsdiqlə və ya təkzib et.

---

## D. Yekun tələb

Codex hesabatı bunları versin:
1. Hər "HƏLL EDİLDİ" tapıntı üçün: **TƏSDİQLƏNDİ / NATAMAM / REQRESSIYA** +
   sübut (test adı, EXPLAIN, log).
2. Açıq tapıntılar üçün: yenilənmiş risk qiyməti.
3. Performans: C bölməsindəki faktiki rəqəmlər + darboğaz siyahısı.
4. Yenilənmiş imtahan sistemi balı və layihə balı (əvvəl 43/100 və 58/100 idi).
