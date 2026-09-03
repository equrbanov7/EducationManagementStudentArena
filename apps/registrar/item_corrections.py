"""Sərbəst iş + kurs işi üçün sənədli düzəliş servisi (audited, geri alına bilər).

Bal xanası düzəlişi (:mod:`apps.registrar.corrections`) ilə eyni müqavilə:
korrektor (İKT rəhbəri) düzəliş rejimində xanaya klikləyir → səbəb + qeyd + PDF
sənəd (üçü də MƏCBURİ) → tətbiq. Dəyər ``journal_extras`` servisləri ilə
(``allow_locked=True`` — 2 saat pəncərəsi keçilir) yazılır; correction qeydi
snapshot + audit saxlayır; xana sarı işarələnir və geri alına bilər.

corrections.py 600 sətir limitinə yaxın olduğu üçün bu köməkçilər ayrıca modulda.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction
from core.rls import journal_unlock

from . import grade_audit, journal_extras
from .correction_reversals import (  # noqa: F401 — public compatibility facade
    revert_last_component_correction,
    revert_last_coursework_correction,
    revert_last_selfwork_correction,
)
from .corrections import correction_author_name
from .models import (
    ComponentScore,
    ComponentScoreCorrection,
    CorrectionReason,
    CourseWork,
    CourseWorkCorrection,
    SelfWorkCorrection,
)


def _validate(reason, note, document):
    if reason not in CorrectionReason.values:
        raise ValidationError(pgettext("registrar.correction", "Choose a correction reason."))
    note = (note or "").strip()
    if not note:
        raise ValidationError(pgettext("registrar.correction", "A note explaining the correction is required."))
    if not document:
        raise ValidationError(pgettext("registrar.correction", "A justification document (PDF) is required."))
    return note


def _audit(offering, by_user, kind, changes, correction, request):
    """Write both audit records; the caller's atomic block is fail-closed."""
    grade_audit.log_grade_changes(
        offering=offering,
        by_user=by_user,
        kind=kind,
        changes=changes,
        fail_closed=True,
    )
    log_action(
        action=AuditAction.UPDATE,
        user=by_user,
        organization=offering.organization,
        obj=correction,
        reason=f"{kind}",
        request=request,
        changes=[{"field": c.get("item", ""), "old": c.get("old", ""), "new": c.get("new", "")} for c in changes],
    )


# ── Sərbəst iş ───────────────────────────────────────────────────────────────


@transaction.atomic
def apply_selfwork_correction(*, offering, topic, enrollment, new_done, reason, note, document, by_user, request=None):
    """Sərbəst iş xanasına (topic × tələbə) sənədli düzəliş: təhvil 0↔1."""
    note = _validate(reason, note, document)
    from .correction_target_locks import lock_selfwork

    topic, enrollment, mark = lock_selfwork(topic, enrollment)
    old_done = bool(mark and mark.done)
    new_done = bool(new_done)
    if old_done == new_done:
        raise ValidationError(pgettext("registrar.correction", "Nothing changed — adjust a field before saving."))
    ok = journal_extras.set_selfwork_mark(
        offering=offering,
        topic_id=topic.id,
        enrollment_id=enrollment.id,
        done=new_done,
        by_user=by_user,
        allow_locked=True,
    )
    if not ok:
        raise ValidationError(pgettext("registrar.correction", "The journal is published — it can't be changed."))
    correction = SelfWorkCorrection(
        organization=offering.organization,
        topic=topic,
        enrollment=enrollment,
        old_done=old_done,
        new_done=new_done,
        reason=reason,
        note=note,
        document=document,
        corrected_by=by_user,
        corrected_by_name=correction_author_name(by_user, request),
    )
    correction.full_clean()
    correction.save()
    _audit(
        offering,
        by_user,
        "selfwork-correction",
        [
            {
                "student": grade_audit.student_label(enrollment),
                "item": f"{str(pgettext('registrar.correction', 'Self-work'))} · {topic.title[:60]}",
                "old": "1" if old_done else "0",
                "new": "1" if new_done else "0",
            }
        ],
        correction,
        request,
    )
    return correction


# ── Kurs işi ─────────────────────────────────────────────────────────────────


