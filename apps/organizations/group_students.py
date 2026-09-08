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
from django.urls import reverse
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
        # İxtisas ŞİFRİ ayrıca — sahib (2026-09-07): siyahıda «qeydiyyat qrupu»
        # əvəzinə ixtisas kodu + qısa adı görünsün.
        "program_code": getattr(program, "display_code", "") or "",
        "program_name": getattr(program, "name", "") or "",
        "program": getattr(program, "display_label", "") or getattr(program, "name", "") or "",
        "education_form": record.education_form or "",
        "education_form_label": str(record.get_education_form_display() or "") if record.education_form else "",
        "group_name": getattr(record.group, "name", "") or "",
        # Tələbənin adına klik → açıq profil (sahib, 2026-09-08).
        "profile_url": reverse("accounts:public_profile", kwargs={"username": student.username}),
    }


def _candidate_row(record, *, group_specialty_id) -> dict:
    """Namizəd seçicisi (`EMSSearchableSelect`) müqaviləsi: {id, text, hint}."""
    student = record.student
    program = record.program
    code = getattr(program, "display_code", "") or ""
    name = (student.get_full_name() or "").strip() or student.username
    meta = ["@" + student.username]
    if code:
        meta.append(code)
    if getattr(program, "name", ""):
        meta.append(program.name)
    if record.group_id and record.group is not None and not record.group.is_active:
        meta.append(pgettext(_CTX, "arxiv qrup: %s") % record.group.name)
    return {
        "id": str(record.pk),
        "text": f"{name} · {' · '.join(meta)}",
        "hint": "",
        "same_specialty": bool(
            group_specialty_id and getattr(program, "specialty_unit_id", None) == group_specialty_id
        ),
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


#: Namizəd axtarışının səhifə ölçüsü (searchable-select lazy scroll ilə uzanır).
CANDIDATE_PAGE_DEFAULT = 20
CANDIDATE_PAGE_MAX = 50
MAX_QUERY_LENGTH = 80


@login_required
@require_GET
def group_student_candidates(request, slug, unit_id):
    """«Tələbə əlavə et» seçicisinin namizədləri — QRUPSUZ, qeydiyyatlı tələbələr.

    Sahib (2026-09-07): başqa qrupda olan tələbə ümumi siyahıda görünməsin;
    axtarış ad / istifadəçi adı / ixtisas şifri / ixtisas adı üzrə. Qrupun öz
    ixtisasındakı tələbələr siyahıda ƏVVƏL gəlir.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    if not can_view_groups(request) or not can_manage_groups(request):
        return _error(pgettext(_CTX, "Qrupları idarə etmək səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    scope = group_scope(request, organization)
    if not scope.has_structure_access:
        return _error(pgettext(_CTX, "Struktur əhatəniz yoxdur."), status=403, code="forbidden")
    unit = _visible_group(organization, scope, str(unit_id))
    if unit is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found")

    from django.db.models import Case, IntegerField, Q, Value, When

    from core.program_codes import program_code_search_q

    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    records = (
        StudentAcademicRecord.objects.filter(organization=organization, is_active=True, status="enrolled")
        .filter(Q(group__isnull=True) | Q(group__is_active=False))
        .select_related("student", "program", "group")
    )
    query = (request.GET.get("q") or "").strip()[:MAX_QUERY_LENGTH]
    if query:
        for token in query.split()[:4]:
            records = records.filter(
                Q(student__first_name__icontains=token)
                | Q(student__last_name__icontains=token)
                | Q(student__username__icontains=token)
                | Q(program__name__icontains=token)
                | program_code_search_q(token, prefix="program__")
            )
    records = records.annotate(
        _same=Case(
            When(program__specialty_unit_id=unit.parent_id, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("_same", "student__last_name", "student__first_name", "student__username")

    try:
        offset = max(0, int(request.GET.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = max(1, min(int(request.GET.get("limit") or CANDIDATE_PAGE_DEFAULT), CANDIDATE_PAGE_MAX))
    except (TypeError, ValueError):
        limit = CANDIDATE_PAGE_DEFAULT
    window = list(records[offset : offset + limit + 1])
    return JsonResponse(
        {
            "has_access": True,
            "results": [_candidate_row(record, group_specialty_id=unit.parent_id) for record in window[:limit]],
            "has_more": len(window) > limit,
        }
    )


__all__ = ["group_student_candidates", "group_students"]
