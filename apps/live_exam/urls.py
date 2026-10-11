from django.urls import path

from . import views

app_name = "liveExam"

urlpatterns = [
    # ✅ Host (müəllim) — SLUG ilə session yarat
    path(
        "live/create/<slug:slug>/",
        views.live_create_session_by_slug,
        name="create_session_slug",
    ),
    path("live/", views.live_pin_entry, name="pin_entry"),
    # Host idarəetmə. WP9a (2026-10-10): köhnə `live/host/<pin>/` lobbisi (təqdimat
    # `?controls=1` əvəz edib) və `live/host/<pin>/start|next|finish/` dublikat ləqəbləri silindi —
    # oyun axını yalnız `live/<pin>/start|next|finish/` (aşağıda).
    path("live/host/<str:pin>/presentation/", views.live_host_presentation, name="host_presentation"),
    path("live/host/<str:pin>/skip-intro/", views.host_skip_question_intro, name="host_skip_question_intro"),
    path("live/host/<str:pin>/reveal/", views.host_reveal, name="host_reveal"),
    path("live/host/<str:pin>/lock/", views.host_toggle_lock, name="host_toggle_lock"),
    path("live/host/<str:pin>/settings/", views.host_update_settings, name="host_update_settings"),
    path("live/host/<str:pin>/players/remove/", views.host_remove_player, name="host_remove_player"),
    # Teacher live results
    path(
        "live/results/<slug:slug>/",
        views.teacher_live_exam_results,
        name="teacher_live_results",
    ),
    path(
        "live/results/<slug:slug>/<str:pin>/",
        views.teacher_live_session_detail,
        name="teacher_live_session_detail",
    ),
    # Audit 2026-09-28 LX-SEC: CSV ixracı (formula neytrallaşdırması ilə).
    path(
        "live/results/<slug:slug>/<str:pin>/export.csv",
        views.teacher_live_session_export,
        name="teacher_live_session_export",
    ),
    # Player (anonim)
    path("live/join/<str:pin>/", views.live_join_page, name="join_page"),
    path("live/join/<str:pin>/enter/", views.live_join_enter, name="join_enter"),
    path("live/play/<str:pin>/", views.live_player_screen, name="player_screen"),
    path("live/play/<str:pin>/answer/", views.live_answer_submit, name="answer_submit"),
    path("live/wait/<str:pin>/", views.live_wait_room, name="wait_room"),
    path("live/wait/<str:pin>/profile/", views.live_wait_profile_update, name="wait_room_profile"),
    path("live/wait/<str:pin>/reaction/", views.live_wait_reaction, name="wait_room_reaction"),
    # QR image
    path("live/qr/<str:pin>.png", views.live_qr_png, name="qr_png"),
    # Game flow endpoints
    path("live/state/<str:pin>/", views.live_state_json, name="state_json"),
    path("live/<str:pin>/start/", views.host_start_game, name="start_game"),
    path("live/<str:pin>/next/", views.host_next_question, name="next_question"),
    path("live/<str:pin>/finish/", views.host_finish, name="finish_game"),
]
