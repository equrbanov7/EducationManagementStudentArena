"""
Base settings for EMS Arena project.
Common settings shared across all environments.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from django.contrib.messages import constants as messages

from csp.constants import NONCE, NONE, SELF, UNSAFE_INLINE

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _redis_url_with_db(redis_url: str, db: int) -> str:
    parsed = urlsplit(redis_url)
    if not parsed.scheme or not parsed.netloc:
        return redis_url

    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts and path_parts[-1].isdigit():
        path_parts[-1] = str(db)
    else:
        path_parts.append(str(db))

    return urlunsplit(parsed._replace(path="/" + "/".join(path_parts)))


def _env_bool_setting(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int_setting(name: str, default: int, *, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _env_float_setting(name: str, default: float, *, minimum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


# ---------------------------------------------------------------------------
# Komponent-include (django-split-settings üslubu)
# ---------------------------------------------------------------------------
# Böyük tək-fayllı settings god-file-ını komponentlərə böldük. Hər komponent
# BU faylın qlobal namespace-ində `exec` olunur ki, enişli çarpaz-istinadlar
# (məs. CELERY_RESULT_BACKEND = CELERY_BROKER_URL, PASSWORD_RESET_TIMEOUT =
# AUTH_OTP_EXPIRY_SECONDS, CSP → MICROSOFT_CLARITY_*) davranışı DƏYİŞMƏDƏN
# işləsin. Sıra ƏHƏMİYYƏTLİDİR — asılılıq istiqamətinə görə düzülüb.
_COMPONENTS = [
    "apps",
    "celery_cache",
    "admin_ratelimit",
    "exam",
    "security",
    "i18n_static",
    "email",
    "integrations",
    "csp",
]
_COMPONENT_DIR = Path(__file__).resolve().parent / "components"
for _component_name in _COMPONENTS:
    _component_path = _COMPONENT_DIR / f"{_component_name}.py"
    exec(  # noqa: S102 — daxili, versiyalanmış settings faylları; xarici input deyil
        compile(_component_path.read_text(encoding="utf-8"), str(_component_path), "exec")
    )

# ---------------------------------------------------------------------------
# Branding & deployment mode (e-university)
# ---------------------------------------------------------------------------
# The platform is white-labelled per deployment. Default brand is the Western
# Caspian University; override with SITE_BRAND_NAME. Templates show a translated
# brand string, while this value is the canonical name used in SEO/structured
# data and page titles.
SITE_BRAND_NAME = os.getenv("SITE_BRAND_NAME", "Qərbi Kaspi Universiteti")
SITE_BRAND_SHORT = os.getenv("SITE_BRAND_SHORT", "QKU")

# UNIVERSITY_MODE hides the public marketing surfaces (home/blog/about/contact
# and the top-nav exam/create shortcuts) so that, like UNEC's EDUMAN / kabinet,
# the platform is a login → personal-cabinet portal rather than a marketing
# site. The pages/routes still exist (deactivated), so this can be flipped off
# to restore the full marketing UI.
UNIVERSITY_MODE = _env_bool_setting("UNIVERSITY_MODE", True)
