from django.urls import path

from . import views

app_name = "appeals"

urlpatterns = [
    # ── Student ──────────────────────────────────────────────────────────
    path("my/", views.my_appeals, name="my_appeals"),
    path("create/<int:attempt_id>/", views.appeal_create, name="appeal_create"),
    # 2026-10-21: zal apellyasiyasından sonra uğur ekranı (tələbə artıq çıxış edib) → giriş səhifəsi.
    path("hall-done/", views.hall_appeal_done, name="hall_appeal_done"),
    # ── Teacher / reviewer ───────────────────────────────────────────────
    # 2026-10-21: müəllimin «Fənnimə aid apellyasiyalar» (yalnız-oxu).
    path("teaching/", views.teaching_appeals, name="teaching_appeals"),
    path("manage/", views.manage_appeals, name="manage_appeals"),
    path("manage/<int:appeal_id>/", views.review_appeal, name="review_appeal"),
    # 2026-10-13 (gecə): cavab açarı düzəlişi — sualı cavablayan BÜTÜN tələbələr üçün (audit olunur).
    path("manage/item/<int:item_id>/key-correction/", views.key_correction_apply, name="key_correction_apply"),
    path(
        "manage/key-correction/<int:correction_id>/revoke/",
        views.key_correction_revoke,
        name="key_correction_revoke",
    ),
    # ── İmtahan mərkəzi — apellyasiya statistikası ───────────────────────
    path("stats/data/", views.appeal_stats_data, name="appeal_stats_data"),
    path("stats/charts/", views.appeal_stats_charts, name="appeal_stats_charts"),
    path("stats/filters/", views.appeal_stats_filters, name="appeal_stats_filters"),
    path("stats/ai/", views.appeal_stats_ai, name="appeal_stats_ai"),
    # ── Detail (sahib və ya reviewer) ────────────────────────────────────
    path("<int:appeal_id>/", views.appeal_detail, name="appeal_detail"),
]
