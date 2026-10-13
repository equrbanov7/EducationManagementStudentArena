"""«Struktur ağacı» — QRUP seçiləndə detal paneli: STAROSTA kartı + qrupun tələbə siyahısı (2026-10-14).

Sahib: «struktur ağacında qrup seçiləndə … rəhbər yoxdursa təyin et yeri olmalıdır — vurub hansısa tələbəni
seçmək mümkün olsun ordan. Altda da, uyğundursa, həmin qrupun tələbələrini göstərmək də olar.»

Qrupun «rəhbəri» starostadır (``lead_student``) — ümumi «Rəhbər təyin et» (``unit.head`` = tyutor, işçi
seçicisi) qrupda göstərilmir. Yazı YENİ endpoint açmır: «Qruplar» reyestrinin çekmecəsi ilə EYNİ
``accounts:group_lead_action`` + ``services/group_lead.py`` (qapı, qaydalar, audit, bildiriş orada).

QAPILAR (açar + əhatə, rol adı YOX — «hər rol öz səlahiyyəti qədər»):
  * panel özü: ağacın ``unit.view`` əhatəsindən keçmiş qrup (tree.py — kənar ``st_unit`` detal almır);
  * «Təyin et / Dəyiş / Götür»: ``views/group_lead.manageable_group`` (``unit.group_manage`` və ya
    ``role.assign`` əhatəsində görünən qrup) — seçici yalnız bu halda qurulur;
  * tələbə siyahısı: ``people.view_students`` əhatəsi qrupu əhatə edirsə; e-poçt yalnız
    ``people.view_contacts`` əhatəsi ilə (B20: kataloq kontaktsız).

MODUL SƏRHƏDİ: registrar modeli ``django_apps.get_model`` ilə açılır. Sorğu büdcəsi: qrup başına sabit
(starosta xəritəsi 2 + tələbə siyahısı 1) — qrupun ölçüsündən asılı deyil.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.urls import reverse

from apps.organizations.public import get_permission_scope

from ....services.group_lead import group_lead_map
from ...group_lead import manageable_group

PERM_VIEW_STUDENTS = "people.view_students"
PERM_VIEW_CONTACTS = "people.view_contacts"


def _covers(scope, unit) -> bool:
    if scope.is_org_wide:
        return True
    if not scope.is_unit_scoped:
        return False
    path = str(unit.path or "")
    return unit.pk in scope.unit_ids or any(path.startswith(f"{root}/") for root in scope.unit_paths if root)


def _display_name(user) -> str:
    return (user.get_full_name() or "").strip() or user.username


def _student_number(user) -> str:
    profile = getattr(user, "profile", None)
    return str(getattr(profile, "institutional_identifier", "") or "") if profile is not None else ""


def _records(organization, group):
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    return list(
        StudentAcademicRecord.objects.filter(organization=organization, group=group, is_active=True)
        .select_related("student", "student__profile")
        .order_by("student__last_name", "student__first_name", "student__username")
    )


def build_group_panel(request, organization, group) -> dict:
    """Seçilmiş qrup üçün starosta + tələbə konteksti (``detail["group_panel"]``)."""
    leads = group_lead_map(organization, [group.pk]).get(group.pk, [])
    primary = leads[0] if leads else None
    warning = ""
    if len(leads) > 1:
        warning = "multiple"
    elif primary is not None and primary.not_in_group:
        warning = "not_in_group"

    can_assign = manageable_group(request, organization, str(group.pk)) is not None
    can_view_students = _covers(
        get_permission_scope(request.user, organization, PERM_VIEW_STUDENTS, request=request), group
    )
    show_contacts = can_view_students and _covers(
        get_permission_scope(request.user, organization, PERM_VIEW_CONTACTS, request=request), group
    )

    records = _records(organization, group) if (can_assign or can_view_students) else []
    lead_user_ids = {lead.user_id for lead in leads}
    lead_options = []
    students = []
    for record in records:
        student = record.student
        number = _student_number(student)
        name = _display_name(student)
        if record.status == "enrolled" and student.pk not in lead_user_ids:
            lead_options.append({"value": str(record.pk), "label": f"{name} · {number or '@' + student.username}"})
        if can_view_students:
            students.append(
                {
                    "name": name,
                    "number": number,
                    "email": (student.email or "") if show_contacts else "",
                    "status": record.status,
                    "status_label": str(record.get_status_display() or ""),
                    "is_lead": student.pk in lead_user_ids,
                    "profile_url": reverse("accounts:public_profile", kwargs={"username": student.username}),
                }
            )

    action_url = reverse("accounts:group_lead_action")
    group_id = str(group.pk)
    return {
        "lead": (
            {"name": primary.name, "username": primary.username, "warning": warning} if primary is not None else None
        ),
        "can_assign_lead": can_assign,
        "lead_options": lead_options if can_assign else [],
        "lead_action_url": action_url,
        "lead_form_data": {"data-tof-form": "1", "data-tof-url": action_url},
        "lead_assign_hidden": [
            {"name": "action", "value": "assign", "keep": True},
            {"name": "group_id", "value": group_id, "keep": True},
        ],
        "lead_remove_hidden": [
            {"name": "action", "value": "remove", "keep": True},
            {"name": "group_id", "value": group_id, "keep": True},
        ],
        "can_view_students": can_view_students,
        "show_contacts": show_contacts,
        "students": students,
        "student_total": len(students),
        "enrolled_total": sum(1 for row in students if row["status"] == "enrolled"),
    }


def attach_group_panel(request, organization, section) -> None:
    """``build_structure_tree_context`` nəticəsinə qrup panelini əlavə edir (yerində)."""
    detail = section.get("detail") if isinstance(section, dict) else None
    if not detail or not detail.get("is_group"):
        return
    detail["group_panel"] = build_group_panel(request, organization, detail["unit"])


__all__ = ["attach_group_panel", "build_group_panel"]
