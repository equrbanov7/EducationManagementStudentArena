from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/exams/supervision/<int:attempt_id>/", consumers.ExamSupervisionConsumer.as_asgi()),
]
