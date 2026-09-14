"""«Statistika» — İMTAHAN MƏRKƏZİ profili (exam_center_head/staff, RİM əməkdaşı;
RİM rəhbərində təşkilat mənzərəsinə ƏLAVƏ blok kimi).

Nə göstərilir: dövrün imtahanları (həyat dövrü üzrə), cəhdlər və keçid,
yoxlama növbəsi, açıq apellyasiyalar, zal/kompüter/oturum, nəzarət insidentləri,
yekun bal daxiletməsi. Köhnə kodda bu rol TƏLƏBƏ qoluna düşürdü («öz cəhdlərim»
— mərkəz əməkdaşı üçün mənasız). Hər rəqəm aqreqatdır (~9 sorğu).
"""

from __future__ import annotations

from django.db.models import Count, Q, Sum
from django.utils import timezone

from ._shared import ROW_LIMIT, Window, attempt_outcome, exam_lifecycle_aggregate, pct


def exam_center_metrics(*, organization, window: Window, period=None) -> dict:
    """İmtahan mərkəzinin metrik modeli — sabit sayda sorğu."""
    from apps.appeals.models import Appeal
    from apps.appeals.public import (
        APPEAL_STATUS_ACCEPTED,
        APPEAL_STATUS_PARTIALLY_ACCEPTED,
        APPEAL_STATUS_PENDING,
        APPEAL_STATUS_REJECTED,
        APPEAL_STATUS_UNDER_REVIEW,
    )
    from apps.exams.models import Exam, ExamAttempt, ExamRoom, ExamRoomSession, SupervisionIncident
    from apps.registrar.models import Enrollment

    now = timezone.now()
    exams = Exam.objects.filter(organization=organization, is_deleted=False)
    lifecycle = exam_lifecycle_aggregate(window.apply(exams, "start_datetime") if window.is_bounded else exams, now=now)

    attempts = window.apply(ExamAttempt.objects.filter(exam__in=exams), "started_at")
    outcome = attempt_outcome(attempts)

    appeals = window.apply(Appeal.objects.filter(organization=organization), "created_at")
    appeal_agg = appeals.aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(status__in=(APPEAL_STATUS_PENDING, APPEAL_STATUS_UNDER_REVIEW))),
        accepted=Count("id", filter=Q(status__in=(APPEAL_STATUS_ACCEPTED, APPEAL_STATUS_PARTIALLY_ACCEPTED))),
        rejected=Count("id", filter=Q(status=APPEAL_STATUS_REJECTED)),
    )

    room_agg = (
        ExamRoom.objects.filter(organization=organization, is_active=True)
        .annotate(active_computer_count=Count("computers", filter=Q(computers__is_active=True)))
        .aggregate(rooms=Count("id"), capacity=Sum("capacity"), computers=Sum("active_computer_count"))
    )
    sessions = window.apply(ExamRoomSession.objects.filter(organization=organization), "scheduled_start")
    session_agg = sessions.aggregate(
        total=Count("id"),
        live=Count("id", filter=Q(state__in=("entry_open", "active"))),
        prepared=Count("id", filter=Q(state="prepared")),
        ended=Count("id", filter=Q(state="ended")),
        cancelled=Count("id", filter=Q(state="cancelled")),
    )
    incident_agg = window.apply(SupervisionIncident.objects.filter(organization=organization), "timestamp").aggregate(
        total=Count("id"),
        severe=Count("id", filter=Q(severity__in=("high", "critical"))),
    )

    score_entry = {"total": 0, "entered": 0, "published": 0, "entered_pct": None}
    if period is not None:
        entry_agg = Enrollment.objects.filter(
            organization=organization, offering__period=period, status=Enrollment.Status.ENROLLED
        ).aggregate(
            total=Count("id"),
            entered=Count("id", filter=Q(final_grade__exam_score__isnull=False)),
            published=Count("id", filter=Q(final_grade__is_published=True)),
        )
        score_entry = {
            "total": int(entry_agg["total"] or 0),
            "entered": int(entry_agg["entered"] or 0),
            "published": int(entry_agg["published"] or 0),
            "entered_pct": pct(entry_agg["entered"], entry_agg["total"]),
        }

    session_filter = Q()
    if window.date_from:
        session_filter &= Q(sessions__scheduled_start__date__gte=window.date_from)
    if window.date_to:
        session_filter &= Q(sessions__scheduled_start__date__lte=window.date_to)
    session_count_kwargs = {"filter": session_filter} if session_filter else {}
    room_rows = list(
        ExamRoom.objects.filter(organization=organization, is_active=True)
        .annotate(
            active_computers=Count("computers", filter=Q(computers__is_active=True), distinct=True),
            session_count=Count("sessions", distinct=True, **session_count_kwargs),
        )
        .order_by("name")
        .values("name", "code", "capacity", "active_computers", "session_count")[:ROW_LIMIT]
    )

    return {
        "profile": "exam_center",
        "window": window.as_dict(),
        "exams": lifecycle,
        "outcome": outcome,
        "appeals": {key: int(value or 0) for key, value in appeal_agg.items()},
        "rooms": {
            "rooms": int(room_agg["rooms"] or 0),
            "capacity": int(room_agg["capacity"] or 0),
            "computers": int(room_agg["computers"] or 0),
            "rows": [
                {
                    "name": row["name"] or "—",
                    "code": row["code"] or "",
                    "capacity": int(row["capacity"] or 0),
                    "computers": int(row["active_computers"] or 0),
                    "sessions": int(row["session_count"] or 0),
                }
                for row in room_rows
            ],
        },
        "sessions": {key: int(value or 0) for key, value in session_agg.items()},
        "incidents": {key: int(value or 0) for key, value in incident_agg.items()},
        "score_entry": score_entry,
    }
