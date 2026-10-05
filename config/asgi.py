"""
ASGI config for EMS Arena project.

Single ASGI entrypoint for both HTTP and WebSocket traffic so production
deployments can serve the live exam experience in real time.
"""

import os


def _require_settings_module() -> None:
    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        raise RuntimeError("DJANGO_SETTINGS_MODULE must be set before loading config.asgi.")


def _apply_asgi_threads_under_uvicorn() -> None:
    """``ASGI_THREADS``-i uvicorn altında da default executor ölçüsünə çevirir.

    Daphne bunu ``daphne.server`` importunda öz loop-u üçün edir; uvicorn isə
    env-i oxumur (defolt ``min(32, cpu+4)``). Uvicorn tətbiqi işləyən loop daxilində
    import edir, ona görə burada həmin loop-a eyni ölçülü pool qoyulur. Yalnız
    ``ASGI_SERVER=uvicorn`` (docker/prod-entrypoint.sh) — Daphne/testlər toxunulmur.
    """
    if os.environ.get("ASGI_SERVER", "").strip().lower() != "uvicorn":
        return
    try:
        threads = int(os.environ.get("ASGI_THREADS", "").strip())
    except ValueError:
        return
    if threads < 1:
        return
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.set_default_executor(ThreadPoolExecutor(max_workers=threads, thread_name_prefix="asgi"))


_require_settings_module()
_apply_asgi_threads_under_uvicorn()

from django.core.asgi import get_asgi_application

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

django_asgi_app = get_asgi_application()

# Import routing only after Django app registry is ready.
from apps.exams.routing import websocket_urlpatterns as exams_ws_urlpatterns
from apps.live_exam.routing import websocket_urlpatterns as live_exam_ws_urlpatterns

all_websocket_urlpatterns = live_exam_ws_urlpatterns + exams_ws_urlpatterns

websocket_application = AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(all_websocket_urlpatterns)))

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": websocket_application,
    }
)
