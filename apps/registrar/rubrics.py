"""Qiymətləndirmə rubrikaları (U22) — servis qatı.

Rubrik = org-səviyyəli, təkrar istifadə olunan meyar şablonu. Komponentə
qoşulanda müəllim tələbəni meyar-meyar qiymətləndirir; meyar ballarının cəmi
komponent balına yazılır (komponentin ``max_score``-u ilə clamp) — yəni rubrik
mövcud komponent → giriş balı → yekun axınının İÇİNDƏ işləyir, ayrıca hesablama
yolu açmır. Komponent balı :func:`gradebook.save_component_scores` ilə yazılır
ki, kilid (approval) və qiymət auditi semantikası dəyişməz qalsın.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum

from apps.registrar import gradebook
from apps.registrar.models import CriterionScore, Rubric, RubricCriterion

_MAX_CRITERIA = 20


def _to_decimal(raw) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


# ── Rubrik CRUD (registrar konsolu) ──────────────────────────────────────────


def parse_criteria_text(text: str) -> list[tuple[str, int]]:
    """Konsol mətn formatı: hər sətir (və ya vergül) ``ad:bal`` → meyar siyahısı.

    ``ValueError`` istifadəçiyə göstərilə bilən AZ mesajla atılır."""
    rows: list[tuple[str, int]] = []
    seen: set[str] = set()
    for chunk in (text or "").replace("\n", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, sep, points_raw = chunk.rpartition(":")
        name = name.strip()
        if not sep or not name:
            raise ValueError(f"Format 'meyar adı:bal' olmalıdır: {chunk!r}")
        try:
            points = int(points_raw.strip())
        except ValueError:
            raise ValueError(f"Bal tam ədəd olmalıdır: {chunk!r}")
        if not 1 <= points <= 100:
            raise ValueError(f"Meyar balı 1–100 aralığında olmalıdır: {chunk!r}")
        if name.lower() in seen:
            raise ValueError(f"Meyar təkrarlanır: {name}")
        seen.add(name.lower())
        rows.append((name, points))
    if not 1 <= len(rows) <= _MAX_CRITERIA:
        raise ValueError(f"Meyar sayı 1–{_MAX_CRITERIA} aralığında olmalıdır.")
    return rows


def criteria_text(rubric) -> str:
    """``parse_criteria_text``-in tərsi (konsol formu üçün)."""
    return "\n".join(f"{c.name}:{c.max_points}" for c in rubric.criteria.all())


@transaction.atomic
def save_rubric(*, organization, name, criteria, description="", rubric=None):
    """Rubriki (+ meyarlarını) yarat/yenilə. ``criteria`` = [(ad, bal), …].

    Meyarlar ada görə upsert olunur ki, mövcud :class:`CriterionScore`-lar ad
    dəyişməyəndə itməsin; siyahıdan çıxarılan meyarlar silinir."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Rubrik adı boş ola bilməz.")
    if rubric is None:
        rubric = Rubric.objects.create(organization=organization, name=name, description=description.strip())
    else:
        rubric.name = name
        rubric.description = description.strip()
        rubric.save(update_fields=["name", "description", "updated_at"])

    existing = {c.name.strip().lower(): c for c in rubric.criteria.all()}
    seen_ids: set = set()
    for order, (criterion_name, max_points) in enumerate(criteria):
        criterion = existing.get(criterion_name.strip().lower())
        if criterion is not None:
            criterion.name = criterion_name
            criterion.max_points = max_points
            criterion.order = order
            criterion.save(update_fields=["name", "max_points", "order", "updated_at"])
        else:
            criterion = RubricCriterion.objects.create(
                organization=organization,
                rubric=rubric,
                name=criterion_name,
                max_points=max_points,
                order=order,
            )
        seen_ids.add(criterion.id)
    rubric.criteria.exclude(id__in=seen_ids).delete()
    return rubric


# ── Meyar-meyar qiymətləndirmə (jurnal) ──────────────────────────────────────


def get_rubric_grid(component):
    """Rubrik qiymətləndirmə cədvəli: meyarlar (sütun) × tələbələr (sətir).

    ``component.rubric`` yoxdursa ``None`` qaytarır."""
    rubric = component.rubric
    if rubric is None:
        return None
    criteria = list(rubric.criteria.all())
    enrollments = list(
        component.offering.enrollments.select_related("student").order_by(
            "student__last_name", "student__first_name", "student__username"
        )
    )
    points_map = {
        (score.criterion_id, score.enrollment_id): score.points
        for score in CriterionScore.objects.filter(criterion__rubric=rubric, enrollment__in=enrollments)
    }
    component_scores = {cs.enrollment_id: cs.score for cs in component.scores.filter(enrollment__in=enrollments)}
    rows = []
    for enrollment in enrollments:
        cells = [
            {"criterion": criterion, "points": points_map.get((criterion.id, enrollment.id))} for criterion in criteria
        ]
        rows.append(
            {
                "enrollment": enrollment,
                "student": enrollment.student,
                "cells": cells,
                "total": component_scores.get(enrollment.id),
            }
        )
    return {
        "rubric": rubric,
        "component": component,
        "criteria": criteria,
        "rows": rows,
        "criteria_max_total": sum(c.max_points for c in criteria),
    }


@transaction.atomic
def save_criterion_scores(*, component, entries, by_user=None):
    """Meyar ballarını yaz + komponent ballarını yenidən hesabla.

    ``entries`` = [{"criterion_id", "enrollment_id", "points"}, …]. Hər bal
    0..meyar.max_points aralığına clamp olunur. Toxunulan hər tələbənin
    komponent balı = meyar cəmi (komponent.max_score ilə clamp) və
    :func:`gradebook.save_component_scores` ilə yazılır — kilid + audit oradan
    gəlir. Jurnal kilidlidirsə heç nə yazılmır (0 qaytarır)."""
    rubric = component.rubric
    if rubric is None or gradebook.journal_is_locked(component.offering):
        return 0

    valid_criteria = {str(c.id): c for c in rubric.criteria.all()}
    valid_enrollments = {str(e.id): e for e in component.offering.enrollments.all()}
    touched: set = set()
    written = 0
    for entry in entries:
        criterion = valid_criteria.get(str(entry.get("criterion_id")))
        enrollment = valid_enrollments.get(str(entry.get("enrollment_id")))
        if criterion is None or enrollment is None:
            continue
        raw = entry.get("points")
        if raw in (None, ""):
            deleted, _ = CriterionScore.objects.filter(criterion=criterion, enrollment=enrollment).delete()
            if deleted:
                touched.add(enrollment)
            continue
        points = max(Decimal("0"), min(_to_decimal(raw), Decimal(criterion.max_points)))
        CriterionScore.objects.update_or_create(
            organization=component.organization,
            criterion=criterion,
            enrollment=enrollment,
            defaults={"points": points, "entered_by": by_user},
        )
        touched.add(enrollment)
        written += 1

    # Toxunulan tələbələrin komponent balını meyar cəmindən yenilə (audit daxil).
    score_entries = []
    for enrollment in touched:
        total = CriterionScore.objects.filter(criterion__rubric=rubric, enrollment=enrollment).aggregate(
            s=Sum("points")
        )["s"]
        score_entries.append(
            {
                "component_id": str(component.id),
                "enrollment_id": str(enrollment.id),
                "score": "" if total is None else str(min(total, Decimal(component.max_score))),
            }
        )
    if score_entries:
        gradebook.save_component_scores(offering=component.offering, entries=score_entries, by_user=by_user)
    return written
