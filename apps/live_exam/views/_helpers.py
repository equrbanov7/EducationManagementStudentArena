"""
live_exam/views/_helpers.py
─────────────────────────────
Helper functions for live exam views.
"""

from __future__ import annotations

import hashlib
import random
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.utils import timezone
from django.utils.translation import pgettext

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.exams.models import ExamQuestion, ExamQuestionOption
from apps.live_exam.models import LiveAnswer, LiveSession

# ════════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════════

AVATAR_KEYS = [
    "avatar_1",
    "avatar_2",
    "avatar_3",
    "avatar_4",
    "avatar_5",
    "avatar_6",
    "avatar_7",
    "avatar_8",
    "avatar_9",
    "avatar_10",
    "avatar_11",
    "avatar_12",
]

PLAYER_COOKIE_NAME = "live_player_token"
PLAYER_TOKEN_SALT = "liveExam.player"


# ════════════════════════════════════════════════════════════════════════════
# Small Utils
# ════════════════════════════════════════════════════════════════════════════


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _clean_nickname(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", " ", name)
    return name[:32]


def _get_client_id(request) -> str:
    """
    client_id cookie yoxdursa yenisini qaytarır (uuid hex).
    """
    cid = request.COOKIES.get("live_client_id")
    return cid or uuid.uuid4().hex


# ════════════════════════════════════════════════════════════════════════════
# URL & Broadcasting
# ════════════════════════════════════════════════════════════════════════════


def _get_public_base_url(request) -> str:
    """
    Join link/QR üçün public base URL:
    1) LIVE_EXAM_PUBLIC_HOST (tam URL və ya host:port)
    2) LAN_HOST (geri uyğunluq)
    3) request-in real host/scheme-i
    """
    configured = (
        getattr(settings, "LIVE_EXAM_PUBLIC_HOST", None) or getattr(settings, "LAN_HOST", None) or ""
    ).strip()

    if configured:
        configured = configured.rstrip("/")
        if configured.startswith(("http://", "https://")):
            return configured
        scheme = "https" if request.is_secure() else "http"
        return f"{scheme}://{configured}"

    return request.build_absolute_uri("/").rstrip("/")


def _build_join_url(request, session: LiveSession) -> str:
    return f"{_get_public_base_url(request)}{session.join_url_path()}"


def _broadcast(pin: str, payload: dict, group_suffix: str) -> None:
    """
    group_suffix: 'lobby' | 'play'
    Consumer-lər:
      - LiveLobbyConsumer -> lobby_event
      - LivePlayConsumer  -> play_event
    """
    layer = get_channel_layer()
    event_type = "play_event" if group_suffix == "play" else "lobby_event"

    async_to_sync(layer.group_send)(
        f"live_{pin}_{group_suffix}",
        {"type": event_type, "data": payload},
    )


# ════════════════════════════════════════════════════════════════════════════
# Serializers
# ════════════════════════════════════════════════════════════════════════════


def _serialize_players(session: LiveSession, limit: int = 50) -> List[Dict[str, Any]]:
    return list(session.players.order_by("-created_at").values("id", "nickname", "avatar_key")[:limit])


def _serialize_top(session: LiveSession, limit: int = 10) -> List[Dict[str, Any]]:
    return list(session.players.order_by("-score", "created_at").values("nickname", "avatar_key", "score")[:limit])


def _serialize_question_results(session: LiveSession, question_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Reveal zamanı: bu sual üzrə kim nə qədər bal aldı, total score nədir.
    """
    answers = (
        LiveAnswer.objects.filter(session=session, question_id=question_id)
        .select_related("player")
        .order_by("-awarded_points", "-created_at")
    )[:limit]

    out: List[Dict[str, Any]] = []
    for a in answers:
        out.append(
            {
                "nickname": a.player.nickname,
                "avatar_key": a.player.avatar_key,
                "is_correct": bool(a.is_correct),
                "awarded_points": _safe_int(a.awarded_points, 0),
                "total_score": _safe_int(a.player.score, 0),
            }
        )
    return out


# ════════════════════════════════════════════════════════════════════════════
# Question Picking Helpers
# ════════════════════════════════════════════════════════════════════════════


def _get_selected_question_ids(session: LiveSession) -> List[int]:
    """
    session.selected_question_ids JSONField ola bilər (list[int] / list[str] / mix).
    """
    ids = getattr(session, "selected_question_ids", None) or []
    out: List[int] = []
    for x in ids:
        try:
            out.append(int(x))
        except Exception:
            pass
    return out


def _get_exam_question_ids(session: LiveSession) -> List[int]:
    """
    Exam-dəki bütün ExamQuestion id-ləri (sıra ilə).
    Səndə order field var deyə: order, id.
    """
    return list(ExamQuestion.objects.filter(exam=session.exam).order_by("order", "id").values_list("id", flat=True))


def _get_total_questions(session: LiveSession) -> int:
    selected = _get_selected_question_ids(session)
    if selected:
        return len(selected)
    return ExamQuestion.objects.filter(exam=session.exam).count()


def _get_question_by_index(session: LiveSession, index: int) -> Optional[ExamQuestion]:
    """
    index 0-based.
    selected_question_ids doludursa -> ordan,
    yoxsa -> exam order ilə.
    """
    index = _safe_int(index, 0)
    if index < 0:
        return None

    selected = _get_selected_question_ids(session)
    if selected:
        if index >= len(selected):
            return None
        qid = selected[index]
        return ExamQuestion.objects.filter(exam=session.exam, id=qid).first()

    qs = ExamQuestion.objects.filter(exam=session.exam).order_by("order", "id")
    try:
        return qs[index]
    except Exception:
        return None


def _get_current_exam_question(session: LiveSession) -> Optional[ExamQuestion]:
    return _get_question_by_index(session, _safe_int(session.current_index, 0))


# ════════════════════════════════════════════════════════════════════════════
# Timing & Points
# ════════════════════════════════════════════════════════════════════════════


def _question_time_limit(session: LiveSession, eq: ExamQuestion) -> int:
    """
    1) eq.effective_time_limit (səndə varsa)
    2) eq.time_limit_seconds
    3) exam.default_question_time_seconds
    default: 15
    """
    if hasattr(eq, "effective_time_limit"):
        v = _safe_int(getattr(eq, "effective_time_limit", 0), 0)
        if v > 0:
            return v

    v = _safe_int(getattr(eq, "time_limit_seconds", 0), 0)
    if v > 0:
        return v

    v = _safe_int(getattr(session.exam, "default_question_time_seconds", 0), 0)
    if v > 0:
        return v

    return 15


def _question_points(session: LiveSession, eq: ExamQuestion) -> int:
    """
    1) eq.points
    2) exam.default_question_points
    default: 1
    """
    v = _safe_int(getattr(eq, "points", 0), 0)
    if v > 0:
        return v

    v = _safe_int(getattr(session.exam, "default_question_points", 0), 0)
    if v > 0:
        return v

    return 1


def _get_question_text(eq: ExamQuestion) -> str:
    """
    Səndə eq.text var deyə əsas onu götürür.
    Alternativ field-lar varsa fallback.
    """
    for attr in ("text", "question_text", "title", "body"):
        v = getattr(eq, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# ════════════════════════════════════════════════════════════════════════════
# Options (NULL fix) + Multi detect
# ════════════════════════════════════════════════════════════════════════════


def _get_option_text(opt) -> str:
    """
    "null" problemini öldürmək üçün:
    mövcud field-lardan birini tapıb qaytarır.
    """
    for attr in ("text", "title", "content", "answer", "option_text", "body"):
        v = getattr(opt, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _get_option_label(opt) -> str:
    v = getattr(opt, "label", None)
    if isinstance(v, str) and v.strip():
        return v.strip()
    return ""


def _options_seed(pin: str, question_id: int, started_at) -> int:
    seed_str = f"{pin}:{int(question_id)}:{started_at.isoformat()}"
    h = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    return int(h[:8], 16)  # 32-bit seed


def _build_options(eq, *, seed: int | None = None):
    """
    ✅ Variantları qarışdırır.
    seed verilsə, shuffle deterministik olur (refresh-də dəyişmir).
    """
    letters = ["A", "B", "C", "D", "E", "F"]

    qs = ExamQuestionOption.objects.filter(question=eq).order_by("id")  # baza stabil olsun

    opts = list(qs)

    rnd = random.Random(seed) if seed is not None else random
    rnd.shuffle(opts)

    out = []
    for i, opt in enumerate(opts):
        label = _get_option_label(opt) or (letters[i] if i < len(letters) else str(i + 1))
        text = _get_option_text(opt) or pgettext("live_exam.view.option", "option_fallback_text").format(label=label)
        out.append({"id": opt.id, "label": label, "text": text})
    return out


def _detect_multi(eq: ExamQuestion) -> Tuple[bool, int, List[int]]:
    """
    Multi sualı aşkarlayır:
    - eq.is_multiple / eq.multi_choice / eq.allow_multiple varsa onları da yoxlayır
    - yoxdursa correct_count > 1 => multi

    max_select:
    - eq.max_select varsa götür
    - yoxdursa correct_count
    """
    correct_ids = list(ExamQuestionOption.objects.filter(question=eq, is_correct=True).values_list("id", flat=True))
    correct_count = len(correct_ids)

    flags = [
        bool(getattr(eq, "is_multiple", False)),
        bool(getattr(eq, "multi_choice", False)),
        bool(getattr(eq, "allow_multiple", False)),
    ]
    multi = any(flags) or (correct_count > 1)

    if multi:
        max_select = _safe_int(getattr(eq, "max_select", 0), 0)
        if max_select <= 1:
            max_select = max(2, correct_count)  # ən az 2
    else:
        max_select = 1

    return multi, max_select, correct_ids


# ════════════════════════════════════════════════════════════════════════════
# Payload Builders
# ════════════════════════════════════════════════════════════════════════════


def _build_question_payload(session: LiveSession, eq: ExamQuestion, idx: int, total: int):
    time_limit = _question_time_limit(session, eq)
    now = timezone.now()
    ends = now + timezone.timedelta(seconds=time_limit)

    multi, max_select, correct_ids = _detect_multi(eq)

    # ✅ deterministik shuffle seed
    seed = _options_seed(session.pin, eq.id, now)

    payload = {
        "type": "question_published",
        "question": {
            "id": eq.id,
            "text": _get_question_text(eq),
            "time_limit": time_limit,
            "points": _question_points(session, eq),
            "multi": multi,
            "max_select": max_select,
            # ✅ qarışdırılmış options
            "options": _build_options(eq, seed=seed),
            "started_at": now.isoformat(),
            "ends_at": ends.isoformat(),
            "index": _safe_int(idx, 0) + 1,
            "total": _safe_int(total, 0),
        },
    }
    return payload, now, ends


def _build_reveal_payload(session: LiveSession, question_id: int) -> Dict[str, Any]:
    """
    reveal event-i üçün yığcam payload.
    """
    eq = ExamQuestion.objects.filter(exam=session.exam, id=question_id).first()
    if not eq:
        return {"type": "error", "message": pgettext("live_exam.view.message", "question_not_found")}

    _, _, correct_ids = _detect_multi(eq)

    return {
        "type": "reveal",
        "question_id": question_id,
        "correct_option_ids": correct_ids,
        "results": _serialize_question_results(session, question_id, limit=50),
        "top": _serialize_top(session, limit=10),
    }


# ════════════════════════════════════════════════════════════════════════════
# Multi Scoring Helper (consumer üçün)
# ════════════════════════════════════════════════════════════════════════════


def _score_multi_fraction(
    chosen_ids: List[int],
    correct_ids: List[int],
    *,
    mode: str = "strict",  # "strict" | "partial"
) -> float:
    """
    Consumer-də istifadə edəcəksən.

    strict:
      - səhv seçimi varsa => 0
      - hamısı düz seçilibsə => 1, yoxsa 0
    partial:
      - T = düz seçilənlərin sayı
      - W = səhv seçilənlərin sayı
      - C = correct_ids sayı
      - fraction = max(0, (T - W) / C)
    """
    chosen = set(int(x) for x in (chosen_ids or []))
    correct = set(int(x) for x in (correct_ids or []))
    if not correct:
        return 0.0

    T = len(chosen & correct)
    W = len(chosen - correct)
    C = len(correct)

    if mode == "strict":
        if W > 0:
            return 0.0
        return 1.0 if T == C else 0.0

    # partial default
    return max(0.0, (T - W) / float(C))
