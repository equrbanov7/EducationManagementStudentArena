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
        },
    },
}

# Cache configuration (used for rate limiting and sessions)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
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

# Periodic tasks (require running `celery -A config beat`).
CELERY_BEAT_SCHEDULE = {
    # Auto-finish supervised attempts whose resume window elapsed without the
    # student returning.  Runs every minute so the supervision monitor never
    # shows stale open rows long after an exam has ended.
    "exams-expire-stale-resumed-attempts": {
        "task": "exams.expire_stale_resumed_attempts",
        "schedule": 60.0,  # seconds
    },
}
