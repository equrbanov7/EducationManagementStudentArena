"""
═══════════════════════════════════════════════════════════════════════════════
PROJECTS VIEWS
═══════════════════════════════════════════════════════════════════════════════
Kurs işləri üçün bütün view-lar:
- CRUD əməliyyatları (create, edit, delete)
- Tələbə görünüşü (detail, submit, my_submissions)
- Müəllim görünüşü (review, grade)
- API helper view-lar (get groups, get students)
═══════════════════════════════════════════════════════════════════════════════
"""

from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.courses.models import Course, CourseMembership
from core.permissions import request_has_permission
from core.tenancy import scoped_by_organization_id
from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from .models import Project, ProjectSubmission

User = get_user_model()
ASSIGNED_TASK_FILTER_CHOICES = {"all", "exams", "courses", "assignments", "labs", "independent"}
REVIEW_EDIT_LOCK_WINDOW = timedelta(minutes=5)


def _tenant_scoped_courses(request, queryset=None):
    base_queryset = queryset if queryset is not None else Course.objects.all()
    return scoped_by_organization_id(
        base_queryset,
        request,
        org_id_field="organization_id",
        fallback_org_field="owner__profile__organization",
    )


def _tenant_scoped_projects(request, queryset=None):
    base_queryset = queryset if queryset is not None else Project.objects.all()
    return base_queryset.filter(course__in=_tenant_scoped_courses(request))


def _tenant_scoped_submissions(request, queryset=None):
    base_queryset = queryset if queryset is not None else ProjectSubmission.objects.all()
    return base_queryset.filter(project__in=_tenant_scoped_projects(request))


def _get_tenant_course_or_404(request, course_id):
    return get_object_or_404(_tenant_scoped_courses(request), id=course_id)


def _get_tenant_project_or_404(request, project_id):
    return get_object_or_404(_tenant_scoped_projects(request), id=project_id)


def _get_tenant_submission_or_404(request, submission_id):
    return get_object_or_404(_tenant_scoped_submissions(request), id=submission_id)


def _safe_same_origin_redirect_path(request, candidate_url):
    raw_url = (candidate_url or "").strip()
    if not raw_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    parsed = urlsplit(raw_url)
    if parsed.netloc and parsed.netloc != request.get_host():
        return ""

    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


def _project_back_url(request, project):
    source_section = (request.GET.get("from_section") or "").strip()
    if source_section == "assigned-exams":
        params = {"section": "assigned-exams"}
        assigned_type = (request.GET.get("assigned_type") or "").strip().lower()
        if assigned_type in ASSIGNED_TASK_FILTER_CHOICES:
            params["assigned_type"] = assigned_type
        return f"{reverse('accounts:profile')}?{urlencode(params)}"

    return reverse("courses:course_dashboard", kwargs={"course_id": project.course.id})


def _teacher_review_back_url(request, project):
    explicit_return_url = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )
    if explicit_return_url:
        return explicit_return_url

    source_section = (request.GET.get("from_section") or "").strip()
    if source_section in {"pending-review", "review-results"}:
        return f"{reverse('accounts:profile')}?section={source_section}"

    return reverse("courses:course_dashboard", kwargs={"course_id": project.course.id})


# ═══════════════════════════════════════════════════════════════════════════════
# CRUD ƏMƏLİYYATLARI
# ═══════════════════════════════════════════════════════════════════════════════


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


