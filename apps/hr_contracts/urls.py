"""«Əmək müqavilələri» marşrutları — ``config/urls.py``-də ``kadrlar/muqavileler/`` altında (namespace ``hr_contracts``)."""

from django.urls import path

from . import views

app_name = "hr_contracts"

urlpatterns = [
    path("api/save/", views.save, name="save"),
    path("api/staff/", views.staff, name="staff"),
    path("api/<uuid:contract_id>/send/", views.send, name="send"),
    path("api/<uuid:contract_id>/terminate/", views.terminate, name="terminate"),
    path("api/<uuid:contract_id>/discard/", views.discard, name="discard"),
    path("api/<uuid:contract_id>/acknowledge/", views.acknowledge, name="acknowledge"),
    path("api/<uuid:contract_id>/history/", views.history, name="history"),
    path("export/", views.export, name="export"),
]
