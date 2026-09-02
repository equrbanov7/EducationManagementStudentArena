# FAZA 28 — CI qapılarının inteqrasiyası (`audit/post-migration-qa-2026-09`)

Tarix: 2026-09-02 · Branch: `audit/post-migration-qa-2026-09` (baza: Develop `260112af`) · PR #119 → Develop

Məqsəd: **davranışı dəyişmədən** GitHub CI-dakı lint/guard qapılarını yaşıllaşdırmaq.
Tam test dəsti LOKAL İCRA OLUNMUR (sahibin qaydası) — pytest job-ları CI-də işləyir.

CI-nin faktiki əmrləri `.github/workflows/_lint.yml`, `_build.yml`, `_security.yml`,
`_unit-tests.yml`, `_rls-txn-pool.yml`-dan götürülüb.

---

## Qapı 1 — `scripts/check_module_size.py --check` (god-file guard)

### ƏVVƏL
```
❌ YENİ fayllar SOFT_CAP=600 sətir limitini keçir:
     604  apps/legacy_import/models.py
     602  apps/registrar/models/grading.py
```
Hər iki fayl baseline-də (`scripts/module_size_budget.json`) YOXDUR, yəni onlara
SOFT_CAP=600 sərt limiti tətbiq olunur. Bu branch-də hər ikisinə yalnız
**performans indeksi + izahat kommenti** əlavə edilmişdi (599→604, 592→602).

### DÜZƏLİŞ (struktur bölgü, davranış dəyişmir)

**`apps/legacy_import/models.py` → yeni qonşu modul `apps/legacy_import/_ledger_base.py`**

Köçürülən (model tərifi DEYİL, yalnız primitivlər):
`TOKEN_PATTERN`, `SHA256_PATTERN`, `OPAQUE_KEY_PATTERN`, `MODEL_LABEL_PATTERN`,
`_RUN_MODE_CHECK`, `_RUN_ACCOUNTING_CHECK`, `token_validator`, `sha256_validator`,
`opaque_key_validator`, `model_label_validator`, `_NoDeleteQuerySet`,
`_NoDeleteManager`, `_NonDeletableLedgerModel` (abstract).

`models.py` hamısını `from ._ledger_base import (...)  # noqa: F401` ilə **re-export**
edir, ona görə mövcud import yolları toxunulmaz qalır:
* `apps/legacy_import/review_models.py` → `from .models import (...)`
* `apps/legacy_import/tests/test_rehearsal_contracts.py` → `from apps.legacy_import.models import MODEL_LABEL_PATTERN, token_validator`

Miqrasiya təsiri YOXDUR: `RegexValidator` instansiyaları `django.core.validators.RegexValidator(regex=…, message=…)`
kimi deconstruct olunur (modul yolu ilə yox), abstract baza isə app registry-yə düşmür.
Artıq istifadə olunmayan `RegexValidator` / `ProtectedError` importları `models.py`-dən silindi.

**`apps/registrar/models/grading.py` → yeni qonşu modul `apps/registrar/models/grading_choices.py`**

Köçürülən `TextChoices` enum-ları: `LessonKind`, `AttendanceStatus`, `ApprovalStatus`,
`ComponentKind`, `ResitReason`, `ResitStatus` (bütün docstring/şərhlər olduğu kimi).
`grading.py` onları `from .grading_choices import (...)  # noqa: F401` ilə re-export edir,
deməli `apps.registrar.models` paket-səviyyə ixracı və `from .grading import LessonKind`
(məs. `apps/registrar/models/corrections.py`) işləməyə davam edir.
Miqrasiyalar `choices=[…]` literal siyahısını saxlayır → `makemigrations --check` təmiz.

Nəticə ölçülər: `legacy_import/models.py` 604 → **573**, `registrar/models/grading.py` 602 → **546**
(hər ikisində gələcək üçün ehtiyat var); yeni modullar 54 və 74 sətir.

### SONRA
```
✅ Modul ölçü budcəsi: bütün fayllar limit daxilindədir (SOFT_CAP=600).
✅ Modul-sərhəd gate-i: yeni dövr yoxdur (0 dondurulmuş)   # scripts/module_deps.py --check
```

---

## Qapı 2 — `scripts/check_worker_atomic_coverage.py --check`

