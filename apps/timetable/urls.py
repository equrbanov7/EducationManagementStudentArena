"""Avtomatik dərs cədvəli — URL-lər (``/cedvel-generatoru/``, namespace ``timetable``)."""

from django.urls import path

from .views import api, pages

app_name = "timetable"

urlpatterns = [
    path("", pages.home, name="home"),
    path("muellimler/", pages.availability_page, name="availability"),
    path("novbeler/", pages.policies_page, name="policies"),
    path("yeni/", pages.new_run_page, name="new_run"),
    path("isleme/<uuid:run_id>/", pages.run_detail, name="run_detail"),
    path("api/elcatanliq/", api.availability_save, name="api_availability"),
    path("api/novbe/", api.policy_save, name="api_policy"),
    path("api/yoxla/", api.precheck_view, name="api_precheck"),
    path("api/islet/", api.run_start, name="api_run_start"),
    path("api/isleme/<uuid:run_id>/status/", api.run_status, name="api_run_status"),
    path("api/isleme/<uuid:run_id>/emeliyyat/", api.run_action, name="api_run_action"),
]
