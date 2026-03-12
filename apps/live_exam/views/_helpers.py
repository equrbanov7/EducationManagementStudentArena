"""
live_exam/views/_helpers.py
─────────────────────────────
Backward-compatible helper re-exports for live exam views.
"""

from __future__ import annotations

from apps.live_exam.auth import PLAYER_COOKIE_NAME, PLAYER_TOKEN_SALT, clean_nickname, get_client_id
from apps.live_exam.constants import AVATAR_KEYS
from apps.live_exam.domain.session import (
    detect_multi,
    get_current_exam_question,
    get_exam_question_ids,
    get_option_label,
    get_option_text,
    get_question_by_index,
    get_question_text,
    get_selected_question_ids,
    get_total_questions,
    question_points,
    question_time_limit,
    safe_int,
)
from apps.live_exam.scoring import score_multi_fraction
from apps.live_exam.serializers import (
    build_options,
    options_seed,
    serialize_player_identity,
    serialize_players,
    serialize_question_results,
    serialize_top,
)
from apps.live_exam.transport import (
    broadcast,
    build_reaction_event_payload,
    build_join_url,
    build_question_payload,
    build_reveal_payload,
    get_public_base_url,
)

_safe_int = safe_int
_clean_nickname = clean_nickname
_get_client_id = get_client_id
_get_public_base_url = get_public_base_url
_build_join_url = build_join_url
_broadcast = broadcast
_serialize_players = serialize_players
_serialize_player_identity = serialize_player_identity
_serialize_top = serialize_top
_serialize_question_results = serialize_question_results
_get_selected_question_ids = get_selected_question_ids
_get_exam_question_ids = get_exam_question_ids
_get_total_questions = get_total_questions
_get_question_by_index = get_question_by_index
_get_current_exam_question = get_current_exam_question
_question_time_limit = question_time_limit
_question_points = question_points
_get_question_text = get_question_text
_get_option_text = get_option_text
_get_option_label = get_option_label
_options_seed = options_seed
_build_options = build_options
_detect_multi = detect_multi
_build_question_payload = build_question_payload
_build_reveal_payload = build_reveal_payload
_build_reaction_event_payload = build_reaction_event_payload
_score_multi_fraction = score_multi_fraction
