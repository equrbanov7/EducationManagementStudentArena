"""
apps/live_exam/api/v1/urls.py

URL patterns for the Live Exam API v1.
"""

from django.urls import path

from . import views

app_name = "live_exam_api_v1"

urlpatterns = [
    path("live/<str:pin>/state/", views.live_state_json_v1, name="state_json"),
]
