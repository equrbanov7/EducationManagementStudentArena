# FAZA 4 — Staging Rollout Runbook (P0-1 Transaction Pooling)

**Versiya:** 1.0 · **Sahib:** ops/backend · **Son yenilənmə:** 2026-07-04

> Bu runbook, `RLS_TRANSACTION_SCOPED=True` + `PGBOUNCER_POOL_MODE=transaction`-i
> STAGING mühitində təhlükəsiz aktivləşdirmək, baseline müqayisə toplamaq və
> canary → tam rollout addımlarını icra etmək üçün ADDIM-ADIM plandır.
> **Production-a bu runbook ödənməyincə keçmə.**

## 0. Ön şərtlər (rollout-a başlamazdan əvvəl)

- [ ] `main` və ya `Staging` branch-də bütün CI gate-ləri yaşıl:
  - `unit-tests-311`, `unit-tests-312`
  - `migration-tests` (MigrationExecutor geri/irəli round-trip testləri — ayrıca job, coverage-siz)
  - `rls-txn-pool` (FAZA 4/Task 3 — bu, transaction-pooling regressiyanı tutur)
  - `lint` (worker-atomic coverage daxil)
  - `docker-build`, `container-scan`
- [ ] Staging DB backup alınıb (rollback zamanı sürətli bərpa üçün).
- [ ] PagerDuty / oncall məlumatlıdır (rollout pəncərəsi 60-90 dəq).
- [ ] Grafana panelləri açıqdır:
  - Session vs transaction pool: `pgbouncer_pool_client_active`, `pgbouncer_pool_server_active`
  - Postgres: `pg_stat_activity` count, `pg_stat_activity` state=idle/active
  - App: p50/p95/p99 dashboard/exam endpoint-ləri, `http_req_failed` rate
- [ ] Staging user pool: **500 aktiv user** (k6 load testləri üçün).

## 1. Gate 1 — İzolyasiya (kritik, blocker)

### 1.1 Staging environment-də flaqları aktivləşdir

`config/settings/production.py` və ya deployment env-də:

```bash
RLS_TRANSACTION_SCOPED=1
```

`docker-compose.prod.yml` pgbouncer service üçün:

```bash
PGBOUNCER_POOL_MODE=transaction
PGBOUNCER_DEFAULT_POOL_SIZE=<Postgres max_connections-dan aşağı, adətən 25-50>
PGBOUNCER_MAX_CLIENT_CONN=1000
```

Deploy et.

### 1.2 Postgres/RLS regression suite

Staging-də tam `-m postgres` paketini işlət:

```bash
DATABASE_URL=<staging-db-url> \
RLS_TRANSACTION_SCOPED=True \
pytest -m postgres \
  apps/organizations/tests/test_rls_transaction_pooling.py \
  apps/organizations/tests/test_rls.py \
  apps/organizations/tests/test_tenant_isolation.py \
  -v --tb=short --timeout=300
```

**Qəbul kriteriyaları:**
- Bütün testlər YAŞIL (özəlliklə FAZA 4/Task 2 əlavələri: `test_five_sequential_tenants_each_isolated`, `test_worker_atomic_sequence_isolates_tenants`, `test_bypass_in_worker_atomic_does_not_persist`, `test_cross_tenant_write_denied_under_transaction_pooling`, `test_txn_applied_flag_reset_between_transactions`).
- Bir tenant test-i belə düşərsə → **STOP və rollback** (bax §5).

## 2. Gate 2 — k6 yük testi + baseline müqayisə

### 2.1 Baseline: session pool ilə çalış (referens)

Əvvəlcə `RLS_TRANSACTION_SCOPED=0` + `PGBOUNCER_POOL_MODE=session` ilə k6 baseline topla.

Hər ssenari üçün 100 → 500 → 1000 VU:

```bash
BASE_URL="https://staging.example.com" \
K6_USERS_FILE="./secrets/staging-k6-users.json" \
K6_TEST_EXAM_SLUG="dedicated-load-test-exam" \
TARGET_VUS=1000 \
RAMP_DURATION="5m" \
HOLD_DURATION="15m" \
k6 run k6/mixed-realistic-load-test.js | tee baseline_session_1000vu.log

k6 run k6/student-exam-flow-test.js  | tee baseline_session_student_1000vu.log
k6 run k6/dashboard-navigation-test.js | tee baseline_session_dashboard_1000vu.log
```

**Baseline metriklər (`docs/performance/FAZA4_BASELINE_RESULTS.md`-ə yaz):**
- `http_req_duration` p50, p95, p99
- `http_req_failed` rate
- `checks` pass rate
- PgBouncer `SHOW POOLS`: server-active, waiting client sayı
- Postgres `pg_stat_activity` count max

### 2.2 Transaction pool ilə çalış

Flaqları aktiv et (`RLS_TRANSACTION_SCOPED=1`, `PGBOUNCER_POOL_MODE=transaction`), deploy et, gözlə (~1 dəq stabilizasiya).

Eyni ssenariləri təkrar et:

```bash
k6 run k6/mixed-realistic-load-test.js | tee txnpool_1000vu.log
k6 run k6/student-exam-flow-test.js | tee txnpool_student_1000vu.log
k6 run k6/dashboard-navigation-test.js | tee txnpool_dashboard_1000vu.log
```

### 2.3 Qəbul kriteriyaları (transaction pool)

100 VU-da:
- [ ] `http_req_failed < 0.5%`
- [ ] p95 < baseline p95 × 1.1 (10% ilə uyğunlaşma)

