"""Ekran 06 «Qruplar» — qrupun TƏLƏBƏ SİYAHISI (JSON, oxu-only).

Sahib rəyi 2026-09-07: «qrupları açanda ordakı tələbələri də açmaq olsun».
Siyahı çekmecədə göstərilir (`teaching_office_groups.js`); hər sətirdə
«qrupdan çıxar» (qrup əməli), «dondur» / «uzaqlaşdır» (tələbə hərəkəti) və
rəsmi «Fərdi tədris planı» DOCX linki var. Düymələrin görünməsi üçün iki bayraq
qaytarılır: ``can_manage`` (`unit.group_manage`) və ``can_move_students``
(`student.movement`) — server tərəfi hər halda öz qapısını yenidən yoxlayır.

QAPI `group_action` ilə EYNİDİR: tenant + `unit.view` + struktur əhatəsi +
görünən (scope daxilində) qrup — əhatədən kənar id 404 alır (IDOR).
MODUL SƏRHƏDİ: registrar modeli `django_apps.get_model` ilə açılır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from .group_actions import _error, _visible_group
from .groups_registry import can_manage_groups, can_move_students, can_view_groups, group_scope
from .models import Organization

_CTX = "accounts.groups"


def _row(record) -> dict:
    student = record.student
    program = record.program
    return {
        "id": str(record.pk),
        "name": (student.get_full_name() or "").strip() or student.username,
        "username": student.username,
        "status": record.status,
        "admission_year": record.admission_year,
        "program": getattr(program, "display_label", "") or getattr(program, "name", "") or "",
    }


@login_required
@require_GET
def group_students(request, slug, unit_id):
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    if not can_view_groups(request):
        return _error(pgettext(_CTX, "Qrup reyestrinə səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    scope = group_scope(request, organization)
    if not scope.has_structure_access:
        return _error(pgettext(_CTX, "Struktur əhatəniz yoxdur."), status=403, code="forbidden")
    unit = _visible_group(organization, scope, str(unit_id), include_archived=True)
    if unit is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found")

    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    records = (
        StudentAcademicRecord.objects.filter(organization=organization, group=unit, is_active=True)
        .select_related("student", "program")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    return JsonResponse(
        {
            "ok": True,
            "group": {"id": str(unit.pk), "name": unit.name, "is_active": unit.is_active},
            "rows": [_row(record) for record in records],
            "can_manage": can_manage_groups(request),
            "can_move_students": can_move_students(request),
        }
    )


__all__ = ["group_students"]
