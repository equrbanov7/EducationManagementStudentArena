"""Staging inspection settings — browse rehearsal data in the real UI.

Bu modul YALNIZ lokal "staging inspection" mühiti üçündür: legacy köçürmə
məşqinin (rehearsal) nəticələrini həqiqi EMS Arena UI-ında nəzərdən keçirmək.
Heç bir yerdən (``base``/``production``) import olunmur və olunmamalıdır.

İki kilid (interlock) var — hər ikisi keçmədən modul yüklənmir:

1. ``EMS_STAGING_INSPECT=1`` env dəyişəni açıq olmalıdır (təsadüfən bu
   settings modulu ilə işə salma qarşısı).
2. ``DATABASES["default"]`` mütləq lokal staging PostgreSQL-ə (127.0.0.1 /
   localhost, ``EMS_STAGING_DB_PORT``, ``EMS_STAGING_DB_NAME``) baxmalıdır —
   yəni dev DB-yə (``emsarena_db`` @ 5432) və ya production-a heç vaxt yox.

``local.py``-dakı ``load_dotenv(...)`` çağırışı ``override=False`` ilə işlədiyi
üçün launcher-in export etdiyi ``DATABASE_URL`` və digər dəyişənlər ``.env``
dəyərlərini üstələyir — ``.env``-ə toxunmağa ehtiyac yoxdur.
"""

from __future__ import annotations

import os

from django.core.exceptions import ImproperlyConfigured

from .local import *  # noqa: F401,F403
from .local import DATABASES  # noqa: F401  (interlock 2 üçün açıq idxal)

# ---------------------------------------------------------------------------
# Interlock 1 — açıq opt-in tələb olunur
# ---------------------------------------------------------------------------
if os.getenv("EMS_STAGING_INSPECT") != "1":
    raise ImproperlyConfigured(
        "config.settings.staging_inspect yalnız staging inspection mühitində "
        "istifadə olunur. Açıq opt-in tələb olunur: EMS_STAGING_INSPECT=1. "
        "Adi lokal iş üçün config.settings.local işlədin, staging inspection "
        "üçün isə scripts/staging_inspect.sh."
    )

# ---------------------------------------------------------------------------
# Interlock 2 — DB mütləq lokal staging instansiyası olmalıdır
# ---------------------------------------------------------------------------
EMS_STAGING_DB_NAME = os.getenv("EMS_STAGING_DB_NAME", "emsarena_staging")
EMS_STAGING_DB_PORT = os.getenv("EMS_STAGING_DB_PORT", "55433")

_default_db = DATABASES.get("default") or {}
_db_host = str(_default_db.get("HOST") or "")
_db_port = str(_default_db.get("PORT") or "")
_db_name = str(_default_db.get("NAME") or "")

if _db_host not in {"127.0.0.1", "localhost"} or _db_port != EMS_STAGING_DB_PORT or _db_name != EMS_STAGING_DB_NAME:
    raise ImproperlyConfigured(
        "staging_inspect settings yalnız ayrılmış lokal staging PostgreSQL-ə "
        "qoşula bilər. "
        f"Gözlənilən: host 127.0.0.1|localhost, port {EMS_STAGING_DB_PORT}, "
        f"baza {EMS_STAGING_DB_NAME}. "
        f"Alınan: host {_db_host or '(yoxdur)'}, port {_db_port or '(yoxdur)'}, "
        f"baza {_db_name or '(yoxdur)'}. "
        "DATABASE_URL-i staging DSN-inə yönləndirin "
        "(scripts/staging_inspect.sh dsn)."
    )

# ---------------------------------------------------------------------------
# Sərt override-lar — inspection mühiti heç nəyə "sızmamalıdır"
# ---------------------------------------------------------------------------
# Rehearsal datasında real e-poçt ünvanları var; SMTP-yə heç bir halda çıxma.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Ayrı cookie adları: eyni brauzerdə açıq dev sessiyası (127.0.0.1:8000) ilə
# staging inspection sessiyası (127.0.0.1:8100) bir-birini əvəz etməsin.
SESSION_COOKIE_NAME = "emsarena_staging_sessionid"
CSRF_COOKIE_NAME = "emsarena_staging_csrftoken"

# RLS rol yoxlaması (apps/organizations/checks.py): default olaraq "error" —
# yəni superuser/BYPASSRLS rolu ilə xidmət göstərmək bloklanır, beləliklə
# inspection production-un RLS davranışını güzgüləyir. Miqrasiya addımı bunu
# qəsdən "off" ilə çağırır (miqrasiyalar owner rolunda qanunidir).
EMS_DB_ROLE_ENFORCE = os.getenv("EMS_DB_ROLE_ENFORCE", "error")

# core/management/command_safety.py üçün: bu mühit production deyil.
MANAGEMENT_COMMAND_ENVIRONMENT = "local"
