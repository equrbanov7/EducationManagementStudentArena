# AGENTS.md — EMSArena üçün AI agent qaydaları

Bu fayl Codex / Claude Code / digər AI agentlərinin bu repozitoriyada task həll
edərkən riayət etməli olduğu qaydaları təyin edir. **Dəyişiklik etməzdən əvvəl
oxuyun.**

---

## 1. Modul ölçüsü — "god-file" yaratma / böyütmə (MƏCBURİ)

Böyük tək-fayllı modullar (1000+ sətir view/servis) oxunması, test edilməsi və
təhlükəsiz dəyişdirilməsi çətindir. Ona görə **sərt qayda** var:

- **Yeni fayl ≤ 600 sətir** olmalıdır (`SOFT_CAP`). Qayda `.py` **və HTML/CSS/JS
  assetlərini** (şablonlar + statiklər) əhatə edir. İstisnalar: migrations, tests,
  `staticfiles/`/`htmlcov/`/`output/`/`node_modules/`/`vendor/`, `.min.*`/`.map`.
- Mövcud böyük fayllar `scripts/module_size_budget.json`-da **dondurulub
  (ratchet)**: onlara yeni sətir əlavə edib **böyütmək qadağandır** — yalnız
  kiçildə bilərsiniz. (Cari: 0 Python; ~44 asset donmuş — HTML {% include %}
  partial, CSS komponent-bölgü, JS ES-modul ilə tədricən kiçildilir.)
- Task həll edərkən böyük fayla məntiq əlavə etmək lazımdırsa: məntiqi **ayrı
  servis / helper / alt-modula** çıxarın və ya faylı **paketə** çevirin
  (aşağıdakı pattern-ə bax).

### Yoxlama əmrləri

```bash
# Budcəni yoxla (CI/_lint.yml-də avtomatik işləyir):
python scripts/check_module_size.py --check

# Şüurlu bölgüdən SONRA baseline-i yenilə (fayl kiçildikdə və ya bilərəkdən
# yeni böyük fayl qəbul ediləndə — review-da əsaslandırın):
python scripts/check_module_size.py --update
```

CI bu yoxlamanı `.github/workflows/_lint.yml` → "Module size budget" addımında
icra edir; budcə aşılarsa lint düşür.

### Faylı təhlükəsiz bölmə pattern-i (import səthini qoru)

`big.py`-ni paketə çevirərkən **bütün public import yollarını saxlayın** ki,
mövcud `from ...big import X` çağırışları və testlər sınmasın:

```
big.py  →  big/
            ├── __init__.py     # FASAD: hər simvolu re-export edir
            ├── _core.py        # nüvə məntiq
            └── extraction.py   # başqa kohezivli qrup
```

`__init__.py` nümunəsi:

```python
from .extraction import *          # public adlar (import-bağlı adlar daxil: fitz, ...)
from ._core import *
from .extraction import (_private_used_externally, END_QUESTION_RE)  # underscore adlar
from ._core import (_validate_questions, parse_bulk_mcq)
```

Diqqət 1 — **patch/mock:** testlər `patch.object(module, "Name")` və ya
`patch("module.Name")` istifadə edirsə, həmin `Name`-i işlədən funksiya onu
**call-time fasaddan** həll etməlidir (yoxsa mock alt-modula təsir etməz). Modul
obyektləri (`subprocess`, `shutil`) fasadda `import`-la expose olunmalıdır.
Nümunələr: `parsing/extraction.py` → `extract_text_from_upload`;
`coding_runtime/execution.py`,`grading.py` → docker/`execute_code`.

Diqqət 2 — **relative importlar (KRİTİK):** fayl paketə çevriləndə bir səviyyə
DƏRİNLƏŞİR. Ona görə orijinal `from .X import ...` (qonşu modul) alt-modullarda
`from ..X import ...` OLMALIDIR (əks halda `.X` paketin öz içində axtarılır →
`ModuleNotFoundError`). Həmçinin alt-modul adı qonşu modulla TOQQUŞMAMALIDIR
(məs. `apps.organizations.views` varsa, alt-modulu `views` yox, `endpoints`
adlandır). Nümunə: `apps/organizations/structure_views/` (`..models`, `..views`,
`endpoints.py`).

