"""
projects/views/crud.py
──────────────────────
CRUD operations for projects.

Contains:
- create_project
- edit_project
- delete_project
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.courses.models import CourseMembership

from ._helpers import _get_tenant_course_or_404, _get_tenant_project_or_404

User = get_user_model()


# ════════════════════════════════════════════════════════════════════════════
# Create Project
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
def create_project(request, course_id):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işi yaratma                                                        │
    │ POST /projects/create/<course_id>/                                      │
    │                                                                         │
    │ Tələb olunan fieldlər: title, start_date, deadline                      │
    │ Opsional: description, max_attempts, max_score, status                  │
    │ Təyin etmə: group_names[] və ya students[]                              │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    from apps.projects.models import Project

    course = _get_tenant_course_or_404(request, course_id)

    # İcazə yoxlaması - yalnız kurs sahibi
    if not request.user.is_teacher_or_above or course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("projects.views.message", "permission_denied")},
            status=403,
        )

    try:
        # Project yarat
        project = Project.objects.create(
            course=course,
            title=request.POST.get("title"),
            description=request.POST.get("description", ""),
            start_date=request.POST.get("start_date"),
            deadline=request.POST.get("deadline"),
            max_attempts=request.POST.get("max_attempts", 1),
            max_score=request.POST.get("max_score", 100),
            status=request.POST.get("status", "active"),
        )

        # ════════════════════════════════════════════════════════════
        # TƏLƏBƏLƏRİ TƏYİN ETMƏ MƏNTİQİ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # ════════════════════════════════════════════════════════════
        group_names = request.POST.getlist("group_names[]")
        student_ids = request.POST.getlist("students[]")

        if student_ids:
            # Konkret tələbələr seçilib
            students = User.objects.filter(id__in=student_ids)
            project.assigned_students.set(students)
        elif group_names:
            # Qrup seçilib - qrupdakı bütün tələbələri əlavə et
            group_students = User.objects.filter(
                course_memberships__course=course,
                course_memberships__group_name__in=group_names,
                course_memberships__role="student",
            ).distinct()
            project.assigned_students.set(group_students)

        messages.success(request, pgettext("projects.views.message", "project_created"))
        return JsonResponse({"success": True, "project_id": project.id})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


# ════════════════════════════════════════════════════════════════════════════
# Edit Project
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["GET", "POST"])
def edit_project(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işini redaktə etmək                                                │
    │ GET  /projects/<pk>/edit/ → JSON data qaytarır                          │
    │ POST /projects/<pk>/edit/ → Yeniləyir                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    # İcazə yoxlaması
    if not request.user.is_teacher_or_above or project.course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("projects.views.message", "permission_denied")},
            status=403,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # GET - Mövcud məlumatları JSON olaraq qaytar
    # ─────────────────────────────────────────────────────────────────────────
    if request.method == "GET":
        assigned_students = list(project.assigned_students.values("id", "username", "first_name", "last_name"))
        assigned_student_ids = [s["id"] for s in assigned_students]

        # Tələbələrin qruplarını tap
        assigned_groups = list(
            CourseMembership.objects.filter(course=project.course, user_id__in=assigned_student_ids, role="student")
            .exclude(group_name="")
            .values_list("group_name", flat=True)
            .distinct()
        )

        data = {
            "id": project.id,
            "title": project.title,
            "description": project.description,
            "start_date": (project.start_date.strftime("%Y-%m-%dT%H:%M") if project.start_date else ""),
            "deadline": (project.deadline.strftime("%Y-%m-%dT%H:%M") if project.deadline else ""),
            "max_attempts": project.max_attempts,
            "max_score": project.max_score,
            "status": project.status,
            "group_names": assigned_groups,
            "student_ids": assigned_student_ids,
            "students": [
                {
                    "id": s["id"],
                    "name": f"{s['first_name']} {s['last_name']}".strip() or s["username"],
                }
                for s in assigned_students
            ],
        }
        return JsonResponse({"success": True, "data": data})

    # ─────────────────────────────────────────────────────────────────────────
    # POST - Yenilə
    # ─────────────────────────────────────────────────────────────────────────
    try:
        project.title = request.POST.get("title")
        project.description = request.POST.get("description", "")
        project.start_date = request.POST.get("start_date")
        project.deadline = request.POST.get("deadline")
        project.max_attempts = request.POST.get("max_attempts", 1)
        project.max_score = request.POST.get("max_score", 100)
        project.status = request.POST.get("status", "active")
        project.save()

        # ════════════════════════════════════════════════════════════
        # TƏLƏBƏLƏRİ TƏYİN ETMƏ MƏNTİQİ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # 3. Heç biri yoxdursa → Boş
        # ════════════════════════════════════════════════════════════
        group_names = request.POST.getlist("group_names[]")
        student_ids = request.POST.getlist("students[]")

        if student_ids:
            students = User.objects.filter(id__in=student_ids)
            project.assigned_students.set(students)
        elif group_names:
            group_students = User.objects.filter(
                course_memberships__course=project.course,
                course_memberships__group_name__in=group_names,
                course_memberships__role="student",
            ).distinct()
            project.assigned_students.set(group_students)
        else:
            project.assigned_students.clear()

        messages.success(request, pgettext("projects.views.message", "project_updated"))
        return JsonResponse({"success": True, "message": pgettext("projects.views.message", "project_updated")})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


# ════════════════════════════════════════════════════════════════════════════
# Delete Project
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
def delete_project(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işini silmək                                                       │
    │ POST /projects/<pk>/delete/                                             │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    if not request.user.is_teacher_or_above or project.course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("projects.views.message", "permission_denied")},
            status=403,
        )

    try:
        project.delete()
        messages.success(request, pgettext("projects.views.message", "project_deleted"))
        return JsonResponse({"success": True, "message": pgettext("projects.views.message", "project_deleted")})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
