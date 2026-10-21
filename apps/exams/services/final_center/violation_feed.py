"""final_center paketi — «Qayda pozanlar» panelinin hadisə lenti (kursorla, 2026-10-21).

Sahib (2026-10-21, zal imtahanı): «Sağda qayda pozuntusu edən hissədə oranı optimallaşdırmaq
lazımdır — say çoxaldıqca baxmaq çətinləşə bilər.»

Zal snapshot-u (``room_monitor_snapshot``) tələbə başına yalnız AQREQAT daşıyır (növ üzrə say,
son an, ən yüksək ciddilik) — hadisələrin özü orada yoxdur, payload hadisə sayı ilə böyümür.
Panelin açılan sətirlərindəki qısa xronologiya bu lentdən gəlir:

* ilk sorğu (kursorsuz) — hər cəhd üçün ən son ``FEED_PER_ATTEMPT`` hadisə (qayda və siqnal
  ayrıca), cavabda cəmi ən çox ``FEED_TOTAL_CAP`` (ən yenilər);
* sonrakı sorğular (``cursor``) — yalnız kursordan YENİ hadisələr (eyni tavanlarla);
* ``attempt`` — bir cəhdin son hadisələri (sətir açılanda buferi boşdursa).

Kursor iki cədvəlin son id-ləridir: ``"<qayda_id>.<siqnal_id>"`` (id-lər monoton artır). Sorğu
sayı sabitdir (2 — qayda + siqnal; zalın cəhd skopu alt-sorğudur, ayrıca sorğu deyil), tələbə və
hadisə sayından asılı deyil. Skop snapshot-la eynidir: zala möhürlənmiş canlı / yenicə bitmiş
cəhdlər + zalın canlı oturumlarının biletli cəhdləri. İcazəni view yoxlayır.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

FEED_PER_ATTEMPT = 5
FEED_TOTAL_CAP = 150
#: Bitmiş / çıxarılmış cəhd lentdə bu qədər qalır (snapshot-un ən uzun görünmə pəncərəsi ilə eyni).
FEED_FINISHED_WINDOW_SECONDS = 900


def parse_cursor(raw) -> tuple[int, int] | None:
    """``"12.34"`` → (12, 34); yanlış / boş → None (ilk sorğu kimi işlənir)."""
    parts = str(raw or "").split(".")
    if len(parts) != 2 or not all(part.isdigit() and len(part) <= 18 for part in parts):
        return None
    return int(parts[0]), int(parts[1])


def format_cursor(rule_id: int, signal_id: int) -> str:
    return f"{int(rule_id)}.{int(signal_id)}"


def room_feed_attempts(room):
    """Zalın lent skopundakı cəhd id-ləri (QuerySet — alt-sorğu kimi istifadə olunur, icra olunmur)."""
    from apps.exams.domain.final_center import ROOM_SESSION_STATE_ACTIVE, ROOM_SESSION_STATE_ENTRY_OPEN
    from apps.exams.models import ExamAttempt

    since = timezone.now() - timedelta(seconds=FEED_FINISHED_WINDOW_SECONDS)
    live_states = (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)
    return (
        ExamAttempt.objects.filter(is_trial=False)
        .filter(
            Q(room_id=room.pk, status="in_progress")
            | Q(room_id=room.pk, finished_at__gte=since)
            | Q(final_tickets__session__room_id=room.pk, final_tickets__session__state__in=live_states)
        )
        .values("id")
    )


def _capped(queryset, attempt_field: str, per_attempt: int, total: int, fields: tuple):
    """Cəhd başına ən yeni ``per_attempt`` sətir (pəncərə funksiyası) + cəmi ``total`` — TƏK sorğu."""
    return list(
        queryset.annotate(feed_rank=Window(RowNumber(), partition_by=[F(attempt_field)], order_by=F("id").desc()))
        .filter(feed_rank__lte=per_attempt)
        .order_by("-id")
        .values(*fields)[:total]
    )


def room_violation_feed(
    room,
    *,
    cursor: tuple[int, int] | None = None,
    attempt_id: int | None = None,
    per_attempt: int = FEED_PER_ATTEMPT,
    total: int = FEED_TOTAL_CAP,
) -> dict:
    """{"cursor", "events": [...], "labels": {kod: ad}, "per_attempt", "truncated", "delta"}.

    Hadisə: {"id": "r12"|"s34", "attempt", "code", "severity", "at", "source": "rule"|"signal"}
    — ən yeni əvvəldə. Metadata / detallar nəzarətçiyə GÖNDƏRİLMİR (yalnız kod + ciddilik + an).
    """
    from apps.exams.models import ProctoringLog, SupervisionIncident
    from apps.exams.services.supervision.monitor_enrich import event_labels_for_codes
    from apps.exams.services.supervision.risk import NOTE_KIND, RISK_INCIDENT_TYPES, SEVERITY_POINTS

    scope = room_feed_attempts(room)
    rules = SupervisionIncident.objects.filter(attempt_id__in=scope, event_type__in=RISK_INCIDENT_TYPES)
    signals = ProctoringLog.objects.filter(exam_attempt_id__in=scope).exclude(details__contains={"kind": NOTE_KIND})
    if attempt_id:
        rules = rules.filter(attempt_id=attempt_id)
        signals = signals.filter(exam_attempt_id=attempt_id)
    if cursor:
        rules = rules.filter(id__gt=cursor[0])
        signals = signals.filter(id__gt=cursor[1])

    rule_rows = _capped(
        rules, "attempt_id", per_attempt, total, ("id", "attempt_id", "event_type", "severity", "timestamp")
    )
    signal_rows = _capped(
        signals,
        "exam_attempt_id",
        per_attempt,
        total,
        ("id", "exam_attempt_id", "event_type", "details__kind", "details__severity", "timestamp"),
    )

    events = [
        {
            "id": f"r{row['id']}",
            "attempt": row["attempt_id"],
            "code": row["event_type"],
            "severity": row["severity"] if row["severity"] in SEVERITY_POINTS else "medium",
            "at": row["timestamp"].isoformat() if row["timestamp"] else None,
            "source": "rule",
        }
        for row in rule_rows
    ] + [
        {
            "id": f"s{row['id']}",
            "attempt": row["exam_attempt_id"],
            "code": str(row["details__kind"] or row["event_type"] or "other"),
            "severity": row["details__severity"] if row["details__severity"] in SEVERITY_POINTS else "low",
            "at": row["timestamp"].isoformat() if row["timestamp"] else None,
            "source": "signal",
        }
        for row in signal_rows
    ]
    events.sort(key=lambda event: event["at"] or "", reverse=True)
    truncated = len(events) > total
    # Cəmi tavan iki cədvəlin birləşməsinə tətbiq olunur; kursor isə OXUNMUŞ sətirlərdən irəli
    # çəkilir (atılanlar daha köhnədir — panel cəhd başına yalnız son hadisələri saxlayır).
    events = events[:total]

    previous = cursor or (0, 0)
    if attempt_id:
        # Tək cəhd sorğusu ümumi kursoru irəli çəkmir (digər cəhdlərin yeni hadisələri itməsin).
        next_cursor = previous
    else:
        next_cursor = (
            max([row["id"] for row in rule_rows] + [previous[0]]),
            max([row["id"] for row in signal_rows] + [previous[1]]),
        )
    return {
        "cursor": format_cursor(*next_cursor),
        "delta": cursor is not None,
        "per_attempt": per_attempt,
        "truncated": truncated or len(rule_rows) >= total or len(signal_rows) >= total,
        "events": events,
        "labels": event_labels_for_codes(event["code"] for event in events),
    }


__all__ = [
    "FEED_PER_ATTEMPT",
    "FEED_TOTAL_CAP",
    "format_cursor",
    "parse_cursor",
    "room_feed_attempts",
    "room_violation_feed",
]
