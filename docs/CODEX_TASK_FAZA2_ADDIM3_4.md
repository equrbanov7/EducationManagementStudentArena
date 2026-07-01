# Codex Task — Faza 2 / Mərhələ 3B: Addım 3 (wiring) + Addım 4 (staging validation)

> Bu sənəd Codex-ə (və ya başqa AI agentinə) birbaşa verilmək üçün hazırlanıb.
> Özü-yetərlidir. Əvvəlcə `AGENTS.md` və `docs/FAZA2_3B_TRANSACTION_POOLING.md`
> oxu. **Tenant izolyasiyası bu layihənin #1 invariantıdır — hər addımda qoru.**

## Kontekst (artıq hazır olan)

PgBouncer transaction-pooling-ə keçid üçün infrastruktur qoyulub, **flaq default
OFF** (`RLS_TRANSACTION_SCOPED`, `config/settings/production.py`):

- `core/rls_pooling.py`:
  - `RLSTransactionGuard` — request transaction-ı daxilində `SET LOCAL` ilə RLS
    tətbiq edən `execute_wrapper` (artıq `apps/organizations/middleware.py`-da
    flaq arxasında qoşulub).
  - `rls_worker_atomic()` — request-dən kənar DB işləri üçün kontekst meneceri:
    flaq açıq → `transaction.atomic()` ilə sarıyır; off → no-op.
- Testlər: `core/tests/test_rls_pooling.py` (10 control-flow testi).

Səbəb: PgBouncer transaction-mode-da bağlantı hər transaction-dan sonra qaytarılır;
session GUC itər. RLS `SET LOCAL` ilə hər transaction daxilində qoyulmalıdır.
`core.rls` köməkçiləri `connection.in_atomic_block` olduqda avtomatik `SET LOCAL`
işlədir — ona görə worker yollarında tək tələb DB işini atomic-ə salmaqdır.

---

## ADDIM 3 — `rls_worker_atomic()`-i çağırış nöqtələrinə yerləşdir (wiring)

**Məqsəd:** Channels consumer-ləri və Celery task-larındakı RLS-qorunan DB
bloklarını `rls_worker_atomic()` ilə sar ki, flaq açıq olduqda RLS `SET LOCAL`
ilə transaction-local olsun. **Flaq OFF olduğu üçün davranış DƏYİŞMƏMƏLİDİR.**

### 3.1 Channels — `apps/live_exam/consumers.py` və `apps/live_exam/auth.py`

Hər `@database_sync_to_async` metodunda (məs. `_get_lobby_state`,
`_get_answer_progress`, `_get_reveal_payload`, `_get_player_reveal_payload`,
`_save_answer_and_score`, `connect`-dəki DB işi) və `auth.py`-dakı `bypass_rls()`
bloklarında DB sorğularını sar:

```python
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

@database_sync_to_async
def _save_answer_and_score(self, ...):
    with rls_worker_atomic(), bypass_rls():   # mövcud bypass_rls() saxlanılır
        ...mövcud DB sorğuları...
```

- Mövcud `bypass_rls()`/`set_rls_tenant()` çağırışlarını **saxla** — yalnız
  onları (və onların DB sorğularını) `rls_worker_atomic()` ilə əlavə olaraq sar.
- Əgər metod org-scoped işləyirsə (bypass deyil), `set_rls_tenant(org_id,
  local=True)`-ı `rls_worker_atomic()` daxilində çağır.

### 3.2 Celery — `core/tasks.py`, `core/email_tasks.py`, `apps/exams/tasks.py`

RLS-qorunan cədvələ toxunan hər task gövdəsini sar. Nümunə —
`core/tasks.py: export_exam_results_csv` (`LiveSession.objects...`),
`warm_session_settings_cache`, `apps/exams/tasks.py: expire_stale_resumed_attempts`:

```python
from core.rls_pooling import rls_worker_atomic

@shared_task(...)
def export_exam_results_csv(*, exam_pk, recipient_email):
    with rls_worker_atomic():
        # superadmin/sistem işi → bypass_rls(); tenant-scoped → set_rls_tenant(org_id, local=True)
        ...mövcud sorğular...
```

- Hər task üçün müəyyən et: superadmin/sistem-geniş işdir (→ `bypass_rls()`),
  yoxsa konkret tenant-a aiddir (→ `set_rls_tenant(org_id, local=True)`). Task
  arqumentlərindən org_id-ni götür; yoxdursa `bypass_rls()` istifadə et və bunu
  şərh ilə əsaslandır.
