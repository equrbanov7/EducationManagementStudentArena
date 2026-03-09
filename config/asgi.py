"""
ASGI config for EMS Arena project.

HTTP request-lər üçün Django ASGI app,
WebSocket (real-time) üçün isə Django Channels routing istifadə olunur.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from django.core.asgi import get_asgi_application

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

django_asgi_app = get_asgi_application()

# Import routing only after Django app registry is ready.
from apps.live_exam import routing


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(routing.websocket_urlpatterns)),
    }
)
