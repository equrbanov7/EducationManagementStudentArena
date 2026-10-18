"""İmtahan Mərkəzi — «imtahan şansı ver» (ikinci şans) bölməsinin view-u.

POST: seçilmiş final/midterm imtahanı üzrə KONKRET tələbələrə yenidən cəhd hüququ verir
(``grant_second_chance``: grant + yeni PIN + final biletinin sıfırlanması + audit).
2026-10-18 (sahib): şans RƏSMİDİR — səbəb növü məcburidir (25% müraciəti / universitet güzəşti /
texniki problem / apellyasiya qərarı / digər), əsas (əmr №, tarix, qeyd) səbəbə görə yoxlanır və hər
tələbə üçün append-only qeyd yazılır (``registrar.retake_chance``); «25% müraciəti» yalnız ödənişi
təsdiqlənmiş + buraxılmış müraciəti olan tələbəyə verilir və müraciəti ``exam_granted`` edir. GET: profil SPA bölməsini render edir —
sidebar itmir (superadmin_exam_rooms / kollokvium_windows pattern-i).
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.services.exam_center_decide import can_exam_center_decide
from apps.exams.models import Exam
from apps.exams.public import SECURE_EXAM_CATEGORIES, SecondChanceError, grant_second_chance, is_exam_center_user
from apps.organizations.public import organization_user_queryset
from apps.registrar.public import retake_chance

from ._helpers import _append_query_params, _get_active_organization, _render_profile_section, _resolve_next_url

logger = logging.getLogger(__name__)

User = get_user_model()


def _collect_students(organization, student_ids=()):
    """Axtarışdan seçilmiş KONKRET tələbələr (hamısı org üzvlüyünə yoxlanır).

    2026-10-18 (sahib): şans yalnız konkret tələbə(lər)ə verilir — bütöv qrupa / ad siyahısına toplu şans
    forması götürüldü (hər tələbə axtarışdan seçilir və səbəb rəsmi qeydə düşür).
    """
    ids = [i for i in student_ids if str(i).isdigit()]
    if not ids:
        return []
    return list(organization_user_queryset(organization, queryset=User.objects.filter(pk__in=ids)).order_by("pk"))


def _exam_info(exam) -> dict:
    """Registrar qeydi üçün imtahan snapshot-u (registrar exams-ı import etmir)."""
    return {
        "id": exam.pk,
        "title": exam.title,
        "exam_type": exam.exam_type or "",
        "category": exam.exam_type_extended or "",
        "subject_id": exam.subject_id,
    }


@login_required
def exam_chance(request):
    """«İmtahan şansı ver» bölməsi (GET render + POST grant)."""
    if not is_exam_center_user(request.user):
        return HttpResponseForbidden(pgettext("accounts.exam_chance", "Bu bölmə yalnız imtahan mərkəzi üçündür."))

    fallback_next = _append_query_params(reverse("accounts:profile"), section="exam-chance")

    if request.method == "POST":
        # 2026-10-13 (rol auditi B1): əvvəl rol adı (`is_exam_center_user`) kifayət edirdi — işçi və RİM
        # əməkdaşı da yeni PIN + final biletini sıfırlayan şans verirdi. İndi bölməni GÖRÜRLƏR (siyahı,
        # son şanslar), şans vermək `exam_center.decide` açarı ilədir (şablonda rəhbərdə).
        if not can_exam_center_decide(request):
            return HttpResponseForbidden(
                pgettext("accounts.exam_chance", "İmtahan şansı vermək üçün qərar səlahiyyətiniz yoxdur.")
            )
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

        students = _collect_students(organization, request.POST.getlist("student_ids"))
        try:
            cleaned = retake_chance.validate(
                organization=organization,
                exam=_exam_info(exam),
                students=students,
                reason=(request.POST.get("reason") or "").strip(),
                reference_number=request.POST.get("reference_number"),
                reference_date=request.POST.get("reference_date"),
                note=request.POST.get("note"),
            )
            # Şans + rəsmi qeyd (səbəb, əsas, müraciət keçidi) BİR tranzaksiyada — biri alınmasa heç biri yazılmır.
            with transaction.atomic():
                summary = grant_second_chance(
                    exam=exam,
                    students=students,
                    extra=request.POST.get("extra_attempts", 1),
                    granted_by=request.user,
                    request=request,
                )
                retake_chance.record(
                    organization=organization,
                    exam=_exam_info(exam),
                    students=students,
                    cleaned=cleaned,
                    extra=summary["extra"],
                    actor=request.user,
                    request=request,
                )
        except ValidationError as exc:
            messages.error(request, "; ".join(str(m) for m in exc.messages))
            return redirect(next_url)
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