Diqqət 3 — **hər bölgüdən sonra** `python manage.py check` + `makemigrations
--check` işlət (relative-import/registry problemlərini tutur).

İstinad nümunəsi (artıq bölünmüş): `apps/exams/services/parsing/`,
`apps/exams/services/coding_runtime/`, `apps/organizations/structure_views/`.

### Nəhəng tək-funksiyalı view (extract-class pattern)

Tək 800+ sətirlik view funksiyası çoxlu iç-içə closure ilə request-scoped state
(`request`, `org`, icazə bayraqları) tutursa, onu **extract-class** ilə böl:
closure-ları `self.*` state ilə **mixin metodlarına** çevir, view isə nazik
qalır (`return _Flow(request).run()`). Paylaşılan state (`org`, `request`, setup-da
hesablanan lokallar closure-larda işlənirsə) `self.*` olur; module-level import/helper-lər
olmur (mixin fayllarında import edilir). Fayl `_x_flow/` paketinə bölünür
(`_audit`/`_predicates`/`_resolvers` və s. mixin + `flow.py` = `__init__`+`run`).
**Diqqət:** (a) closure-lar `patch`/mock hədəfi deyilsə AST-transform işlədir; (b) fayllar
paketə düşəndə relative-import səviyyəsi +1 (bax yuxarı); (c) `ast.unparse` şərhləri
(`# noqa`) silir — F811/F401 üçün əl ilə geri qoy; (d) **MÜTLƏQ** characterization
testi ilə davranışı təsdiqlə. Nümunələr: `roles/_assignment_flow/`,
`organization/_management_flow/`.

**Linear god-funksiya (org_sections pattern):** funksiyanın erkən-return-ları YALNIZ
setup-da, qalan gövdə lineardırsa → **verbatim statement-split**: setup+guard public
funksiyada, tail `_queries`/`_pagination` kimi hissələrə; sərhəddə yalnız keçən dəyişənləri
açıq threading et (AST-rewrite yox, source-slice, şərhlər qorunur). Sərhəd dəyişənlərini
AST-lə hesabla (assigned-before ∩ used-after). Nümunə: `_helpers/org_sections/`.

**Çox-lokal-lı god-funksiya (context_builder pattern, staged-builder):** funksiya nested
def-siz, comprehension/walrus/global-suz, çoxlu (~100+) lokal bütün gövdə boyu axırsa →
**extract-class + self.X**: bütün funksiya-lokallarını (assigned adlar ∪ param − import-adları)
AST-rewrite ilə `self.X`-ə çevir, gövdəni ardıcıl `_stage_N` mixin-metodlarına böl (istənilən
statement-sərhədi təhlükəsiz, çünki bütün state self-dədir). Erkən-return-ları `run()`-da
None-check ilə propagate et. Func-level (lazy) importlar method-daxili qalır; DIRECT-body
cross-stage importları re-inject et; **bütün relative body-importlar (nested daxil) +1 bump**.
`ast.unparse` şərhləri itirir — bu pattern üçün qəbul edilir, MÜTLƏQ characterization testi ilə
doğrula. Nümunə: `profile/context_builder/`.

**Nə vaxt tam əl işi:** linear funksiyada erkən-return-lar gövdəyə yayılıbsa VƏ çoxlu-lokal-lıdırsa
(hər iki çətinlik birləşirsə) — avtomatlaşdırma risklidir, manual staged Postgres-CI PR lazımdır.

### Settings faylını bölmə (fərqli pattern)

