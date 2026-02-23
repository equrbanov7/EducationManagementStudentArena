"""
ASGI config for EMS Arena project.

HTTP request-lər üçün Django ASGI app,
WebSocket (real-time) üçün isə Django Channels routing istifadə olunur.
"""
import os

from django.core.asgi import get_asgi_application

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

# Import routing after Django setup
from apps.live_exam import routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

django_asgi_app = get_asgi_application()


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(routing.websocket_urlpatterns)),
    }
)
