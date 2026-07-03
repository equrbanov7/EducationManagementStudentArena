# Faza 2 / Mərhələ 3B — PgBouncer Transaction Pooling + RLS (icraya-hazır spesifikasiya)

> **Status:** Config scaffolding (`RLS_TRANSACTION_SCOPED` flaqı, default
> **OFF**), request guard və Channels/Celery wiring tətbiq olunub. Production-da
> flaqın açılması yalnız staging-də cross-tenant + k6 load testindən sonra
> edilməlidir.
>
> Əsas kontekst: [`EMSArena_Performans_Icra_Plani_2026-06-08.md`](../../EMSArena_Performans_Icra_Plani_2026-06-08.md) (Mərhələ 3B).

## 1. Problem

RLS tenant konteksti (`app.current_org_id`, `app.current_user_id`,
`app.bypass_rls`) hazırda `OrganizationMiddleware`-də **session GUC** kimi
qoyulur (atomik blokdan kənarda → `SET`, `SET LOCAL` deyil). PgBouncer
**session pooling** rejimi bunu işlədir, çünki hər client bütün sessiya boyu
eyni backend bağlantısını saxlayır.

**Niyə transaction pooling-ə keçmək istəyirik:** session mode-da
`DEFAULT_POOL_SIZE` qədər backend slot var; 500 VU-da pool tükənir, p95 ~60s,
xəta ~29%. Transaction mode bir neçə on backend bağlantısının yüzlərlə client-ə
xidmət etməsinə imkan verir.

**Niyə sadəlövh keçid TƏHLÜKƏLİDİR:** transaction mode-da bağlantı hər
transaction-dan sonra hovuza qaytarılır. Session GUC növbəti transaction-da
itər → RLS **yanlış tenant** göstərə bilər. Bu, layihənin #1 təhlükəsizlik
invariantını (tenant izolyasiyası) pozar.

## 2. Həll prinsipi

RLS konteksti hər request-in **atomik transaction-ı daxilində**, `SET LOCAL`
ilə (yəni `set_config(..., is_local=true)`) qoyulmalıdır. `core/rls.py` bunu
artıq dəstəkləyir: `_should_use_local()` `connection.in_atomic_block`-u aşkar
edib `SET LOCAL`-a keçir. Çatışmayan hissə — RLS-i atomik transaction
**başlayandan sonra, birinci sorğudan əvvəl** tətbiq etmək.

Şərtlər (hamısı birlikdə, yoxsa RLS sınar):

1. `ATOMIC_REQUESTS = True` — hər request/view bir transaction-da.
2. RLS konteksti həmin transaction daxilində `SET LOCAL` ilə qoyulsun.
3. `DISABLE_SERVER_SIDE_CURSORS = True` — transaction pooling server-side
   cursor-ları sındırır.
4. **Channels (live exam)** və **Celery** öz bağlantı dövrlərində RLS-i
   transaction daxilində idarə etsin (aşağıda 6-cı bölmə).
5. PgBouncer `POOL_MODE = transaction`.

## 3. Mexanizm — `execute_wrapper` ilə lazy SET LOCAL

`ATOMIC_REQUESTS` transaction-ı **view-u** sarıyır; middleware ondan əvvəl
işlədiyi üçün middleware-də `SET LOCAL` etmək həmin transaction-a düşməz. Ona
görə RLS konteksti transaction-ın **birinci sorğusu** ilə tətbiq olunmalıdır.
`connection.execute_wrapper` bunun üçün idealdır.

> **DİQQƏT — reentrancy:** wrapper daxilində `cursor.execute(...)` çağırmaq
> wrapper-i yenidən tetikləyir → sonsuz rekursiya. Mütləq reentrancy guard
> lazımdır.

