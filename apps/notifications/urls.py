from django.urls import path

from . import views

app_name = "notifications"

# WP9a (2026-10-10): müstəqil qutu/detal səhifələri (`""`, `<pk>/`), `<pk>/unread/` və
# `unread-count/` silindi — bildiriş qutusu kabinet bölməsidir (`?section=notifications`)
# və yalnız aşağıdakı əməliyyat uclarını işlədir.
urlpatterns = [
    # Read
    path("<int:pk>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("read-all/", views.notification_mark_all_read, name="notification_mark_all_read"),
    # Delete
    path("<int:pk>/delete/", views.notification_delete, name="notification_delete"),
    path("bulk-delete/", views.notification_bulk_delete, name="notification_bulk_delete"),
]
