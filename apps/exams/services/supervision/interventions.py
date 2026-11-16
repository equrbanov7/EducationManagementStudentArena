"""Tələbəyə görünən nəzarətçi müdaxiləsi məlumatları."""

from apps.exams.models import FinalExamTicket, SupervisionIncident

_VISIBLE_STATUSES = {"locked", "removed"}
_INCIDENT_ACTIONS = {"teacher_temporary_lock", "teacher_force_stopped"}
# Sahib 2026-11-16: nəticə ləğvi (``final_center.result_annul``) — bilet/digər müdaxilədən ÜSTÜNDÜR.
_ANNUL_ACTION = "result_annulled"


def _blank_intervention():
    return {
        "action": "",
        "reason": "",
        "is_terminal": False,
        "is_annulled": False,
    }


def _annulled_intervention(incident):
    metadata = incident.metadata if isinstance(incident.metadata, dict) else {}
    return {
        "action": "annulled",
        "reason": (metadata.get("display_reason") or "").strip(),
        "is_terminal": True,
        "is_annulled": True,
    }


def _build_intervention(attempt, *, ticket=None, incident=None):
    if attempt.supervision_status not in _VISIBLE_STATUSES:
        return _blank_intervention()

    action = ""
    reason = ""
    if ticket is not None:
        action = (ticket.removal_action or "").strip()
        reason = (ticket.removal_reason or "").strip()

    metadata = incident.metadata if incident is not None and isinstance(incident.metadata, dict) else {}
    if not reason:
        reason = (metadata.get("display_reason") or "").strip()

    is_terminal = attempt.supervision_status == "removed"
    if not action:
        action = "removed" if is_terminal else "suspended"

    return {
        "action": action,
        "reason": reason,
        "is_terminal": is_terminal,
        # Uzaqlaşdırma (texniki dayandırma yox) = nəticə ləğv olunub (jurnalda 0) — tələbəyə qeyd.
        "is_annulled": is_terminal and action == "removed",
    }


def get_attempt_intervention(attempt):
    """Bir attempt üçün hazırkı/son nəzarətçi müdaxiləsini qaytar."""
    if attempt.supervision_status not in _VISIBLE_STATUSES:
        return _blank_intervention()

    annul = (
        SupervisionIncident.objects.filter(attempt_id=attempt.pk, teacher_action=_ANNUL_ACTION)
        .only("attempt_id", "metadata", "teacher_action")
        .order_by("-timestamp", "-id")
        .first()
    )
    if annul is not None:
        return _annulled_intervention(annul)

    ticket = (
        FinalExamTicket.objects.filter(attempt_id=attempt.pk)
        .only("attempt_id", "removal_action", "removal_reason")
        .order_by("-updated_at", "-id")
        .first()
    )
    if ticket is not None and (ticket.removal_reason or "").strip():
        return _build_intervention(attempt, ticket=ticket)

    incident = (
        SupervisionIncident.objects.filter(
            attempt_id=attempt.pk,
            teacher_action__in=_INCIDENT_ACTIONS,
        )
        .only("attempt_id", "metadata", "teacher_action")
        .order_by("-timestamp", "-id")
        .first()
    )
    return _build_intervention(attempt, ticket=ticket, incident=incident)


def attach_attempt_interventions(attempts):
    """Nəticə siyahısına müdaxilə məlumatını N+1 yaratmadan əlavə et."""
    attempts = list(attempts)
    attempt_ids = [attempt.pk for attempt in attempts if attempt.pk and attempt.supervision_status in _VISIBLE_STATUSES]
    if not attempt_ids:
        for attempt in attempts:
            attempt.exam_intervention = _blank_intervention()
        return attempts

    tickets_by_attempt = {}
    tickets = (
        FinalExamTicket.objects.filter(attempt_id__in=attempt_ids)
        .only("attempt_id", "removal_action", "removal_reason", "updated_at")
        .order_by("attempt_id", "-updated_at", "-id")
    )
    for ticket in tickets:
        tickets_by_attempt.setdefault(ticket.attempt_id, ticket)

    incidents_by_attempt = {}
    incidents = (
        SupervisionIncident.objects.filter(
            attempt_id__in=attempt_ids,
            teacher_action__in=_INCIDENT_ACTIONS | {_ANNUL_ACTION},
        )
        .only("attempt_id", "metadata", "teacher_action", "timestamp")
        .order_by("attempt_id", "-timestamp", "-id")
    )
    annul_by_attempt = {}
    for incident in incidents:
        if incident.teacher_action == _ANNUL_ACTION:
            annul_by_attempt.setdefault(incident.attempt_id, incident)
        else:
            incidents_by_attempt.setdefault(incident.attempt_id, incident)

    for attempt in attempts:
        if attempt.pk in annul_by_attempt:
            attempt.exam_intervention = _annulled_intervention(annul_by_attempt[attempt.pk])
            continue
        attempt.exam_intervention = _build_intervention(
            attempt,
            ticket=tickets_by_attempt.get(attempt.pk),
            incident=incidents_by_attempt.get(attempt.pk),
        )
    return attempts
