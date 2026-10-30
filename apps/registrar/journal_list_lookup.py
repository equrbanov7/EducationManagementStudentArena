"""Jurnal siyahısı (`/jurnal/`) geniş görünüşünün «MÜƏLLİM» axtarışlı seçicisi (2026-10-29).

``EMSSearchableSelect`` müqaviləsi: ``?q`` / ``?offset`` / ``?limit`` →
``{"results": [{"id", "text"}], "has_more": bool}``.

Niyə ayrıca endpoint: seçici əvvəl ``accounts:journal_teacher_search``-ə gedirdi — o,
«Akademik qeydlər» açarının (``student.records_view``) əhatəsindən oxuyur. Jurnal siyahısı isə
``journal.correct`` / ``journal.roster`` / ``journal.view`` əhatəsi ilə qurulur. Açarı olmayan
(və ya əhatəsi kafedra olan) aktor siyahıda jurnalları görür, seçicidə isə HEÇ BİR müəllim
tapmırdı. Burada namizədlər məhz siyahının öz əhatəsindən gəlir
(:func:`apps.registrar.journal_list_scope.journal_list_base`), yəni seçilən hər müəllim
siyahını süzür (boş nəticə verən «xəyali» variant yoxdur).

Axtarış ``core.search_text.tolerant_q`` ilə: tokenlər arası VƏ, hər token ad / soyad /
istifadəçi adında (registrsiz, az/ing hərf qatlaması: ``i/ı/İ/I``, ``ə/e/a``, ``ş/s``, ``ç/c``,
``ğ/g``, ``ö/o``, ``ü/u``) — «fir», «aida», «İSMA», «Firuzə Əli», «Əliyeva Firuzə» hamısı tapılır.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.search_text import tolerant_q

from .journal_list_scope import journal_list_base

_PAGE_SIZE = 10
_MAX_PAGE = 50
_NAME_FIELDS = ("first_name", "last_name", "username")


def _bounds(request):
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = max(1, min(int(request.GET.get("limit", _PAGE_SIZE)), _MAX_PAGE))
    except (TypeError, ValueError):
        limit = _PAGE_SIZE
    return offset, limit


@never_cache
@login_required
@require_GET
def teacher_search(request):
    """Siyahının görünüş əhatəsindəki açılışların müəllimləri (yalnız geniş görünüşdə)."""
    empty = JsonResponse({"results": [], "has_more": False})
    if getattr(request, "organization", None) is None:
        return empty
    base_qs, is_broad = journal_list_base(request.user, request)
    if not is_broad:
        return empty  # adi müəllimin seçicisi yoxdur — öz adı statik göstərilir
    from .journal_teacher_filters import teachers_for

    users = teachers_for(base_qs)
    search = tolerant_q(request.GET.get("q") or "", _NAME_FIELDS)
    if search is not None:
        users = users.filter(search)
    users = users.order_by("last_name", "first_name", "username", "pk")
    offset, limit = _bounds(request)
    window = list(users[offset : offset + limit + 1])
    results = [{"id": str(u.pk), "text": (u.get_full_name() or "").strip() or u.username} for u in window[:limit]]
    return JsonResponse({"results": results, "has_more": len(window) > limit})


__all__ = ["teacher_search"]