```python
# core/rls_pooling.py  (YENİ — spesifikasiya, hələ canlı deyil)
from core.rls import _NO_TENANT, _NO_USER, _BYPASS_ON, _BYPASS_OFF


class RLSTransactionGuard:
    """Hər atomik transaction-ın BİRİNCİ sorğusundan əvvəl RLS GUC-larını
    SET LOCAL ilə tətbiq edir (PgBouncer transaction-mode təhlükəsiz).

    Per-request `OrganizationMiddleware` tərəfindən qeydiyyatdan keçirilir."""

    def __init__(self, *, user_id, org_id, bypass: bool):
        self.user_id = user_id
        self.org_id = org_id
        self.bypass = bypass

    def __call__(self, execute, sql, params, many, context):
        conn = context["connection"]
        # Yalnız PostgreSQL + atomik blok + bu transaction-da hələ tətbiq
        # olunmayıbsa. `_rls_applying` reentrancy guard-dır.
        if (
            conn.vendor == "postgresql"
            and conn.in_atomic_block
            and not getattr(conn, "_rls_txn_applied", False)
            and not getattr(conn, "_rls_applying", False)
        ):
            conn._rls_applying = True
            try:
                items = [("app.current_user_id", str(self.user_id) if self.user_id else _NO_USER)]
                if self.bypass:
                    items.append(("app.bypass_rls", _BYPASS_ON))
                else:
                    items.append(("app.bypass_rls", _BYPASS_OFF))
                    items.append(("app.current_org_id", str(self.org_id) if self.org_id else _NO_TENANT))
                select_list = ", ".join(["set_config(%s, %s, true)"] * len(items))
                flat = [x for pair in items for x in pair]
                # `execute` callable-ından istifadə edirik ki, wrapper zənciri
                # düzgün işləsin, amma reentrancy guard rekursiyanı kəsir.
                execute(f"SELECT {select_list}", flat, False, context)
                conn._rls_txn_applied = True
            finally:
                conn._rls_applying = False
        return execute(sql, params, many, context)
```

`_rls_txn_applied` bayrağı **hər transaction sonunda sıfırlanmalıdır**
(növbəti transaction yenidən tətbiq etsin):

```python
# core/rls_pooling.py (davamı)
from django.db.backends.signals import connection_created
from django.dispatch import receiver

def reset_txn_flag(connection):
    connection._rls_txn_applied = False
    connection._rls_applying = False

# Django-da transaction commit/rollback üçün birbaşa signal yoxdur; ən etibarlı
# yol — request sonunda (middleware `finally`) və hər atomic exit-də sıfırlamaq.
# Praktiki həll: ATOMIC_REQUESTS ilə hər request 1 transaction olduğundan,
# middleware `finally`-də `reset_txn_flag(connection)` çağırmaq kifayətdir.
```

`OrganizationMiddleware`-də (flaq açıq olduqda) wrapper-i qeydiyyatdan keçir:

```python
# apps/organizations/middleware.py — Step 4 əvəzinə (flaq açıq olduqda)
from django.conf import settings
from django.db import connection

if getattr(settings, "RLS_TRANSACTION_SCOPED", False):
    guard = RLSTransactionGuard(
        user_id=request.user.pk,
        org_id=request.organization.pk if request.organization else None,
        bypass=is_superuser,
    )
    cm = connection.execute_wrapper(guard)
    cm.__enter__()
    request._rls_wrapper_cm = guard_cm = cm   # finally-də __exit__
else:
    # mövcud davranış (session-scope SET)
    apply_rls_request_context(user_id=..., org_id=..., bypass=is_superuser)
```

`finally`-də:

```python
finally:
    cm = getattr(request, "_rls_wrapper_cm", None)
    if cm is not None:
        cm.__exit__(None, None, None)
        reset_txn_flag(connection)
    else:
        reset_rls_context(only_if_connection_open=True)
```

## 4. Settings (tətbiq OLUNUB — config scaffolding)

`config/settings/production.py` (və `base.py` default):

```python
RLS_TRANSACTION_SCOPED = _env_bool("RLS_TRANSACTION_SCOPED", False)
if RLS_TRANSACTION_SCOPED:
    DATABASES["default"]["ATOMIC_REQUESTS"] = True
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
```

Default **OFF** → production davranışı dəyişmir. Flaq yalnız staging
validasiyasından sonra açılır.

## 5. PgBouncer (infra, kod xaricində)

`docker-compose.prod.yml` pgbouncer servisində:

```
PGBOUNCER_POOL_MODE=transaction        # session → transaction
PGBOUNCER_DEFAULT_POOL_SIZE=...        # Postgres max_connections daxilində
PGBOUNCER_MAX_CLIENT_CONN=...          # yüksək (yüzlərlə client)
```

`server_reset_query` transaction mode-da `DISCARD ALL` olmamalıdır (və ya GUC
təmizləməsinə diqqət) — `SET LOCAL` onsuz da transaction sonunda itir.

## 6. Channels (live exam) və Celery — `rls_worker_atomic()`

