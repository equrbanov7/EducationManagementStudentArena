from django.urls import path

from .views import trial_exam_request_page

app_name = "trial_exams"

urlpatterns = [
    path("trial-exam/", trial_exam_request_page, name="request"),
]