500 VU-da:
- [ ] `http_req_failed < 1%`
- [ ] p95 < baseline p95 × 1.2
- [ ] PgBouncer waiting = 0 (transaction rejimində pool tükənmə YOXDUR)

1000 VU-da:
- [ ] `http_req_failed < 1%`
- [ ] p95 dashboard < 1500ms
- [ ] p95 exam endpoints < 2500ms
- [ ] Postgres `pg_stat_activity` count < DB max_connections × 0.8
- [ ] Session baseline (əgər 1000 VU-da tab tuta bilirdisə) ilə müqayisə: transaction pool p95 ≤ session p95

**Hər hansı gate düşərsə** → §5 rollback + issue aç.

## 3. Gate 3 — Channels + Celery cross-tenant smoke

### 3.1 Live exam websocket testi

1. Tenant A (`org-a`) və Tenant B (`org-b`) üçün eyni vaxtda iki live exam başladın.
2. Hər tenant-a 2 host + 5 player websocket qoşun.
3. Tenant A player-i cavab göndərir; Tenant A host `answer_saved` payload alır.
4. **Yoxla:** Tenant B host və Tenant B player Tenant A-nın datasını GÖRMƏMƏLİDİR.
5. Reveal stage: Tenant A reveal → yalnız Tenant A player-ləri alır.
6. Tenant A-da supervision lock → yalnız Tenant A player-i kilidlənir.

### 3.2 Celery periodic sweep

1. Tenant A üçün 3 locked supervision attempt yarat.
2. Tenant B üçün 2 locked supervision attempt yarat.
3. Celery-ni işə sal (`celery -A config worker -l info` staging-də).
4. `exams.periodic.supervision_sweep` task-ını manual trigger et.
5. **Yoxla:**
   - Tenant A-nın 3 attempt-i düzgün bitir və `exam.organization = org_a`.
   - Tenant B-nin attempt-ləri toxunulmaz qalır (öz sweep window-larına qədər).
   - `audit_log`-da hər incident-in `organization_id` düzgündür.

**Qəbul:** websocket və Celery payload-larında **sıfır** cross-tenant sızıntı.

## 4. Gate 4 — Canary rollout (production)

- [ ] Bir production replika seç (məsələn `web-1`).
- [ ] Yalnız o replikada `RLS_TRANSACTION_SCOPED=1` aktiv et.
- [ ] PgBouncer həmin replika üçün transaction mode.
- [ ] **Bir peak pəncərəsi** izlə (adətən 1-2 saat, iş saatı):
  - `http_req_failed` rate replika səviyyəsində baseline-la eyni.
  - Grafana p95 alarm-ı işə düşmür.
  - `pg_stat_activity` sağlamdır.
  - Cross-tenant leak alarm-ları yoxdur (əgər varsa: `audit_log` cross-tenant query attempts).
- [ ] Uğursuz olarsa → §5 (yalnız canary rollback: replika-səviyyəli env-i geri qaytar).

## 5. Rollback (sürətli, kod dəyişikliyi lazım deyil)

```bash
# ENV-i geri qaytar
RLS_TRANSACTION_SCOPED=0
PGBOUNCER_POOL_MODE=session
```

Deploy et. Xidmət avtomatik session-scope davranışına qayıdır (kod default OFF).

Rollback-dan sonra yoxla:

```bash
python manage.py check --deploy
pytest -m postgres apps/organizations/tests/test_rls.py apps/organizations/tests/test_tenant_isolation.py
```

Metrik pəncərəsi (session baseline-a qayıdıb-qayıtmadığını təsdiqlə):
- 5xx rate
- PgBouncer wait queue
- `pg_stat_activity` count
- Dashboard/login p95

## 6. Tam rollout (bütün production replikalar)

Canary uğurlu keçdikdən sonra:
- [ ] Bütün production replikalarına eyni vaxtda flaqları apply et (blue-green deploy tövsiyə olunur).
- [ ] İlk 24 saat peak-pəncərələri izlə (Grafana alert-lər ON).
- [ ] Bu runbook-un yekun `Nəticələr` bölməsini doldur: baseline vs transaction pool müqayisə cədvəli.

## 7. Nəticələr (doldurulacaq)

Bax: `docs/performance/FAZA4_BASELINE_RESULTS.md` (yaradıldıqdan sonra hər testin bitirməsindən sonra doldurulur).

| Test | Baseline (session) | Transaction pool | Delta |
|------|--------------------|-----------------:|-------|
| Dashboard p95 @ 500 VU | | | |
| Dashboard p95 @ 1000 VU | | | |
| Exam p95 @ 500 VU | | | |
| Exam p95 @ 1000 VU | | | |
| `http_req_failed` @ 1000 VU | | | |
| PgBouncer max waiting @ 1000 VU | | | |
| `pg_stat_activity` count @ 1000 VU | | | |

## Əlavə istinadlar

- `docs/performance/FAZA2_3B_TRANSACTION_POOLING.md` — arxitektura və mexanizm izahı
- `docs/prompts/CODEX_PROMPT_P0-1_TRANSACTION_POOLING.md` — orijinal Codex tapşırığı
- `docs/audits/FAZA4_TASK1_AUDIT.md` — request-external DB path audit
- `apps/organizations/tests/test_rls_transaction_pooling.py` — regression testləri
- `.github/workflows/_rls-txn-pool.yml` — CI gate
- `scripts/check_worker_atomic_coverage.py` — yerli/CI coverage guardı
