"""Profil "my-exams" bölməsinin «Midterm / Final» (imtahan mərkəzi) alt-görünüşü.

Sahib (2026-10-26): «Midterm ya da final imtahanı yaradılıbsa onu imtahan mərkəzi işçisi də,
imtahan mərkəzi rəhbəri də görsün — bu, profildən asılı olmasın. Çünki sonra nə isə etmək
lazım gələndə başqa profil axtarılır.» Əvvəl «İmtahanlarım» yalnız müəllifin öz imtahanlarını
göstərirdi; mərkəzin bir hesabının (və ya RİM-in) yaratdığı midterm/final digər mərkəz
əməkdaşına görünmürdü.

İndi imtahan mərkəzi üzvü üçün bölmədə üçüncü tab var: ``?section=my-exams&exam_scope=center``
— təşkilatın BÜTÜN midterm/final imtahanları (yaradandan asılı olmayaraq), kartda yaradanın
adı ilə. «İmtahanlarım» tabı əvvəlki kimi yalnız öz imtahanlarıdır (sidebar sayğacları və
yoxlama nişanları dəyişmir). Detal/redaktə/nəticə səhifələri eyni qaydanı
``apps.exams.services.access_policy.manageable_exams_q`` ilə tətbiq edir.
"""

from __future__ import annotations

from django.urls import reverse

from apps.accounts.views._helpers.tenant import _tenant_scoped_exams

#: Alt-görünüş sorğu parametri (`?section=my-exams&exam_scope=center`).
CENTER_SCOPE_PARAM = "exam_scope"
CENTER_SCOPE_VALUE = "center"


def center_tab_enabled(request) -> bool:
    """İstifadəçi aktiv təşkilatda imtahan mərkəzi üzvüdürmü (tab yalnız onda görünür)."""
    from apps.exams.public import is_exam_center_member

    return is_exam_center_member(request.user, getattr(request.user, "active_organization", None))


def is_center_scope(request) -> bool:
    """Sorğu «Midterm / Final» alt-görünüşünü istəyirmi (və istifadəçiyə icazə varmı)."""
    requested = (request.GET.get(CENTER_SCOPE_PARAM, "") or "").strip() == CENTER_SCOPE_VALUE
    return requested and center_tab_enabled(request)


def center_view_url() -> str:
    return f"{reverse('accounts:profile')}?section=my-exams&{CENTER_SCOPE_PARAM}={CENTER_SCOPE_VALUE}"


def center_exams_queryset(request):
    """Təşkilatın bütün midterm/final imtahanları (silinməmiş, tenant-scoped, yaradanla)."""
    from apps.exams.models import Exam
    from apps.exams.public import center_overseen_exams_q

    organization = getattr(request.user, "active_organization", None)
    return _tenant_scoped_exams(request, Exam.objects.filter(center_overseen_exams_q(organization))).order_by(
        "-created_at"
    )


def build_center_tab_context(request, *, is_open: bool, count: int | None = None) -> dict:
    """Tab üçün context (`my_exams_dashboard.center` altında). Mərkəz üzvü deyilsə tab yoxdur.

    Sayğac yalnız mərkəz üzvü üçün hesablanır (1 COUNT); tab açıqdırsa siyahının öz
    sayğacı ötürülür və əlavə sorğu olmur.
    """
    if not center_tab_enabled(request):
        return {"enabled": False, "is_open": False, "count": 0, "url": ""}
    if count is None:
        count = center_exams_queryset(request).count()
    return {"enabled": True, "is_open": is_open, "count": count, "url": center_view_url()}
