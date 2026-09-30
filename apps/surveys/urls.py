"""``/sorgu/`` — tələbə sorğu səthi, kampaniya idarəsinin POST ucu, «Sorğu nəticələri»
kabinet bölməsinin köməkçi ucları (müəllim axtarışı, müəllim kartı, aqreqat ixracı) və
sorğu qurucusunun (2026-09-30) respondent / idarə ucları."""

from django.urls import path

from .views import builder, manage, respond, results_api, results_detail, results_export, student, survey_export

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
    # Sorğu qurucusu (2026-09-30) — respondent səhifələri (hər auditoriya üzvü).
    path("s/<uuid:survey_id>/", respond.take, name="take"),
    path("s/<uuid:survey_id>/qaralama/", respond.draft, name="draft"),
    path("s/<uuid:survey_id>/kec/", respond.skip, name="skip"),
    path("s/<uuid:survey_id>/sonra/", respond.defer_survey, name="survey_defer"),
    path("s/<uuid:survey_id>/tesekkurler/", respond.thanks, name="survey_thanks"),
    # Qurucu (``survey.manage``) — POST ucları + CSV ixracı; bölmə kabinetdədir.
    path("qurucu/yarat/", builder.create, name="builder_create"),
    path("qurucu/<uuid:survey_id>/ayarlar/", builder.update, name="builder_update"),
    path("qurucu/<uuid:survey_id>/emel/", builder.action, name="builder_action"),
    path("qurucu/<uuid:survey_id>/suallar/", builder.questions, name="builder_questions"),
    path("qurucu/<uuid:survey_id>/ixrac.csv", survey_export.export_csv, name="builder_export"),
]
