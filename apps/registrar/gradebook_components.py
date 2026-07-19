"""Çəkili qiymətləndirmə komponentləri (U7.1) — gradebook-un davamı.

``gradebook.py`` modul-ölçü büdcəsinə görə bölünüb: giriş balının kanonik
hesablanması və komponent CRUD-u buradadır. Bütün ictimai adlar
``gradebook``-dan re-eksport olunur — çağıranlar üçün API dəyişməyib.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.registrar import grade_audit
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    LessonMark,
    SelfWorkMark,
)

from .gradebook import MARK_EDIT_WINDOW, _to_decimal, journal_is_locked  # noqa: F401

# ── Çəkili qiymətləndirmə komponentləri (U7.1) ───────────────────────────────


def entry_score_for(enrollment, cap, *, marks=None, components=None) -> Decimal:
    """Canonical semester entry score, capped at ``cap`` (≈ entry_score_max).

    Qayda (analytics._evaluate ilə GÜZGÜ saxlanmalıdır):
    * GENERIC komponentlər varsa → onların cəmi lesson-cəmi ƏVƏZ edir
      (köhnə çəkili-komponent davranışı); yoxdursa seminar/lab dərs ballarının
      cəmi işlədilir;
    * KOLLOKVIUM komponent balları həmişə ÜSTƏGƏLdir;
    * SƏRBƏST İŞ çeklist cəmi (təhvil sayı) həmişə ÜSTƏGƏLdir;
    * yekun ``cap`` ilə clamp olunur.

    Performans: ``marks`` (bu enrollment-in LessonMark-ları) və ``components``
    (offering-in AssessmentComponent-ləri) əvvəlcədən verilə bilər — toplu
    (batch) çağırışlarda per-subject təkrar sorğunu aradan qaldırır. Verilməsə
    əvvəlki kimi ayrıca sorğulanır (geriyə-uyğun)."""
    cap = Decimal(cap)
    if components is None:
        components = list(AssessmentComponent.objects.filter(offering=enrollment.offering))
    generic = [c for c in components if c.kind == ComponentKind.GENERIC]
    kollokvium = [c for c in components if c.kind == ComponentKind.KOLLOKVIUM]
    selfwork = [c for c in components if c.kind == ComponentKind.SELF_WORK]

    if generic:
        max_by = {c.id: Decimal(c.max_score) for c in generic}
        total = sum(
            (
                min(cs.score or Decimal("0"), max_by[cs.component_id])
                for cs in ComponentScore.objects.filter(component_id__in=list(max_by), enrollment=enrollment)
            ),
            Decimal("0"),
        )
    else:
        mark_iter = marks if marks is not None else LessonMark.objects.filter(enrollment=enrollment)
        total = sum((m.score for m in mark_iter if m.score is not None), Decimal("0"))

    if kollokvium:
        kmax_by = {c.id: Decimal(c.max_score) for c in kollokvium}
        total += sum(
            (
                min(cs.score or Decimal("0"), kmax_by[cs.component_id])
                for cs in ComponentScore.objects.filter(component_id__in=list(kmax_by), enrollment=enrollment)
            ),
            Decimal("0"),
        )
    if selfwork:
        done = SelfWorkMark.objects.filter(
            enrollment=enrollment, topic__offering=enrollment.offering, done=True
        ).count()
        for comp in selfwork:
            total += min(Decimal(done), Decimal(comp.max_score))
    return min(total, cap)


def get_components(offering):
    """Ordered assessment components of an offering."""
    return list(AssessmentComponent.objects.filter(offering=offering).order_by("order", "name"))


@transaction.atomic
def save_components(*, offering, definitions, by_user=None):
    """Upsert/delete an offering's assessment components from ``definitions``.

    ``definitions`` = list of ``{"id"?, "name", "max_score", "rubric_id"?}``.
    Rows with an id not present are deleted. Blocked once the journal is locked."""
    if journal_is_locked(offering):
        return get_components(offering)

    from apps.registrar.models import Rubric

    org_rubrics = {str(r.id): r for r in Rubric.objects.filter(organization=offering.organization, is_active=True)}
    existing = {str(c.id): c for c in AssessmentComponent.objects.filter(offering=offering)}
    existing_by_name = {c.name.strip().lower(): c for c in existing.values()}
    seen: set = set()
    for order, defn in enumerate(definitions):
        name = (defn.get("name") or "").strip()
        if not name:
            continue
        max_score = max(1, min(100, int(_to_decimal(defn.get("max_score")))))
        # Match by explicit id, else by (case-insensitive) name so a re-save
        # without ids upserts instead of colliding with the unique (offering, name).
        rubric = org_rubrics.get(str(defn.get("rubric_id") or ""))  # U22: meyar şablonu (opsional)
        component = existing.get(str(defn.get("id") or "")) or existing_by_name.get(name.lower())
        if component is not None and str(component.id) not in seen:
            component.name = name
            component.max_score = max_score
            component.order = order
            component.rubric = rubric
            component.save(update_fields=["name", "max_score", "order", "rubric"])
            seen.add(str(component.id))
        elif component is None:
            created = AssessmentComponent.objects.create(
                organization=offering.organization,
                offering=offering,
                name=name,
                max_score=max_score,
                order=order,
                rubric=rubric,
            )
            seen.add(str(created.id))
    # Drop components the teacher removed from the form.
    for cid, component in existing.items():
        if cid not in seen:
            component.delete()
    return get_components(offering)


@transaction.atomic
def save_component_scores(*, offering, entries, by_user=None, bypass_edit_window=False):
    """Persist per-(component, enrollment) scores. ``entries`` = list of
    ``{"component_id", "enrollment_id", "score"}``. Lock-aware + tenant-safe.

    ``bypass_edit_window``: kollokvium İmtahan Mərkəzi pəncərəsi AÇIQ olduqda True
    verilir — 2 saat kilidini HƏM servis-səviyyəsində, HƏM DB trigger-ində
    (``journal_unlock`` GUC) bypass edir ki, müəllim aralıq boyu balı dəyişsin.
    """
    from contextlib import nullcontext

    from core.rls import journal_unlock

    if journal_is_locked(offering):
        return 0

    valid_components = {str(c.id): c for c in AssessmentComponent.objects.filter(offering=offering)}
    valid_enrollments = {str(e.id): e for e in offering.enrollments.all()}
    written = 0
    audit_changes = []
    notify_events = []
    now = timezone.now()
    with journal_unlock() if bypass_edit_window else nullcontext():
        for entry in entries:
            component = valid_components.get(str(entry.get("component_id")))
            enrollment = valid_enrollments.get(str(entry.get("enrollment_id")))
            if component is None or enrollment is None:
                continue
            # Kollokvium YALNIZ pəncərə-yoxlanışlı yolla (journal_actions.kollokvium_save,
            # bypass_edit_window=True) yazıla bilər — generic cscore__/rubrik yolları
            # İmtahan Mərkəzi pəncərəsini YAN KEÇMƏMƏLİDİR.
            if component.kind == ComponentKind.KOLLOKVIUM and not bypass_edit_window:
                continue
            existing = ComponentScore.objects.filter(component=component, enrollment=enrollment).first()
            if not bypass_edit_window and existing is not None and (now - existing.created_at) > MARK_EDIT_WINDOW:
                continue  # komponent balı da 2 saatdan sonra toxunulmazdır (kollokvium istisna — pəncərə)
            old_score = existing.score if existing else None
            raw = entry.get("score")
            if raw in (None, ""):
                if existing is not None:
                    existing.delete()
                    audit_changes.append(_component_change(component, enrollment, old_score, None))
                continue
            score = max(Decimal("0"), min(_to_decimal(raw), Decimal(component.max_score)))
            ComponentScore.objects.update_or_create(
                organization=offering.organization,
                component=component,
                enrollment=enrollment,
                defaults={"score": score, "entered_by": by_user},
            )
            if old_score != score:
                audit_changes.append(_component_change(component, enrollment, old_score, score))
                from apps.registrar import journal_notifications as jn

                kind = jn.EVENT_KOLLOKVIUM if component.kind == ComponentKind.KOLLOKVIUM else jn.EVENT_SCORE
                notify_events.append({"enrollment": enrollment, "kind": kind, "score": score})
            written += 1
    grade_audit.log_grade_changes(offering=offering, by_user=by_user, kind="component", changes=audit_changes)

    if notify_events:
        from django.db import transaction as _tx

        from apps.registrar import journal_notifications as jn

        _tx.on_commit(lambda: jn.send_journal_events(offering=offering, events=notify_events))
    return written


def _component_change(component, enrollment, old_score, new_score):
    return {
        "student": grade_audit.student_label(enrollment),
        "item": component.name,
        "old": grade_audit.score_repr(old_score),
        "new": grade_audit.score_repr(new_score),
    }


def get_component_grid(offering):
    """Teacher grid: components (columns) × enrolled students (rows) + scores."""
    components = get_components(offering)
    enrollments = list(
        offering.enrollments.filter(status=offering.enrollments.model.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    comp_ids = [c.id for c in components]
    score_map: dict = {}
    if comp_ids:
        for cs in ComponentScore.objects.filter(component_id__in=comp_ids, enrollment__offering=offering):
            score_map[(cs.enrollment_id, cs.component_id)] = cs.score
    rows = [
        {
            "enrollment": e,
            "student": e.student,
            "cells": [{"component": c, "score": score_map.get((e.id, c.id))} for c in components],
        }
        for e in enrollments
    ]
    total_max = sum(c.max_score for c in components)
    return {"components": components, "rows": rows, "total_max": total_max}


def get_component_breakdown(enrollment):
    """Student-facing per-component breakdown (name, score, max)."""
    components = get_components(enrollment.offering)
    if not components:
        return []
    comp_ids = [c.id for c in components]
    score_by = {
        cs.component_id: cs.score
        for cs in ComponentScore.objects.filter(component_id__in=comp_ids, enrollment=enrollment)
    }
    return [{"name": c.name, "score": score_by.get(c.id), "max": c.max_score} for c in components]
