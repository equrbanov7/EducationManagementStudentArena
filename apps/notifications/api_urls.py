"""``/api/notifications/`` — mobil tətbiqin bildiriş + push cihaz uçları (bax ``api_views.py``)."""

from django.urls import path

from . import api_views

app_name = "notifications_api"

urlpatterns = [
    path("", api_views.notification_list, name="list"),
    path("unread-count/", api_views.notification_unread_count, name="unread_count"),
    path("read-all/", api_views.notification_read_all, name="read_all"),
    path("<int:pk>/read/", api_views.notification_read, name="read"),
    path("devices/", api_views.devices, name="devices"),
    path("devices/test/", api_views.device_test, name="device_test"),
]
