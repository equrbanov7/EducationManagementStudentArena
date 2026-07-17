"""EMS Arena base settings — exam komponenti.

Bu fayl `config/settings/base.py` tərəfindən paylaşılan namespace-də
`exec`-include olunur (django-split-settings üslubu). Ona görə burada
ayrıca import yoxdur — os, Path, messages, CSP sabitləri və `_env_*`
köməkçiləri base.py-dən gəlir. Sıra base.py-dəki _COMPONENTS siyahısı ilə
idarə olunur (asılılıqlar: bax base.py).
"""

# flake8: noqa: F821  (paylaşılan namespace: adlar base.py-dən gəlir)

# Autosave interval. Cavablar dərhal brauzer localStorage-inə yazılır; server
# DB yazıları bu intervalla batch olunur. QEYD (2026-07-13): əvvəlki 5 dəq
# nəzarətçinin "çiyni üzərindən" canlı görüntüsünü faktiki yararsız edirdi
# (snapshot serverdəki answers-i oxuyur → 5 dəq gecikmə). LAN exam-center
# miqyasında 30s həm canlı monitorinqi işlək edir, həm yükü məqbul saxlayır.
# .env ilə override oluna bilər (böyük miqyasda artırın).
EXAM_AUTOSAVE_INTERVAL_MS = _env_int_setting("EXAM_AUTOSAVE_INTERVAL_MS", 30_000, minimum=10_000)
EXAM_AUTOSAVE_JITTER_MS = _env_int_setting("EXAM_AUTOSAVE_JITTER_MS", 10_000, minimum=0)
EXAM_AUTOSAVE_BINARY_UPLOADS_ENABLED = _env_bool_setting("EXAM_AUTOSAVE_BINARY_UPLOADS_ENABLED", False)

# Written-answer uploads are accepted on explicit save/submit, but kept tight
# so a single student cannot push large multipart or canvas payloads repeatedly.
EXAM_ANSWER_FILE_MAX_SIZE_MB = _env_int_setting("EXAM_ANSWER_FILE_MAX_SIZE_MB", 5, minimum=1)
EXAM_ANSWER_MAX_FILES_PER_QUESTION = _env_int_setting("EXAM_ANSWER_MAX_FILES_PER_QUESTION", 3, minimum=1)
EXAM_PAINT_MAX_BASE64_CHARS = _env_int_setting("EXAM_PAINT_MAX_BASE64_CHARS", 1_500_000, minimum=100_000)

# --- HTTP form body limits (Django request parsing) -------------------------
# When a student finishes a WRITTEN exam the whole form is re-submitted, so the
# request carries one text field per question PLUS the canvas/paint answers,
# which travel as base64 *text* fields (`paint_data_<qid>`), not as file uploads.
# Django sums every non-file field against DATA_UPLOAD_MAX_MEMORY_SIZE (default
# 2.5MB) and counts the fields against DATA_UPLOAD_MAX_NUMBER_FIELDS (default
# 1000). A single drawn answer can be ~1.5MB, so heavy/large exams silently trip
# RequestDataTooBig / TooManyFieldsSent → HTTP 400 raised during request parsing.
# That 400 is logged only to the `django.security` logger (no app traceback),
# which is why the server "looks fine" while some students cannot submit.
# File uploads stream to disk and do NOT count here; only text + paint do. We
# keep the ceiling under nginx `client_max_body_size` (64M) so oversized bodies
# still get a clean Django 400 instead of an opaque proxy 413.
DATA_UPLOAD_MAX_MEMORY_SIZE = _env_int_setting("DATA_UPLOAD_MAX_MEMORY_SIZE_MB", 50, minimum=3) * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = _env_int_setting("DATA_UPLOAD_MAX_NUMBER_FIELDS", 10_000, minimum=1_000)
# Sized to DB write capacity (pgbouncer pool ~150 / Postgres max_connections),
# NOT the legacy CPU cap. At 12/6 only a dozen students could start system-wide
# and the rest blocked a sync thread (sleep-poll) up to the wait timeout →
# simultaneous exam start froze the whole app. See docs/performance/OPTIMIZATION_5000_USERS.md.
EXAM_START_GLOBAL_CONCURRENCY = _env_int_setting("EXAM_START_GLOBAL_CONCURRENCY", 200, minimum=0)
EXAM_START_PER_EXAM_CONCURRENCY = _env_int_setting("EXAM_START_PER_EXAM_CONCURRENCY", 100, minimum=0)
EXAM_START_WAIT_TIMEOUT_SECONDS = _env_float_setting("EXAM_START_WAIT_TIMEOUT_SECONDS", 30.0, minimum=0.0)
EXAM_START_POLL_INTERVAL_SECONDS = _env_float_setting("EXAM_START_POLL_INTERVAL_SECONDS", 0.05, minimum=0.01)
EXAM_START_LOCK_LEASE_SECONDS = _env_int_setting("EXAM_START_LOCK_LEASE_SECONDS", 120, minimum=1)
EXAM_RANDOMIZER_USAGE_CACHE_SECONDS = _env_int_setting("EXAM_RANDOMIZER_USAGE_CACHE_SECONDS", 30, minimum=0)
EXAM_PDF_OCR_ENABLED = _env_bool_setting("EXAM_PDF_OCR_ENABLED", True)
EXAM_PDF_OCR_LANG = os.getenv("EXAM_PDF_OCR_LANG", "aze").strip() or "aze"
EXAM_PDF_OCR_DPI = _env_int_setting("EXAM_PDF_OCR_DPI", 160, minimum=72)
EXAM_PDF_OCR_MAX_PAGES = _env_int_setting("EXAM_PDF_OCR_MAX_PAGES", 40, minimum=1)
EXAM_PDF_OCR_HIGHLIGHT = _env_bool_setting("EXAM_PDF_OCR_HIGHLIGHT", True)
EXAM_PDF_OCR_HIGHLIGHT_MIN_RATIO = _env_float_setting("EXAM_PDF_OCR_HIGHLIGHT_MIN_RATIO", 0.10, minimum=0.0)

