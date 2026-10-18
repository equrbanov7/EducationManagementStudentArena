"""25% / alt qrup — OXU qatı: tələbə paneli, iz (trail), nəticə sətirləri (sahib 2026-10-18).

Sorğu sayı siyahı uzunluğundan ASILI DEYİL: müraciətlər, hadisələr (``Prefetch``), qəbzlər və imtahan şansı
qeydləri hər biri tək sorğu ilə oxunur; uyğunluq ``retake_eligibility`` (toplu ``finals_batch``) ilədir.
Heyət növbəsi (Mühasibatlıq / dekanlıq) :mod:`apps.registrar.retake_desk`-dədir.
"""

from __future__ import annotations

from django.db.models import Prefetch
from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy

from core.media_urls import protected_media_url

from . import retake_eligibility, retake_rules
from .models import (
    ExamChanceGrant,
    ExamChanceReason,
    RetakeActorRole,
    RetakeApplication,
    RetakeApplicationEvent,
    RetakeEventAction,
    RetakeKind,
    RetakeReceipt,
    RetakeRefundState,
    RetakeStatus,
)
from .models.retake import consumes_attempt

_CTX = "registrar.retake"

#: Hadisə → timeline nöqtəsinin tonu.
_EVENT_TONES = {
    RetakeEventAction.SUBMITTED: "info",
    RetakeEventAction.RECEIPT_UPLOADED: "warning",
    RetakeEventAction.PAYMENT_VERIFIED: "success",
    RetakeEventAction.PAYMENT_REJECTED: "danger",
    RetakeEventAction.ADMITTED: "primary",
    RetakeEventAction.SUBGROUP_APPROVED: "primary",
    RetakeEventAction.PLACED: "success",
    RetakeEventAction.REJECTED: "danger",
    RetakeEventAction.EXAM_GRANTED: "primary",
    RetakeEventAction.RESULT_RECORDED: "success",
    RetakeEventAction.WITHDRAWN: "muted",
    RetakeEventAction.REFUND_DECIDED: "warning",
    RetakeEventAction.REFUNDED: "success",
}

BASE_LABEL = pgettext_lazy(_CTX, "Əsas imtahan")
RETAKE_LABEL = pgettext_lazy(_CTX, "25%")


def fmt(value) -> str:
    if value is None:
        return "—"
    try:
        return format(value.normalize(), "f")
    except AttributeError:
        return str(value)


def events_prefetch():
    return Prefetch("events", queryset=RetakeApplicationEvent.objects.order_by("created_at"), to_attr="ordered_events")


def timeline(application) -> list:
    events = getattr(application, "ordered_events", None)
    if events is None:
        events = list(application.events.order_by("created_at"))
    rows = []
    last = len(events) - 1
    for index, event in enumerate(events):
        role = RetakeActorRole(event.actor_role).label if event.actor_role else ""
        who = " · ".join(part for part in (str(role), event.actor_name) if part)
        what = str(RetakeEventAction(event.action).label)
        if event.to_status and event.from_status and event.to_status != event.from_status:
            what = f"{what} → {RetakeStatus(event.to_status).label}"
        reference = (event.metadata or {}).get("payment_reference")
        if reference:
            what = f"{what} · {pgettext(_CTX, 'Ödəniş №')}: {reference}"
        refund_amount = (event.metadata or {}).get("refund_amount")
        if refund_amount and event.action in (RetakeEventAction.REFUND_DECIDED, RetakeEventAction.REFUNDED):
            what = f"{what} · {refund_amount} AZN"
        score = (event.metadata or {}).get("score")
        if score and event.action == RetakeEventAction.RESULT_RECORDED:
            what = f"{what} · {pgettext(_CTX, 'Bal')}: {score}"
        rows.append(
            {
                "who": who,
                "when": event.created_at,
                "what": what,
                "reason": event.note,
                "tone": _EVENT_TONES.get(event.action, "neutral"),
                "current": index == last,
            }
        )
    return rows


def result_text(application) -> str:
    """«Əsas imtahan: 32 → 25%: 61» — nəticə yazılmayıbsa boş sətir."""
    if application.result_score is None:
        return ""
    return f"{BASE_LABEL}: {fmt(application.base_exam_score)} → {RETAKE_LABEL}: {fmt(application.result_score)}"


