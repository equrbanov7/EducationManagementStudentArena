from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path("ws/live/<str:pin>/lobby/", consumers.LiveLobbyConsumer.as_asgi()),
    path("ws/live/<str:pin>/play/", consumers.LivePlayConsumer.as_asgi()),
]
