"""
ASGI config for EMS Arena project.

Single ASGI entrypoint for both HTTP and WebSocket traffic so production
deployments can serve the live exam experience in real time.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

# Import routing only after Django app registry is ready.
from apps.live_exam.routing import websocket_urlpatterns

websocket_application = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": websocket_application,
    }
)
