"""
WSGI config for EMS Arena project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application


def _require_settings_module() -> None:
    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        raise RuntimeError("DJANGO_SETTINGS_MODULE must be set before loading config.wsgi.")


_require_settings_module()

application = get_wsgi_application()
