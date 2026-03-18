"""
ASGI config for EMS Arena project.

Single ASGI entrypoint for both HTTP and WebSocket traffic so production
deployments can serve the live exam experience in real time.
"""

import os


def _require_settings_module() -> None:
    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        raise RuntimeError("DJANGO_SETTINGS_MODULE must be set before loading config.asgi.")


_require_settings_module()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

# Import routing only after Django app registry is ready.
from apps.live_exam.routing import websocket_urlpatterns

websocket_application = AllowedHostsOriginValidator(
    AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": websocket_application,
    }
)
