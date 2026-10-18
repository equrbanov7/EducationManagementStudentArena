"""«Alt qrupa tələbə əlavə et» panelinin ÇƏRÇİVƏSİ — `{% subgroup_placement_panel %}` tag-ı bunu çağırır.

Profil context qurucusuna (``context_builder/_stage*``) əlavə olunmur (``journal_hygiene`` naxışı): panel öz
çərçivəsini tag-dan alır, məlumat JSON GET-lərlə gəlir. Burada AĞIR SORĞU YOXDUR — yalnız cari dövr, hədlər
və (``?student=`` ilə gəlinibsə) ilkin tələbənin adı.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar.public import SubgroupPlacementError, credit_limits, subgroup_placement_lookups
from core import runtime_settings

from .i18n import panel_strings
from .policy import resolve_actor


def _initial_student(request, actor) -> dict:
    raw = (request.GET.get("student") or "").strip()
    if not raw:
        return {}
    try:
        student, record = subgroup_placement_lookups.resolve_student(
            actor=actor.user, organization=actor.organization, student_id=raw
        )
    except SubgroupPlacementError:
        return {}
    name = (student.get_full_name() or "").strip() or student.username
    group = getattr(record.group, "name", "") or ""
    return {"id": str(student.pk), "text": f"{name} · {group}" if group else name, "group": group}


def build_panel_context(request) -> dict:
    actor = resolve_actor(request)
    panel = {
        "has_access": actor.has_access,
        "access_denied_message": pgettext(
            "accounts.subgroup_placement", "Bu alət üçün «retake.manage» səlahiyyəti lazımdır."
        ),
    }
    if not actor.has_access:
        return panel
    period = subgroup_placement_lookups.current_period(actor.organization)
    limits = credit_limits()
    panel.update(
        can_write=actor.can_write,
        view_as=actor.view_as,
        period_label=f"{period.year_display} · {period.name}" if period else "",
        has_period=period is not None,
        base_limit=limits["base"],
        subgroup_limit=limits["with_subgroup"],
        clash_blocks=runtime_settings.get_bool("credits.clash_blocks"),
        initial_student=_initial_student(request, actor),
        urls={
            "students": reverse("accounts:subgroup_placement_students"),
            "student": reverse("accounts:subgroup_placement_student", args=[0]),
            "subjects": reverse("accounts:subgroup_placement_subjects"),
            "offerings": reverse("accounts:subgroup_placement_offerings"),
            "preview": reverse("accounts:subgroup_placement_preview"),
            "place": reverse("accounts:subgroup_placement_place"),
            "undo": reverse("accounts:subgroup_placement_undo"),
            "recent": reverse("accounts:subgroup_placement_recent"),
        },
        i18n=panel_strings(),
    )
    return panel


__all__ = ["build_panel_context"]
