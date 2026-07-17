"""İmtahan Mərkəzi — «imtahan şansı ver» (ikinci şans) bölməsinin view-u.

POST: seçilmiş final/midterm imtahanı üzrə qrupa və ya ad-ad tələbələrə
yenidən cəhd hüququ verir (``grant_second_chance``: grant + yeni PIN + final
biletinin sıfırlanması + audit). GET: profil SPA bölməsini render edir —
sidebar itmir (superadmin_exam_rooms / kollokvium_windows pattern-i).
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.models import Exam, StudentGroup
from apps.exams.public import SecondChanceError, grant_second_chance, is_exam_center_user
from apps.exams.services.access_policy import SECURE_EXAM_CATEGORIES
from apps.organizations.public import organization_user_queryset

from ._helpers import _append_query_params, _get_active_organization, _render_profile_section, _resolve_next_url

logger = logging.getLogger(__name__)

User = get_user_model()


def _parse_usernames(raw):
    """Vergül/yeni sətirlə ayrılmış istifadəçi adları/emailləri → təmiz siyahı."""
    tokens = (raw or "").replace(",", "\n").splitlines()
    return [t.strip() for t in tokens if t.strip()]


def _collect_students(organization, group, username_tokens, student_ids=()):
    """Qrup üzvləri + axtarışdan seçilmiş id-lər + ad-ad verilən istifadəçilər
    (hamısı org üzvlüyünə yoxlanır). Qaytarır: (tələbə siyahısı, tapılmayanlar).
    """
    students = {}
    if group is not None:
        for student in group.students.all():
            students[student.pk] = student

    ids = [i for i in student_ids if str(i).isdigit()]
    if ids:
        id_qs = organization_user_queryset(organization, queryset=User.objects.filter(pk__in=ids))
        for user in id_qs:
            students[user.pk] = user

    missing = []
    for token in username_tokens:
        user = User.objects.filter(username__iexact=token).first() or User.objects.filter(email__iexact=token).first()
        if user is None:
            missing.append(token)
            continue
        # Yalnız bu təşkilatın üzvləri — yad istifadəçiyə şans verilə bilməz.
        if not organization_user_queryset(organization, queryset=User.objects.filter(pk=user.pk)).exists():
            missing.append(token)
            continue
        students[user.pk] = user
    return list(students.values()), missing


@login_required
def exam_chance(request):
    """«İmtahan şansı ver» bölməsi (GET render + POST grant)."""
    if not is_exam_center_user(request.user):
        return HttpResponseForbidden(pgettext("accounts.exam_chance", "Bu bölmə yalnız imtahan mərkəzi üçündür."))

    fallback_next = _append_query_params(reverse("accounts:profile"), section="exam-chance")

    if request.method == "POST":
        next_url = _resolve_next_url(request, fallback_next)
        organization = _get_active_organization(request)
        if organization is None:
            messages.error(request, pgettext("accounts.exam_chance", "Aktiv təşkilat konteksti tapılmadı."))
            return redirect(next_url)

        exam_id = (request.POST.get("exam_id") or "").strip()
        if not exam_id.isdigit():
            messages.error(request, pgettext("accounts.exam_chance", "İmtahan seçin."))
            return redirect(next_url)
        exam = get_object_or_404(
            Exam,
            pk=int(exam_id),
            organization=organization,
            exam_type_extended__in=SECURE_EXAM_CATEGORIES,
            is_deleted=False,
        )

        group = None
        group_id = (request.POST.get("group_id") or "").strip()
        if group_id.isdigit():
            group = get_object_or_404(StudentGroup, pk=int(group_id), organization=organization)

        username_tokens = _parse_usernames(request.POST.get("usernames"))
        students, missing = _collect_students(
            organization, group, username_tokens, student_ids=request.POST.getlist("student_ids")
        )
        for token in missing[:5]:
            messages.warning(
                request,
                pgettext("accounts.exam_chance", "İstifadəçi tapılmadı və ya bu təşkilatda deyil: %(u)s")
                % {"u": token},
            )

        try:
            summary = grant_second_chance(
                exam=exam,
                students=students,
                extra=request.POST.get("extra_attempts", 1),
                granted_by=request.user,
                request=request,
            )
        except SecondChanceError as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        message = pgettext(
            "accounts.exam_chance",
            "«%(exam)s» üzrə %(n)s tələbəyə +%(extra)s cəhd verildi.",
        ) % {"exam": exam.title, "n": summary["students"], "extra": summary["extra"]}
        if summary["pins_reissued"]:
            message += " " + pgettext("accounts.exam_chance", "Yeni PIN-lər yaradıldı: %(n)s.") % {
                "n": summary["pins_reissued"]
            }
        if summary["tickets_reset"]:
            message += " " + pgettext("accounts.exam_chance", "Final girişi yenidən açıldı: %(n)s.") % {
                "n": summary["tickets_reset"]
            }
        messages.success(request, message)
        return redirect(_append_query_params(next_url, chance_exam=str(exam.pk)))

    return _render_profile_section(request, "exam-chance")


__all__ = ["exam_chance"]