- Sırf email göndərən, DB-yə toxunmayan task-ları (məs. təmiz SMTP) DƏYİŞMƏ.

### 3.3 Qəbul meyarları (Addım 3)

1. **Flaq OFF (default) davranış dəyişməz:** bütün mövcud testlər keçməli.
   ```
   DATABASE_URL="sqlite://" pytest apps/live_exam core -m "not postgres" --no-migrations -p no:cacheprovider
   ```
2. `rls_worker_atomic()` flaq-off-da no-op olduğu üçün heç bir yeni transaction
   açılmamalı (mövcud autocommit davranışı qalır).
3. `black --check . && isort --check-only --profile black . && flake8 .` təmiz.
4. `python scripts/check_module_size.py --check` keçməli (fayllar böyüməsin —
   lazım gələrsə alt-modula çıxar).
5. Hər consumer metodu / task üçün `bypass` yoxsa `tenant` qərarı şərhdə yazılsın.

---

## ADDIM 4 — Staging validasiyası (flaq ON, PostgreSQL + transaction pooling)

**Bu addım staging mühitində icra olunur** (PostgreSQL + PgBouncer). Lokal/CI-də
yalnız `-m postgres` testləri PostgreSQL servisi ilə işlədilə bilər.

### 4.1 Cross-tenant izolyasiya testləri (transaction-mode altında) — YENİ

`apps/organizations/tests/test_rls_transaction_pooling.py` yarat (`@pytest.mark.postgres`):

- `override_settings(RLS_TRANSACTION_SCOPED=True)` + `ATOMIC_REQUESTS=True`
  ekvivalenti altında:
  1. **Connection-reuse simulyasiyası:** A tenant-ı üçün request → sonra B
     tenant-ı üçün request (eyni backend bağlantısı təkrar istifadə). B heç vaxt
     A-nın sətirlərini görməməli; A-nın GUC-ları B transaction-ında qalmamalı.
  2. **Worker yolu:** `rls_worker_atomic()` + `set_rls_tenant(A)` daxilində
     sorğu yalnız A datasını qaytarmalı; blokdan sonra GUC itməli (SET LOCAL).
  3. **Fail-closed:** org konteksti olmadan (no tenant) RLS-qorunan sorğu boş
     qaytarmalı (deny-all).
- Mövcud RLS paketi transaction mode-da tam keçməli:
  ```
  pytest -m postgres apps/organizations/tests/test_rls.py apps/organizations/tests/test_tenant_isolation.py
  ```

### 4.2 k6 load testi

- `k6/` qovluğundakı mövcud dashboard/exam ssenarisini istifadə et.
- Staging-də: `RLS_TRANSACTION_SCOPED=1`, PgBouncer `POOL_MODE=transaction`,
  `DEFAULT_POOL_SIZE` Postgres `max_connections` daxilində.
- Hədəf: 500+ VU dashboard — p95 hədəf daxilində, HTTP error ~0%, pool tükənməsi
  yoxdur. Session-mode baseline ilə müqayisə et (əvvəl ~29% error, p95 ~60s).

### 4.3 Channels + Celery cross-tenant (staging)

- İki tenant-ın eyni vaxtda canlı imtahanı: bir consumer digərinin sessiya/cavab
  datasını görməməli.
- Celery: tenant-A task-ı tenant-B datasına toxunmamalı.

### 4.4 Rollout gating

Yalnız 4.1–4.3 yaşıl olduqda:
1. Staging-də `RLS_TRANSACTION_SCOPED=1` + PgBouncer `transaction` — müşahidə.
2. Production canary (kiçik faiz) → metrik müşahidəsi → tam rollout.
3. **Ani rollback:** `RLS_TRANSACTION_SCOPED=0` + PgBouncer `POOL_MODE=session`.

### 4.5 Qəbul meyarları (Addım 4)

- `pytest -m postgres` (RLS + yeni transaction-pooling testləri) tam yaşıl.
- k6 500+ VU stabil, error ~0%, cross-tenant sızma YOX.
- Rollback proseduru sənədləşdirilib və sınanıb.

---

## Toxunulmamalı / diqqət

- `core/rls.py`-ın mövcud `local` semantikasını dəyişmə (artıq düzgündür).
- Flaq default OFF qalmalı; production-da yalnız staging validasiyasından sonra
  açılır.
- `server_reset_query` (PgBouncer) transaction mode-da GUC-ları sıfırlamağa
  çalışmasın — `SET LOCAL` onsuz da transaction sonunda itir.
