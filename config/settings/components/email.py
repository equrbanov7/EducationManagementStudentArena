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
# Sahib 2026-10-16: info@/support@/no-reply@ qutuları YOXDUR. Env verilməyibsə göndərici — real
# default M365 qutusu (EMAIL_HOST_USER, verification@); o da yoxdursa Django-nun öz defaultu.
DEFAULT_FROM_EMAIL = (
    os.getenv("DEFAULT_FROM_EMAIL")
    or os.getenv("BREVO_FROM_EMAIL")
    or (os.getenv("EMAIL_HOST_USER") or "").strip()
    or "webmaster@localhost"
)
# Sahibin qərarı (2026-09-15): göndərici (From) Brevo-da təsdiqlənmiş domen qalır,
# cavab ünvanı (Reply-To) isə universitetin ünvanı — domen təsdiqlənənə qədər.
# Boşdursa Reply-To başlığı əlavə olunmur. Bütün sistem məktubları
# (`core.mailing.system_email_headers`) bunu işlədir.
EMAIL_REPLY_TO = (os.getenv("EMAIL_REPLY_TO") or "").strip()
# Sahib 2026-10-01: universitet poçtu (Microsoft 365) — parol bərpası ayrıca recovery@ qutusundan.
# Hər ikisi doludursa core.mailing.sender_for("password_reset") onu qaytarır və
# core.mail_backend.AccountRoutingEmailBackend həmin hesabla daxil olur. Boşdursa əvvəlki davranış.
EMAIL_RECOVERY_HOST_USER = (os.getenv("EMAIL_RECOVERY_HOST_USER") or "").strip()
EMAIL_RECOVERY_HOST_PASSWORD = os.getenv("EMAIL_RECOVERY_HOST_PASSWORD") or ""
# From-da görünən ad (boşdursa SITE_BRAND_NAME).
EMAIL_FROM_NAME = (os.getenv("EMAIL_FROM_NAME") or "").strip()
# SMTP socket timeout. Kept low so the request thread (or even background
# threads) cannot stall on an unresponsive SMTP host. Override via env if
# the upstream server is known-slow.
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "8"))
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

# ---------------------------------------------------------------------------
# Contact form notifications
# ---------------------------------------------------------------------------
# Sahib 2026-10-16: təsdiqlənmiş ümumi qutu (info@/support@) yoxdur — default BOŞDUR.
# * CONTACT_NOTIFY_EMAIL boşdursa əlaqə formu bildirişi aktiv superuser-lərin e-poçtlarına gedir
#   (core.mailing.staff_notify_recipients); vergüllə bir neçə ünvan yazmaq olar.
# * CONTACT_SUPPORT_EMAIL / CONTACT_PUBLIC_EMAIL boşdursa sayt altlığında, əlaqə səhifəsində və
#   e-poçt altlığında həmin sətir/blok gizlənir.
CONTACT_NOTIFY_EMAIL = (os.getenv("CONTACT_NOTIFY_EMAIL") or "").strip()
CONTACT_SUPPORT_EMAIL = (os.getenv("CONTACT_SUPPORT_EMAIL") or "").strip()
CONTACT_PUBLIC_EMAIL = (os.getenv("CONTACT_PUBLIC_EMAIL") or "").strip()

# Trial-exam ("sınaq imtahanı") request submissions are emailed here.
# Falls back to CONTACT_NOTIFY_EMAIL, then to the active superusers. Max upload
# size (MB) caps the uploaded questions PDF.
TRIAL_NOTIFY_EMAIL = (os.getenv("TRIAL_NOTIFY_EMAIL") or "").strip() or CONTACT_NOTIFY_EMAIL
TRIAL_EXAM_MAX_UPLOAD_MB = int(os.getenv("TRIAL_EXAM_MAX_UPLOAD_MB", "25"))

# Brevo (formerly Sendinblue) HTTP API key. Used as a fallback when SMTP
# fails (e.g., ISP blocks port 587). Generated in Brevo dashboard:
# Settings → SMTP & API → API Keys. Port 443 / HTTPS bypasses every
# port-blocking middlebox so this is the most reliable transport.
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
