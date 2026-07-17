"""Profil "exam-chance" bölməsi — İmtahan Mərkəzi «imtahan şansı ver».

``section`` dict-ini YERİNDƏ mutasiya edir (kollokvium_windows pattern-i).
İmtahan Mərkəzi aktiv təşkilatının final/midterm imtahanları üzrə seçilmiş
tələbə(lər)ə və ya bütöv qrupa yenidən cəhd (ikinci şans) verir: grant +
yeni fərdi PIN + final biletinin sıfırlanması (hamısı auditə düşür).
"""

from django.urls import reverse

from apps.accounts.views._helpers.formatting import _append_query_params

RECENT_GRANT_LIMIT = 15


def build_exam_chance_section(request, section, *, active_organization, allowed_sections, active_section):
    if "exam-chance" not in allowed_sections or active_section != "exam-chance":
        return

    from apps.exams.models import Exam, StudentExamAttemptGrant, StudentGroup
    from apps.exams.services.access_policy import SECURE_EXAM_CATEGORIES

    organization = active_organization
    section["selected_org"] = organization
    section["post_next_url"] = _append_query_params(reverse("accounts:profile"), section="exam-chance")
    if organization is None:
        return

    exams = list(
        Exam.objects.filter(
            organization=organization,
            exam_type_extended__in=sorted(SECURE_EXAM_CATEGORIES),
            is_deleted=False,
            is_archived=False,
        )
        .only("id", "title", "exam_type_extended", "start_datetime", "max_attempts_per_user")
        .order_by("-start_datetime", "-id")[:300]
    )
    section["exams"] = exams
    section["groups"] = list(StudentGroup.objects.filter(organization=organization).only("id", "name").order_by("name"))
    # Son verilən şanslar — «loglara düşsün» tələbinin görünən üzü (tam tarixçə
    # audit jurnalındadır; bu, mərkəz üçün sürətli baxışdır).
    section["recent_grants"] = list(
        StudentExamAttemptGrant.objects.filter(exam__organization=organization)
        .select_related("exam", "student", "granted_by")
        .order_by("-updated_at")[:RECENT_GRANT_LIMIT]
    )
    selected_exam = (request.GET.get("chance_exam") or "").strip()
    section["selected_exam_id"] = selected_exam if selected_exam.isdigit() else ""