# --- Final imtahan mərkəzi (/exams/final/) giriş siyahısı --------------------
# Vergüllə ayrılmış IP və ya CIDR (məs. "10.0.0.5,192.168.10.0/24").
# BOŞ siyahı = hamıya açıq (hazırkı rejim). Doldurulanda yalnız bu
# ünvanlardan gələn sorğular final səhifəsinə girə bilir.
# QEYD: MAC ünvanı HTTP səviyyəsində serverə çatmır (yalnız lokal şəbəkə
# kadrlarında mövcuddur) — MAC-əsaslı məhdudiyyət gələcəkdə imtahan zalı
# şlüzü/agenti vasitəsilə tətbiq oluna bilər; server tərəfi IP/CIDR yoxlayır.
FINAL_EXAM_ALLOWED_IPS = [item.strip() for item in os.getenv("FINAL_EXAM_ALLOWED_IPS", "").split(",") if item.strip()]

# --- İmtahan zalı MAC yoxlaması (ARP agenti) ---------------------------------
# "off" → köhnə IP-əsaslı kompüter yoxlaması (dev/test default).
# "arp_agent" → müştəri MAC-ı host-un ARP cədvəlindən (docker/arp-agent
# sidecar-ı vasitəsilə) oxunur və ExamRoomComputer qeydləri MAC ilə
# tutuşdurulur — DHCP IP dəyişəndə giriş pozulmur. MAC yalnız serverlə eyni
# L2 seqmentdəki müştərilər üçün görünür; kənar/marşrutlanmış sorğular üçün
# MAC yoxdur → giriş rədd edilir (fail-closed).
EXAM_CLIENT_MAC_RESOLUTION = os.getenv("EXAM_CLIENT_MAC_RESOLUTION", "off").strip() or "off"
EXAM_ARP_AGENT_URL = os.getenv("EXAM_ARP_AGENT_URL", "http://172.18.0.1:8953").strip()
EXAM_ARP_AGENT_TIMEOUT_SECONDS = _env_float_setting("EXAM_ARP_AGENT_TIMEOUT_SECONDS", 0.5, minimum=0.05)

# --- Final imtahan PIN siyasəti ----------------------------------------------
# Hər tələbəyə imtahan üçün fərdi, kriptoqrafik təsadüfi PIN verilir.
# Saxlanma: salted hash (doğrulama) + Fernet şifrəli nüsxə (icazəli göstərmə);
# oturum bitdikdə şifrəli nüsxə silinir. Xam PIN log/URL-lərə düşmür.
FINAL_EXAM_PIN_LENGTH = _env_int_setting("FINAL_EXAM_PIN_LENGTH", 8, minimum=6)
# PIN oturumun planlaşdırılan sonundan neçə dəqiqə sonra avtomatik keçərsizləşir.
FINAL_EXAM_PIN_EXPIRY_GRACE_MINUTES = _env_int_setting("FINAL_EXAM_PIN_EXPIRY_GRACE_MINUTES", 120, minimum=0)
# Ardıcıl yanlış PIN cəhdlərindən sonra biletin müvəqqəti kilidi.
FINAL_EXAM_PIN_MAX_FAILURES = _env_int_setting("FINAL_EXAM_PIN_MAX_FAILURES", 5, minimum=3)
FINAL_EXAM_PIN_LOCK_MINUTES = _env_int_setting("FINAL_EXAM_PIN_LOCK_MINUTES", 10, minimum=1)
# Giriş səhifəsi üçün IP-əsaslı rate limit (cəhd / dəqiqə).
FINAL_EXAM_ENTRY_RATE_PER_MINUTE = _env_int_setting("FINAL_EXAM_ENTRY_RATE_PER_MINUTE", 10, minimum=3)
# Tələbə panelində PIN imtahan başlamazdan neçə dəqiqə əvvəl görünür.
# 0 = erkən pəncərə məhdudiyyəti YOXDUR → imtahan mərkəzi oturumu hazırlayıb PIN
# yaradan kimi tələbə öz PIN-ini kabinetdə görür ("həmin vaxt"). PIN yenə yalnız
# biletin öz sahibinə və oturum hazırlıq/giriş/aktiv fazasında göstərilir; oturum
# bitdikdə şifrəli nüsxə silinir. Erkən görünüşü məhdudlaşdırmaq üçün env ilə >0 verin.
FINAL_EXAM_PIN_VISIBILITY_MINUTES = _env_int_setting("FINAL_EXAM_PIN_VISIBILITY_MINUTES", 0, minimum=0)
# Final imtahan xatırlatma bildirişlərinin göndərildiyi eşiklər (gün, vergüllə).
# Hər eşik üçün bir dəfə (dublikat reminder_stage ilə əngəllənir).
FINAL_EXAM_REMINDER_DAYS = tuple(
    int(v.strip())
    for v in os.getenv("FINAL_EXAM_REMINDER_DAYS", "3,1").split(",")
    if v.strip().isdigit() and int(v.strip()) > 0
)


