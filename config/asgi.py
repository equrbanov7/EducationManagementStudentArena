"""
ASGI config for EMS Arena project.

HTTP request-lər üçün Django ASGI app,
WebSocket (real-time) üçün isə Django Channels routing istifadə olunur.
"""

import os

from django.core.asgi import get_asgi_application

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# Django setup must happen BEFORE importing any app modules
django_asgi_app = get_asgi_application()

# Import routing AFTER Django setup (get_asgi_application() call above)
from apps.live_exam import routing

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(routing.websocket_urlpatterns)),
    }
)
