"""
ASGI config for blogApp project.

HTTP request-lər üçün Django ASGI app,
WebSocket (real-time) üçün isə Django Channels routing istifadə olunur.
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

import liveExam.routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "blogApp.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(liveExam.routing.websocket_urlpatterns)
        ),
    }
)
