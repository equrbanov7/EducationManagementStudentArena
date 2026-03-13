"""
live_exam/views/__init__.py
────────────────────────────
Re-exports all views for backward compatibility with URLs.

This allows the existing urls.py to continue working with:
    from . import views
    views.live_create_session_by_slug
"""

# ═══════════════════════════════════════════════════════════════
# Host Views
# ═══════════════════════════════════════════════════════════════
from .host import (
    host_finish,
    host_next_question,
    host_reveal,
    host_start_game,
    live_create_session_by_slug,
    live_host_lobby,
    live_host_presentation,
)

# ═══════════════════════════════════════════════════════════════
# Player Views
# ═══════════════════════════════════════════════════════════════
from .player import (
    live_pin_entry,
    live_join_enter,
    live_join_page,
    live_player_screen,
    live_qr_png,
    live_wait_profile_update,
    live_wait_reaction,
    live_wait_room,
)

# ═══════════════════════════════════════════════════════════════
# API Views
# ═══════════════════════════════════════════════════════════════
from .api import live_state_json

# ═══════════════════════════════════════════════════════════════
# __all__ - Explicit exports
# ═══════════════════════════════════════════════════════════════
__all__ = [
    # Host
    "live_create_session_by_slug",
    "live_host_lobby",
    "live_host_presentation",
    "host_start_game",
    "host_next_question",
    "host_reveal",
    "host_finish",
    # Player
    "live_pin_entry",
    "live_join_page",
    "live_join_enter",
    "live_qr_png",
    "live_wait_room",
    "live_wait_profile_update",
    "live_wait_reaction",
    "live_player_screen",
    # API
    "live_state_json",
]
