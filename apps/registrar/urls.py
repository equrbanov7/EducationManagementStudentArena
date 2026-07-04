"""Registrar web URLs — elektron jurnal (müəllim üzü)."""

from django.urls import path

from . import views

app_name = "registrar"

urlpatterns = [
    path("", views.journal_list, name="journal_list"),
    path("cedvel/", views.schedule_view, name="schedule"),
    path("cedvel/slot/<uuid:slot_id>/sil/", views.schedule_slot_delete, name="schedule_slot_delete"),
    path("<uuid:offering_id>/", views.journal_detail, name="journal_detail"),
]
