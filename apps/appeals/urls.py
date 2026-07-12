from django.urls import path

from . import views

app_name = "appeals"

urlpatterns = [
    # ── Student ──────────────────────────────────────────────────────────
    path("my/", views.my_appeals, name="my_appeals"),
    path("create/<int:attempt_id>/", views.appeal_create, name="appeal_create"),
    # ── Teacher / reviewer ───────────────────────────────────────────────
    path("manage/", views.manage_appeals, name="manage_appeals"),
    path("manage/<int:appeal_id>/", views.review_appeal, name="review_appeal"),
    # ── İmtahan mərkəzi — apellyasiya statistikası ───────────────────────
    path("stats/data/", views.appeal_stats_data, name="appeal_stats_data"),
    path("stats/charts/", views.appeal_stats_charts, name="appeal_stats_charts"),
    path("stats/filters/", views.appeal_stats_filters, name="appeal_stats_filters"),
    path("stats/ai/", views.appeal_stats_ai, name="appeal_stats_ai"),
    # ── Detail (sahib və ya reviewer) ────────────────────────────────────
    path("<int:appeal_id>/", views.appeal_detail, name="appeal_detail"),
]