# Request queueing for mutating HTTP calls. This protects every app view from
# duplicate/bursty writes by serialising unsafe methods per user/session and by
# limiting concurrent write requests per worker process.
# Set REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT=1 if deployment needs strict
# one-write-at-a-time behaviour.
REQUEST_QUEUE_ENABLED = _env_bool_setting("REQUEST_QUEUE_ENABLED", True)
REQUEST_QUEUE_UNSAFE_METHODS = tuple(
    method.strip().upper()
    for method in os.getenv("REQUEST_QUEUE_UNSAFE_METHODS", "POST,PUT,PATCH,DELETE").split(",")
    if method.strip()
)
REQUEST_QUEUE_PER_ACTOR_SERIALIZATION = _env_bool_setting("REQUEST_QUEUE_PER_ACTOR_SERIALIZATION", True)
REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT = _env_int_setting("REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT", 8, minimum=0)
REQUEST_QUEUE_WAIT_TIMEOUT_SECONDS = _env_float_setting("REQUEST_QUEUE_WAIT_TIMEOUT_SECONDS", 60.0, minimum=0.0)
REQUEST_QUEUE_LOCK_POLL_INTERVAL_SECONDS = _env_float_setting(
    "REQUEST_QUEUE_LOCK_POLL_INTERVAL_SECONDS",
    0.05,
    minimum=0.01,
)
REQUEST_QUEUE_LOCK_LEASE_SECONDS = _env_int_setting("REQUEST_QUEUE_LOCK_LEASE_SECONDS", 600, minimum=1)
REQUEST_QUEUE_LOCAL_LOCK_TTL_SECONDS = _env_int_setting("REQUEST_QUEUE_LOCAL_LOCK_TTL_SECONDS", 300, minimum=1)
REQUEST_QUEUE_RETRY_AFTER_SECONDS = _env_int_setting("REQUEST_QUEUE_RETRY_AFTER_SECONDS", 2, minimum=1)
REQUEST_QUEUE_CACHE_ALIAS = os.getenv("REQUEST_QUEUE_CACHE_ALIAS", RATELIMIT_USE_CACHE)
# NOTE: Authentication / onboarding POST endpoints are intentionally excluded
# from the request queue. They are unauthenticated (so the per-actor lock keys
# every visitor behind a shared proxy IP onto the SAME lock, serialising all
# logins) and they must never be gated by the global write-concurrency
# semaphore — otherwise concurrent logins queue up to
# REQUEST_QUEUE_WAIT_TIMEOUT_SECONDS and time out under load. Authenticated
# mutating /accounts/ endpoints (profile, role/org management) are NOT listed
# here, so they keep their double-submit protection.
REQUEST_QUEUE_EXCLUDED_PATH_PREFIXES = tuple(
    prefix.strip()
    for prefix in os.getenv(
        "REQUEST_QUEUE_EXCLUDED_PATH_PREFIXES",
        (
            "/static/,/media/,/metrics/,/ping/,/health/,"
            "/accounts/login/,/accounts/register/,/accounts/verify-code/,"
            "/accounts/resend-code/,/accounts/send-otp/,/accounts/verify-otp/,"
            "/accounts/resend-otp/,/accounts/password-reset/,/accounts/reset/"
        ),
    ).split(",")
    if prefix.strip()
)
HEALTH_CHECK_CACHE_SECONDS = _env_float_setting("HEALTH_CHECK_CACHE_SECONDS", 2.0, minimum=0.0)
AUTH_OTP_EXPIRY_SECONDS = int(os.getenv("AUTH_OTP_EXPIRY_SECONDS", "300"))
AUTH_OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("AUTH_OTP_RESEND_COOLDOWN_SECONDS", "60"))
AUTH_OTP_MAX_ATTEMPTS = int(os.getenv("AUTH_OTP_MAX_ATTEMPTS", "5"))
AUTH_OTP_MAX_SENDS_PER_HOUR = int(os.getenv("AUTH_OTP_MAX_SENDS_PER_HOUR", "5"))
AUTH_PENDING_SIGNUP_TTL_SECONDS = int(os.getenv("AUTH_PENDING_SIGNUP_TTL_SECONDS", "86400"))
