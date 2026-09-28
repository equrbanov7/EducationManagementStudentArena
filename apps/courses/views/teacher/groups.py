"""
courses/views/teacher/groups.py — kursa qrup əlavə etmə / çıxarma (2026-09-28).

«Qrup əlavə et» əvvəl köhnə ``exams.StudentGroup`` cədvəlini oxuyurdu — real bazada
boş idi, modal heç vaxt qrup göstərmirdi. İndi mənbə reyestrdir
(``apps.registrar.public.course_groups``): müəllimin cari dövrdə dərs dediyi qruplar
(«Mənim qruplarım») + təşkilatın digər aktiv qrupları (axtarışla). Kurs üzvlüyünün
``group_name`` sahəsinə reyestr qrupunun ADI yazılır — tapşırıq/lab/layihə
modallarının qrup seçiciləri məhz bu sahəni oxuyur.

Contains:
- AvailableGroupsView    GET  JSON — seçici mənbəyi
- AddMembersBulkView     POST — seçilmiş qrupların tələbələrini kursa əlavə edir
- DeleteGroupFromCourseView POST — qrupu (group_name üzrə) kursdan çıxarır
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.translation import pgettext, pgettext_lazy
from django.views.generic import View

from apps.courses.models import CourseMembership
from apps.registrar.public import course_groups
from core.helpers import _safe_same_origin_redirect_path
from core.permissions import request_has_permission
from core.tenancy import get_request_organization

from ..shared._helpers import _get_owner_course_or_404, _owner_courses_queryset

User = get_user_model()
logger = logging.getLogger(__name__)

_CTX = "courses.view.message"

#: Bir sorğuda əlavə olunan qrupların tavanı (audit 2026-09-28 DB-04): bütün
#: təşkilat qruplarını bir tranzaksiyada əlavə etmək dəqiqələrlə kilid saxlayırdı.
MAX_GROUPS_PER_REQUEST = 20


def _is_ajax(request) -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _course_group_names(course) -> set:
    return {
        (name or "").strip().casefold()
        for name in course.memberships.filter(role="student").values_list("group_name", flat=True)
        if (name or "").strip()
    }


class _OwnerCourseMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return _owner_courses_queryset(self.request).filter(id=self.kwargs.get("course_id")).exists()

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        return JsonResponse({"success": False, "error": pgettext(_CTX, "no_permission")}, status=403)


class AvailableGroupsView(_OwnerCourseMixin, View):
    """Qrup seçicisinin mənbəyi.

    GET ``q`` (istəyə bağlı). Cavab: ``{"success", "mine": [...], "others": [...], "q"}``.
    ``mine`` — müəllimin cari dövrdə dərs dediyi qruplar (fənn adları ilə); ``others`` —
    yalnız ``q`` verildikdə, təşkilatın digər aktiv qrupları. Hər sətirdə ``in_course``
    — qrup artıq kursdadırsa (adı üzrə) ``true``.
    """

    def get(self, request, *args, **kwargs):
        course = _get_owner_course_or_404(request, kwargs.get("course_id"))
        organization = get_request_organization(request) or course.organization
        q = (request.GET.get("q") or "").strip()[:80]
        in_course = _course_group_names(course)

        mine = course_groups.taught_group_rows(organization=organization, teacher=request.user)
        others = []
        if q:
            others = course_groups.search_group_rows(
                organization=organization,
                query=q,
                exclude_ids=[row["id"] for row in mine],
            )
        for row in (*mine, *others):
            row["in_course"] = row["name"].strip().casefold() in in_course
        return JsonResponse({"success": True, "mine": mine, "others": others, "q": q})


class AddMembersBulkView(_OwnerCourseMixin, View):
    """Seçilmiş reyestr qruplarının aktiv tələbələrini kursa əlavə edir (atomik)."""

    def post(self, request, *args, **kwargs):
        if not request_has_permission(request, "course.edit"):
            return JsonResponse({"success": False, "error": pgettext(_CTX, "no_permission")}, status=403)

        from apps.notifications.public import notify_course_membership_assigned

        course = _get_owner_course_or_404(request, kwargs.get("course_id"))
        organization = get_request_organization(request) or course.organization
        raw_ids = request.POST.getlist("group_ids")
        if len(raw_ids) > MAX_GROUPS_PER_REQUEST:
            return JsonResponse({"success": False, "error": pgettext(_CTX, "too_many_groups")}, status=400)
        groups = course_groups.resolve_groups(organization=organization, group_ids=raw_ids)
        if not groups:
            return JsonResponse({"success": False, "error": pgettext(_CTX, "no_group_selected")}, status=400)

        student_ids_by_group = course_groups.group_student_ids(
            organization=organization, groups=groups, teacher=request.user
        )
        allowed_users = User.objects.filter(is_active=True)
        if organization is not None:
            allowed_users = allowed_users.filter(profile__organization=organization)

        added_count = 0
        try:
            # Audit 2026-09-13 backend F-07: toplu əlavə + bildirişlər bir tranzaksiyada —
            # ortada sınsa yarım qrup qalmasın (istisna `except`-ə çıxır → 500).
            with transaction.atomic():
                for group in groups:
                    ids = student_ids_by_group.get(group.pk) or []
                    for student in allowed_users.filter(pk__in=ids).order_by("pk"):
                        membership, created = CourseMembership.objects.get_or_create(
                            course=course,
                            user=student,
                            defaults={"role": "student", "group_name": group.name},
                        )
                        previous_group_name = membership.group_name or ""
                        if created:
                            added_count += 1
                        elif membership.role == "student" and not previous_group_name.strip():
                            membership.group_name = group.name
                            membership.save(update_fields=["group_name"])
                        else:
                            continue
                        notify_course_membership_assigned(
                            membership=membership,
                            created=created,
                            previous_group_name=previous_group_name,
                        )
        except Exception:
            logger.exception("Unexpected error in AddMembersBulkView")
            return JsonResponse({"success": False, "error": pgettext(_CTX, "unexpected_error")}, status=500)

        return JsonResponse(
            {
                "success": True,
                "message": pgettext(_CTX, "students_added_to_course").format(count=added_count),
                "added_count": added_count,
                "groups": [group.name for group in groups],
            }
        )


class DeleteGroupFromCourseView(_OwnerCourseMixin, View):
    """Kursdan müəyyən qrup adını daşıyan bütün tələbə üzvlüklərini silir."""

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        if not request_has_permission(request, "course.edit"):
            if _is_ajax(request):
                return JsonResponse({"success": False, "error": pgettext(_CTX, "no_permission")}, status=403)
            raise PermissionDenied(pgettext("courses.view.permission", "no_permission_edit_course"))

        course = _get_owner_course_or_404(request, course_id)
        group_name = (request.POST.get("group_name") or "").strip()
        if not group_name:
            if _is_ajax(request):
                return JsonResponse({"success": False, "error": pgettext(_CTX, "group_name_missing")}, status=400)
            messages.error(request, pgettext_lazy(_CTX, "group_name_missing"))
            return redirect("courses:course_members", course_id=course_id)

        deleted_count, _ = CourseMembership.objects.filter(
            course=course, role="student", group_name=group_name
        ).delete()
        message = pgettext(_CTX, "group_removed_from_course").format(group_name=group_name, count=deleted_count)
        if _is_ajax(request):
            return JsonResponse({"success": True, "message": message, "deleted_count": deleted_count})

        messages.success(request, message)
        next_url = _safe_same_origin_redirect_path(request, request.POST.get("next"))
        if next_url:
            return redirect(next_url)
        return redirect("courses:course_members", course_id=course_id)
