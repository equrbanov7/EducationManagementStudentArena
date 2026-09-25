"""
Apellyasiya oxuma (read) selektorları.

Eyni sorğu məntiqi həm standalone ``appeals.views.my_appeals``, həm də profil
dashboard bölməsində (``accounts.views.profile.main``) istifadə olunur — DRY.
Tenant/sahiblik scope-u həmişə qoruyur: yalnız ``student``-in öz apellyasiyaları.
"""

from __future__ import annotations

from django.core.paginator import Paginator

from core.search_text import tolerant_q

from .constants import APPEAL_STATUS_VALUES
from .models import Appeal

MY_APPEALS_PAGE_SIZE = 12


def student_appeals_queryset(user):
    """Verilmiş istifadəçinin öz apellyasiyaları (optimallaşdırılmış)."""
    return (
        Appeal.objects.filter(student=user)
        .select_related("exam", "attempt", "reviewed_by")
        .prefetch_related("items")
        .order_by("-created_at")
    )


def filter_student_appeals(queryset, *, status="", exam_slug="", search=""):
    """Status / imtahan / mətn üzrə təhlükəsiz filtr (yalnız icazəli dəyərlər)."""
    status = (status or "").strip()
    if status in APPEAL_STATUS_VALUES:
        queryset = queryset.filter(status=status)

    exam_slug = (exam_slug or "").strip()
    if exam_slug:
        queryset = queryset.filter(exam__slug=exam_slug)

    # İmtahan adı — az/ing hərfə dözümlü, tokenli (sahib 2026-09-26).
    search_q = tolerant_q(search, ("exam__title",))
    if search_q is not None:
        queryset = queryset.filter(search_q)

    return queryset


def paginate_student_appeals(queryset, page_number, *, per_page=MY_APPEALS_PAGE_SIZE):
    """Səhifələmə — ortaq səhifə ölçüsü ilə."""
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(page_number)


__all__ = [
    "MY_APPEALS_PAGE_SIZE",
    "student_appeals_queryset",
    "filter_student_appeals",
    "paginate_student_appeals",
]
