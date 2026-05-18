from django.urls import path

from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("quota/", views.quota_view, name="quota"),
    path("chat/", views.chat_view, name="chat"),
]
