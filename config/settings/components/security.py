"""EMS Arena base settings — security komponenti.

Bu fayl `config/settings/base.py` tərəfindən paylaşılan namespace-də
`exec`-include olunur (django-split-settings üslubu). Ona görə burada
ayrıca import yoxdur — os, Path, messages, CSP sabitləri və `_env_*`
köməkçiləri base.py-dən gəlir. Sıra base.py-dəki _COMPONENTS siyahısı ilə
idarə olunur (asılılıqlar: bax base.py).
"""

# flake8: noqa: F821  (paylaşılan namespace: adlar base.py-dən gəlir)

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Login / logout settings
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# ---------------------------------------------------------------------------
# Session timeout settings
# ---------------------------------------------------------------------------
# Absolute lifetime of the session cookie (seconds).  After this period the
# browser discards the cookie and the user must log in again regardless of
# activity.  Default: 7 days.
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", str(7 * 24 * 60 * 60)))

# Expire the session cookie when the browser is closed (no persistent cookie).
# Set to True for higher-security deployments; False keeps the cookie across
# browser restarts up to SESSION_COOKIE_AGE.
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Inactivity timeout enforced by SessionTimeoutMiddleware (seconds).
# Users who have not made any request within this window are automatically
# logged out on their next request, even if SESSION_COOKIE_AGE has not yet
# elapsed.  Default: 3 days.
SESSION_INACTIVITY_TIMEOUT = int(os.getenv("SESSION_INACTIVITY_TIMEOUT", str(3 * 24 * 60 * 60)))

# ---------------------------------------------------------------------------
# Session storage backend (performance)
# ---------------------------------------------------------------------------
# Default to ``cached_db``: session reads are served from Redis (no DB hit on
# every authenticated request) while writes still persist to the DB so a Redis
# restart does not log everyone out mid-exam. Combined with the throttled
# ``last_activity`` write in SessionTimeoutMiddleware (see below), this removes
# the per-request session write that previously serialised authenticated
# traffic on the database under load. Override with SESSION_ENGINE=... if a
# deployment prefers pure-cache or pure-db sessions.
SESSION_ENGINE = os.getenv("SESSION_ENGINE", "django.contrib.sessions.backends.cached_db")
SESSION_CACHE_ALIAS = os.getenv("SESSION_CACHE_ALIAS", "default")

# SessionTimeoutMiddleware records the last activity timestamp on the session.
# Writing it on EVERY request marks the session dirty and forces a save (and a
# DB write under cached_db/db) on every hit. Instead we only persist the
# timestamp once per this interval; inactivity is still enforced accurately
# because the stored value is at most this many seconds stale relative to the
# multi-hour inactivity timeout. Default: 5 minutes.
SESSION_ACTIVITY_WRITE_INTERVAL = int(os.getenv("SESSION_ACTIVITY_WRITE_INTERVAL", str(5 * 60)))

# ---------------------------------------------------------------------------
# Cookie security settings
# ---------------------------------------------------------------------------
# Session cookie: HttpOnly prevents JS access; Lax blocks cross-site POST.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# CSRF cookie: SameSite=Lax protects against CSRF on cross-site requests.
# HttpOnly must be False so the JS CSRF helper can read the token.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# Custom CSRF failure view: logs full diagnostic context (reason, Origin,
# Referer, CF-Ray, cookie presence) and shows a user-friendly page instead of
# Django's bare 403.  Used to pinpoint the source of production login 403s
# (Django CSRF vs Cloudflare).
CSRF_FAILURE_VIEW = "core.views.csrf_failure"

# Language cookie: HttpOnly and SameSite to protect the i18n cookie
# set by /i18n/setlang/.
LANGUAGE_COOKIE_HTTPONLY = True
LANGUAGE_COOKIE_SAMESITE = "Lax"

# ---------------------------------------------------------------------------
# Security headers (apply to all environments; stricter values in production)
# ---------------------------------------------------------------------------
# Prevent the browser from MIME-sniffing a response away from the declared
# content-type.
SECURE_CONTENT_TYPE_NOSNIFF = True

# Instruct browsers not to render this site inside a frame (clickjacking).
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = os.getenv("REFERRER_POLICY", "strict-origin-when-cross-origin")

# Additional response headers that tighten browser-side defaults without
# requiring per-view duplication.
#
# An env var set to an empty string ("") removes the header — useful in HTTP
# dev where browsers ignore the COOP header anyway and only emit a noisy
# console warning ("origin was untrustworthy"). Production must always send
# the header, so we keep "same-origin" as the default.
SECURITY_RESPONSE_HEADERS = {
    k: v
    for k, v in {
        "Referrer-Policy": SECURE_REFERRER_POLICY,
        "Permissions-Policy": os.getenv(
            "PERMISSIONS_POLICY",
            "camera=(), geolocation=(), microphone=()",
        ),
        "Cross-Origin-Resource-Policy": os.getenv("CROSS_ORIGIN_RESOURCE_POLICY", "same-origin"),
        "Cross-Origin-Opener-Policy": os.getenv("CROSS_ORIGIN_OPENER_POLICY", "same-origin"),
    }.items()
    if v
}

# Authentication backends
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Password reset token expiry defaults to the same short-lived OTP window.
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", str(AUTH_OTP_EXPIRY_SECONDS)))
