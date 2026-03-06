"""
courses/views.py
────────────────
Kurs modulu üçün view-lər.

Labs app inteqrasiyası əlavə edilib.
"""

import json
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Max, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.exams.models import Exam, ExamAttempt, StudentGroup
from apps.labs.models import LabAssignment, LabSubmission
from core.permissions import request_has_permission
from core.tenancy import get_organization_int_id, get_request_organization, scoped_by_organization_id

from .forms import CourseForm, CourseResourceForm, CourseTopicForm
from .models import Course, CourseMembership, CourseResource, CourseTopic

User = get_user_model()
ASSIGNED_TASK_FILTER_CHOICES = {"all", "courses", "assignments", "labs", "independent"}
REVIEW_EDIT_LOCK_WINDOW = timedelta(minutes=5)


def _tenant_scoped_courses(request, queryset=None):
    base_queryset = queryset if queryset is not None else Course.objects.all()
    return scoped_by_organization_id(
        base_queryset,
        request,
        org_id_field="organization_id",
        fallback_org_field="owner__profile__organization",
    )


def _owner_courses_queryset(request):
    return _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))


def _get_owner_course_or_404(request, course_id):
    return get_object_or_404(_owner_courses_queryset(request), id=course_id)


def _student_users_queryset(queryset):
    return queryset.filter(
        Q(profile__role__in=["student", "lead_student"]) | Q(groups__name__in=["student", "lead_student"])
    ).distinct()


def _safe_same_origin_redirect_path(request, candidate_url):
    """
    Return a safe same-origin relative path (with query/fragment) or empty string.
    """
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


def _require_org_permission(request, permission):
    if request_has_permission(request, permission):
        return
    raise PermissionDenied(
        pgettext("courses.view.permission", "required_permission_missing").format(permission=permission)
    )


# ════════════════════════════════════════════════════════════════════════════
# Mixin: Müəllim İcazə Yoxlaması
# ════════════════════════════════════════════════════════════════════════════


class IsTeacherMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Yalnız müəllim (is_teacher_or_above) bu view-a girə bilər."""

    def test_func(self):
        return getattr(self.request.user, "is_teacher_or_above", False)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(pgettext("courses.view.permission", "teachers_only_action"))


class IsCourseOwnerMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Yalnız kursun sahibi (owner) redaktə edə bilər."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        return _owner_courses_queryset(self.request).filter(id=course_id).exists()

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(pgettext("courses.view.permission", "no_permission_edit_course"))


# ════════════════════════════════════════════════════════════════════════════
# VIEW 1: Kurs Yaratma
# ════════════════════════════════════════════════════════════════════════════


class CreateCourseView(IsTeacherMixin, CreateView):
    """Kurs yaratma view-u."""

    model = Course
    form_class = CourseForm
    template_name = "courses/create_course.html"
    modal_form_template_name = "courses/partials/_create_course_modal_form.html"

    def _is_modal_request(self):
        return self.request.GET.get("modal") == "1"

    def get(self, request, *args, **kwargs):
        if self._is_modal_request():
            self.object = None
            form = self.get_form()
            return render(
                request,
                self.modal_form_template_name,
                {
                    "form": form,
                },
            )
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        _require_org_permission(self.request, "course.create")
        form.instance.owner = self.request.user
        form.instance.status = "draft"
        organization = get_request_organization(self.request)
        form.instance.organization_id = get_organization_int_id(organization)
        super().form_valid(form)
        messages.success(
            self.request,
            pgettext("courses.view.message", "course_created_successfully").format(title=form.instance.title),
        )
        if self._is_modal_request():
            return JsonResponse(
                {
                    "success": True,
                    "course_id": self.object.id,
                    "dashboard_url": str(self.get_success_url()),
                }
            )
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        if self._is_modal_request():
            html = render_to_string(
                self.modal_form_template_name,
                {
                    "form": form,
                },
                request=self.request,
            )
            return JsonResponse({"success": False, "html": html}, status=400)
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("courses:course_dashboard", args=[self.object.id])


# ═══���════════════════════════════════════════════════════════════════════════
# VIEW 2: Kurs Dashboard (Accordion) - LABS ƏLAVƏSİ
# ════════════════════════════════════════════════════════════════════════════


class CourseDashboardView(LoginRequiredMixin, DetailView):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs Dashboard View                                                     │
    │ GET /courses/<course_id>/dashboard/                                     │
    │                                                                         │
    │ Tələbə yalnız özünə təyin olunmuş işləri görür.                         │
    │ Müəllim bütün işləri görür və idarə edir.                               │
    └───���─────────────────────────────────────────────────────────────────────┘
    """

    model = Course
    template_name = "courses/course_dashboard.html"
    context_object_name = "course"
    pk_url_kwarg = "course_id"

    def get_queryset(self):
        return _tenant_scoped_courses(self.request).select_related("owner", "owner__profile")

    def get_object(self, queryset=None):
        course = super().get_object(queryset=queryset)
        membership = CourseMembership.objects.filter(course=course, user=self.request.user).first()
        is_owner = course.owner_id == self.request.user.id

        if not is_owner and membership is None:
            raise PermissionDenied(pgettext("courses.view.permission", "no_access_this_course"))

        self._membership = membership
        return course

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.get_object()
        user = self.request.user

        # ═══════════════════════════════════════════════════════════════════
        # 1. İSTİFADƏÇİ ROLUNU TƏYİN ET
        # ═══════════════════════════════════════════════════════════════════
        membership = getattr(self, "_membership", None)
        user_role = membership.role if membership else None

        # ─────────────────────────────────────────────────────────────────────
        # Context-ə rol məlumatlarını əlavə et
        # ─────────────────────────────────────────────────────────────────────
        context["is_owner"] = course.owner_id == user.id
        context["is_teacher"] = context["is_owner"] or user_role in {"teacher", "assistant"}
        context["is_student"] = user_role == "student"
        context["is_assistant"] = user_role == "assistant"
        context["can_manage_course"] = context["is_owner"] or context["is_assistant"] or user_role == "teacher"
        context["can_view_members"] = context["can_manage_course"]
        context["user_role"] = user_role
        context["membership"] = membership  # Template-də lazım ola bilər

        requested_profile_section = (self.request.GET.get("from_section") or "").strip()
        valid_profile_sections = {"my-courses", "assigned-courses", "courses", "assigned-exams"}
        if requested_profile_section not in valid_profile_sections:
            requested_profile_section = "assigned-courses" if context["is_student"] else "my-courses"

        profile_return_params = {"section": requested_profile_section}
        if requested_profile_section == "assigned-exams":
            assigned_type = (self.request.GET.get("assigned_type") or "").strip().lower()
            if assigned_type in ASSIGNED_TASK_FILTER_CHOICES:
                profile_return_params["assigned_type"] = assigned_type

        fallback_profile_return_url = f"{reverse('accounts:profile')}?{urlencode(profile_return_params)}"
        explicit_return_url = _safe_same_origin_redirect_path(
            self.request,
            self.request.GET.get("return_to") or self.request.GET.get("next"),
        )
        if explicit_return_url == self.request.get_full_path():
            explicit_return_url = ""

        context["profile_return_section"] = requested_profile_section
        context["profile_return_url"] = explicit_return_url or fallback_profile_return_url

        # ═══════════════════════════════════════════════════════════════════
        # 2. MÖVZULAR & RESURSLAR (Hamı görür)
        # ═══════════════════════════════════════════════════════════════════
        context["topics"] = course.topics.all().order_by("order")
        context["resources"] = course.resources.all().order_by("-created_at")

        # ═══════════════════════════════════════════════════════════════════
        # 3. ÜZVLƏR (Yalnız owner və assistant görür)
        # ═══════════════════════════════════════════════════════════════════
        if context["can_view_members"]:
            context["members"] = course.memberships.select_related("user").order_by("group_name", "joined_at")
        else:
            context["members"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 4. SƏRBƏST İŞLƏR (Assignments)
        # ───────────────────────────────────────────────────────────────────
        # Müəllim: Bütün assignment-ları görür
        # Tələbə: Yalnız özünə təyin olunmuşları görür (arxivlənmişlər istisna)
        # ═══════════════════════════════════════════════════════════════════
        if context["can_manage_course"]:
            # MÜƏLLİM - bütün assignment-lar
            context["assignments"] = course.assignments.all().order_by("-created_at")
            context["assignments_with_user_data"] = []

        elif context["is_student"]:
            # TƏLƏBƏ - arxivlənmişlər istisna (status != 'inactive' filter)
            assignments_qs = (
                course.assignments.filter(assigned_students=user)
                .exclude(status="inactive")  # Deaktiv olanları göstərmə
                .order_by("-created_at")
            )

            # Hər assignment üçün user-specific məlumat hazırla
            assignments_with_user_data = []
            for a in assignments_qs:
                user_attempts = a.submissions.filter(user=user).count()
                is_deadline_passed = a.is_deadline_passed if hasattr(a, "is_deadline_passed") else False
                is_active = a.status in {"active", "published"}
                can_submit = user_attempts < a.max_attempts and not is_deadline_passed and is_active
                attempts_left = a.max_attempts - user_attempts

                assignments_with_user_data.append(
                    {
                        "assignment": a,
                        "user_attempts": user_attempts,
                        "can_submit": can_submit,
                        "attempts_left": attempts_left,
                        "is_deadline_passed": is_deadline_passed,
                    }
                )

            context["assignments"] = assignments_qs
            context["assignments_with_user_data"] = assignments_with_user_data
        else:
            context["assignments"] = []
            context["assignments_with_user_data"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 5. KURS İŞLƏRİ (Projects)
        # ───────────────────────────────────────────────────────────────────
        # Müəllim: Bütün project-ləri görür
        # Tələbə: Yalnız özünə təyin olunmuşları görür (arxivlənmişlər istisna)
        # ═════════════════════════════════════════��═════════════════════════
        if context["can_manage_course"]:
            # MÜƏLLİM - bütün project-lər
            context["projects"] = course.projects.all().order_by("-created_at")
            context["projects_with_user_data"] = []

        elif context["is_student"]:
            # TƏLƏBƏ - arxivlənmişlər istisna
            try:
                projects_qs = (
                    course.projects.filter(assigned_students=user)
                    .exclude(status="archived")  # Arxivlənmişləri göstərmə
                    .order_by("-created_at")
                )

                # Hər project üçün user-specific məlumat hazırla
                projects_with_user_data = []
                for p in projects_qs:
                    user_attempts = p.submissions.filter(student=user).count()
                    is_deadline_passed = p.is_deadline_passed
                    is_active = p.status == "active"
                    can_submit = user_attempts < p.max_attempts and not is_deadline_passed and is_active
                    attempts_left = p.max_attempts - user_attempts

                    projects_with_user_data.append(
                        {
                            "project": p,
                            "user_attempts": user_attempts,
                            "can_submit": can_submit,
                            "attempts_left": attempts_left,
                            "is_deadline_passed": is_deadline_passed,
                        }
                    )

                context["projects"] = projects_qs
                context["projects_with_user_data"] = projects_with_user_data
            except Exception:
                context["projects"] = []
                context["projects_with_user_data"] = []
        else:
            context["projects"] = []
            context["projects_with_user_data"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 7. İMTAHANLAR
        # ───────────────────────────────────────────────────────────────────

        if context["can_manage_course"]:
            # MÜƏLLİM - bu kursa bağlı bütün imtahanları görür
            context["course_exams"] = scoped_by_organization_id(
                Exam.objects.filter(course=course),
                self.request,
                org_id_field="organization_id",
                fallback_org_field="author__profile__organization",
            ).order_by("-created_at")

            # Müəllimin bütün imtahanları (kurs ilə əlaqələndirmək üçün)
            context["teacher_exams"] = scoped_by_organization_id(
                Exam.objects.filter(author=user).exclude(course=course),
                self.request,
                org_id_field="organization_id",
                fallback_org_field="author__profile__organization",
            ).order_by("-created_at")[:10]

        elif context["is_student"]:
            # TƏLƏBƏ - yalnız aktiv və ona icazəli imtahanları görür
            all_course_exams = scoped_by_organization_id(
                Exam.objects.filter(course=course, is_active=True),
                self.request,
                org_id_field="organization_id",
                fallback_org_field="author__profile__organization",
            )

            exams_with_data = []
            for exam in all_course_exams:
                if exam.can_user_see(user):
                    # Bu tələbənin attempt-ları
                    attempts = (
                        ExamAttempt.objects.filter(exam=exam, user=user).exclude(status="draft").order_by("-started_at")
                    )

                    last_attempt = attempts.first()
                    attempt_count = attempts.count()
                    attempts_left = exam.attempts_left_for(user)

                    exams_with_data.append(
                        {
                            "exam": exam,
                            "last_attempt": last_attempt,
                            "attempt_count": attempt_count,
                            "attempts_left": attempts_left,
                            "can_start": exam.can_user_start(user)[0],
                        }
                    )

            context["course_exams"] = []
            context["exams_with_data"] = exams_with_data
        else:
            context["course_exams"] = []
            context["exams_with_data"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 6. LAB İŞLƏRİ
        # ───────────────────────────────────────────────────────────────────
        # Müəllim: Bütün lab-ları görür
        # Tələbə: Yalnız özünə təyin olunmuşları görür + user-specific data
        # ═══════════════════════════════════════════════════════════════════

        if context["can_manage_course"]:
            # MÜƏLLİM - bütün lab-lar
            context["labs"] = course.labs.all().order_by("-created_at")
            context["labs_with_user_data"] = []

        elif context["is_student"]:
            # TƏLƏBƏ - yalnız özünə təyin olunmuş lab-ları görür

            # Tələbənin qrup adını al
            student_group = ""
            if membership and hasattr(membership, "group_name"):
                student_group = membership.group_name or ""

            labs_with_user_data = []

            # Published olan lab-ları yoxla
            for lab in course.labs.filter(status="published").order_by("-created_at"):

                # Bu lab tələbəyə təyin olunubmu?
                is_assigned = False

                # Allowed students - vergüllə ayrılmış ID-lər
                allowed_student_ids = []
                if lab.allowed_students and lab.allowed_students.strip():
                    for x in lab.allowed_students.split(","):
                        x = x.strip()
                        if x.isdigit():
                            allowed_student_ids.append(int(x))

                # Allowed groups - vergüllə ayrılmış qrup adları
                allowed_group_names = []
                if lab.allowed_groups and lab.allowed_groups.strip():
                    for g in lab.allowed_groups.split(","):
                        g = g.strip()
                        if g:
                            allowed_group_names.append(g)

                # ƏSAS MƏNTİQ:
                # 1. Əgər hər iki filtr boşdursa → HAMIYA AÇIQ DEYİL, heç kim görməsin
                # 2. Əgər student ID siyahısında varsa → görür
                # 3. Əgər qrup siyahısında varsa → görür

                has_any_filter = len(allowed_student_ids) > 0 or len(allowed_group_names) > 0

                if not has_any_filter:
                    # Heç bir filtr yoxdur - heç kim görməsin (və ya hamı görsün - hansını istəyirsən?)
                    # Əgər heç bir tələbə/qrup seçilməyibsə, heç kim görməsin:
                    is_assigned = False
                else:
                    # Filtr var - yoxla
                    # Student ID ilə yoxla
                    if user.id in allowed_student_ids:
                        is_assigned = True

                    # Qrup adı ilə yoxla
                    if not is_assigned and student_group and student_group in allowed_group_names:
                        is_assigned = True

                # Əgər təyin olunmayıbsa, skip et
                if not is_assigned:
                    continue

                # Assignment və submission məlumatlarını al
                assignment = LabAssignment.objects.filter(lab=lab, student=user).first()

                submissions_qs = LabSubmission.objects.none()
                attempt_count = 0
                has_submitted = False
                latest_submission = None

                if assignment:
                    submissions_qs = LabSubmission.objects.filter(assignment=assignment).order_by("-submitted_at")
                    attempt_count = submissions_qs.count()
                    has_submitted = attempt_count > 0
                    latest_submission = submissions_qs.first() if has_submitted else None

                max_attempts = lab.max_attempts or 1
                can_submit = (attempt_count < max_attempts) and lab.is_open
                can_show_grade = bool(
                    latest_submission
                    and latest_submission.status == "graded"
                    and latest_submission.graded_at
                    and timezone.now() >= latest_submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
                )

                labs_with_user_data.append(
                    {
                        "lab": lab,
                        "has_submitted": has_submitted,
                        "submission": latest_submission,
                        "submissions": submissions_qs,
                        "attempt_count": attempt_count,
                        "max_attempts": max_attempts,
                        "attempts_left": max_attempts - attempt_count,
                        "can_submit": can_submit,
                        "can_show_grade": can_show_grade,
                    }
                )

            context["labs"] = []
            context["labs_with_user_data"] = labs_with_user_data

        else:
            context["labs"] = []
            context["labs_with_user_data"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 7. FORMALAR VƏ MODAL ÜÇÜN DATA (Yalnız owner üçün)
        # ═══════════════════════════════════════════════════════════════════
        if context["is_owner"]:
            # ─────────────────────────────────────────────────────────────────
            # Form instance-ları
            # ─────────────────────────────────────────────────────────────────
            context["topic_form"] = CourseTopicForm()
            context["resource_form"] = CourseResourceForm()

            # ─────────────────────────────────────────────────────────────────
            # Kursdakı qruplar (modal-da seçim üçün)
            # ─────────────────────────────────────────────────────────────────
            context["assignment_groups"] = list(
                course.memberships.filter(role="student")
                .exclude(group_name__isnull=True)
                .exclude(group_name__exact="")
                .values_list("group_name", flat=True)
                .distinct()
                .order_by("group_name")
            )

            # ─────────────────────────────────────────────────────────────────
            # Kursa əlavə olunmamış istifadəçilər (üzv əlavə etmək üçün)
            # ─────────────────────────────────────────────────────────────────
            course_user_ids = course.memberships.values_list("user_id", flat=True)
            user_org = get_request_organization(self.request)
            user_candidates = User.objects.exclude(id__in=course_user_ids)
            if user_org is not None:
                user_candidates = user_candidates.filter(profile__organization=user_org)
            context["all_users"] = _student_users_queryset(user_candidates).order_by("username")

            # ─────────────────────────────────────────────────────────────────
            # Bütün qruplar (StudentGroup modelindən)
            # ─────────────────────────────────────────────────────────────────
            try:
                qs = StudentGroup.objects.filter(teacher=user)
                if user_org is not None:
                    qs = qs.filter(organization=user_org)
                context["all_groups"] = qs.order_by("name")
            except ImportError:
                context["all_groups"] = []
        else:
            # Owner deyilsə boş saxla
            context["all_users"] = []
            context["all_groups"] = []
            context["assignment_groups"] = []

        return context


# ════════════════════════════════════════════════════════════════════════════
# VIEW 3: Mövzu Əlavə Etmə (AJAX/Modal)
# ════════════════════════════════════════════════════════════════════════════


class AddTopicView(IsCourseOwnerMixin, CreateView):
    """Mövzu əlavə etmə (AJAX POST)."""

    model = CourseTopic
    form_class = CourseTopicForm

    def dispatch(self, request, *args, **kwargs):
        self.course = _get_owner_course_or_404(request, kwargs["course_id"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.course = self.course
        max_order = CourseTopic.objects.filter(course=self.course).aggregate(Max("order"))["order__max"] or 0
        form.instance.order = max_order + 1

        response = super().form_valid(form)
        success_message = pgettext("courses.view.message", "topic_added").format(title=form.instance.title)

        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": success_message,
                    "topic": {
                        "id": form.instance.id,
                        "title": form.instance.title,
                        "order": form.instance.order,
                    },
                }
            )

        messages.success(self.request, success_message)
        return response

    def form_invalid(self, form):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "errors": form.errors}, status=400)
        messages.error(self.request, pgettext_lazy("courses.view.message", "topic_add_failed"))
        return redirect("courses:course_dashboard", course_id=self.course.id)

    def get_success_url(self):
        return reverse_lazy("courses:course_dashboard", args=[self.course.id])


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Mövzu Redaktə Etmə (AJAX)
# ════════════════════════════════════════════════════════════════════════════


class EditTopicView(IsCourseOwnerMixin, UpdateView):
    """Mövzu redaktə etmə (AJAX POST)."""

    model = CourseTopic
    form_class = CourseTopicForm
    pk_url_kwarg = "topic_id"

    def test_func(self):
        topic = self.get_object()
        return _owner_courses_queryset(self.request).filter(id=topic.course_id).exists()

    def dispatch(self, request, *args, **kwargs):
        self.topic = self.get_object()
        self.course = self.topic.course
        if not _owner_courses_queryset(request).filter(id=self.course.id).exists():
            return HttpResponseForbidden(pgettext("courses.view.message", "no_permission_edit_course"))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        success_message = pgettext("courses.view.message", "topic_updated").format(title=form.instance.title)

        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": success_message,
                    "topic": {
                        "id": form.instance.id,
                        "title": form.instance.title,
                        "description": form.instance.description,
                        "order": form.instance.order,
                    },
                }
            )

        messages.success(self.request, success_message)
        return response

    def form_invalid(self, form):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "errors": form.errors}, status=400)

        messages.error(self.request, pgettext_lazy("courses.view.message", "topic_update_failed"))
        return redirect("courses:course_dashboard", course_id=self.course.id)

    def get_success_url(self):
        return reverse_lazy("courses:course_dashboard", args=[self.course.id])


