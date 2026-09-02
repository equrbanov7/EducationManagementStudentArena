# FAZA 28 — CI düzəlişləri (PR #119, `audit/post-migration-qa-2026-09`)

Baza: Develop `260112af` (bu job-larda YAŞIL). Aşağıdakı iki uğursuzluq bizim
branch-ın gətirdiyi reqressiyalardır.

---

## Uğursuzluq 1 — `rls-txn-pool` job-u: 9 failed + 28 errors

CI əmri: `.github/workflows/_rls-txn-pool.yml:105-119` —
`RLS_TRANSACTION_SCOPED=True pytest --ds=config.settings.test --ignore=tests/e2e -m postgres`.

### Kök səbəb (BİR ədəd)

`apps/accounts/migrations/0018_account_restore_evidence.py:36-39` —
`accounts_accountrestoreevidence` cədvəli **yalnız xam SQL** (`RunPython`,
`0018:481`) ilə yaradılır və `organizations_organization(id)`-ə FOREIGN KEY
saxlayır. Həmin cədvəl üçün **Django modeli yox idi**, ona görə də
`connection.introspection.django_table_names()`-ə düşmür.

Django-nun `flush`-u (hər `TransactionTestCase` teardown-ı) yalnız qeydiyyatlı
model cədvəllərini `TRUNCATE` edir və `allow_cascade=False`-dur. PostgreSQL isə
FK ilə istinad olunan cədvəli, istinad edən cədvəl eyni `TRUNCATE` ifadəsində
deyilsə, kəsməyə imkan vermir:

```
psycopg2.errors.FeatureNotSupported: cannot truncate a table referenced in a foreign key constraint
django.db.utils.NotSupportedError: …
django.core.management.base.CommandError: Database test_test_db couldn't be flushed.
```

Bu, `apps/organizations/tests/test_rls_transaction_pooling.py`-nin BÜTÜN
teardown-larını partladır; baza təmizlənmədiyi üçün ardınca gələn modullar
`IntegrityError: duplicate key value violates unique constraint "auth_user_…"`
/ `"accounts_userprofile_pkey"` ilə düşür. Yəni **9 «failed» migration
round-trip testi müstəqil defekt deyil** — çirklənmiş bazanın ardıcıl
nəticəsidir (`legacy_import/0007_legacy_map_lookup_index.py` və `_ledger_base.py`
bölgüsü günahsızdır; təsdiqi aşağıdadır).

Müqayisə: 0013-dəki **aktivasiya** sübutu bu tələyə düşmür, çünki o
`migrations.CreateModel` ilə yaradılıb
(`0013_identity_staging_and_canonical_guards.py:734`, model
`apps/accounts/identity_models.py:8`) — yəni `django_table_names()`-dədir və
`flush` onu da eyni `TRUNCATE`-ə daxil edir. Hər iki cədvəldəki
`BEFORE TRUNCATE` trigger-i superuser session-a icazə verir
(`usesuper` yoxlaması), ona görə CI-ın `test_user`-i ilə `TRUNCATE` keçir.

Diaqnostikanın təsdiqi (test bazasında):

```
unregistered tables with FK to model tables:
  accounts_accountrestoreevidence -> organizations_organization
```

— bütün bazada məhz bir belə cədvəl var.

### Düzəliş

0018 artıq QA klonunda (və hər yerdə) TƏTBİQ OLUNUB, ona görə ona toxunulmur;
irəli-yönlü **state-only** migration əlavə olunur:

* `apps/accounts/identity_models.py:54` — yeni `AccountRestoreEvidence` modeli
  (0018-dəki xam sxemin eynisi: uuid PK, `organizations.Organization` FK
  `PROTECT`, `user_ref/role_ref/actor_ref/evidence_digest/reason_code` `varchar(64)`,
  `transaction_id` bigint, `created_at`, nullable `consumed_at`).
* `apps/accounts/models.py:448` — modelin yenidən ixracı (mövcud konvensiya).
* `apps/accounts/migrations/0019_account_restore_evidence_state.py` —
  `SeparateDatabaseAndState(database_operations=[], state_operations=[CreateModel(...)])`.
  **Heç bir DDL icra olunmur**: trigger-lər, `REVOKE`-lar, RLS siyasəti və
  `accounts_restore_archived_identity(...)` funksiyası 0018-də olduğu kimi qalır,
  cədvəl append-only olaraq qalır.
  `(organization_id, user_ref)` indeksi (`accounts_restore_evidence_org_user_idx`)
  qəsdən state-ə salınmır — adı Django-nun 30 simvolluq indeks-ad limitindən
  uzundur, DB əməliyyatı olmadığı üçün drift yaranmır.

