"""``/sorgu/`` — tələbə sorğu səthi, kampaniya idarəsinin POST ucu və «Sorğu nəticələri»
kabinet bölməsinin köməkçi ucları (müəllim axtarışı, müəllim kartı, aqreqat ixracı)."""

from django.urls import path

from .views import manage, results_api, results_detail, results_export, student

app_name = "surveys"

urlpatterns = [
    path("", student.home, name="home"),
    path("<uuid:campaign_id>/m/<uuid:offering_id>/<int:teacher_id>/", student.teacher_form, name="teacher"),
    path("<uuid:campaign_id>/umumi/", student.general_form, name="general"),
    path("tesekkurler/", student.thanks, name="thanks"),
    path("sonra/", student.defer, name="defer"),
    path("idare/", manage.manage, name="manage"),
    # «Sorğu nəticələri» (F2) — hamısı GET; icazə hər ucda FAIL-CLOSED yenidən yoxlanılır.
    path("neticeler/muellimler/", results_api.teacher_search, name="results_teachers"),
    path("neticeler/muellim/<int:teacher_id>/", results_detail.teacher_drawer, name="results_teacher"),
    path("neticeler/muellim/<int:teacher_id>/cap/", results_detail.teacher_print, name="results_teacher_print"),
    path("neticeler/ixrac/<str:fmt>/", results_export.export, name="results_export"),
]
