# AGENTS.md — EMSArena üçün AI agent qaydaları

Bu fayl Codex / Claude Code / digər AI agentlərinin bu repozitoriyada task həll
edərkən riayət etməli olduğu qaydaları təyin edir. **Dəyişiklik etməzdən əvvəl
oxuyun.**

---

## 1. Modul ölçüsü — "god-file" yaratma / böyütmə (MƏCBURİ)

Böyük tək-fayllı modullar (1000+ sətir view/servis) oxunması, test edilməsi və
təhlükəsiz dəyişdirilməsi çətindir. Ona görə **sərt qayda** var:

- **Yeni `.py` faylı ≤ 600 sətir** olmalıdır (`SOFT_CAP`).
- Mövcud böyük fayllar `scripts/module_size_budget.json`-da **dondurulub
  (ratchet)**: onlara yeni sətir əlavə edib **böyütmək qadağandır** — yalnız
  kiçildə bilərsiniz.
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

Diqqət: testlər `patch.object(module, "Name")` istifadə edirsə, həmin `Name`-i
işlədən funksiya onu **call-time fasaddan** həll etməlidir (yoxsa mock alt-modula
təsir etməz). Real nümunə: `apps/exams/services/parsing/extraction.py` →
`extract_text_from_upload`.

İstinad nümunəsi (artıq bölünmüş): `apps/exams/services/parsing/`.

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
