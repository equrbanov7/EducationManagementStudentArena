from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/exams/supervision/<int:attempt_id>/", consumers.ExamSupervisionConsumer.as_asgi()),
    # Final imtahan mərkəzi — otaq monitoru (heyət) və gözləmə otağı (tələbə).
    path("ws/exams/final/room/<int:session_id>/", consumers.FinalExamRoomConsumer.as_asgi()),
    path("ws/exams/final/wait/<int:ticket_id>/", consumers.FinalExamWaitConsumer.as_asgi()),
]