@login_required
@require_http_methods(["POST"])
def delete_project(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işini silmək                                                       │
    │ POST /projects/<pk>/delete/                                             │
    └─────────────────────────────��───────────────────────────────────────────┘
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


# ═══════════════════════════════════════════════════════════════════════════════
# TƏLƏBƏ GÖRÜNÜŞÜ
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
def project_detail(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işinin detalları (tələbə üçün)                                     │
    │ GET /projects/<pk>/                                                     │
    │                                                                         │
    │ Tələbə burada:                                                          │
    │ - Project məlumatlarını görür                                           │
    │ - Əvvəlki cavablarını görür                                             │
    │ - Yeni cavab göndərə bilir (cəhd varsa)                                 │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    # ─────────────────────────────────────────────────────────────────────────
    # İcazə yoxlaması - tələbə yalnız özünə təyin olunmuşlara baxa bilər
    # ─────────────────────────────────────────────────────────────────────────
    if getattr(request.user, "is_student", False):
        has_access = project.assigned_students.filter(id=request.user.id).exists()
        if not has_access:
            messages.error(request, pgettext("projects.views.message", "no_project_access"))
            return redirect("courses:course_dashboard", course_id=project.course.id)

    # İstifadəçinin əvvəlki cavablarını al
    user_submissions = project.submissions.filter(student=request.user).order_by("-submitted_at")
    user_attempts = user_submissions.count()

    context = {
        "project": project,
        "user_submissions": user_submissions,
        "user_attempts": user_attempts,
        "can_submit": project.can_user_submit(request.user),
        "attempts_left": project.max_attempts - user_attempts,
        "back_url": _project_back_url(request, project),
    }

    return render(request, "projects/project_detail.html", context)


@login_required
@require_http_methods(["POST"])
def submit_project(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işinə cavab göndərmək                                              │
    │ POST /projects/<pk>/submit/                                             │
    │                                                                         │
    │ Form data: content (text), file (optional)                              │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    # Cavab göndərə bilərmi yoxla
    if not project.can_user_submit(request.user):
        return JsonResponse(
            {
                "success": False,
                "error": pgettext("projects.views.message", "submit_not_allowed"),
            },
            status=400,
        )

    uploaded_file = request.FILES.get("file")
    if uploaded_file is not None:
        try:
            validate_uploaded_file(
                uploaded_file,
                allowed_extensions={
                    ".zip",
                    ".rar",
                    ".7z",
                    ".pdf",
                    ".txt",
                    ".doc",
                    ".docx",
                    ".png",
                    ".jpg",
                    ".jpeg",
                },
                max_size_mb=25,
            )
            randomize_uploaded_filename(uploaded_file)
        except ValidationError as exc:
            return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)

    try:
        submission = ProjectSubmission.objects.create(
            project=project,
            student=request.user,
            content=request.POST.get("content", ""),
        )

        # Fayl yükləmə
        if uploaded_file is not None:
            submission.file = uploaded_file
            submission.save()

        messages.success(request, pgettext("projects.views.message", "project_submitted"))
        return JsonResponse(
            {
                "success": True,
                "message": pgettext("projects.views.message", "project_submitted"),
                "submission_id": submission.id,
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
def my_submissions(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Tələbənin öz cavablarını görmək                                         │
    │ GET /projects/<pk>/my-submissions/                                      │
    │                                                                         │
    │ Tələbə burada:                                                          │
    │ - Bütün göndərdiyi cavabları görür                                      │
    │ - Qiymətlərini görür                                                    │
    │ - Müəllim rəyini görür                                                  │
    │ - Qalan cəhd sayını görür                                               │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    # ─────────────────────────────────────────────────────────────────────────
    # İcazə yoxlaması - yalnız özünə təyin olunmuş project-lərə baxa bilər
    # ─────────────────────────────────────────────────────────────────────────
    if not project.assigned_students.filter(id=request.user.id).exists():
        messages.error(request, pgettext("projects.views.message", "no_project_access"))
        return redirect("courses:course_dashboard", course_id=project.course.id)

    # İstifadəçinin cavablarını al
    submissions = project.submissions.filter(student=request.user).order_by("-submitted_at")
    user_attempts = submissions.count()

    context = {
        "project": project,
        "submissions": submissions,
        "user_attempts": user_attempts,
        "can_submit": project.can_user_submit(request.user),
        "attempts_left": project.max_attempts - user_attempts,
    }

    return render(request, "projects/my_submissions.html", context)


# ═══════════════════════════════════════════════════════════════════════════════
# MÜƏLLİM GÖRÜNÜŞÜ
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
def review_submissions(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Cavabları yoxlamaq (müəllim üçün)                                       │
    │ GET /projects/<pk>/submissions/                                         │
    │                                                                         │
    │ Müəllim burada:                                                         │
    │ - Bütün tələbə cavablarını görür                                        │
    │ - Qiymət verə bilir                                                     │
    │ - Rəy yaza bilir                                                        │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    # İcazə yoxlaması
    if not request.user.is_teacher_or_above or project.course.owner != request.user:
        messages.error(request, pgettext("projects.views.message", "permission_denied"))
        return redirect("courses:course_dashboard", course_id=project.course.id)

    submissions = project.submissions.select_related("student").order_by("-submitted_at")
    selected_submission_raw = (request.GET.get("submission") or "").strip()
    selected_submission_id = selected_submission_raw if selected_submission_raw.isdigit() else ""

    context = {
        "project": project,
        "submissions": submissions,
        "selected_submission_id": selected_submission_id,
        "back_url": _teacher_review_back_url(request, project),
    }

    return render(request, "projects/review_submissions.html", context)


@login_required
@require_http_methods(["POST"])
def grade_submission(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Cavabı qiymətləndirmək                                                  │
    │ POST /projects/submission/<pk>/grade/                                   │
    │                                                                         │
    │ Form data: grade, feedback (optional)                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    submission = _get_tenant_submission_or_404(request, pk)

    if not request_has_permission(request, "grade.input"):
        return JsonResponse(
            {"success": False, "error": pgettext("projects.views.message", "permission_denied")},
            status=403,
        )

    # İcazə yoxlaması
    if not request.user.is_teacher_or_above or submission.project.course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("projects.views.message", "permission_denied")},
            status=403,
        )

    if (
        submission.status == "graded"
        and submission.graded_at
        and timezone.now() >= submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
    ):
        return JsonResponse(
            {"success": False, "error": "Yoxlama müddəti bitib. Artıq dəyişiklik etmək mümkün deyil."},
            status=400,
        )

    try:
        submission.grade = request.POST.get("grade")
        submission.feedback = request.POST.get("feedback", "")
        submission.status = "graded"
        if not submission.graded_at:
            submission.graded_at = timezone.now()
        submission.graded_by = request.user
        submission.save()

        messages.success(request, pgettext("projects.views.message", "grade_given"))
        return JsonResponse({"success": True, "message": pgettext("projects.views.message", "grade_given")})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


# ═══════════════════════════════════════════════════════════════════════════════
# API HELPER VIEW-LAR (AJAX üçün)
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
def api_get_groups(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kursdakı qrupları qaytarır (AJAX)                                       │
    │ GET /projects/api/groups/?course_id=<id>                                │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    course_id = request.GET.get("course_id")

    if not course_id:
        return JsonResponse({"groups": []})

    course = _get_tenant_course_or_404(request, course_id)

    # Unique qrup adlarını tap
    groups = (
        CourseMembership.objects.filter(course=course, role="student")
        .exclude(group_name="")
        .exclude(group_name__isnull=True)
        .values_list("group_name", flat=True)
        .distinct()
        .order_by("group_name")
    )

    return JsonResponse({"groups": [{"id": i, "name": name} for i, name in enumerate(groups, 1)]})


@login_required
def api_get_students(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Qruplardakı tələbələri qaytarır (AJAX)                                  │
    │ GET /projects/api/students/?course_id=<id>&groups=<g1,g2>               │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    course_id = request.GET.get("course_id")
    groups_param = request.GET.get("groups", "")

    if not course_id or not groups_param:
        return JsonResponse({"students": []})

    course = _get_tenant_course_or_404(request, course_id)
    group_names = [g.strip() for g in groups_param.split(",") if g.strip()]

    if not group_names:
        return JsonResponse({"students": []})

    # Qruplardakı tələbələri tap
    memberships = (
        CourseMembership.objects.filter(course=course, group_name__in=group_names, role="student")
        .select_related("user")
        .order_by("group_name", "user__first_name")
    )

    # Dublikatları çıxar
    students = []
    seen = set()
    for m in memberships:
        if m.user.id not in seen:
            seen.add(m.user.id)
            students.append(
                {
                    "id": m.user.id,
                    "name": m.user.get_full_name() or m.user.username,
                    "group_name": m.group_name,
                }
            )

    return JsonResponse({"students": students})
