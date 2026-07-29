"""EMS Arena base settings — celery_cache komponenti.

Bu fayl `config/settings/base.py` tərəfindən paylaşılan namespace-də
`exec`-include olunur (django-split-settings üslubu). Ona görə burada
ayrıca import yoxdur — os, Path, messages, CSP sabitləri və `_env_*`
köməkçiləri base.py-dən gəlir. Sıra base.py-dəki _COMPONENTS siyahısı ilə
idarə olunur (asılılıqlar: bax base.py).
"""

# flake8: noqa: F821  (paylaşılan namespace: adlar base.py-dən gəlir)

# Channel Layers for WebSocket support
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
REDIS_CACHE_URL = _redis_url_with_db(REDIS_URL, 1)
CELERY_BROKER_URL = _redis_url_with_db(REDIS_URL, 2)

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            # Live-proctor fan-out at 5000 WS: buffer more per channel before
            # dropping, and shed stale events faster than the 60s library default.
            "capacity": _env_int_setting("CHANNEL_LAYER_CAPACITY", 1500, minimum=100),
            "expiry": _env_int_setting("CHANNEL_LAYER_EXPIRY", 20, minimum=5),
        },
    },
}

# Cache configuration (sessions/cached_db, rate-limits, request-queue + exam-start
# locks all hit this alias). Bound the socket so a slow/saturated Redis fails fast
# (callers already tolerate cache errors) instead of hanging a scarce sync worker
# thread forever, which would take the whole app down under exam-day peak.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "OPTIONS": {
            # django.core.cache RedisCache passes OPTIONS straight to redis-py's
            # ConnectionPool.from_url — use redis-py's lowercase kwarg names
            # (NOT the uppercase django-redis third-party names).
            "socket_connect_timeout": _env_int_setting("REDIS_CACHE_CONNECT_TIMEOUT", 2, minimum=1),
            "socket_timeout": _env_int_setting("REDIS_CACHE_TIMEOUT", 2, minimum=1),
            "max_connections": _env_int_setting("REDIS_CACHE_MAX_CONNECTIONS", 100, minimum=10),
        },
    }
}

# ─────────────────────────────────────────────────────────────────────────
# Celery — background task processing
# Broker: Redis DB 2  |  Results: Redis DB 2  |  Worker: see docker-compose
# ─────────────────────────────────────────────────────────────────────────
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Baku"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes hard limit per task
CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4 minutes soft limit (raises SoftTimeLimitExceeded)

# ── Queue separation (audit: the single highest-leverage change) ──────────────
# Heavy/bursty jobs (OCR, AI generation, Excel export) go to a dedicated "heavy"
# queue consumed by the celery_worker_heavy pool, so a slow OCR/AI job can NEVER
# starve the latency-sensitive 60s attempt-expiry sweeps + notifications, which
# stay on the default "celery" queue.
CELERY_TASK_DEFAULT_QUEUE = "celery"
CELERY_TASK_ROUTES = {
    "exams.run_text_extraction_job": {"queue": "heavy"},
    "exams.run_ai_generation_job": {"queue": "heavy"},
    "exams.run_export_job": {"queue": "heavy"},
}
# A long OCR/AI job must not hold prefetched slots hostage; re-queue on crash.
CELERY_WORKER_PREFETCH_MULTIPLIER = _env_int_setting("CELERY_PREFETCH_MULTIPLIER", 1, minimum=1)
CELERY_TASK_ACKS_LATE = True
# Bound the Redis result backend so it can't grow unbounded under maxmemory-noeviction.
CELERY_RESULT_EXPIRES = _env_int_setting("CELERY_RESULT_EXPIRES", 3600, minimum=60)

# Periodic tasks (require running `celery -A config beat`).
# crontab lokal ad kimi qalır (kiçik hərf → Django setting olmur); beat
# cədvəlindəki gündəlik fixed-time işlər üçün lazımdır.
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Auto-finish supervised attempts whose resume window elapsed without the
    # student returning.  Runs every minute so the supervision monitor never
    # shows stale open rows long after an exam has ended.
    "exams-expire-stale-resumed-attempts": {
        "task": "exams.expire_stale_resumed_attempts",
        "schedule": 60.0,  # seconds
    },
    # Vaxtı bitmiş (deadline-ı keçmiş) draft/in_progress cəhdləri avtomatik
    # bitirir ki, imtahan heç yerdə (zal monitoru, müəllim nəzarəti, nəticə)
    # "gözləmədə/davam edir" kimi ilişib qalmasın — tələbənin brauzeri bağlı
    # olub client-side avtomatik təqdim işləməsə belə. Hər dəqiqə.
    "exams-expire-overdue-attempts": {
        "task": "exams.expire_overdue_attempts",
        "schedule": 60.0,  # seconds
    },
    # Final imtahanı yaxınlaşan tələbələrə xatırlatma bildirişi (saatda bir).
    # Dublikat FinalExamTicket.reminder_stage ilə əngəllənir, ona görə saatlıq
    # işləmə spam yaratmır.
    "exams-notify-upcoming-final-exams": {
        "task": "exams.notify_upcoming_final_exams",
        "schedule": 3600.0,  # seconds
    },
    # EXAM-P1-15: crash olub PROCESSING-də ilişmiş text-extraction/AI job-ları
    # lease vaxtından sonra FAILED-ə keçir ki, istifadəçi yenidən cəhd edə bilsin.
    "exams-reap-stuck-extraction-jobs": {
        "task": "exams.reap_stuck_extraction_jobs",
        "schedule": 300.0,  # seconds
    },
    "exams-purge-expired-import-stashes": {
        "task": "exams.purge_expired_import_stashes",
        "schedule": 3600.0,  # seconds
    },
    # Sistem Monitorinqi: worker/queue statistikası cache-ə → /metrics/
    # gauge-ları (CeleryWorkersDown/CeleryBeatStale alert-lərinin mənbəyi).
    "monitoring-collect-celery-stats": {
        "task": "monitoring.collect_celery_stats",
        "schedule": 60.0,  # seconds
    },
    # Backup təzəliyi (BackupTooOld alerti üçün) — 15 dəqiqədən bir.
    "monitoring-collect-backup-age": {
        "task": "monitoring.collect_backup_age",
        "schedule": 900.0,  # seconds
    },
    # Gün sonu təhlükəsizlik süpürgəsi: hər gün 22:00-da (Asia/Baku) hələ açıq
    # qalmış zal oturumlarını avtomatik bağlayır — aktivləri bitirir, giriş açıq
    # amma başlamamışları ləğv edir. Heç bir imtahan gecəyə qalmasın deyə.
    "exams-auto-close-daily-room-sessions": {
        "task": "exams.auto_close_daily_room_sessions",
        "schedule": crontab(hour=22, minute=0),
    },
}
