"""Profil "groups" (müəllim qrupları) bölməsi üçün context-fragment qurucusu.

Yalnız bölmə aktiv VƏ aktiv təşkilat mövcud olduqda çağırılır (caller şərti).
Davranış köhnə inline blokla eynidir.
"""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q

from apps.accounts.models import ProfileRole
from apps.exams.models import StudentGroup
from apps.exams.public import StudentGroupForm


def build_groups_context(
    request,
    *,
    profile,
    capabilities,
    active_organization,
    teacher_groups_search_query,
    group_students_search_query,
) -> dict:
    current_role_level = (
        request.user._highest_role_level()
        if hasattr(request.user, "_highest_role_level")
        else ProfileRole.LEVELS.get(getattr(profile, "role", ProfileRole.MEMBER), 0)
    )
    can_manage_groups = capabilities["is_superadmin"] or capabilities["can_manage_org"]
    can_multi_assign = can_manage_groups and (
        capabilities["is_superadmin"] or current_role_level >= ProfileRole.LEVELS.get(ProfileRole.TEACHER, 60)
    )
    group_form = None
    if can_manage_groups:
        group_form = StudentGroupForm(
            actor=request.user,
            organization=active_organization,
            can_multi_assign_teachers=can_multi_assign,
            is_superadmin=capabilities["is_superadmin"],
            auto_id="group_%s",
        )

    teacher_groups_qs = (
        StudentGroup.objects.filter(organization=active_organization)
        .select_related("teacher")
        .prefetch_related("students", "teachers")
        .order_by("name")
    )
    can_view_all_groups = capabilities["is_superadmin"] or capabilities["can_manage_org"]
    if not can_view_all_groups:
        teacher_groups_qs = teacher_groups_qs.filter(Q(teacher=request.user) | Q(teachers=request.user)).distinct()

    visible_teacher_groups_qs = teacher_groups_qs
    teacher_groups_count = visible_teacher_groups_qs.count()

    if teacher_groups_search_query:
        visible_teacher_groups_qs = visible_teacher_groups_qs.filter(
            Q(name__icontains=teacher_groups_search_query)
            | Q(teacher__username__icontains=teacher_groups_search_query)
            | Q(teacher__first_name__icontains=teacher_groups_search_query)
            | Q(teacher__last_name__icontains=teacher_groups_search_query)
            | Q(students__username__icontains=teacher_groups_search_query)
            | Q(students__first_name__icontains=teacher_groups_search_query)
            | Q(students__last_name__icontains=teacher_groups_search_query)
            | Q(students__profile__student_group_number__icontains=teacher_groups_search_query)
        ).distinct()

    teacher_groups_filtered_count = visible_teacher_groups_qs.count()
    teacher_groups_page = Paginator(visible_teacher_groups_qs, 8).get_page(request.GET.get("groups_page"))
    teacher_groups = list(teacher_groups_page.object_list)

    selected_teacher_group = None
    selected_group_id = (request.GET.get("group") or "").strip()
    if selected_group_id.isdigit():
        selected_teacher_group = teacher_groups_qs.filter(id=int(selected_group_id)).first()

    teacher_groups_pagination_query = urlencode(
        {
            key: value
            for key, value in {
                "section": "groups",
                "group_q": teacher_groups_search_query,
                "group": selected_teacher_group.id if selected_teacher_group else "",
                "student_q": group_students_search_query if selected_teacher_group else "",
            }.items()
            if value not in ("", None)
        }
    )

    selected_group_students_count = 0
    selected_group_students_filtered_count = 0
    selected_group_students_page = None
    group_students_pagination_query = ""
    if selected_teacher_group:
        students_qs = selected_teacher_group.students.select_related("profile").order_by(
            "first_name", "last_name", "username", "id"
        )
        selected_group_students_count = students_qs.count()
        if group_students_search_query:
            students_qs = students_qs.filter(
                Q(username__icontains=group_students_search_query)
                | Q(first_name__icontains=group_students_search_query)
                | Q(last_name__icontains=group_students_search_query)
                | Q(email__icontains=group_students_search_query)
                | Q(profile__student_group_number__icontains=group_students_search_query)
            )
        selected_group_students_filtered_count = students_qs.count()
        selected_group_students_page = Paginator(students_qs, 12).get_page(request.GET.get("students_page"))
        group_students_pagination_query = urlencode(
            {
                key: value
                for key, value in {
                    "section": "groups",
                    "group": selected_teacher_group.id,
                    "group_q": teacher_groups_search_query,
                    "groups_page": teacher_groups_page.number if teacher_groups_page else "",
                    "student_q": group_students_search_query,
                }.items()
                if value not in ("", None)
            }
        )

    teacher_groups_payload = {}
    for group in teacher_groups:
        student_ids = [student.id for student in group.students.all()]
        teacher_ids = [teacher.id for teacher in group.teachers.all()]
        if group.teacher_id and group.teacher_id not in teacher_ids:
            teacher_ids.append(group.teacher_id)
        teacher_groups_payload[str(group.id)] = {
            "name": group.name,
            "primary_teacher": group.teacher_id,
            "students": student_ids,
            "teachers": teacher_ids,
        }
    if selected_teacher_group and str(selected_teacher_group.id) not in teacher_groups_payload:
        student_ids = [student.id for student in selected_teacher_group.students.all()]
        teacher_ids = [teacher.id for teacher in selected_teacher_group.teachers.all()]
        if selected_teacher_group.teacher_id and selected_teacher_group.teacher_id not in teacher_ids:
            teacher_ids.append(selected_teacher_group.teacher_id)
        teacher_groups_payload[str(selected_teacher_group.id)] = {
            "name": selected_teacher_group.name,
            "primary_teacher": selected_teacher_group.teacher_id,
            "students": student_ids,
            "teachers": teacher_ids,
        }

    return {
        "can_multi_assign_group_teachers": can_multi_assign,
        "group_form": group_form,
        "teacher_groups": teacher_groups,
        "teacher_groups_count": teacher_groups_count,
        "teacher_groups_filtered_count": teacher_groups_filtered_count,
        "teacher_groups_page": teacher_groups_page,
        "teacher_groups_pagination_query": teacher_groups_pagination_query,
        "selected_teacher_group": selected_teacher_group,
        "selected_group_students_count": selected_group_students_count,
        "selected_group_students_filtered_count": selected_group_students_filtered_count,
        "selected_group_students_page": selected_group_students_page,
        "group_students_pagination_query": group_students_pagination_query,
        "teacher_groups_payload": teacher_groups_payload,
    }
