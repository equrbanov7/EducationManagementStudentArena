"""Sistem Monitorinqi URL-ləri (hamısı superadmin-only API-lardır)."""

from django.urls import path

from . import views

app_name = "monitoring"

urlpatterns = [
    path("overview/", views.overview_api, name="overview"),
    path("server/", views.server_api, name="server"),
    path("containers/", views.containers_api, name="containers"),
    path("application/", views.application_api, name="application"),
    path("database/", views.database_api, name="database"),
    path("redis-celery/", views.redis_celery_api, name="redis_celery"),
    path("exams/", views.exams_api, name="exams"),
    path("alerts/", views.alerts_api, name="alerts"),
    path("logs/", views.logs_api, name="logs"),
    path("incidents/", views.incidents_api, name="incidents"),
    path("incidents/<int:incident_id>/action/", views.incident_action_api, name="incident_action"),
    path("security-events/", views.security_events_api, name="security_events"),
    path("alertmanager-webhook/", views.alertmanager_webhook, name="alertmanager_webhook"),
]