@transaction.atomic
def apply_coursework_correction(
    *, enrollment, new_score, new_topic, new_date, reason, note, document, by_user, request=None
):
    """Kurs işi xanasına (tələbə) sənədli düzəliş: bal / mövzu / tarix."""
    note = _validate(reason, note, document)
    from .correction_target_locks import lock_coursework

    enrollment, existing = lock_coursework(enrollment)
    offering = enrollment.offering
    old_score = existing.score if existing else None
    old_topic = existing.topic if existing else ""
    old_date = existing.submitted_on if existing else None
    ok = journal_extras.save_course_work(
        enrollment=enrollment,
        topic=new_topic,
        score=new_score,
        submitted_on=new_date,
        by_user=by_user,
        allow_locked=True,
    )
    if not ok:
        raise ValidationError(pgettext("registrar.correction", "The journal is published — it can't be changed."))
    fresh = CourseWork.objects.get(enrollment=enrollment)
    if old_score == fresh.score and old_topic == fresh.topic and old_date == fresh.submitted_on:
        raise ValidationError(pgettext("registrar.correction", "Nothing changed — adjust a field before saving."))
    correction = CourseWorkCorrection(
        organization=offering.organization,
        enrollment=enrollment,
        old_score=old_score,
        new_score=fresh.score,
        old_topic=old_topic,
        new_topic=fresh.topic,
        old_date=old_date,
        new_date=fresh.submitted_on,
        reason=reason,
        note=note,
        document=document,
        corrected_by=by_user,
        corrected_by_name=correction_author_name(by_user, request),
    )
    correction.full_clean()
    correction.save()
    _audit(
        offering,
        by_user,
        "coursework-correction",
        [
            {
                "student": grade_audit.student_label(enrollment),
                "item": str(pgettext("registrar.correction", "Course work")),
                "old": grade_audit.score_repr(old_score),
                "new": grade_audit.score_repr(fresh.score),
            }
        ],
        correction,
        request,
    )
    return correction


# ── Kollokvium / komponent balı ──────────────────────────────────────────────


@transaction.atomic
def apply_component_correction(*, component, enrollment, new_score, reason, note, document, by_user, request=None):
    """Komponent balına (Kollokvium K1/K2/K3) sənədli düzəliş — 2 saat + pəncərə keçilir."""
    note = _validate(reason, note, document)
    from .correction_target_locks import lock_component

    component, enrollment, existing = lock_component(component, enrollment)
    offering = component.offering
    if journal_extras.journal_is_locked(offering):
        raise ValidationError(pgettext("registrar.correction", "The journal is published — it can't be changed."))
    old_score = existing.score if existing else None
    if new_score in (None, ""):
        new_val = None
    else:
        new_val = max(Decimal("0"), min(_to_decimal(new_score), Decimal(component.max_score)))
    if old_score == new_val:
        raise ValidationError(pgettext("registrar.correction", "Nothing changed — adjust a field before saving."))
    with journal_unlock():  # ComponentScore-da da 2 saat DB trigger var — rəsmi yolda keçilir.
        if new_val is None:
            if existing is not None:
                existing.delete()
        else:
            ComponentScore.objects.update_or_create(
                organization=offering.organization,
                component=component,
                enrollment=enrollment,
                defaults={"score": new_val, "entered_by": by_user},
            )
    correction = ComponentScoreCorrection(
        organization=offering.organization,
        component=component,
        enrollment=enrollment,
        old_score=old_score,
        new_score=new_val,
        reason=reason,
        note=note,
        document=document,
        corrected_by=by_user,
        corrected_by_name=correction_author_name(by_user, request),
    )
    correction.full_clean()
    correction.save()
    _audit(
        offering,
        by_user,
        "component-correction",
        [
            {
                "student": grade_audit.student_label(enrollment),
                "item": str(getattr(component, "title", "") or getattr(component, "name", "") or "komponent"),
                "old": grade_audit.score_repr(old_score),
                "new": grade_audit.score_repr(new_val),
            }
        ],
        correction,
        request,
    )
    return correction


def _to_decimal(raw):
    return journal_extras._to_decimal(raw)


def _cm_entry(c, include_document):
    data = {
        "id": str(c.id),
        "date": c.created_at.strftime("%d.%m.%Y %H:%M"),
        "field_display": str(pgettext("registrar.correction", "Kollokvium")),
        "old": grade_audit.score_repr(c.old_score),
        "new": grade_audit.score_repr(c.new_score),
        "reason": c.get_reason_display(),
        "note": c.note,
        "by": c.corrected_by_name,
    }
    if include_document and c.document:
        data["document_url"] = c.document.url
    return data


def component_corrections_map(offering, *, include_document=False):
    """{"<component_id>:<enrollment_id>": [düzəliş qeydləri]} — sarı xana + tarixçə."""
    result: dict[str, list[dict]] = {}
    qs = ComponentScoreCorrection.objects.filter(
        component__offering=offering,
        reversal__isnull=True,
    ).order_by("created_at")
    for c in qs:
        result.setdefault(f"{c.component_id}:{c.enrollment_id}", []).append(_cm_entry(c, include_document))
    return result


