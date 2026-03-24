"""
courses/views/membership.py
────────────────────────────
Course membership management views.

Contains:
- CourseMembersView
- AvailableStudentsView
- AddMemberView
- AddMembersBulkView
- DeleteMemberView
- DeleteGroupFromCourseView
- StudentCoursesView
- link_exam_to_course (function-based)
- unlink_exam_from_course (function-based)
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_POST
from django.views.generic import ListView, View

from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam, StudentGroup
from core.helpers import _tenant_scoped_courses
from core.permissions import request_has_permission
from core.tenancy import get_request_organization, scoped_by_organization

from ._helpers import _get_owner_course_or_404, _owner_courses_queryset, _student_users_queryset

User = get_user_model()

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Course Members View
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


# ════════════════════════════════════════════════════════════════════════════
# Available Students View
# ════════════════════════════════════════════════════════════════════════════


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
# Add Member View
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
# Add Members Bulk View
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
            return JsonResponse(
                {"success": False, "error": pgettext("courses.view.message", "no_permission")}, status=403
            )

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
        except Exception:
            logger.exception("Unexpected error in AddMembersBulkView")
            return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


# ════════════════════════════════════════════════════════════════════════════
# Delete Member View
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
# Delete Group From Course View
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
# Student Courses View
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

        user = self.request.user
        courses_page = context["courses"]

        # Batch-fetch memberships for all courses on this page in one query
        # instead of one per course (N+1 avoidance).
        course_ids = [c.id for c in courses_page]
        membership_by_course = {
            m.course_id: m
            for m in CourseMembership.objects.filter(course_id__in=course_ids, user=user, role="student")
        }

        # Hər kurs üçün əlavə məlumat
        courses_with_info = []
        for course in courses_page:
            membership = membership_by_course.get(course.id)

            courses_with_info.append(
                {
                    "course": course,
                    "group_name": membership.group_name if membership else "",
                    "joined_at": membership.joined_at if membership else None,
                }
            )

        context["courses_with_info"] = courses_with_info
        return context


# ════════════════════════════════════════════════════════════════════════════
# Link/Unlink Exam Functions
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_POST
def link_exam_to_course(request, pk):
    """İmtahanı kursa əlaqələndir"""
    course = _get_owner_course_or_404(request, pk)

    try:
        data = json.loads(request.body)
        exam_id = data.get("exam_id")

        exam_qs = scoped_by_organization(
            Exam.objects.filter(author=request.user),
            request,
        )
        exam = get_object_or_404(exam_qs, id=exam_id)
        exam.course = course
        exam.save()

        return JsonResponse({"success": True})
    except Exception:
        logger.exception("Unexpected error in link_exam_to_course")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


@login_required
@require_POST
def unlink_exam_from_course(request, pk):
    """İmtahanı kursdan ayır"""
    course = _get_owner_course_or_404(request, pk)

    try:
        data = json.loads(request.body)
        exam_id = data.get("exam_id")

        exam = get_object_or_404(
            scoped_by_organization(
                Exam.objects.filter(course=course),
                request,
            ),
            id=exam_id,
        )
        exam.course = None
        exam.save()

        return JsonResponse({"success": True})
    except Exception:
        logger.exception("Unexpected error in unlink_exam_from_course")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)
