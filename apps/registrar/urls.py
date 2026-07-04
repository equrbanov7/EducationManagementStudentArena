"""Registrar web URLs — elektron jurnal (müəllim üzü)."""

from django.urls import path

from . import views

app_name = "registrar"

urlpatterns = [
    path("", views.journal_list, name="journal_list"),
    path("<uuid:offering_id>/", views.journal_detail, name="journal_detail"),
]