def annotate_kollokvium_grid(grid, cmap):
    """Kollokvium grid xanalarına `corr_key` + `corrected` (sarı) əlavə et."""
    for row in grid.get("rows", []):
        for cell in row.get("cells", []):
            comp = cell.get("component")
            if comp is not None:
                key = f"{comp.id}:{row['enrollment'].id}"
                cell["corr_key"] = key
                cell["corrected"] = key in cmap
    return grid


# ── Oxu köməkçiləri (sarı xana + tarixçə) ────────────────────────────────────


def _sw_entry(c, include_document):
    data = {
        "id": str(c.id),
        "date": c.created_at.strftime("%d.%m.%Y %H:%M"),
        "field_display": str(pgettext("registrar.correction", "Self-work")),
        "old": "1" if c.old_done else "0",
        "new": "1" if c.new_done else "0",
        "reason": c.get_reason_display(),
        "note": c.note,
        "by": c.corrected_by_name,
    }
    if include_document and c.document:
        data["document_url"] = c.document.url
    return data


def _cw_entry(c, include_document):
    data = {
        "id": str(c.id),
        "date": c.created_at.strftime("%d.%m.%Y %H:%M"),
        "field_display": str(pgettext("registrar.correction", "Course work")),
        "old": grade_audit.score_repr(c.old_score),
        "new": grade_audit.score_repr(c.new_score),
        "reason": c.get_reason_display(),
        "note": c.note,
        "by": c.corrected_by_name,
    }
    if include_document and c.document:
        data["document_url"] = c.document.url
    return data


def annotate_selfwork_board(board, cmap):
    """Sərbəst iş board xanalarına `corr_key` + `corrected` (sarı) əlavə et."""
    for row in board.get("rows", []):
        for cell in row.get("cells", []):
            topic = cell.get("topic")
            if topic is not None:
                key = f"{topic.id}:{row['enrollment'].id}"
                cell["corr_key"] = key
                cell["corrected"] = key in cmap
    return board


def annotate_coursework_rows(rows, cmap):
    """Kurs işi sətirlərinə `corr_key` + `corrected` (sarı) əlavə et."""
    for row in rows:
        key = str(row["enrollment"].id)
        row["corr_key"] = key
        row["corrected"] = key in cmap
    return rows


def selfwork_corrections_map(offering, *, include_document=False):
    """{"<topic_id>:<enrollment_id>": [düzəliş qeydləri]} — sarı xana + tarixçə."""
    result: dict[str, list[dict]] = {}
    qs = SelfWorkCorrection.objects.filter(
        topic__offering=offering,
        reversal__isnull=True,
    ).order_by("created_at")
    for c in qs:
        result.setdefault(f"{c.topic_id}:{c.enrollment_id}", []).append(_sw_entry(c, include_document))
    return result


def coursework_corrections_map(offering, *, include_document=False):
    """{"<enrollment_id>": [düzəliş qeydləri]} — sarı sətir + tarixçə."""
    result: dict[str, list[dict]] = {}
    qs = CourseWorkCorrection.objects.filter(
        enrollment__offering=offering,
        reversal__isnull=True,
    ).order_by("created_at")
    for c in qs:
        result.setdefault(str(c.enrollment_id), []).append(_cw_entry(c, include_document))
    return result


# COURSE_WORK_MAX re-export (validasiya üçün — journal_extras-dən).
COURSE_WORK_MAX = Decimal("100")


def annotate_normal_view(offering, context):
    """Normal (düzəliş-rejimsiz) görünüş üçün sərbəst iş / kurs işi / kollokvium
    board-larını sarı düzəliş işarəsi (``corrected`` + ``corr_key``) ilə annotasiya
    et (yerində) və read-only tarixçə map-larını qaytar (sənədsiz). Beləcə bal
    xanası kimi bu tab-larda da düzəlişli xana normal görünüşdə sarı olur + kliklə
    tarixçə açılır. Kontekst-də board-lar artıq qurulub — onları dəyişirik."""
    sw = selfwork_corrections_map(offering)
    cw = coursework_corrections_map(offering)
    cm = component_corrections_map(offering)
    if context.get("selfwork_board"):
        annotate_selfwork_board(context["selfwork_board"], sw)
    if context.get("coursework_rows") is not None:
        annotate_coursework_rows(context["coursework_rows"], cw)
    if context.get("kollokvium_grid"):
        annotate_kollokvium_grid(context["kollokvium_grid"], cm)
    return {
        "selfwork_corrections_map": sw,
        "coursework_corrections_map": cw,
        "component_corrections_map": cm,
    }
