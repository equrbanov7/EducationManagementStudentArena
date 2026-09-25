"""Jurnalın aralıq qiymətləndirmə tabı — 3 kollokvium (keçmiş dövrlər) və ya 1 midterm (2026/2027-dən).

Rejim qərarı :mod:`apps.registrar.interim_assessment`-dədir; bu modul həmin rejimə görə
komponentləri idempotent qurur və müəllim tabının grid-ini hazırlayır. ``journal_extras``
modul-ölçü büdcəsinə görə bu hissəni buraya köçürüb və adları re-eksport edir — çağıranlar
üçün API dəyişməyib (``journal_extras.ensure_kollokviums`` və s.).

Kollokvium/midterm mövcud komponent mexanizmi üzərində işləyir (``AssessmentComponent``
kind=KOLLOKVIUM + ``held_on`` tarixi; ballar ``ComponentScore``-da). Bal yazmaq İmtahan
Mərkəzinin PƏNCƏRƏSİ ilə idarə olunur (``kollokvium_windows``): midterm rejimində yalnız
``k_index=0`` pəncərəsi var.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.registrar import interim_assessment
from apps.registrar.gradebook import journal_is_locked
from apps.registrar.models import AssessmentComponent, ComponentKind, ComponentScore, CriterionScore, Enrollment


def _has_evidence(component) -> bool:
    """Komponentin balı və ya rubrik sübutu varmı (belə komponent heç vaxt silinmir)."""
    return (
        ComponentScore.objects.filter(component=component).exists()
        or CriterionScore.objects.filter(component=component).exists()
    )


def _ensure_kollokvium_mode(offering, all_components, spec):
    """Keçmiş dövrlər: 3 kollokvium komponentini idempotent yarat (K1, K2, K3 · max 10).

    Köhnə məlumat uyğunluğu: "Kollokvium N" ADLI generic komponent artıq varsa
    (kind sahəsi yeni olduğundan köhnə sətirlər generic-dir), onu yenidən
    yaratmaq əvəzinə MƏNİMSƏYİRİK — kind=KOLLOKVIUM-a normalizə olunur
    (unique (offering, name) toqquşması da bununla aradan qalxır)."""
    by_name = {c.name: c for c in all_components}
    result = []
    base_order = len(all_components)
    for i, name in enumerate(spec.component_names, start=1):
        component = by_name.get(name)
        if component is not None:
            if component.kind != ComponentKind.KOLLOKVIUM:
                component.kind = ComponentKind.KOLLOKVIUM
                component.save(update_fields=["kind"])
            result.append(component)
            continue
        result.append(
            AssessmentComponent.objects.create(
                organization=offering.organization,
                offering=offering,
                name=name,
                kind=ComponentKind.KOLLOKVIUM,
                max_score=spec.max_score,
                order=base_order + i,
            )
        )
    return result


def _ensure_midterm_mode(offering, all_components, spec):
    """2026/2027-dən: TƏK «Midterm» komponenti (max 20) + köhnə kodun qalıqlarının təmizlənməsi.

    Bu dövrdə köhnə kod (``ensure_kollokviums`` 3-K versiyası) jurnal açılanda «Kollokvium 1–3»
    komponentlərini yaratmış ola bilər. BALI/SÜBUTU OLMAYAN belə qalıqlar silinir; balı olan
    (nəzəri olaraq İKT keçidi ilə yazılmış) komponent heç vaxt silinmir — o, oxu-rejimli əlavə
    sütun kimi göstərilir və giriş balına əvvəlki kimi daxildir (data itmir)."""
    name_key = spec.component_names[0].lower()
    midterm = next((c for c in all_components if c.name.strip().lower() == name_key), None)
    leftovers = []
    for component in all_components:
        if component is midterm or component.kind != ComponentKind.KOLLOKVIUM:
            continue
        if _has_evidence(component):
            leftovers.append(component)
            continue
        try:
            with transaction.atomic():
                component.delete()
        except ProtectedError:  # sənədli düzəliş sübutu komponenti qoruyur
            leftovers.append(component)
    if midterm is None:
        midterm = AssessmentComponent.objects.create(
            organization=offering.organization,
            offering=offering,
            name=spec.component_names[0],
            kind=ComponentKind.KOLLOKVIUM,
            max_score=spec.max_score,
            order=max((c.order for c in all_components), default=0) + 1,
        )
    else:
        update_fields = []
        if midterm.kind != ComponentKind.KOLLOKVIUM:
            midterm.kind = ComponentKind.KOLLOKVIUM
            update_fields.append("kind")
        if midterm.max_score != spec.max_score and not _has_evidence(midterm):
            midterm.max_score = spec.max_score
            update_fields.append("max_score")
        if update_fields:
            midterm.save(update_fields=update_fields)
    return [midterm, *sorted(leftovers, key=lambda c: (c.order, c.name))]


@transaction.atomic
def ensure_kollokviums(offering):
    """Aralıq qiymətləndirmə komponentlərini rejimə görə idempotent qur və sıralı qaytar.

    * kollokvium rejimi (keçmiş dövrlər) → [Kollokvium 1, 2, 3] (hər biri max 10);
    * midterm rejimi (2026/2027-dən) → [Midterm] (max 20) + balı olan köhnə qalıqlar (varsa).

    Qaytarılan siyahıdakı MÖVQE İmtahan Mərkəzi pəncərəsinin ``k_index``-idir."""
    spec = interim_assessment.spec_for_offering(offering)
    all_components = list(AssessmentComponent.objects.filter(offering=offering))
    if spec.is_midterm:
        return _ensure_midterm_mode(offering, all_components, spec)
    return _ensure_kollokvium_mode(offering, all_components, spec)


def set_kollokvium_date(*, component, held_on) -> bool:
    """Kollokviumun/midtermin keçirilmə tarixini yaz (tələbə tarixçəsində göstərilir)."""
    if component.kind != ComponentKind.KOLLOKVIUM or journal_is_locked(component.offering):
        return False
    component.held_on = held_on or None
    component.save(update_fields=["held_on"])
    return True


def score_options(offering) -> list[int]:
    """Müəllimin bal seçimi: kollokviumda 0–10, midtermdə 0–20 (tam ədədlər)."""
    return list(range(0, interim_assessment.spec_for_offering(offering).max_score + 1))


#: ``journal_extras``/``views`` üçün aydın ad (``journal_extras.interim_score_options``).
interim_score_options = score_options


def get_kollokvium_grid(offering):
    """Aralıq qiymətləndirmə tabı: komponentlər × tələbələr + ballar.

    Redaktə edilə bilirlik İmtahan Mərkəzi PƏNCƏRƏSİNDƏN gəlir — kollokvium/midterm üçün
    2 saat kilidi YOXDUR (pəncərə onu əvəz edir). Hər sütun üçün vəziyyət
    ``kollokvium_windows.entry_state`` ilə hesablanır; midterm rejimində yalnız birinci
    sütunun (``k_index=0``) pəncərəsi ola bilər, qalıq sütunlar həmişə oxu-rejimlidir.
    """
    from apps.registrar import kollokvium_windows as kw

    spec = interim_assessment.spec_for_offering(offering)
    components = ensure_kollokviums(offering)
    today = timezone.localdate()
    states = [kw.entry_state(offering, idx, today) for idx in range(len(components))]
    columns = []
    for idx, component in enumerate(components):
        primary = idx < spec.count
        is_open = primary and states[idx]["status"] == "open"
        columns.append(
            {
                "component": component,
                "k_index": idx,
                "label": spec.label_for(idx) if primary else component.name,
                "is_primary": primary,
                "status": states[idx]["status"] if primary else "archived",
                "opens_on": states[idx].get("opens_on"),
                "deadline": states[idx].get("deadline"),
                "open": is_open,
            }
        )
    open_by_comp = {col["component"].id: col["open"] for col in columns}

    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    score_map = {}
    for cs in ComponentScore.objects.filter(component__in=components, enrollment__offering=offering):
        score_map[(cs.enrollment_id, cs.component_id)] = cs.score
    rows = [
        {
            "enrollment": e,
            "student": e.student,
            "cells": [
                {
                    "component": c,
                    "score": score_map.get((e.id, c.id)),
                    "editable": open_by_comp[c.id],
                }
                for c in components
            ],
        }
        for e in enrollments
    ]
    return {
        "spec": spec,
        "components": components,
        "columns": columns,
        "rows": rows,
        "any_open": any(col["open"] for col in columns),
        # «CƏMİ» sütunu yalnız bir neçə sütun olanda mənalıdır (kollokvium: /30).
        "show_total": len(columns) > 1,
        "total_max": sum(int(c.max_score) for c in components),
    }


def kollokvium_columns_only(offering):
    """Aralıq qiymətləndirmə XƏBƏRDARLIQ lenti üçün yalnız sütun meta (sətirsiz).

    Lent hər tabda görünür, amma 555 sətirlik grid yalnız öz tabında lazımdır.
    """
    grid = get_kollokvium_grid(offering)
    return {**grid, "rows": []} if isinstance(grid, dict) else grid


def display_components(offering):
    """Oxu səthləri (yekun cədvəl, tələbə görünüşü) üçün aralıq komponentlər — YAZMADAN.

    Midterm rejimində BALI OLMAYAN köhnə «Kollokvium N» qalıqları göstərilmir (onlar növbəti
    jurnal açılışında onsuz da silinir); balı olanlar görünür, çünki giriş balına daxildir."""
    spec = interim_assessment.spec_for_offering(offering)
    components = list(
        AssessmentComponent.objects.filter(offering=offering, kind=ComponentKind.KOLLOKVIUM).order_by("order", "name")
    )
    if not spec.is_midterm:
        return spec, components
    name_key = spec.component_names[0].lower()
    primary = [c for c in components if c.name.strip().lower() == name_key]
    others = [c for c in components if c.name.strip().lower() != name_key]
    if others:
        scored = set(
            ComponentScore.objects.filter(component__in=others).values_list("component_id", flat=True).distinct()
        )
        others = [c for c in others if c.id in scored]
    return spec, primary + others


__all__ = [
    "display_components",
    "ensure_kollokviums",
    "get_kollokvium_grid",
    "interim_score_options",
    "kollokvium_columns_only",
    "score_options",
    "set_kollokvium_date",
]
