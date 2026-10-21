"""exam_center paketi — zal monitorunun «Qayda pozanlar» paneli üçün hadisə LENTİ (2026-10-21).

``GET center/rooms/<room_id>/api/violations/feed/?cursor=<r.s>[&attempt=<id>]``

* kursorsuz — hər cəhd üçün ən son bir neçə hadisə (tavanlı);
* ``cursor`` — yalnız yeni hadisələr (hər poll-da payload sabit qalır);
* ``attempt`` — bir cəhdin son hadisələri (sətir açılanda).

İcazə snapshot-la EYNİDİR (``_get_room_and_sessions``: mərkəz və ya bu zalda aktiv növbəsi olan
nəzarətçi; növbə bitəndə 403). Lent zalın cəhd skopundan kənara çıxmır (bax
``services.final_center.violation_feed``). İstifadəçi × zal başına rate-limit.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext

from apps.exams.services.final_center.violation_feed import parse_cursor, room_violation_feed
from core.rate_limit import record_rate_limit_hit

from .room_monitor import _get_room_and_sessions

#: Snapshot-la eyni tezlik (10 s poll + sətir açılanda tək-cəhd sorğuları).
_FEED_RATE = "60/1m"
_CTX = "exams.final_center.violations"


def violation_panel_labels() -> dict:
    """``violations_panel.js`` etiketləri (``#fxc-monitor-i18n`` → ``violations.panel``)."""
    return {
        "shown": pgettext(_CTX, "%(shown)s / %(total)s göstərilir"),
        "noMatch": pgettext(_CTX, "Süzgəcə uyğun tələbə yoxdur."),
        "latest": pgettext(_CTX, "Son hadisələr"),
        "loadingEvents": pgettext(_CTX, "Hadisələr yüklənir…"),
        "fullHistory": pgettext(_CTX, "Tam tarixçə və qeyd üçün «Bax» düyməsini basın."),
        "moreTypes": pgettext(_CTX, "+%(count)s növ"),
        "lastAt": pgettext(_CTX, "Son hadisə"),
        "isNew": pgettext(_CTX, "Yeni"),
    }


@login_required
def exam_center_room_violation_feed(request, room_id):
    _organization, room, _sessions = _get_room_and_sessions(request, room_id)
    exceeded, retry_after = record_rate_limit_hit("fxc_room_vio_feed", _FEED_RATE, request.user.id, room.pk)
    if exceeded:
        response = JsonResponse({"error": "rate_limited"}, status=429)
        response["Retry-After"] = str(retry_after or 10)
        return response
    raw_attempt = (request.GET.get("attempt") or "").strip()
    attempt_id = int(raw_attempt) if raw_attempt.isdigit() and len(raw_attempt) <= 18 else None
    payload = room_violation_feed(room, cursor=parse_cursor(request.GET.get("cursor")), attempt_id=attempt_id)
    response = JsonResponse(payload)
    response["Cache-Control"] = "private, no-cache"
    return response


__all__ = ["exam_center_room_violation_feed", "violation_panel_labels"]
