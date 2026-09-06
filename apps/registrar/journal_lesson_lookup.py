"""Dərs modalının (``_jd_lesson_modal.html``) axtarışlı/lazy seçiciləri üçün
AJAX lookup-ları (QA 2026-09-05 P3-13).

Əvvəllər müəllim (təşkilatda 554-ə qədər namizəd) və otaq (159-a qədər) siyahısı
HƏR jurnal səhifəsi yüklənməsində TAM HTML/JSON kimi modala bişirilirdi —
modal heç açılmasa belə. Burada:

* :func:`lesson_teacher_search` — ``EMSSearchableSelect`` müqaviləsinə uyğun
  (``{"results": [{"id","text"}], "has_more": bool}`` + ``?q``/``?offset``/
  ``?limit``), server-side axtarış + səhifələmə. ``?resolve=<id>`` — redaktə
  zamanı ARTIQ bilinən id-nin ETIKETINI tapır (hidden input dəyəri
  ``journal_grid.js``-dən onsuz da doğrudur, bu yalnız çipin adını tamamlayır).
* :func:`lesson_room_data` — korpus→otaq kaskadının (``journal_lesson_room.js``)
  TAM otaq siyahısı, modal İLK dəfə açılanda gətirilir (siyahı kiçik olduğundan
  axtarış/səhifələmə yoxdur, bax ``lesson_rooms.lesson_room_choices``).

Giriş qapısı hər ikisində jurnal SƏHİFƏSİ (``views.journal_detail`` GET) ilə
EYNİDİR — dərs modalı elə həmin səhifənin içindədir: redaktor / korrektor /
siyahı idarəçisi / köhnə müəllim (yalnız-oxu) buraya çata bilər, başqası yox."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET

from . import journal_extras, lesson_rooms
from .journal_access import can_edit_journal, can_observe_journal, offering_or_404

_PAGE_SIZE = 20
_MAX_PAGE = 50


def _offering_for_lesson_modal(request, offering_id):
    """Açılışı yüklə + jurnal səhifəsi ilə EYNİ giriş qapısı (bax
    ``views.journal_detail``): birbaşa redaktor, korrektor (İKT/admin),
    siyahı idarəçisi (koordinator/dekanlıq) və ya təhvil vermiş köhnə müəllim
    (yalnız-oxu). Heç biri deyilsə 404 — mövcudluq sızmasın."""
    offering = offering_or_404(request, offering_id)
    from . import corrections as corrections_service
    from . import guest_roster

    allowed = (
        can_edit_journal(request.user, offering)
        or corrections_service.can_correct_journal(request)
        or guest_roster.can_manage_offering_roster(request.user, offering)
        or can_observe_journal(request.user, offering)
    )
    if not allowed:
        raise Http404
    return offering


def _bounds(request):
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.GET.get("limit", _PAGE_SIZE))
    except (TypeError, ValueError):
        limit = _PAGE_SIZE
    return offset, max(1, min(limit, _MAX_PAGE))


@login_required
@require_GET
def lesson_teacher_search(request, offering_id):
    """ "DƏRSİN MÜƏLLİMİ" axtarışı — ``journal_extras.lesson_teacher_choices``
    üzərində server-side axtarış + səhifələmə (namizəd dəsti onsuz da bir
    yüngül sorğudur, dəyişən yalnız BROWSER-ə göndərilən HİSSƏDİR)."""
    offering = _offering_for_lesson_modal(request, offering_id)
    candidates = journal_extras.lesson_teacher_choices(offering)

    resolve_id = (request.GET.get("resolve") or "").strip()
    if resolve_id:
        match = next((c for c in candidates if c["id"] == resolve_id), None)
        results = [{"id": match["id"], "text": match["name"]}] if match else []
        return JsonResponse({"results": results, "has_more": False})

    query = (request.GET.get("q") or "").strip().lower()
    if query:
        candidates = [c for c in candidates if query in c["name"].lower()]
    offset, limit = _bounds(request)
    window = candidates[offset : offset + limit + 1]
    results = [{"id": c["id"], "text": c["name"]} for c in window[:limit]]
    return JsonResponse({"results": results, "has_more": len(window) > limit})


@login_required
@require_GET
def lesson_room_data(request, offering_id):
    """Korpus→otaq kaskadı üçün TAM otaq siyahısı — modal İLK dəfə açılanda
    (bax ``journal_lesson_room.js``). Siyahı kiçik olduğundan (təşkilatda
    onlarla/yüzlərlə otaq) axtarış/səhifələmə yoxdur — köhnə client-side
    süzgəc məntiqi olduğu kimi qalır, yalnız data mənbəyi dəyişir."""
    offering = _offering_for_lesson_modal(request, offering_id)
    return JsonResponse(lesson_rooms.lesson_room_choices(offering), safe=False)
