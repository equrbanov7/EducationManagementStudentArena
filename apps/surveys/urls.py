"""``/sorgu/`` — tələbə sorğu səthi və kampaniya idarəsinin POST ucu."""

from django.urls import path

from .views import manage, student

app_name = "surveys"

urlpatterns = [
    path("", student.home, name="home"),
    path("<uuid:campaign_id>/m/<uuid:offering_id>/<int:teacher_id>/", student.teacher_form, name="teacher"),
    path("<uuid:campaign_id>/umumi/", student.general_form, name="general"),
    path("tesekkurler/", student.thanks, name="thanks"),
    path("sonra/", student.defer, name="defer"),
    path("idare/", manage.manage, name="manage"),
]
