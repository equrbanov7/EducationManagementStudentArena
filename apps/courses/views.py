"""
courses/views.py
────────────────
Kurs modulu üçün view-lər.

Labs app inteqrasiyası əlavə edilib.
"""

import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Max
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import (CreateView, DetailView, ListView, UpdateView,
                                  View)

from apps.exams.models import Exam, ExamAttempt, StudentGroup
from apps.labs.models import LabAssignment, LabSubmission

from .forms import CourseForm, CourseResourceForm, CourseTopicForm
from .models import Course, CourseMembership, CourseResource, CourseTopic

User = get_user_model()


# ════════════════════════════════════════════════════════════════════════════
# Mixin: Müəllim İcazə Yoxlaması
# ════════════════════════════════════════════════════════════════════════════


class IsTeacherMixin(UserPassesTestMixin):
    """Yalnız müəllim (is_teacher_or_above) bu view-a girə bilər."""

    def test_func(self):
        return getattr(self.request.user, "is_teacher_or_above", False)

    def handle_no_permission(self):
        messages.error(self.request, "Bu əməliyyat yalnız müəllimlər üçün mümkündür.")
        return redirect("home")


class IsCourseOwnerMixin(UserPassesTestMixin):
    """Yalnız kursun sahibi (owner) redaktə edə bilər."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user

    def handle_no_permission(self):
        messages.error(self.request, "Bu kursu redaktə etməyə icazəniz yoxdur.")
        return redirect("home")


# ════════════════════════════════════════════════════════════════════════════
# VIEW 1: Kurs Yaratma
# ════════════════════════════════════════════════════════════════════════════


class CreateCourseView(IsTeacherMixin, CreateView):
    """Kurs yaratma view-u."""

    model = Course
    form_class = CourseForm
    template_name = "courses/create_course.html"

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.status = "draft"
        response = super().form_valid(form)
        messages.success(
            self.request, f'✅ "{form.instance.title}" kursu uğurla yaradıldı!'
        )
        return response

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.get_object()
        user = self.request.user

        # ═══════════════════════════════════════════════════════════════════
        # 1. İSTİFADƏÇİ ROLUNU TƏYİN ET
        # ═══════════════════════════════════════════════════════════════════
        membership = CourseMembership.objects.filter(course=course, user=user).first()
        user_role = membership.role if membership else None

        # ─────────────────────────────────────────────────────────────────────
        # Context-ə rol məlumatlarını əlavə et
        # ─────────────────────────────────────────────────────────────────────
        context["is_owner"] = course.owner == user
        context["is_teacher"] = getattr(user, "is_teacher_or_above", False)
        context["is_student"] = user_role == "student"
        context["is_assistant"] = user_role in ["assistant_teacher", "moderator"]
        context["can_view_members"] = context["is_owner"] or context["is_assistant"]
        context["user_role"] = user_role
        context["membership"] = membership  # Template-də lazım ola bilər

        # ═══════════════════════════════════════════════════════════════════
        # 2. MÖVZULAR & RESURSLAR (Hamı görür)
        # ═══════════════════════════════════════════════════════════════════
        context["topics"] = course.topics.all().order_by("order")
        context["resources"] = course.resources.all().order_by("-created_at")

        # ═══════════════════════════════════════════════════════════════════
        # 3. ÜZVLƏR (Yalnız owner və assistant görür)
        # ═══════════════════════════════════════════════════════════════════
        if context["can_view_members"]:
            context["members"] = course.memberships.select_related("user").order_by(
                "group_name", "joined_at"
            )
        else:
            context["members"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 4. SƏRBƏST İŞLƏR (Assignments)
        # ───────────────────────────────────────────────────────────────────
        # Müəllim: Bütün assignment-ları görür
        # Tələbə: Yalnız özünə təyin olunmuşları görür (arxivlənmişlər istisna)
        # ═══════════════════════════════════════════════════════════════════
        if context["is_owner"] or context["is_teacher"]:
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
                user_attempts = a.submissions.filter(student=user).count()
                is_deadline_passed = (
                    a.is_deadline_passed if hasattr(a, "is_deadline_passed") else False
                )
                is_active = a.status == "active"
                can_submit = (
                    user_attempts < a.max_attempts
                    and not is_deadline_passed
                    and is_active
                )
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
        if context["is_owner"] or context["is_teacher"]:
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
                    can_submit = (
                        user_attempts < p.max_attempts
                        and not is_deadline_passed
                        and is_active
                    )
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

        if context["is_owner"] or context["is_teacher"]:
            # MÜƏLLİM - bu kursa bağlı bütün imtahanları görür
            context["course_exams"] = Exam.objects.filter(course=course).order_by(
                "-created_at"
            )

            # Müəllimin bütün imtahanları (kurs ilə əlaqələndirmək üçün)
            context["teacher_exams"] = (
                Exam.objects.filter(author=user)
                .exclude(course=course)
                .order_by("-created_at")[:10]
            )

        elif context["is_student"]:
            # TƏLƏBƏ - yalnız aktiv və ona icazəli imtahanları görür
            all_course_exams = Exam.objects.filter(course=course, is_active=True)

            exams_with_data = []
            for exam in all_course_exams:
                if exam.can_user_see(user):
                    # Bu tələbənin attempt-ları
                    attempts = (
                        ExamAttempt.objects.filter(exam=exam, user=user)
                        .exclude(status="draft")
                        .order_by("-started_at")
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

        if context["is_owner"] or context["is_teacher"]:
            # MÜƏLLİM - bütün lab-lar
            context["labs"] = course.labs.all().order_by("-created_at")
            context["labs_with_user_data"] = []

        elif context["is_student"]:
            # TƏLƏBƏ - yalnız özünə təyin olunmuş lab-ları görür

            # Tələbənin qrup adını al
            student_group = ""
            if membership and hasattr(membership, "group_name"):
                student_group = membership.group_name or ""

            print(f"DEBUG: Student ID: {user.id}, Group: '{student_group}'")  # DEBUG

            labs_with_user_data = []

            # Published olan lab-ları yoxla
            for lab in course.labs.filter(status="published").order_by("-created_at"):

                print(f"DEBUG: Checking Lab '{lab.title}' (ID: {lab.id})")  # DEBUG
                print(f"DEBUG:   allowed_students: '{lab.allowed_students}'")  # DEBUG
                print(f"DEBUG:   allowed_groups: '{lab.allowed_groups}'")  # DEBUG

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

                print(f"DEBUG:   Parsed student IDs: {allowed_student_ids}")  # DEBUG
                print(f"DEBUG:   Parsed group names: {allowed_group_names}")  # DEBUG

                # ƏSAS MƏNTİQ:
                # 1. Əgər hər iki filtr boşdursa → HAMIYA AÇIQ DEYİL, heç kim görməsin
                # 2. Əgər student ID siyahısında varsa → görür
                # 3. Əgər qrup siyahısında varsa → görür

                has_any_filter = (
                    len(allowed_student_ids) > 0 or len(allowed_group_names) > 0
                )

                if not has_any_filter:
                    # Heç bir filtr yoxdur - heç kim görməsin (və ya hamı görsün - hansını istəyirsən?)
                    # Əgər heç bir tələbə/qrup seçilməyibsə, heç kim görməsin:
                    is_assigned = False
                    print("DEBUG:   No filter set - NOT assigned")  # DEBUG
                else:
                    # Filtr var - yoxla
                    # Student ID ilə yoxla
                    if user.id in allowed_student_ids:
                        is_assigned = True
                        print("DEBUG:   Assigned by student ID")  # DEBUG

                    # Qrup adı ilə yoxla
                    if (
                        not is_assigned
                        and student_group
                        and student_group in allowed_group_names
                    ):
                        is_assigned = True
                        print("DEBUG:   Assigned by group name")  # DEBUG

                print(f"DEBUG:   Final is_assigned: {is_assigned}")  # DEBUG

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
                    submissions_qs = LabSubmission.objects.filter(
                        assignment=assignment
                    ).order_by("-submitted_at")
                    attempt_count = submissions_qs.count()
                    has_submitted = attempt_count > 0
                    latest_submission = (
                        submissions_qs.first() if has_submitted else None
                    )

                max_attempts = lab.max_attempts or 1
                can_submit = (attempt_count < max_attempts) and lab.is_open

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
                    }
                )

            context["labs"] = []
            context["labs_with_user_data"] = labs_with_user_data
            print(f"DEBUG: Total labs for student: {len(labs_with_user_data)}")  # DEBUG

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
            context["all_users"] = (
                User.objects.exclude(id__in=course_user_ids)
                .filter(groups__name="student")
                .distinct()
                .order_by("username")
            )

            # ─────────────────────────────────────────────────────────────────
            # Bütün qruplar (StudentGroup modelindən)
            # ─────────────────────────────────────────────────────────────────
            try:

                context["all_groups"] = StudentGroup.objects.all().order_by("name")
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
        self.course = get_object_or_404(Course, id=kwargs["course_id"])
        if self.course.owner != request.user:
            return HttpResponseForbidden("Bu kursu redaktə etməyə icazəniz yoxdur.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.course = self.course
        max_order = (
            CourseTopic.objects.filter(course=self.course).aggregate(Max("order"))[
                "order__max"
            ]
            or 0
        )
        form.instance.order = max_order + 1

        response = super().form_valid(form)

        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": f'"{form.instance.title}" mövzusu əlavə olundu',
                    "topic": {
                        "id": form.instance.id,
                        "title": form.instance.title,
                        "order": form.instance.order,
                    },
                }
            )

        messages.success(self.request, f'"{form.instance.title}" mövzusu əlavə olundu')
        return response

    def form_invalid(self, form):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "errors": form.errors}, status=400)
        messages.error(self.request, "Mövzu əlavə olunarkən xəta baş verdi.")
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

    def dispatch(self, request, *args, **kwargs):
        self.topic = self.get_object()
        self.course = self.topic.course
        if self.course.owner != request.user:
            return HttpResponseForbidden("Bu kursu redaktə etməyə icazəniz yoxdur.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)

        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": f'"{form.instance.title}" mövzusu yeniləndi',
                    "topic": {
                        "id": form.instance.id,
                        "title": form.instance.title,
                        "description": form.instance.description,
                        "order": form.instance.order,
                    },
                }
            )

        messages.success(self.request, f'"{form.instance.title}" mövzusu yeniləndi')
        return response

    def form_invalid(self, form):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "errors": form.errors}, status=400)

        messages.error(self.request, "Mövzu yenilənərkən xəta baş verdi.")
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

        course = get_object_or_404(Course, id=course_id)
        topic = get_object_or_404(CourseTopic, id=topic_id, course=course)

        if course.owner != request.user:
            messages.error(request, "Bu əməliyyata icazəniz yoxdur.")
            return redirect("courses:course_dashboard", course_id=course_id)

        topic_title = topic.title
        topic.delete()

        messages.success(request, f'✅ "{topic_title}" mövzusu silindi.')

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
        self.course = get_object_or_404(Course, id=kwargs["course_id"])
        if self.course.owner != request.user:
            return HttpResponseForbidden("Bu kursu redaktə etməyə icazəniz yoxdur.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.course = self.course
        response = super().form_valid(form)

        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": f'"{form.instance.title}" resursu əlavə olundu',
                    "resource": {
                        "id": form.instance.id,
                        "title": form.instance.title,
                        "type": form.instance.get_resource_type_display(),
                    },
                }
            )

        messages.success(self.request, f'"{form.instance.title}" resursu əlavə olundu')
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

        course = get_object_or_404(Course, id=course_id)
        resource = get_object_or_404(CourseResource, id=resource_id, course=course)

        if course.owner != request.user:
            messages.error(request, "Bu əməliyyata icazəniz yoxdur.")
            return redirect("courses:course_dashboard", course_id=course_id)

        resource_title = resource.title
        resource.delete()

        messages.success(request, f'✅ "{resource_title}" resursu silindi.')

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
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user

    def handle_no_permission(self):
        messages.error(self.request, "Bu səhifəyə giriş icazəniz yoxdur.")
        return redirect("home")

    def get(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        course = get_object_or_404(Course, id=course_id)

        members = course.memberships.all().order_by("joined_at")
        teacher = members.filter(role="teacher").first()
        assistants = members.filter(role="assistant")
        students = members.filter(role="student").order_by(
            "group_name", "user__username"
        )

        course_user_ids = course.memberships.values_list("user_id", flat=True)

        if hasattr(User, "groups"):
            all_users = (
                User.objects.exclude(id__in=course_user_ids)
                .filter(groups__name="student")
                .distinct()
                .order_by("username")
            )
        else:
            all_users = User.objects.exclude(id__in=course_user_ids).order_by(
                "username"
            )

        try:

            all_groups = StudentGroup.objects.all().order_by("name")
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
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user

    def get(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        course = get_object_or_404(Course, id=course_id)

        course_user_ids = course.memberships.values_list("user_id", flat=True)

        qs = (
            User.objects.exclude(id__in=course_user_ids)
            .filter(groups__name="student")
            .distinct()
            .order_by("username")
        )

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
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user

    def handle_no_permission(self):
        return JsonResponse(
            {"success": False, "error": "Bu əməliyyata icazəniz yoxdur."}, status=403
        )

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        course = get_object_or_404(Course, id=course_id)

        user_ids = request.POST.getlist("user_ids")
        group_name = request.POST.get("group_name", "").strip()

        if not user_ids:
            return JsonResponse(
                {"success": False, "error": "Heç bir tələbə seçilməyib."}, status=400
            )

        added_count = 0

        for uid in user_ids:
            try:
                user = User.objects.get(id=uid)
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
            {"success": True, "message": f"{added_count} tələbə kursa əlavə olundu."}
        )


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Qrup Əlavə Et (Bulk)
# ════════════════════════════════════════════════════════════════════════════


class AddMembersBulkView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Qrupları toplu şəkildə kursa əlavə et."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user

    def handle_no_permission(self):
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur."}, status=403)

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        course = get_object_or_404(Course, id=course_id)

        group_ids = request.POST.getlist("group_ids")

        if not group_ids:
            return JsonResponse(
                {"success": False, "error": "Qrup seçilməyib."}, status=400
            )

        try:

            groups = StudentGroup.objects.filter(id__in=group_ids)

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
                    "message": f"{added_count} tələbə kursa əlavə olundu.",
                    "added_count": added_count,
                }
            )

        except ImportError:
            return JsonResponse(
                {"success": False, "error": "StudentGroup modeli tapılmadı."},
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
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user

    def handle_no_permission(self):
        return JsonResponse(
            {"success": False, "error": "Bu əməliyyata icazəniz yoxdur."}, status=403
        )

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        member_id = kwargs.get("member_id")

        course = get_object_or_404(Course, id=course_id)
        membership = get_object_or_404(CourseMembership, id=member_id, course=course)

        username = membership.user.username
        membership.delete()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True, "message": f"{username} silindi."})

        messages.success(request, f"✅ {username} silindi.")
        return redirect("courses:course_members", course_id=course_id)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Qrup Silmə (Toplu)
# ════════════════════════════════════════════════════════════════════════════


class DeleteGroupFromCourseView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Kursdan müəyyən bir qrup adını daşıyan bütün tələbələri silir."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        course = get_object_or_404(Course, id=course_id)
        return course.owner == self.request.user

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        group_name = request.POST.get("group_name")

        if not group_name:
            messages.error(request, "Qrup adı tapılmadı.")
            return redirect("courses:course_members", course_id=course_id)

        course = get_object_or_404(Course, id=course_id)

        deleted_count, _ = CourseMembership.objects.filter(
            course=course, group_name=group_name
        ).delete()

        messages.success(
            request,
            f'✅ "{group_name}" qrupundan {deleted_count} tələbə kursdan çıxarıldı.',
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

    def form_valid(self, form):
        messages.success(self.request, f'✅ "{form.instance.title}" kursu yeniləndi.')
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
        course = get_object_or_404(Course, id=course_id)

        if course.owner != request.user:
            messages.error(request, "Bu kursu silməyə icazəniz yoxdur.")
            return redirect("home")

        course_title = course.title
        course.delete()

        messages.success(
            request, f'✅ "{course_title}" kursu və bütün məlumatları silindi.'
        )
        return redirect("user_profile", username=request.user.username)


# ════════════════════════════════════════════════════════════════════════════
# VIEW: Mənim Kurslarım
# ════════════════════════════════════════════════════════════════════════════


class MyCoursesListView(LoginRequiredMixin, ListView):
    template_name = "courses/my_courses.html"
    context_object_name = "courses"
    paginate_by = 12

    def get_queryset(self):
        return Course.objects.filter(owner=self.request.user).order_by("-created_at")


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
        return (
            Course.objects.filter(
                memberships__user=user, memberships__role="student", status="published"
            )
            .distinct()
            .select_related("owner")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Hər kurs üçün əlavə məlumat
        courses_with_info = []
        for course in context["courses"]:
            membership = CourseMembership.objects.filter(
                course=course, user=self.request.user
            ).first()

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
    course = get_object_or_404(Course, id=pk)

    if course.owner != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    try:
        data = json.loads(request.body)
        exam_id = data.get("exam_id")

        exam = get_object_or_404(Exam, id=exam_id, author=request.user)
        exam.course = course
        exam.save()

        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required
@require_POST
def unlink_exam_from_course(request, pk):
    """İmtahanı kursdan ayır"""
    course = get_object_or_404(Course, id=pk)

    if course.owner != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    try:
        data = json.loads(request.body)
        exam_id = data.get("exam_id")

        exam = get_object_or_404(Exam, id=exam_id, course=course)
        exam.course = None
        exam.save()

        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})
