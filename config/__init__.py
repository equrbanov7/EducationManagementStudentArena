# Expose the Celery application so that ``celery -A config`` works and
# Django tasks can use the ``@shared_task`` decorator.
from .celery import app as celery_app

__all__ = ["celery_app"]
