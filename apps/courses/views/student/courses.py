"""Courses — tələbə səthi: "Kurslarım" siyahısı (F3 rol-skeleti, 2026-07-02)."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from apps.courses.models import Course, CourseMembership
from core.helpers import _tenant_scoped_courses


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
            m.course_id: m for m in CourseMembership.objects.filter(course_id__in=course_ids, user=user, role="student")
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
