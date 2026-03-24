from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    # Inbox
    path("", views.notification_list, name="notification_list"),
    # Detail
    path("<int:pk>/", views.notification_detail, name="notification_detail"),
    # Read / Unread
    path("<int:pk>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("<int:pk>/unread/", views.notification_mark_unread, name="notification_mark_unread"),
    path("read-all/", views.notification_mark_all_read, name="notification_mark_all_read"),
    # Delete
    path("<int:pk>/delete/", views.notification_delete, name="notification_delete"),
    path("bulk-delete/", views.notification_bulk_delete, name="notification_bulk_delete"),
    # Unread count (AJAX)
    path("unread-count/", views.unread_count, name="unread_count"),
]