Nəticə: cədvəl `django_table_names()`-ə düşür → `flush` onu da kəsir → FK
`TRUNCATE`-i bloklamır.

`makemigrations --check --dry-run` → `No changes detected`.

### Yerli reproduksiya (CI əmrinin eynisi, yalnız modullar məhdud)

```bash
RLS_TRANSACTION_SCOPED=True \
DATABASE_URL="postgres://emsarena_agent:…@127.0.0.1:55432/ems_cifix_7f3a2b" USE_REDIS=False \
.venv/bin/pytest -m postgres \
  apps/organizations/tests/test_rls_transaction_pooling.py \
  apps/legacy_import/tests/test_batch_accounting_migration_postgres.py \
  apps/legacy_import/tests/test_rehearsal_postgres.py \
  apps/legacy_import/tests/test_review_migration_postgres.py \
  apps/exams/tests/test_access_code_migration.py \
  -q -p no:cacheprovider --ds=config.settings.test
```

| | nəticə |
|---|---|
| ƏVVƏL | `9 failed, 17 passed, 1 skipped, 27 errors in 147.43s` |
| SONRA | `36 passed, 1 skipped in 184.58s` |

Genişlənmiş yoxlama (`-m postgres` üzrə `apps/accounts apps/applications
apps/workload apps/audit apps/monitoring apps/ai_assistant`): bax aşağıdakı
«Əlavə qaçışlar».

---

## Uğursuzluq 2 — `security` job-u: pip-audit

`requirements/base.txt:92` — `pypdf==6.15.0` üçün CVE-2026-84309 / 84310 / 84311;
düzəldilən buraxılış **6.16.1**. `_security.yml:72-75`-də `pip-audit` uğursuzluğu
merge-i bloklayır.

### Düzəliş

`requirements/base.txt:92` → `pypdf==6.16.1` (şərh də yeniləndi: hansı CVE-lərin
qapandığı yazılıb). Başqa heç bir requirements faylında pypdf pin-i yoxdur.

### Yoxlama

* `.venv/bin/pip install pypdf==6.16.1` → uğurlu, `pypdf.__version__ == "6.16.1"`.
* Təmiz venv-də `pip-audit -r requirements/base.txt` → **`No known vulnerabilities found`**
  (əvvəl 3 tapıntı).
* PDF idxal yolu (`apps/exams`):
  `test_import_media.py test_text_extraction_jobs.py test_pdf_layout.py
  test_pdf_layout_limits.py test_visual_import_upload.py` → `71 passed, 2 skipped`;
  `test_services.py -k "pypdf or extract_text"` → `8 passed`.

---

## Dəyişən fayllar üzrə gate-lər

| Gate | Nəticə |
|---|---|
| `black --check` (3 dəyişən .py) | `3 files would be left unchanged` |
| `isort --check-only` | təmiz |
| `flake8` | `exit=0` |
| `scripts/check_module_size.py --check` | ✅ SOFT_CAP=600 daxilində |
| `scripts/module_deps.py --check` | ✅ yeni dövr yoxdur |
| `manage.py makemigrations --check --dry-run` | `No changes detected` |

## Əlavə qaçışlar

`RLS_TRANSACTION_SCOPED=True pytest -m postgres apps/accounts apps/applications
apps/workload apps/audit apps/monitoring apps/ai_assistant` →
**`22 passed, 1446 deselected in 36.58s`** (o cümlədən
`apps/accounts/tests/test_account_archive_postgres.py` — bərpa sübutu axını —
və `applications`/`workload` RLS testləri).

## Operativ qeyd

QA klonunda 0018 artıq tətbiq olunub; `0019` **state-only** olduğu üçün klonda
`migrate` yalnız `django_migrations` sətri yazır, sxemə toxunmur. Klonda işləyən
agentlər növbəti dəfə `scripts/staging_inspect.sh migrate` çağırmalıdır.
