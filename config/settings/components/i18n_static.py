"""EMS Arena base settings — i18n_static komponenti.

Bu fayl `config/settings/base.py` tərəfindən paylaşılan namespace-də
`exec`-include olunur (django-split-settings üslubu). Ona görə burada
ayrıca import yoxdur — os, Path, messages, CSP sabitləri və `_env_*`
köməkçiləri base.py-dən gəlir. Sıra base.py-dəki _COMPONENTS siyahısı ilə
idarə olunur (asılılıqlar: bax base.py).
"""

# flake8: noqa: F821  (paylaşılan namespace: adlar base.py-dən gəlir)

# Internationalization
LANGUAGE_CODE = "az"
LANGUAGES = [
    ("az", "Azərbaycan dili"),
    ("en", "English"),
    ("ru", "Русский"),
    ("tr", "Türkçe"),
]
LOCALE_PATHS = [
    BASE_DIR / "locale",
]
TIME_ZONE = "Asia/Baku"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
# WhiteNoise adds a wildcard ACAO header by default; keep static assets same-origin
# unless cross-origin delivery is explicitly configured at the edge.
WHITENOISE_ALLOW_ALL_ORIGINS = False

# Media files (Uploaded by users)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
SERVE_MEDIA = False
FILE_UPLOAD_SECURITY_MAX_SIZE_MB = int(os.getenv("FILE_UPLOAD_SECURITY_MAX_SIZE_MB", "25"))
OBJECT_STORAGE_ENABLED = _env_bool_setting("OBJECT_STORAGE_ENABLED", False)
METRICS_ALLOW_ANONYMOUS = _env_bool_setting("METRICS_ALLOW_ANONYMOUS", False)

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