### ƏVVƏL
```
❌ Sarınmamış request-external DB entry-point-ləri tapıldı:
   - apps/applications/management/commands/close_stale_resolved.py
   - apps/applications/management/commands/seed_application_catalog.py
   - apps/legacy_import/management/commands/legacy_repair_archive_status.py
   - apps/legacy_import/management/commands/legacy_repair_current_period.py
   - apps/legacy_import/management/commands/legacy_repair_demographics.py
   - apps/legacy_import/management/commands/legacy_repair_missing_accounts.py
```

### DÜZƏLİŞ
`INTENTIONAL_EXEMPTIONS` İSTİFADƏ EDİLMƏDİ — altı əmrin hamısı həqiqətən DB-yə yazır,
ona görə hamısı `apps/registrar/management/commands/set_program_official_codes.py`
nümunəsindəki kimi sarındı:

```python
from core.rls_pooling import rls_worker_atomic
...
    def handle(self, *args, **options):
        # RLS transaction-pooling təhlükəsizliyi (FAZA 4/Task 1) …
        with rls_worker_atomic():
            <əvvəlki handle gövdəsi, olduğu kimi>
```

**Davranış dəyişmir:**
* `rls_worker_atomic()` yalnız `RLS_TRANSACTION_SCOPED=True` olduqda `transaction.atomic()`-dir;
  flaq sönülü olanda **no-op**-dur (`core/rls_pooling.py:106`).
* Repair əmrlərinin **sətir-səviyyə fail-open semantikası saxlanıldı**: xarici sarğı
  əlavə edildi, servislərdəki daxili `transaction.atomic()` (`repair_archive.apply_decision`,
  `repair_accounts.create_account`, `applications/services/maintenance.close_stale_resolved`)
  toxunulmadı — onlar indi savepoint kimi işləyir, yəni bir sətrin xətası yalnız
  o sətri geri qaytarır, əmr isə `failed[]` hesabatı ilə davam edir.
* Mənbə (MariaDB) bağlantısı və `CommandError` fail-closed yolları dəyişmədi.

### SONRA
```
✅ Bütün 44 request-external DB entry-point-i düzgün sarınıb
   (aktiv istisna: 6).
```

Reqressiya testi (öz şəxsi postgres bazasında, `integ_gates_agent`):
```
apps/legacy_import/tests/test_repair_commands.py .....................   [ 65%]
apps/applications/tests/test_sla.py ...........                          [100%]
============================= 32 passed in 42.00s ==============================
```

Köçürülən model primitivlərini işlədən testlər (Qapı 1 üçün reqressiya):
```
apps/legacy_import/tests/test_rehearsal_contracts.py  +  apps/registrar/tests/test_components.py
============================= 36 passed in 39.31s ==============================
```

---

## Qapı 3 — `scripts/check_i18n_catalogs.py`

### ƏVVƏL
> Tapşırıqdakı `3 → 37` rəqəmi KÖHNƏLMİŞDİ; ölçülən faktiki vəziyyət:
```
❌ i18n qapısı KEÇMƏDİ:
   django: source_missing 3 → 4 (sonra dashboard işi ilə birlikdə → 6)
   django/tr: identity 270 → 287 (ARTIB)
```

### Kor nöqtə: dəyişən-kontekstli `pgettext`

FAZA 22 dashboard-ı 100 msgid gətirdi, lakin qapı onlardan yalnız BİRİNİ
(şablondakını) gördü. Səbəb: `dashboard*.py` fayllarında kontekst modul-səviyyə
dəyişəndir — `_CTX = "accounts.dashboard"` (layihədə 20+ faylda eyni konvensiya,
məs. `student_intake`, `accounts.schedule_manage`). Nə `xgettext`, nə də
`scripts/i18n_source_scan.py` **dəyişən** kontekstli çağırışı literal kimi görmür,
ona görə bu girişlər `makemessages` ilə ÇIXARILMIR. Layihənin cavabı elə buna görə
`scripts/i18n_fill_*.py` skriptləridir. Msgid siyahısı sənəddəki nəsr siyahıdan
DEYİL, mənbədən AST ilə çıxarıldı (99 Python + 1 şablon = 100).

### DÜZƏLİŞ

Yeni `scripts/i18n_fill_dashboard.py` (ev üslubu: yalnız ƏLAVƏ edir, mövcud
girişə toxunmur; `makemessages` işlədilmir). Mövcudluq yoxlaması mətn axtarışı ilə
deyil, `polib` ilə aparılır — kontekstsiz girişlərdə `msgid "…"` substring probe-u
yalançı müsbət verirdi.

