"""
WSGI config for EMS Arena project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import time
from pathlib import Path

from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")


def _bootstrap_tmp_sqlite() -> None:
    """
    Vercel-də /tmp SQLite istifadə olunursa ilk cold-start-da migrasiyaları tətbiq et.
    """
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url.startswith("sqlite:////tmp/"):
        return

    marker = Path("/tmp/.emsarena_migrated")
    if marker.exists():
        return

    lock = Path("/tmp/.emsarena_migrating.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # Başqa request migrate edir; qısa müddət marker gözlə.
        for _ in range(50):
            if marker.exists():
                return
            time.sleep(0.1)
        return

    try:
        import django

        django.setup()
        call_command("migrate", interactive=False, run_syncdb=True, verbosity=0)
        marker.touch(exist_ok=True)
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


_bootstrap_tmp_sqlite()

application = get_wsgi_application()