`config/settings/base.py` funksiya/sinif deyil, sıralı **assignment**-lərdən ibarət
idi (çarpaz-istinadlar: `CELERY_RESULT_BACKEND = CELERY_BROKER_URL`,
`PASSWORD_RESET_TIMEOUT = AUTH_OTP_EXPIRY_SECONDS`, CSP → `MICROSOFT_CLARITY_*`).
Belə faylı paket-fasada YOX, **`components/` + exec-include** (django-split-settings
üslubu) ilə böl: hər komponent base.py-nin **paylaşılan qlobal namespace-ində**
`exec` olunur, ona görə davranış dəyişmir və çarpaz-istinadlar işləyir. Sıra
asılılıq istiqamətinə görə `_COMPONENTS` siyahısında idarə olunur. Köməkçilər
(`_env_*`, `_redis_url_with_db`) və importlar base.py başlığında qalır.
**Doğrulama:** bölgüdən əvvəl/sonra bütün UPPER_CASE setting-ləri `repr`-lə
snapshot götür və diff-i sıfır olduğunu təsdiqlə (BASE_DIR fərqi yalnız fayl
yerindən yaranırsa, eyni qovluqdan snapshot al).

---

## 2. Testləri lokal işlətmə (Postgres olmadan)

Test mühiti default olaraq PostgreSQL tələb edir. RLS/tenant testlərindən başqa
servis/parse testlərini sürətlə Postgres-siz işlətmək üçün `DATABASE_URL`-i
sqlite-a yönləndirin (repo və `.env` dəyişmir):

```bash
DATABASE_URL="sqlite://" pytest apps/exams/tests/test_services.py --no-migrations -p no:cacheprovider
```

PostgreSQL ilə (RLS/`-m postgres` daxil): `DATABASE_URL`-dəki əsas baza mövcud
olmalı və DB rolunda `CREATEDB` icazəsi olmalıdır.

---

## 3. Layihə prinsipləri (xülasə)

- **Tenant izolyasiyası > hər şey.** İstifadəçi öz təşkilatı / rolu / icazə
  sahəsindən kənar məlumata çıxa bilməz. RLS (`core/rls.py`) + RBAC
  (`apps/organizations/permissions.py`) mərkəzi mənbədir.
- **Mərkəzləşdirilmiş RBAC.** Rol-adına görə kodda xüsusi hallar yaratmayın;
  icazələri rol tərifinə (`default_roles.py`) və ya data migrasiyasına qoyun.
- **Mövcud pattern-lərdən istifadə.** Yeni izolə kod yazmadan əvvəl mövcud
  servis/helper/komponentləri yoxlayın (DRY).
- **Təhlükəsizlik.** Input validasiyası, upload qorunması
  (`core/upload_security.py`), CSRF/CSP qaydalarına riayət.
- **Migrasiyalar idempotent və geri-qaytarıla bilən** olmalıdır.
- Cavablar/izahlar **Azərbaycan dilində** (kod/identifikator adları istisna).

---

## 4. Dəyişiklikdən sonra məcburi yoxlama siyahısı

```bash
python scripts/check_module_size.py --check        # god-file guard
black --check . && isort --check-only --profile black .
flake8 .
DATABASE_URL="sqlite://" pytest <dəyişdirilən sahənin testləri> --no-migrations -p no:cacheprovider
```


---

## 5. Modul sərhədləri — M1 ratchet gate (MƏCBURİ)

Cross-modul asılılıqlar `scripts/module_deps.py` ilə qorunur (CI: `_lint.yml`
→ "Module boundary gate"). Qayda:

- **YENİ dövri (qarşılıqlı) modul cütü yaratmaq QADAĞANDIR.** M2 (2026-07-02)
  ilə bütün 18 tarixi cüt əridilib — baseline
  (`scripts/module_deps_baseline.json`) SIFIRDIR və sıfır qalmalıdır.