def decorate(application, *, viewer_is_student=False) -> dict:
    receipt = application.current_receipt
    return {
        "app": application,
        "id": str(application.pk),
        "kind_label": RetakeKind(application.kind).label,
        "status_label": RetakeStatus(application.status).label,
        "tone": retake_rules.tone_for(application.status),
        "next_step": retake_rules.next_step_for(application),
        "timeline": timeline(application),
        "can_withdraw": viewer_is_student and application.status in retake_rules.WITHDRAWABLE,
        "can_upload_receipt": (
            viewer_is_student
            and application.kind == RetakeKind.RETAKE_25
            and application.status in retake_rules.RECEIPT_UPLOADABLE
        ),
        "receipt": receipt,
        "receipt_url": protected_media_url(receipt.file) if receipt is not None else "",
        "document_url": protected_media_url(application.decision_document) if application.decision_document else "",
        "closure_document_url": (
            protected_media_url(application.closure_document) if application.closure_document else ""
        ),
        "result_text": result_text(application),
        "eligibility": application.eligibility or {},
        **refund_info(application),
    }


def refund_info(application) -> dict:
    """2026-10-19: qaytarılma vəziyyəti (tələbə kartı, növbə sətri) — «» / qərar verilib / qaytarılıb."""
    state = application.refund_state or ""
    if not state:
        return {"refund_state": "", "refund_label": "", "refund_document_url": ""}
    return {
        "refund_state": state,
        "refund_label": str(RetakeRefundState(state).label),
        "refund_amount_text": fmt(application.refund_amount),
        # Review 2026-10-19: qərar cəhdi bərpa edibmi (``refund_restores_attempt``) — nəticə həqiqi sayğacdan.
        "refund_restores_attempt": application.refund_restores_attempt,
        "refund_attempt_label": (
            pgettext(_CTX, "25% cəhdi istifadə olunmuş sayılır")
            if consumes_attempt(application)
            else pgettext(_CTX, "25% cəhdi istifadə olunmuş sayılmır")
        ),
        "refund_document_url": (
            protected_media_url(application.refund_document) if application.refund_document else ""
        ),
    }


def student_applications(*, student, organization) -> list:
    return list(
        RetakeApplication.objects.filter(organization=organization, student=student)
        .select_related("subject", "period", "current_receipt", "target_offering", "target_offering__group")
        .prefetch_related(events_prefetch())
        .order_by("-created_at")
    )


def _grants_by_subject(grants) -> dict:
    grouped: dict = {}
    for grant in grants:
        grouped.setdefault(grant.subject_id, []).append(grant)
    return grouped


def attempt_history(applications, grants) -> list:
    """Fənn başına «neçə dəfə 25%-ə girib, nə olub»: əsas bal, hər cəhd, şans qeydləri, yekun."""
    by_subject: dict = {}
    for application in sorted(applications, key=lambda a: a.created_at):
        entry = by_subject.setdefault(
            application.subject_id,
            {"subject": application.subject, "base": application.base_exam_score, "attempts": [], "subgroup": []},
        )
        if application.kind == RetakeKind.SUBGROUP:
            entry["subgroup"].append(application)
        elif application.status in (RetakeStatus.ADMITTED, RetakeStatus.EXAM_GRANTED, RetakeStatus.COMPLETED):
            entry["attempts"].append(application)
    grants_by_subject = _grants_by_subject(grants)
    rows = []
    for subject_id, entry in by_subject.items():
        attempts = entry["attempts"]
        last_scored = next((a for a in reversed(attempts) if a.result_score is not None), None)
        rows.append(
            {
                "subject": entry["subject"],
                "base": entry["base"],
                "attempts": attempts,
                "attempt_count": len(attempts),
                "subgroup": entry["subgroup"],
                "grants": grants_by_subject.get(subject_id, []),
                "final_score": last_scored.result_score if last_scored else None,
                "final_passed": last_scored.result_passed if last_scored else None,
                "chain": " → ".join(
                    [f"{BASE_LABEL}: {fmt(entry['base'])}"]
                    + [f"{RETAKE_LABEL} #{a.attempt_number}: {fmt(a.result_score)}" for a in attempts]
                ),
            }
        )
    return rows