**105 giriş × 4 dil** (az = msgid, en/ru/tr real tərcümə):

* `accounts.dashboard` — **100** (vidjet başlıqları, keçid linkləri, statistika
  etiketləri, rəqəmdən sonrakı vahid sözləri, boş-vəziyyət mətnləri);
* `profile.sidebar|Ana səhifə` — 1;
* qalıq `source_missing` — 4: `exams.final_center.permission|…`,
  `registrar.journal|Otaq`, kontekstsiz PDF altlığı və `Yekun nəticə`.

Terminologiya mövcud kataloqla uzlaşdırıldı (`RİM` → *Digital Development Centre
(RİM)* / *Центр цифрового развития (RİM)* / *Dijital Gelişim Merkezi (RİM)*;
`Jurnal` → *journal* / *журнал* / *yoklama defteri`*; `Sillabus` → *syllabus* /
*силлабус* / *ders izlencesi*).

`Salam, %(name)s` — yer tutucu hər dörd dildə saxlanıldı (`bad_placeholder = 0`).

`compilemessages` icra edildi; `.mo`-larda **105/105** giriş təsdiqləndi
(`Hello, %(name)s` / `Здравствуйте, %(name)s` / `Merhaba, %(name)s`).

### AZ tarix msgid-ləri + fuzzy qaydası (yoxlanıldı)

* AZ kataloqundakı tarix girişləri msgid-i İNGİLİS, msgstr-i AZƏRBAYCAN olan
  Django sətirləridir (`Monday → Bazar ertəsi`, `January → Yanvar`,
  `jan → ynv`, `alt. month`/`abbrev. month` kontekstləri daxil) — DÜZGÜNDÜR və
  `identity` sayılmır (identity qaydası yalnız qeyri-AZ dillərə tətbiq olunur).
  Bu girişlərə TOXUNULMADI.
* Fuzzy: kataloqlarda 370–395 fuzzy giriş var. `msgfmt` fuzzy girişi QƏSDƏN
  `.mo`-ya salmır, ona görə `_check_mo_freshness()` onları müqayisədən çıxarır —
  əks halda hər fuzzy giriş yalançı «.mo köhnədir» siqnalı verərdi. Əlavə etdiyim
  105 girişin heç birində fuzzy bayrağı YOXDUR, deməli hamısı `.mo`-ya düşür
  (yuxarıdakı 105/105 təsdiqi). Mövcud fuzzy girişlərə toxunulmadı.

### `identity` artımı və baseline

Ratchet iki yerdə qalxdı; hər ikisi **həqiqətən eyni yazılan düzgün tərcümədir**,
tərcümə borcu deyil:

* **`django/tr` 270 → 290 (+20).**
  17-si bu branch-də ƏVVƏLDƏN vardı (schedule-manage / applications /
  student-intake): `Gün`, `Saat`, `Seçin…`, `Sil`, `Slot silindi.`, `Slotlar`,
  `Slotu sil`, `Yeni`, `gün`, `{n} iş günü`, `(boş)`, `Ad`, `Ad Soyad`, `Soyad`,
  `Sütun`, `Sütunlar`, `Telefon` — hamısı Azərbaycan və türk dilində eyni yazılan
  qanuni türk sözləridir (bir-bir yoxlanıldı).
  3-ü mənim əlavəmdəndir: `slot`, `saat`, `sonuncu` — üçü də düzgün türkcədir.
* **`django/en` 233 → 235 (+2):** `Limit`, `Status` — ingiliscədə eyni sözlərdir.

Ona görə baseline `--update` ilə yeniləndi. Diff-in TAMAMI:

```
az   source_missing  3 → 0      (SIXILDI — qapı indi daha sərtdir)
en   identity      233 → 235
tr   identity      270 → 290
*    total         (ratchet açarı deyil — girişlərin sayı)
```
Heç bir ölçü BOŞALDILMADI: `missing_vs_source`, `untranslated`,
`bad_placeholder`, `raw_key_leak`, `extra_vs_source` və bütün `djangojs`
ölçüləri dəyişməz qaldı.

`djangojs/az source_missing 52` və `django/{en,ru} extra_vs_source 24` baseline
səviyyəsindədir (əvvəlcədən mövcud borc) — qapını qırmır, toxunulmadı.

### SONRA
```
✅ i18n kataloq qapısı: yeni borc yoxdur.
```
```
apps/accounts/tests/test_profile_i18n_role_matrix.py ...   [100%]
============================== 3 passed in 39.49s ==============================
```
(FAZA 22 §8.1-də qırmızı olan 18 alt-test artıq yaşıldır.)

---

## Qapı 3b — `test_view_as.py::test_no_unreviewed_mutating_get_route_exists`

**Diaqnoz: skanerin YALANÇI MÜSBƏTİ, marşrutda qüsur yoxdur.**

`workload:my_export` (`apps/workload/views/teacher_api.py:56`) DB-yə heç nə yazmır:

* view `@never_cache @login_required @require_GET`-dir;
* yeganə məlumat mənbəyi `teacher_workload_rows()`
  (`apps/workload/services/queries.py:158`) — həmin modulda BİR DƏNƏ də
  `.save(`/`.create(`/`.delete(`/`.update(` yoxdur;
* testi yandıran `.save(` **openpyxl-in yaddaşdaxili `workbook.save(buffer)`**
  çağırışıdır — Excel faylı `BytesIO`-ya yazılır, baza yox.

Ona görə marşrut testin öz mexanizmi ilə `REVIEWED_SAFE`-ə əlavə edildi
(qonşuları da ixrac endpoint-ləridir: `accounts:statistics_export_csv`,
`exams:exam_center_stats_export`), səbəbi kod şərhində yazıldı.

**`require_GET` QƏSDƏN `guard` regex-inə əlavə EDİLMƏDİ.** `guard` (`request.method`,
`require_POST`, `require_http_methods`, `http_method_names`) «view metodları ayırır,
deməli `.save()` POST qolundadır» deməkdir. `require_GET` isə əksi: marşrut YALNIZ
GET-dir — mutasiya edirsə təhlükə məhz odur (testin docstring-indəki
`live_create_session_by_slug` nümunəsi). Regex-i genişləndirmək bütün gələcək
GET-only mutasiyalarını gizlədərdi.

## Qapı 4 — Black / isort / Flake8 (CI-nin dəqiq əmrləri)

### `black --check --diff --color .`
```
All done! ✨ 🍰 ✨
1655 files would be left unchanged.
```

### `isort --check-only --diff --profile black .`
Bütün repo üzrə (`isort … .`): **çıxış boş, exit 0** → keçdi.
CI-ekvivalent icra (git-in izlədiyi 1664 `.py`, `migrations/` çıxarılmaqla): `Skipped 1 files`, exit 0 → keçdi.

### `flake8 . --count --max-line-length=120 --extend-ignore=E203,E266,E501,W503 --exclude=.git,__pycache__,migrations,venv,.venv,env --statistics --show-source`
Bütün repo üzrə: **çıxış boş, exit 0** → keçdi.
CI-ekvivalent icra (eyni 1664 fayl): `--count` nəticəsi **`0`**, exit 0 → keçdi.

> Lokal tələ: CI-nin `--exclude` siyahısında `.claude` YOXDUR. Təmiz CI checkout-unda
> bu qovluq kiçikdir, lakin lokal maşında 285 MB sessiya datası var və `flake8 .`
> dəqiqələrlə sürünür. Ona görə lokal təsdiq `git ls-files '*.py'` siyahısı ilə
> aparıldı — bu, CI-nin gördüyü faylların dəqiq ekvivalentidir (5 saniyə).

Branch-də dəyişən 231 `.py` faylı üzrə hədəflənmiş icra: **0 tapıntı** (flake8 və isort).

> Qeyd: fayl yolları AÇIQ verildikdə `isort` `skip = ["migrations", …]` qaydasını
> tətbiq etmir və `apps/{applications,workload}/migrations/0001_initial.py` üçün
> yalançı-müsbət verir. CI `isort … .` (qovluq) formasını işlədir, ona görə
> həmin miqrasiyalar CI-də skan olunmur.

---

## Qapı 5 — Miqrasiya bütövlüyü + sistem yoxlaması

```
$ DATABASE_URL=sqlite:///$PWD/x.sqlite3 manage.py makemigrations --check --dry-run
No changes detected

$ manage.py check
System check identified no issues (0 silenced).

$ manage.py check --fail-level WARNING          # _unit-tests.yml addımı
System check identified no issues (0 silenced).

$ manage.py collectstatic --noinput --dry-run   # _build.yml addımı
319 static files copied to '…/staticfiles', 524 unmodified.
```
`x.sqlite3` icradan sonra silindi.

---

## Qapı 6 — CI-nin qalan **test olmayan** əmrləri

| Workflow | Addım | Lokal nəticə |
|---|---|---|
| `_lint.yml` | `black --check` | ✅ |
| `_lint.yml` | `isort --check-only --profile black` | ✅ (aşağıdakı qeyd) |
| `_lint.yml` | `flake8 …` | ✅ |
| `_lint.yml` | `check_module_size.py --check` | ✅ |
| `_lint.yml` | `module_deps.py --check` | ✅ |
| `_lint.yml` | `check_i18n_catalogs.py` | ✅ |
| `_lint.yml` | `check_worker_atomic_coverage.py --check` | ✅ |
| `_build.yml` | `collectstatic --noinput` | ✅ |
| `_build.yml` | `makemigrations --check --dry-run` | ✅ (`No changes detected`) |
| `_build.yml` | `migrate --noinput` (postgres) | CI-də icra olunur (lokal QA klonunda artıq tətbiq edilib) |
| `_security.yml` | `check --deploy --fail-level WARNING` | ✅ (aşağıya bax) |
| `_security.yml` | `pip-audit` / `bandit` | dəyişməyib (requirements toxunulmayıb) |
| `_unit-tests.yml` | `check --fail-level WARNING` | ✅ |
| `_rls-txn-pool.yml` | `check_worker_atomic_coverage.py --check` | ✅ |
| pytest job-ları | — | **QƏSDƏN LOKAL İCRA EDİLMƏDİ** (sahibin qaydası) |

### `check --deploy --fail-level WARNING` — LOKAL `.env` TƏLƏSİ

CI env-i (`_security.yml`): `DJANGO_SETTINGS_MODULE=config.settings.production`,
`DEBUG=False`, `ALLOWED_HOSTS=localhost,127.0.0.1`, `ADMIN_ALLOWED_IPS=127.0.0.1`,
`EMS_DB_ROLE_ENFORCE=error` (+ postgres-də məhdud `security_app` rolu provision edilir).
Lokal icrada tapşırığa uyğun `EMS_DB_ROLE_ENFORCE=off` işlədildi.

İlk icra 4 xəbərdarlıq verdi (W004 HSTS, W008 SSL redirect, W012 session cookie,
W016 CSRF cookie). **Bu kod qüsuru DEYİL** — səbəb repo kökündəki LAN deploy
`.env` faylıdır (sətir 51-54: `SECURE_SSL_REDIRECT=False`, `SESSION_COOKIE_SECURE=False`,
`CSRF_COOKIE_SECURE=False`, `SECURE_HSTS_SECONDS=0`). `config/settings/production.py:330-357`
bu dəyərlərin DEFOLTUNU `True`/`31536000` saxlayır və CI-də `.env` yoxdur.
CI-ekvivalent env ilə təkrar icra:
```
System check identified no issues (0 silenced).
```

---

## Dəyişən fayllar (bu inteqrasiya addımı)

```
A  apps/legacy_import/_ledger_base.py                     (yeni, 54 sətir)
M  apps/legacy_import/models.py                           (604 → 573)
A  apps/registrar/models/grading_choices.py               (yeni, 74 sətir)
M  apps/registrar/models/grading.py                       (602 → 546)
M  apps/applications/management/commands/close_stale_resolved.py
M  apps/applications/management/commands/seed_application_catalog.py
M  apps/legacy_import/management/commands/legacy_repair_archive_status.py
M  apps/legacy_import/management/commands/legacy_repair_current_period.py
M  apps/legacy_import/management/commands/legacy_repair_demographics.py
M  apps/legacy_import/management/commands/legacy_repair_missing_accounts.py
A  scripts/i18n_fill_dashboard.py                          (yeni, 105 giriş × 4 dil)
M  locale/{az,en,ru,tr}/LC_MESSAGES/django.po              (+105 giriş / dil)
M  locale/{az,en,ru,tr}/LC_MESSAGES/django.mo              (compilemessages)
M  scripts/i18n_baseline.json                              (source_missing 3→0; en/tr identity)
M  apps/accounts/tests/test_view_as.py                     (REVIEWED_SAFE += workload:my_export)
A  docs/audits/2026-09-02/PHASE28_INTEGRATION_GATES.md     (bu sənəd)
```

Heç bir miqrasiya dəyişdirilmədi. `module_size_budget.json` və
`module_deps_baseline.json` TOXUNULMADI. `i18n_baseline.json` yalnız Qapı 3-də
əsaslandırılmış şəkildə yeniləndi (yuxarıdakı diff).