- **`core/` HEÇ BİR app modulunu import edə bilməz** (shared-kernel təmizliyi).
  M3 (2026-07-02) ilə bütün core→apps kənarları əridilib (baseline: 0). App
  datası lazımdırsa `django_apps.get_model()` və ya hook registry işlədin
  (nümunələr: `core/audit.py`, `core/auth_otp.py`).
- Başqa modulun funksionallığına ehtiyac olduqda birbaşa servis-daxili import
  ƏVƏZİNƏ modulun `public.py` fasadını çağırın. M3-B (2026-07-02) ilə fasadlar
  MÖVCUDDUR: accounts, appeals, audit, contact, courses, exams, notifications,
  organizations, task_submission_core, trial_exams. Yeni cross-modul istehlak
  YALNIZ `apps.<modul>.public` üzərindən getməlidir; fasadda çatışmayan adı
  fasada əlavə edib istifadə edin. Modellər üçün ORM əlaqələri /
  `django_apps.get_model` qalır (fasadlar model re-export etmir).
- Dövr sağaldıqda `python scripts/module_deps.py --update` ilə baseline-i
  KİÇİLDİN (böyütmə yalnız PR-da açıq əsaslandırma ilə).

Dövr əritmək üçün təsdiqlənmiş 4 pattern (M2):

1. **Lazy signal sender**: `@receiver(post_save, sender="app_label.Model")` —
   model importu tam silinir (nümunə: `apps/notifications/signals.py`).
2. **Lazy model lookup**: `django_apps.get_model("app_label", "Model")` yalnız
   funksiya gövdəsində (nümunə: `apps/notifications/services/events.py`).
3. **Hook/registry genişlənmə nöqtəsi**: aşağı modul neytral default-lu hook
   modulu saxlayır, yuxarı modul `AppConfig.ready()`-də öz implementasiyasını
   `register()` edir (nümunələr: `apps/exams/score_adjustments.py` ←
   `apps/appeals/apps.py`; provider-list variantı
   `apps/courses/dashboard_sources.py` ← assignments/projects/labs
   `course_dashboard.py` provider-ləri). Optional inteqrasiyalar üçün ideal —
   try/except import blokları lazımsızlaşır.
4. **Lazy accessor funksiyası**: modul-səviyyə sabit əvəzinə çağırış anında
   həll olunan funksiya (nümunə: `apps/exams/constants.py` →
   `get_live_session_model()` / `get_live_active_states()`).

Yoxlama: `python scripts/module_deps.py --check` (hesabat üçün arqumentsiz).

---

## 6. Rol-əsaslı view skeleti (F-plan konvensiyası)

Təqdimat qatı ROL qovluqlarına bölünür, domen qatı (models/services) feature
modulunda rol-suz qalır. Etalon: `apps/exams/views/{student,teacher,shared}`.

```
apps/<modul>/views/
├── shared/     # rollar-arası ortaq (api, tenant helper-lər)
├── student/
├── teacher/
├── org_admin/  # owner/admin/dekan/kafedra
└── superadmin/
```

Qaydalar:
1. URL adları/yolları DƏYİŞMİR — `views/__init__.py` fasadı bütün mövcud
   import səthini qoruyur (bölmə 1-dəki paket-çevirmə pattern-i).
2. Alt-modul adı `endpoints.py` (AGENTS §1 toqquşma qaydası); köçürülən fayl
   öz adını saxlaya bilər (məs. `teacher/crud.py`).
3. Relative importlar mənbə faylın YENİ dərinliyinə görə bump olunur:
   views/ içindəki fayl üçün +1 (`..models` → `...models`), app-kökündəki
   köhnə views.py-dən views/<rol>/-a keçəndə +2 (`.constants` →
   `...constants`); `._helpers` → `..shared._helpers`.
4. Templates/static güzgü prinsipi: `templates/<modul>/{student,teacher,...}`.
5. Hər modul ayrıca PR: `manage.py check` + modul testləri + bu faylın §4
   yoxlama siyahısı MÜTLƏQ.
