"""«Nəzarət otağı» — HƏR imtahan növü üçün imtahan səviyyəli canlı nəzarət (sahib 2026-11-06).

Sahib: «Adi quiz-də nəzarət sistemi yanılı olanda nəzarət otağı yoxdur, bloklanan tələbəni bərpa etmək
mümkün deyil. Midterm/final kimi quiz, yazılı və praktiki imtahanda da heyət imtahana daxil olub
«Nəzarət otağı»na keçib izləyə bilsin.»

Əvvəl canlı nəzarət YALNIZ İmtahan Mərkəzinin zal oturumu monitorunda idi (``final_center.monitor``) —
o, bilet/oturum üzərində qurulub, ona görə zal axınında olmayan imtahanların (quiz, yazılı, praktiki,
açar sönülüdürsə midterm) cəhdləri heç bir monitorda görünmürdü və «Bərpa et» yolu yox idi
(``exam_center_ticket_resume`` bilet tələb edir). Bu modul biletdən asılı OLMAYAN, birbaşa imtahanın
cəhdləri üzərində qurulmuş snapshot verir; sətirlər mərkəz monitoru ilə EYNİ zənginləşdirmədən
(``enrich_monitor_rows`` — kimlik, risk, heartbeat, irəliləyiş) keçir ki, iki ekran ayrılmasın.

Əhatə: imtahanın açıq (``draft``/``in_progress``) cəhdləri + son ``RECENT_FINISHED_WINDOW``-da bitənlər.
Müəllifin «Sınaq keç» cəhdləri (``is_trial``) sayılmır — nəticəyə düşmürlər və kilidlənmirlər.
İcazə (kim baxa bilər) çağıran view-dadır (``get_teacher_exam_or_404``).
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.exams.features import exam_supervision_enabled

from ._shared import get_supervision_config
from .monitor_enrich import enrich_monitor_rows, event_labels_for_rows

#: Bitmiş cəhd otaqda bu qədər müddət görünür (kim nə vaxt bitirdi).
RECENT_FINISHED_WINDOW = timedelta(hours=3)
#: Bir otaqda göstərilən sətir tavanı (payload imtahanın bütün tarixçəsi ilə böyüməsin).
ROOM_ROW_LIMIT = 500
_OPEN_STATUSES = ("draft", "in_progress")
_LOCK_STATUSES = ("locked", "removed")

STATE_ACTIVE = "active"
STATE_WARNED = "warned"
STATE_LOCKED = "locked"
STATE_COMPLETED = "completed"


def resume_refusal(attempt, config) -> str:
    """Kilidli cəhd bərpa oluna bilməzsə səbəb kodu, bilərsə ``""``.

    ``actions.teacher_resume_attempt``-in qaydalarının YAN TƏSİRSİZ güzgüsüdür (düymə yalnız
    işləyəcəksə görünsün): əl ilə pauza həmişə bərpa olunur; avtomatik kilid — nəzarət konfiqi
    və bərpa siyasəti icazə verirsə.
    """
    if attempt.is_finished:
        return "finished"
    if attempt.supervision_status not in _LOCK_STATUSES:
        return "not_locked"
    if attempt.supervision_manual_lock:
        return ""
    if config is None:
        return "no_config"
    if config.recovery_policy == "no_second_chance":
        return "policy"
    if config.recovery_policy == "one_extra_chance" and attempt.supervision_extra_chances >= 1:
        return "chance_used"
    return ""


def _state(attempt) -> str:
    if attempt.is_finished:
        return STATE_COMPLETED
    if attempt.supervision_status in _LOCK_STATUSES:
        return STATE_LOCKED
    if attempt.supervision_status == "warned" or attempt.supervision_violation_count > 0:
        return STATE_WARNED
    return STATE_ACTIVE


def _remaining_seconds(attempt, now):
    if attempt.is_finished:
        return None
    deadline = attempt.deadline_at
    if deadline is None:
        return None
    return max(0, int((deadline - now).total_seconds()))


def room_attempts_queryset(exam, *, now=None):
    from apps.exams.models import ExamAttempt

    now = now or timezone.now()
    since = now - RECENT_FINISHED_WINDOW
    return (
        ExamAttempt.objects.filter(exam=exam, is_trial=False)
        .filter(Q(status__in=_OPEN_STATUSES) | Q(finished_at__gte=since))
        .select_related("user", "exam", "exam__supervision_config")
        .order_by("-started_at", "-id")
    )


def _row(attempt, *, config, max_violations, now) -> dict:
    user = attempt.user
    refusal = resume_refusal(attempt, config)
    finished = attempt.is_finished
    return {
        "attempt_id": attempt.pk,
        "exam_id": attempt.exam_id,
        "student_id": attempt.user_id,
        "name": user.get_full_name() or user.username,
        "username": user.username,
        # «active» = imtahandadır (zənginləşdirmə heartbeat/irəliləyişi yalnız buna hesablayır).
        "status": "completed" if finished else "active",
        "state": _state(attempt),
        "supervision_status": attempt.supervision_status,
        "manual_lock": bool(attempt.supervision_manual_lock and attempt.supervision_status == "locked"),
        "violation_count": attempt.supervision_violation_count,
        "max_violations": max_violations,
        "extra_chances": attempt.supervision_extra_chances,
        "language": attempt.language or "",
        "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
        "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
        "remaining_seconds": _remaining_seconds(attempt, now),
        "can_resume": refusal == "",
        "resume_refusal": "" if refusal in ("finished", "not_locked") else refusal,
        "can_pause": bool(config is not None and not finished and attempt.supervision_status not in _LOCK_STATUSES),
    }


def _counts(rows) -> dict:
    counts = {"total": len(rows), STATE_ACTIVE: 0, STATE_WARNED: 0, STATE_LOCKED: 0, STATE_COMPLETED: 0}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    counts["in_exam"] = counts[STATE_ACTIVE] + counts[STATE_WARNED] + counts[STATE_LOCKED]
    counts["flagged"] = sum(1 for row in rows if row.get("flagged"))
    return counts


def exam_room_snapshot(exam) -> dict:
    """İmtahanın «Nəzarət otağı» snapshot-u (JSON-a hazır)."""
    from apps.exams.models import ExamAttempt

    from .actions import sweep_expired_resume_windows

    now = timezone.now()
    # Lazy oxu: bərpa pəncərəsi bitmiş kilidli cəhdlər (fon işi gecikibsə) otağı açanda bağlanır.
    sweep_expired_resume_windows(ExamAttempt.objects.filter(exam=exam))
    config = get_supervision_config(exam)
    max_violations = config.get_max_total_violations() if config is not None else 0
    attempts = list(room_attempts_queryset(exam, now=now)[:ROOM_ROW_LIMIT])
    rows = [_row(attempt, config=config, max_violations=max_violations, now=now) for attempt in attempts]
    rows = enrich_monitor_rows(rows, exam.organization, {attempt.user_id: attempt.user for attempt in attempts})
    # Kilidlilər yuxarıda — nəzarətçi əvvəl onları görsün; sonra imtahanda olanlar, sonda bitənlər.
    order = {STATE_LOCKED: 0, STATE_WARNED: 1, STATE_ACTIVE: 2, STATE_COMPLETED: 3}
    rows.sort(key=lambda row: (order.get(row["state"], 9), (row["name"] or "").lower()))
    return {
        "server_now": now.isoformat(),
        "feature_enabled": exam_supervision_enabled(),
        "supervised": config is not None,
        "max_violations": max_violations,
        "recovery_policy": config.recovery_policy if config is not None else "",
        "counts": _counts(rows),
        "rows": rows,
        "truncated": len(attempts) >= ROOM_ROW_LIMIT,
        "event_labels": event_labels_for_rows(rows),
    }


__all__ = [
    "RECENT_FINISHED_WINDOW",
    "ROOM_ROW_LIMIT",
    "exam_room_snapshot",
    "resume_refusal",
    "room_attempts_queryset",
]
