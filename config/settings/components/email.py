"""EMS Arena base settings — email komponenti.

Bu fayl `config/settings/base.py` tərəfindən paylaşılan namespace-də
`exec`-include olunur (django-split-settings üslubu). Ona görə burada
ayrıca import yoxdur — os, Path, messages, CSP sabitləri və `_env_*`
köməkçiləri base.py-dən gəlir. Sıra base.py-dəki _COMPONENTS siyahısı ilə
idarə olunur (asılılıqlar: bax base.py).
"""

# flake8: noqa: F821  (paylaşılan namespace: adlar base.py-dən gəlir)

# Email base settings (to be overridden in environment-specific settings)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in {"1", "true", "yes", "on"}
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() in {"1", "true", "yes", "on"}
EMAIL_HOST_USER = os.getenv("BREVO_SMTP_LOGIN") or os.getenv("BREVO_EMAIL") or os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("BREVO_SMTP_KEY") or os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or os.getenv("BREVO_FROM_EMAIL") or "no-reply@qku.edu.az"
# SMTP socket timeout. Kept low so the request thread (or even background
# threads) cannot stall on an unresponsive SMTP host. Override via env if
# the upstream server is known-slow.
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "8"))
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

# ---------------------------------------------------------------------------
# Contact form notifications
# ---------------------------------------------------------------------------
# Inbound public contact form submissions are delivered to this address.
# These are brand-neutral fallbacks; set the real verified-sender addresses per
# deployment via the CONTACT_* / DEFAULT_FROM_EMAIL / BREVO_FROM_EMAIL env vars.
CONTACT_NOTIFY_EMAIL = os.getenv("CONTACT_NOTIFY_EMAIL", "info@qku.edu.az")
CONTACT_SUPPORT_EMAIL = os.getenv("CONTACT_SUPPORT_EMAIL", "support@qku.edu.az")
CONTACT_PUBLIC_EMAIL = os.getenv("CONTACT_PUBLIC_EMAIL", "info@qku.edu.az")

# Trial-exam ("sınaq imtahanı") request submissions are emailed here.
# Falls back to CONTACT_NOTIFY_EMAIL when unset. Max upload size (MB) caps
# the uploaded questions PDF.
TRIAL_NOTIFY_EMAIL = os.getenv("TRIAL_NOTIFY_EMAIL", "") or CONTACT_NOTIFY_EMAIL
TRIAL_EXAM_MAX_UPLOAD_MB = int(os.getenv("TRIAL_EXAM_MAX_UPLOAD_MB", "25"))

# Brevo (formerly Sendinblue) HTTP API key. Used as a fallback when SMTP
# fails (e.g., ISP blocks port 587). Generated in Brevo dashboard:
# Settings → SMTP & API → API Keys. Port 443 / HTTPS bypasses every
# port-blocking middlebox so this is the most reliable transport.
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