`core.rls` köməkçiləri (`bypass_rls`, `set_rls_*`) `local=None` olduqda
`connection.in_atomic_block`-u avtomatik aşkarlayıb `SET LOCAL`-a keçir. Ona görə
request-response yolundan kənar DB işlərində lazım olan TƏK şey — həmin işi
`transaction.atomic()` daxilində icra etmək. Bunun üçün **hazır, flaqlı primitiv**
var: `core.rls_pooling.rls_worker_atomic()` (tətbiq OLUNUB + 10 unit test).

- Flaq açıq → `transaction.atomic()` ilə sarıyır (daxildəki RLS təyinatları
  `SET LOCAL` olur).
- Flaq off (default) → **no-op** (mövcud session-scope davranış toxunulmur).

**Channels consumer-ləri** (`apps/live_exam/consumers.py`, `auth.py`) — hər
`database_sync_to_async` DB blokunu sarı:

```python
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

@database_sync_to_async
def _load(self):
    with rls_worker_atomic(), bypass_rls():   # və ya set_rls_tenant(org_id)
        ...DB sorğuları...
```

**Celery task-ları** (`core/tasks.py`, `core/email_tasks.py`,
`apps/exams/tasks.py`) — RLS-qorunan cədvəllərə toxunan task gövdəsini sarı:

```python
with rls_worker_atomic():
    set_rls_tenant(org_id, local=True)   # və ya bypass_rls() superadmin işləri üçün
    ...DB sorğuları...
```

> **Qeyd:** `rls_worker_atomic()` primitivi, control-flow testləri və
> consumer/task wiring hazırdır. Flaq-off olduğu üçün requestdən kənar
> transaction davranışı dəyişmir; flaq-on altında düzgünlük **staging-də**
> Channels + Celery cross-tenant testləri ilə təsdiqlənməlidir.

### 6.1 Request-xarici audit statusu (2026-07-04)

Bu mərhələdə DB-yə toxunan request-xarici entrypoint-lər `rls_worker_atomic()`
ilə sarınıb:

- Celery / thread-pool: `core/email_tasks.py`, `core/tasks.py`,
  `apps/exams/tasks.py`.
- Channels/live exam: `apps/live_exam/auth.py`, `apps/live_exam/cache.py`,
  `apps/live_exam/consumers.py`.
- Signal side-effect-ləri: `apps/accounts/signals.py`,
  `apps/audit/signals.py`, `apps/blog/signals.py`,
  `apps/courses/signals.py`, `apps/notifications/signals.py`,
  `apps/organizations/signals.py`.
- Maintenance/seed command-ları: `purge_notifications`,
  `backfill_admin_memberships`, `create_sample_orgs`, `seed_ci_e2e_user`,
  `seed_ci_e2e_scenario`, `seed_group_demo_data`.

Audit qeydi: `apps/exams/consumers.py` ORM/`database_sync_to_async` çağırışı
etmir; yalnız channel-layer group subscribe/send edir, ona görə sarğı tələb
olunmadı. `apps/accounts/management/commands/create_roles.py` də DB-yə toxunmayan
deprecated no-op command-dır.

Hardening qeydi: tək-tenant signal yolları RLS-i söndürmür; mümkün olan yerlərdə
`set_rls_tenant(<object org>)` istifadə olunur (`courses.signals`,
`notifications.signals`, `organizations.signals`). `bypass_rls()` yalnız qəsdən
system-wide/global işlərdə saxlanılıb: purge/seed/backfill command-ları,
`apps/exams/tasks.py` sweep/export task-ları və blog reviewer/subscriber
siqnalları.

## 7. Test planı (MÜTLƏQ — flaq açılmadan əvvəl)

1. **Cross-tenant izolyasiya (Postgres + transaction mode):** A tenant-ı B-nin
   datasını **heç vaxt** görməsin. RLS secure-default (`_NO_TENANT` → deny-all)
   fail-closed-dur, lakin tam regress lazımdır.
2. **Connection reuse simulyasiyası:** eyni backend bağlantısının ardıcıl iki
   müxtəlif tenant request-i — ikincinin birincinin GUC-larını görməməsi.
3. **`-m postgres` RLS test paketi** transaction mode-da tam keçməli
   (`apps/organizations/tests/test_rls.py`, `test_tenant_isolation.py`).
4. **k6 500+ VU** dashboard stabil (p95 < hədəf, xəta ~0%).
5. **Channels live exam** + **Celery** cross-tenant testləri.

### 7.1 Staging validasiya runbook-u

**Mühit şərtləri**