def student_grants(*, student, organization) -> list:
    return list(
        ExamChanceGrant.objects.filter(organization=organization, student=student)
        .select_related("application")
        .order_by("created_at")
    )


def student_panel(*, student, organization) -> dict:
    subjects = retake_eligibility.failed_subjects(student=student, organization=organization)
    applications = student_applications(student=student, organization=organization)
    grants = student_grants(student=student, organization=organization)
    active = [a for a in applications if a.is_active]
    # 2026-10-19 (sahib): təxmini məbləğ (təhsil haqqı cədvəli + düstur) — 2 sorğu, fənn sayından asılı deyil.
    from . import retake_fees, retake_window

    fee_context = retake_fees.student_context(student, organization)
    for row in subjects:
        row["fee"] = retake_fees.estimate(context=fee_context, period=row["period"], subject=row["subject"])
    window = retake_window.current(organization)
    return {
        "subjects": subjects,
        "eligible_count": sum(1 for row in subjects if row["any_allowed"]),
        "applications": [decorate(a, viewer_is_student=True) for a in applications],
        "active_count": len(active),
        "history": attempt_history(applications, grants),
        "window_open": retake_rules.master_switch() and window is not None,
        "window": window,
        "upcoming_window": None if window is not None else retake_window.upcoming(organization),
        "max_attempts": retake_rules.max_attempts(),
        "urls": {"apply": reverse("retake:apply")},
        "accept": ".pdf,.jpg,.jpeg,.png",
    }


def student_trail(*, student, organization) -> dict:
    """Heyətin iz görünüşü — bütün müraciətlər, hadisələr, bütün qəbz yükləmələri, şans qeydləri, nəticələr."""
    applications = student_applications(student=student, organization=organization)
    grants = student_grants(student=student, organization=organization)
    receipts = list(
        RetakeReceipt.objects.filter(organization=organization, application__student=student).order_by("created_at")
    )
    receipts_by_app: dict = {}
    for receipt in receipts:
        receipts_by_app.setdefault(receipt.application_id, []).append(
            {"receipt": receipt, "url": protected_media_url(receipt.file)}
        )
    decorated = []
    for application in applications:
        row = decorate(application)
        row["receipts"] = receipts_by_app.get(application.pk, [])
        decorated.append(row)
    return {
        "student": student,
        "applications": decorated,
        "history": attempt_history(applications, grants),
        "grants": grants,
    }


def result_lines(*, organization, enrollment_ids) -> dict:
    """``enrollment_id`` → nəticə izi (tək sorğu) — «Nəticələrim», «Jurnalım», «Ümumi tədris məlumatı».

    Sətir: ``{"text": "Əsas imtahan: 32 → 25%: 61", "base": …, "attempts": [(n, bal, keçdi)], "passed": …}``.
    """
    ids = [pk for pk in enrollment_ids if pk]
    if not ids or organization is None:
        return {}
    rows = (
        RetakeApplication.objects.filter(
            organization_id=getattr(organization, "pk", organization),
            enrollment_id__in=ids,
            kind=RetakeKind.RETAKE_25,
            result_score__isnull=False,
        )
        .only("enrollment_id", "base_exam_score", "result_score", "result_passed", "attempt_number", "created_at")
        .order_by("created_at")
    )
    lines: dict = {}
    for application in rows:
        entry = lines.setdefault(
            application.enrollment_id, {"base": application.base_exam_score, "attempts": [], "passed": None}
        )
        entry["attempts"].append(
            {
                "number": application.attempt_number,
                "score": application.result_score,
                "passed": application.result_passed,
            }
        )
        entry["passed"] = application.result_passed
    for entry in lines.values():
        parts = [f"{BASE_LABEL}: {fmt(entry['base'])}"]
        parts += [f"{RETAKE_LABEL}: {fmt(a['score'])}" for a in entry["attempts"]]
        entry["text"] = " → ".join(parts)
    return lines


def grant_reason_label(reason) -> str:
    try:
        return str(ExamChanceReason(reason).label)
    except ValueError:
        return str(reason or "")


__all__ = [
    "attempt_history",
    "decorate",
    "events_prefetch",
    "fmt",
    "grant_reason_label",
    "refund_info",
    "result_lines",
    "result_text",
    "student_applications",
    "student_panel",
    "student_trail",
    "timeline",
]
