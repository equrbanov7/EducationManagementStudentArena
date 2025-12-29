from django.urls import path
from . import views

app_name = "liveExam"

urlpatterns = [
    # ✅ Host (müəllim) — SLUG ilə session yarat
    path("live/create/<slug:slug>/", views.live_create_session_by_slug, name="create_session_slug"),



    # Host lobby + idarəetmə
    path("live/host/<str:pin>/", views.live_host_lobby, name="host_lobby"),
    path("live/host/<str:pin>/start/", views.host_start_game, name="host_start_game"),
    path("live/host/<str:pin>/next/", views.host_next_question, name="host_next_question"),
    path("live/host/<str:pin>/reveal/", views.host_reveal, name="host_reveal"),
    path("live/host/<str:pin>/finish/", views.host_finish, name="host_finish"),

    # Player (anonim)
    path("live/join/<str:pin>/", views.live_join_page, name="join_page"),
    path("live/join/<str:pin>/enter/", views.live_join_enter, name="join_enter"),
    path("live/play/<str:pin>/", views.live_player_screen, name="player_screen"),
    path("live/wait/<str:pin>/", views.live_wait_room, name="wait_room"),
    
    # QR image
    path("live/qr/<str:pin>.png", views.live_qr_png, name="qr_png"),
    
    #Game flow endpoints
    path("live/state/<str:pin>/", views.live_state_json, name="state_json"),
    path("live/<str:pin>/start/", views.host_start_game, name="start_game"),
    path("live/<str:pin>/next/", views.host_next_question, name="next_question"),
    path("live/<str:pin>/end/", views.host_reveal, name="end_question"),
    path("live/<str:pin>/finish/", views.host_finish, name="finish_game"),

]