- `RLS_TRANSACTION_SCOPED=1`
- PgBouncer `POOL_MODE=transaction`
- PgBouncer `DEFAULT_POOL_SIZE` Postgres `max_connections` daxilində
- Django DB ayarında `ATOMIC_REQUESTS=True` və `DISABLE_SERVER_SIDE_CURSORS=True`
  (`RLS_TRANSACTION_SCOPED=1` bunu production settings-də avtomatik edir)
- Staging-də ayrıca load-test user pool-u: 500 VU üçün ən azı 500 aktiv istifadəçi
  tövsiyə olunur; user reuse yalnız bilərəkdən müqayisə sınağında açılsın.

**Postgres/RLS regression**

```bash
pytest -m postgres \
  apps/organizations/tests/test_rls_transaction_pooling.py \
  apps/organizations/tests/test_rls.py \
  apps/organizations/tests/test_tenant_isolation.py
```

Qəbul: hamısı yaşıl; `test_rls_transaction_pooling.py` request reuse, worker
`SET LOCAL` və no-tenant fail-closed davranışını ayrıca yoxlayır.

**Dashboard k6 (əsas 500 VU hədəfi)**

```bash
BASE_URL="https://staging.example.com" \
K6_USERS_FILE="./secrets/staging-k6-users.json" \
DASHBOARD_VUS=500 \
DASHBOARD_DURATION="10m" \
k6 run k6/dashboard-navigation-test.js
```

Qəbul: `http_req_failed < 0.01`, dashboard p95 hədəf daxilində, pool exhaustion
və 5xx spike yoxdur.

**Mixed exam/read/autosave k6**

```bash
BASE_URL="https://staging.example.com" \
K6_USERS_FILE="./secrets/staging-k6-users.json" \
K6_TEST_EXAM_SLUG="dedicated-load-test-exam" \
TARGET_VUS=500 \
RAMP_DURATION="5m" \
HOLD_DURATION="15m" \
k6 run k6/mixed-realistic-load-test.js
```

Qəbul: `http_req_failed < 0.01`, `checks > 0.99`, normal p95 < 1500ms, exam p95
< 2500ms və DB connection pool tükənməsi yoxdur.

**Channels + Celery kross-tenant smoke**

1. Tenant A və Tenant B üçün eyni vaxtda iki live exam başladın.
2. Hər tenant-da host + player websocket-ləri qoşun.
3. Tenant A cavab/progress/reveal payload-larında Tenant B player/result datası
   görünməməlidir və əksi də belə olmalıdır.
4. Tenant A-da locked supervision attempt yaradıb periodic Celery sweep-i
   işə salın; Tenant B attempt-ləri dəyişməməlidir.

Qəbul: websocket payload-larında cross-tenant data yoxdur; Celery sweep yalnız
şərti ödənən öz attempt-lərini bitirir və incident-lər attempt-in öz
`exam.organization` dəyəri ilə yazılır.

## 8. Rollout / rollback

- **Rollout:** staging → flaq ON → testlər yaşıl → kiçik canary → tam.
- **Rollback (ani):** `RLS_TRANSACTION_SCOPED=0` + PgBouncer `POOL_MODE=session`
  → əvvəlki davranışa qayıdır (kod default-OFF olduğu üçün təhlükəsiz).

Rollback-dan sonra yoxla:

```bash
python manage.py check --deploy
pytest -m postgres apps/organizations/tests/test_rls.py apps/organizations/tests/test_tenant_isolation.py
```

Qısa müşahidə pəncərəsi: 5xx, DB connection count, PgBouncer pool wait, login
və dashboard p95 metrikləri əvvəlki session-mode baseline-a qayıtmalıdır.

## 9. İcra ardıcıllığı

1. ✅ Config scaffolding (`RLS_TRANSACTION_SCOPED`, default OFF).
2. ✅ `core/rls_pooling.py` (`RLSTransactionGuard`) + middleware inteqrasiyası
   (flaq arxasında) + 8 control-flow unit testi.
3. ✅ Channels + Celery: `rls_worker_atomic()` consumer/task çağırış
   nöqtələrinə yerləşdirilib; sistem-geniş bypass/tenant qərarları şərhlərdədir.
4. ◻️ Staging: yeni transaction-pooling postgres regression testləri +
   mövcud RLS paketi + k6 load testləri.
5. ⬜ PgBouncer `POOL_MODE=transaction` + canary → tam rollout.