# ════════════════════════════════════════════════════════════════════════════
# VIEW 4: Mövzu Silmə (AJAX)
# ════════════════════════════════════════════════════════════════════════════


class DeleteTopicView(IsCourseOwnerMixin, View):
    """Mövzu silmə (POST)."""

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        topic_id = kwargs.get("topic_id")

        course = _get_owner_course_or_404(request, course_id)
        topic = get_object_or_404(CourseTopic, id=topic_id, course=course)

        topic_title = topic.title
        topic.delete()

        messages.success(
            request,
            pgettext("courses.view.message", "topic_deleted").format(title=topic_title),
        )

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True})

        return redirect("courses:course_dashboard", course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW 5: Resurs Əlavə Etmə
# ════════════════════════════════════════════════════════════════════════════


class AddResourceView(IsCourseOwnerMixin, CreateView):
    """Resurs əlavə etmə (AJAX/Modal)."""

    model = CourseResource
    form_class = CourseResourceForm

    def dispatch(self, request, *args, **kwargs):
        self.course = _get_owner_course_or_404(request, kwargs["course_id"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.course = self.course
        response = super().form_valid(form)
        success_message = pgettext("courses.view.message", "resource_added").format(title=form.instance.title)

        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": success_message,
                    "resource": {
                        "id": form.instance.id,
                        "title": form.instance.title,
                        "type": form.instance.get_resource_type_display(),
                    },
                }
            )

        messages.success(self.request, success_message)
        return response

    def get_success_url(self):
        return reverse_lazy("courses:course_dashboard", args=[self.course.id])


# ════════════════════════════════════════════════════════════════════════════
# VIEW 6: Resurs Silmə
# ════════════════════════════════════════════════════════════════════════════


class DeleteResourceView(IsCourseOwnerMixin, View):
    """Resurs silmə."""

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        resource_id = kwargs.get("resource_id")

        course = _get_owner_course_or_404(request, course_id)
        resource = get_object_or_404(CourseResource, id=resource_id, course=course)

        resource_title = resource.title
        resource.delete()

        messages.success(
            request,
            pgettext("courses.view.message", "resource_deleted").format(title=resource_title),
        )

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True})

        return redirect("courses:course_dashboard", course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW 7: Kurs Üzvləri (Members)
# ════════════════════════════════════════════════════════════════════════════


class CourseMembersView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Kurs üzvlüyü səhifəsi."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        return _owner_courses_queryset(self.request).filter(id=course_id).exists()

    def handle_no_permission(self):
        messages.error(self.request, pgettext_lazy("courses.view.message", "no_permission_access_page"))
        return redirect("home")

    def get(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        course = _get_owner_course_or_404(request, course_id)

        members = course.memberships.all().order_by("joined_at")
        teacher = members.filter(role="teacher").first()
        assistants = members.filter(role="assistant")
        students = members.filter(role="student").order_by("group_name", "user__username")

        course_user_ids = course.memberships.values_list("user_id", flat=True)

        user_org = get_request_organization(request)
        all_users = User.objects.exclude(id__in=course_user_ids)
        if user_org is not None:
            all_users = all_users.filter(profile__organization=user_org)
        all_users = _student_users_queryset(all_users).order_by("username")

        try:
            all_groups_qs = StudentGroup.objects.filter(teacher=request.user)
            if user_org is not None:
                all_groups_qs = all_groups_qs.filter(organization=user_org)
            all_groups = all_groups_qs.order_by("name")
        except ImportError:
            all_groups = []

        context = {
            "course": course,
            "members": members,
            "teacher": teacher,
            "assistants": assistants,
            "students": students,
            "all_users": all_users,
            "all_groups": all_groups,
            "is_owner": course.owner == request.user,
        }

        return render(request, "courses/course_members.html", context)


class AvailableStudentsView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Kursda olmayan tələbələri JSON kimi qaytarır."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        return _owner_courses_queryset(self.request).filter(id=course_id).exists()

    def get(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        course = _get_owner_course_or_404(request, course_id)

        course_user_ids = course.memberships.values_list("user_id", flat=True)
        user_org = get_request_organization(request)

        qs = User.objects.exclude(id__in=course_user_ids)
        if user_org is not None:
            qs = qs.filter(profile__organization=user_org)
        qs = _student_users_queryset(qs).order_by("username")

        data = [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.get_full_name() or u.username,
            }
            for u in qs
        ]

        return JsonResponse({"success": True, "users": data})


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Tələbə Əlavə Et (AJAX)
# ════════════════════════════════════════════════════════════════════════════


class AddMemberView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Tələbə əlavə etmə (Modal-dan AJAX)."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        return _owner_courses_queryset(self.request).filter(id=course_id).exists()

    def handle_no_permission(self):
        return JsonResponse(
            {"success": False, "error": pgettext("courses.view.message", "no_permission_action")},
            status=403,
        )

    def post(self, request, *args, **kwargs):
        if not request_has_permission(request, "course.edit"):
            return JsonResponse(
                {"success": False, "error": pgettext("courses.view.message", "no_permission_action")},
                status=403,
            )

        course_id = kwargs.get("course_id")
        course = _get_owner_course_or_404(request, course_id)

        user_ids = request.POST.getlist("user_ids")
        group_name = request.POST.get("group_name", "").strip()

        if not user_ids:
            return JsonResponse(
                {"success": False, "error": pgettext("courses.view.message", "no_student_selected")},
                status=400,
            )

        added_count = 0

        owner_org = get_request_organization(request)
        for uid in user_ids:
            try:
                user_qs = User.objects.filter(id=uid)
                if owner_org is not None:
                    user_qs = user_qs.filter(profile__organization=owner_org)
                user = user_qs.get()
                membership, created = CourseMembership.objects.get_or_create(
                    course=course,
                    user=user,
                    defaults={"role": "student", "group_name": group_name},
                )
                if not created:
                    membership.group_name = group_name
                    membership.save()
                added_count += 1
            except User.DoesNotExist:
                continue

        return JsonResponse(
            {
                "success": True,
                "message": pgettext("courses.view.message", "students_added_to_course").format(count=added_count),
            }
        )


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Qrup Əlavə Et (Bulk)
# ════════════════════════════════════════════════════════════════════════════


class AddMembersBulkView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Qrupları toplu şəkildə kursa əlavə et."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        return _owner_courses_queryset(self.request).filter(id=course_id).exists()

    def handle_no_permission(self):
        return JsonResponse({"success": False, "error": pgettext("courses.view.message", "no_permission")}, status=403)

    def post(self, request, *args, **kwargs):
        if not request_has_permission(request, "course.edit"):
            return JsonResponse({"success": False, "error": pgettext("courses.view.message", "no_permission")}, status=403)

        course_id = kwargs.get("course_id")
        course = _get_owner_course_or_404(request, course_id)

        group_ids = request.POST.getlist("group_ids")

        if not group_ids:
            return JsonResponse(
                {"success": False, "error": pgettext("courses.view.message", "no_group_selected")},
                status=400,
            )

        try:
            user_org = get_request_organization(request)
            groups = StudentGroup.objects.filter(id__in=group_ids, teacher=request.user)
            if user_org is not None:
                groups = groups.filter(organization=user_org)

            added_count = 0

            for group in groups:
                students = group.students.all()

                for student in students:
                    membership, created = CourseMembership.objects.get_or_create(
                        course=course,
                        user=student,
                        defaults={"role": "student", "group_name": group.name},
                    )
                    if created:
                        added_count += 1
                    else:
                        if not (membership.group_name or "").strip():
                            membership.group_name = group.name
                            membership.save(update_fields=["group_name"])

            return JsonResponse(
                {
                    "success": True,
                    "message": pgettext("courses.view.message", "students_added_to_course").format(count=added_count),
                    "added_count": added_count,
                }
            )

        except ImportError:
            return JsonResponse(
                {"success": False, "error": pgettext("courses.view.message", "studentgroup_model_not_found")},
                status=500,
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Üzv Silmə (AJAX)
# ════════════════════════════════════════════════════════════════════════════


class DeleteMemberView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Tələbə və ya köməkçi silmə."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        return _owner_courses_queryset(self.request).filter(id=course_id).exists()

    def handle_no_permission(self):
        return JsonResponse(
            {"success": False, "error": pgettext("courses.view.message", "no_permission_action")},
            status=403,
        )

    def post(self, request, *args, **kwargs):
        if not request_has_permission(request, "course.edit"):
            return JsonResponse(
                {"success": False, "error": pgettext("courses.view.message", "no_permission_action")},
                status=403,
            )

        course_id = kwargs.get("course_id")
        member_id = kwargs.get("member_id")

        course = _get_owner_course_or_404(request, course_id)
        membership = get_object_or_404(CourseMembership, id=member_id, course=course)

        username = membership.user.username
        membership.delete()
        success_message = pgettext("courses.view.message", "member_deleted").format(username=username)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True, "message": success_message})

        messages.success(request, success_message)
        return redirect("courses:course_members", course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Qrup Silmə (Toplu)
# ════════════════════════════════════════════════════════════════════════════


class DeleteGroupFromCourseView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Kursdan müəyyən bir qrup adını daşıyan bütün tələbələri silir."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        return _owner_courses_queryset(self.request).filter(id=course_id).exists()

    def post(self, request, *args, **kwargs):
        if not request_has_permission(request, "course.edit"):
            raise PermissionDenied(pgettext("courses.view.permission", "no_permission_edit_course"))

        course_id = kwargs.get("course_id")
        group_name = request.POST.get("group_name")

        if not group_name:
            messages.error(request, pgettext_lazy("courses.view.message", "group_name_missing"))
            return redirect("courses:course_members", course_id=course_id)

        course = _get_owner_course_or_404(request, course_id)

        deleted_count, _ = CourseMembership.objects.filter(course=course, group_name=group_name).delete()

        messages.success(
            request,
            pgettext("courses.view.message", "group_removed_from_course").format(
                group_name=group_name,
                count=deleted_count,
            ),
        )
        return redirect("courses:course_members", course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Kurs Redaksiya Etmə
# ════════════════════════════════════════════════════════════════════════════


class EditCourseView(IsCourseOwnerMixin, UpdateView):
    """Kurs məlumatını redaktə etmə."""

    model = Course
    form_class = CourseForm
    template_name = "courses/edit_course.html"
    context_object_name = "course"
    pk_url_kwarg = "course_id"

    def dispatch(self, request, *args, **kwargs):
        _require_org_permission(request, "course.edit")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(
            self.request,
            pgettext("courses.view.message", "course_updated").format(title=form.instance.title),
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("courses:course_dashboard", args=[self.object.id])


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Kurs Silmə
# ════════════════════════════════════════════════════════════════════════════


class DeleteCourseView(IsCourseOwnerMixin, View):
    """Kursun tam silinməsi."""

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        course = _get_owner_course_or_404(request, course_id)

        course_title = course.title
        course.delete()

        messages.success(
            request,
            pgettext("courses.view.message", "course_deleted").format(title=course_title),
        )
        return_to = _safe_same_origin_redirect_path(
            request,
            request.POST.get("return_to") or request.GET.get("return_to"),
        )
        if return_to:
            return redirect(return_to)

        return redirect(f"{reverse('accounts:profile')}?section=my-courses")


@login_required
@require_POST
def update_course_status(request, course_id):
    _require_org_permission(request, "course.edit")
    course = _get_owner_course_or_404(request, course_id)

    requested_status = (request.POST.get("status") or "").strip().lower()
    normalized_status = {"active": "published", "published": "published", "draft": "draft"}.get(requested_status)

    if normalized_status is None:
        messages.error(request, pgettext("courses.view.message", "invalid_course_status"))
    else:
        course.status = normalized_status
        course.save(update_fields=["status", "updated_at"])
        messages.success(
            request,
            pgettext("courses.view.message", "course_status_updated").format(status=course.get_status_display()),
        )

    redirect_target = _safe_same_origin_redirect_path(
        request,
        request.POST.get("next") or request.GET.get("next"),
    )
    if redirect_target:
        return redirect(redirect_target)
    return redirect("courses:course_dashboard", course_id=course.id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Mənim Kurslarım
# ════════════════════════════════════════════════════════════════════════════


class MyCoursesListView(LoginRequiredMixin, ListView):
    template_name = "courses/my_courses.html"
    context_object_name = "courses"
    paginate_by = 12

    def get_queryset(self):
        return _owner_courses_queryset(self.request).order_by("-created_at")


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Tələbənin Kursları
# ════════════════════════════════════════════════════════════════════════════


class StudentCoursesView(LoginRequiredMixin, ListView):
    """
    Tələbəyə təyin olunmuş kursların siyahısı.

    Tələbə kursa iki yolla əlavə oluna bilər:
    1. Birbaşa - CourseMembership.user = tələbə
    2. Qrup vasitəsilə - CourseMembership qrupuna əlavə edilib
    """

    template_name = "courses/student_courses.html"
    context_object_name = "courses"
    paginate_by = 12

    def get_queryset(self):
        user = self.request.user

        # Tələbənin üzv olduğu kurslar
        courses = (
            Course.objects.filter(memberships__user=user, memberships__role="student", status="published")
            .distinct()
            .select_related("owner")
            .order_by("-created_at")
        )
        return _tenant_scoped_courses(self.request, courses)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Hər kurs üçün əlavə məlumat
        courses_with_info = []
        for course in context["courses"]:
            membership = CourseMembership.objects.filter(course=course, user=self.request.user).first()

            courses_with_info.append(
                {
                    "course": course,
                    "group_name": membership.group_name if membership else "",
                    "joined_at": membership.joined_at if membership else None,
                }
            )

        context["courses_with_info"] = courses_with_info
        return context


@login_required
@require_POST
def link_exam_to_course(request, pk):
    """İmtahanı kursa əlaqələndir"""
    course = _get_owner_course_or_404(request, pk)

    try:
        data = json.loads(request.body)
        exam_id = data.get("exam_id")

        exam_qs = scoped_by_organization_id(
            Exam.objects.filter(author=request.user),
            request,
            org_id_field="organization_id",
            fallback_org_field="author__profile__organization",
        )
        exam = get_object_or_404(exam_qs, id=exam_id)
        exam.course = course
        exam.save()

        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required
@require_POST
def unlink_exam_from_course(request, pk):
    """İmtahanı kursdan ayır"""
    course = _get_owner_course_or_404(request, pk)

    try:
        data = json.loads(request.body)
        exam_id = data.get("exam_id")

        exam = get_object_or_404(
            scoped_by_organization_id(
                Exam.objects.filter(course=course),
                request,
                org_id_field="organization_id",
                fallback_org_field="author__profile__organization",
            ),
            id=exam_id,
        )
        exam.course = None
        exam.save()

        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})
