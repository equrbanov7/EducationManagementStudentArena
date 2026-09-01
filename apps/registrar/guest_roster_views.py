"""«Alt qrupdan tələbə əlavə et» — HTTP səthi (lookup + əlavə + geri götürmə).

Servis məntiqi :mod:`apps.registrar.guest_roster`-dədir; burada yalnız icazə
qapısı, giriş datasının təmizlənməsi və JSON cavabları var. Bütün səthlər
tenant-scope-lu (``offering_or_404``) və fail-closed-dur: ``journal.roster``
icazəsi + struktur əhatəsi olmayan aktor 404 alır (mövcudluq sızmasın).

Lookup-lar `EMSSearchableSelect` (static/js/searchable_select.js) müqaviləsinə
uyğundur: ``{"results": [{"id", "text"}], "has_more": bool}`` + ``?q``/``?offset``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from . import guest_merge, guest_roster
from .journal_access import offering_or_404
from .models import AcademicStatus, Enrollment

_CTX = "registrar.guest_roster"
_PAGE_SIZE = 20
_MAX_PAGE = 50


def _uuid(value):
    """Səhv formatlı UUID sorğunu 500-ə çevirməsin — ``None`` qaytar."""
    import uuid as _uuid_module

    try:
        return _uuid_module.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _int(value):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _offering_for_roster(request, offering_id, *, require_open=True):
    """Açılışı yüklə + ``journal.roster`` əhatəsini yoxla (yoxdursa 404).

    ``require_open`` (lookup-lar üçün default) bağlanmış jurnalı və keçmiş
    dövrü də 404-ə çevirir — dondurulmuş jurnalın namizəd siyahısı ümumiyyətlə
    açılmasın. Əməllər (əlavə/çıxarma) ``require_open=False`` ilə yükləyir və
    :func:`guest_roster.roster_block_reason` mətnini 409 ilə qaytarır ki,
    köhnəlmiş modal istifadəçiyə səbəbi göstərsin — qapı yenə bağlıdır.
    """
    offering = offering_or_404(request, offering_id)
    if not guest_roster.can_manage_offering_roster(request.user, offering):
        raise Http404
    if require_open and not guest_roster.roster_is_open(offering):
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


def _page(queryset, offset, limit, serializer):
    """``limit + 1`` gətir → ``has_more`` (infinite scroll)."""
    window = list(queryset[offset : offset + limit + 1])
    return [serializer(row) for row in window[:limit]], len(window) > limit


# ── Lookup-lar ───────────────────────────────────────────────────────────────


@login_required
@require_GET
def guest_group_search(request, offering_id):
    """Aktorun əhatəsindəki AKADEMİK QRUPLAR (açılışın öz qrupu xaric)."""
    offering = _offering_for_roster(request, offering_id)
    query = (request.GET.get("q") or "").strip()
    groups = guest_roster.scoped_group_queryset(request.user, offering.organization)
    if offering.group_id is not None:
        groups = groups.exclude(pk=offering.group_id)
    if query:
        groups = groups.filter(name__icontains=query)
    groups = groups.order_by("name")
    offset, limit = _bounds(request)
    results, has_more = _page(groups, offset, limit, lambda unit: {"id": str(unit.id), "text": unit.name})
    return JsonResponse({"results": results, "has_more": has_more})


@login_required
@require_GET
def guest_student_search(request, offering_id):
    """Seçilmiş qrupun bu jurnala əlavə oluna bilən tələbələri (``?group=``)."""
    offering = _offering_for_roster(request, offering_id)
    group_id = _uuid((request.GET.get("group") or "").strip())
    if group_id is None:
        return JsonResponse({"results": [], "has_more": False})
    group = guest_roster.scoped_group_queryset(request.user, offering.organization).filter(pk=group_id).first()
    if group is None or (offering.group_id is not None and str(group.pk) == str(offering.group_id)):
        return JsonResponse({"results": [], "has_more": False})

    records = guest_roster.candidate_records(offering=offering, group=group)
    query = (request.GET.get("q") or "").strip()
    if query:
        from django.db.models import Q

        records = records.filter(
            Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
            | Q(student__username__icontains=query)
        )
    # Artıq jurnalda olanlar siyahıdan ÇIXARILMIR — görünür, amma `disabled`
    # bayrağı ilə seçilə bilmir və səbəbi yazılır (bax guest_roster.py izahı).
    already = guest_roster.enrolled_student_ids(offering)
    hint = pgettext(_CTX, "onsuz da bu jurnaldadır")
    offset, limit = _bounds(request)
    results, has_more = _page(
        records,
        offset,
        limit,
        lambda record: {
            "id": str(record.student_id),
            "text": guest_roster.student_label(record),
            "disabled": record.student_id in already,
            "hint": hint if record.student_id in already else "",
        },
    )
    return JsonResponse({"results": results, "has_more": has_more})


# ── Əməllər ──────────────────────────────────────────────────────────────────


def _resolve_student(request, offering, group, student_id):
    """Seçilmiş qrupun UYĞUN tələbəsi — namizəd siyahısı ilə EYNİ süzgəc.

    ``status=ENROLLED`` qəsdən buradadır: əvvəllər lookup ``ENROLLED`` süzürdü,
    mutasiya isə yalnız ``is_active`` — yəni axtarışda görünməyən tələbə birbaşa
    POST ilə jurnala salına bilirdi (eyni funksiyanın iki fərqli «uyğun tələbə»
    tərifi). Servis qatı (:func:`guest_roster._record_for`) eyni süzgəci təkrar
    edir və sətri kilidləyir (TOCTOU).
    """
    return (
        get_user_model()
        .objects.filter(
            pk=student_id,
            academic_records__organization=offering.organization,
            academic_records__group=group,
            academic_records__is_active=True,
            academic_records__status=AcademicStatus.ENROLLED,
        )
        .distinct()
        .first()
    )


@login_required
@require_GET
def guest_add_preview(request, offering_id):
    """Təsdiqdən ƏVVƏL nəticə: münaqişə varmı, hansı jurnaldan, nə qədər iş.

    Yazma əməli DEYİL — modal «bəli» düyməsini yalnız istifadəçi rəqəmləri
    gördükdən sonra açır (bax :func:`guest_merge.merge_preview`).
    """
    offering = _offering_for_roster(request, offering_id)
    group_id = _uuid((request.GET.get("group") or "").strip())
    student_id = _int((request.GET.get("student") or "").strip())
    if group_id is None or student_id is None:
        return _error(pgettext(_CTX, "Qrup və tələbə seçilməlidir."))
    group = guest_roster.scoped_group_queryset(request.user, offering.organization).filter(pk=group_id).first()
    if group is None:
        return _error(pgettext(_CTX, "Seçilmiş qrup sizin əhatənizdə deyil."), status=403)
    student = _resolve_student(request, offering, group, student_id)
    if student is None:
        return _error(pgettext(_CTX, "Tələbə seçilmiş qrupda tapılmadı."), status=404)
    preview = guest_merge.merge_preview(offering=offering, student=student)
    preview["ok"] = True
    return JsonResponse(preview)


def _payload(request):
    import json

    if (request.content_type or "").startswith("application/json"):
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:  # UnicodeDecodeError bunun alt sinfidir
            return {}
    return request.POST


def _field(data, key) -> str:
    """JSON və form-encoded girişi eyni cür təmizlə (tip-təhlükəsiz)."""
    return str(data.get(key) or "").strip()


def _flag(data, key) -> bool:
    """Bayraq: JSON ``true`` və form-encoded ``"on"/"1"/"true"`` eyni sayılır."""
    value = data.get(key)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "on", "yes")


@login_required
@require_POST
def guest_add(request, offering_id):
    """Tələbəni alt qrupdan bu jurnala əlavə et."""
    offering = _offering_for_roster(request, offering_id, require_open=False)
    blocked = guest_roster.roster_block_reason(offering)
    if blocked:
        return _error(blocked, status=409)
    data = _payload(request)
    student_id = _int(_field(data, "student"))
    group_id = _uuid(_field(data, "group"))
    if student_id is None or group_id is None:
        return _error(pgettext(_CTX, "Qrup və tələbə seçilməlidir."))

    group = guest_roster.scoped_group_queryset(request.user, offering.organization).filter(pk=group_id).first()
    if group is None:
        return _error(pgettext(_CTX, "Seçilmiş qrup sizin əhatənizdə deyil."), status=403)

    student = _resolve_student(request, offering, group, student_id)
    if student is None:
        return _error(pgettext(_CTX, "Tələbə seçilmiş qrupda tapılmadı."), status=404)

    release = _flag(data, "release_source")
    try:
        enrollment = guest_roster.add_guest_student(
            offering=offering,
            student=student,
            by_user=request.user,
            source_group=group,
            reason=_field(data, "reason"),
            release_source=release,
        )
    except ValidationError as exc:
        return _error("; ".join(exc.messages))

    return JsonResponse(
        {
            "ok": True,
            "enrollment_id": str(enrollment.pk),
            "student": (student.get_full_name() or "").strip() or student.username,
            "source_group": group.name,
            "released": release,
            "message": (
                pgettext(_CTX, "Tələbə öz jurnalından azad edilib bu jurnala köçürüldü.")
                if release
                else pgettext(_CTX, "Tələbə jurnala əlavə olundu.")
            ),
        }
    )


@login_required
@require_POST
def guest_remove(request, offering_id):
    """Alt qrupdan əlavə olunmuş tələbəni jurnaldan geri götür."""
    offering = _offering_for_roster(request, offering_id, require_open=False)
    blocked = guest_roster.roster_block_reason(offering)
    if blocked:
        return _error(blocked, status=409)
    data = _payload(request)
    enrollment_id = _uuid(_field(data, "enrollment"))
    enrollment = (
        None
        if enrollment_id is None
        else Enrollment.objects.filter(pk=enrollment_id, organization=offering.organization, offering=offering).first()
    )
    if enrollment is None:
        return _error(pgettext(_CTX, "Qeydiyyat tapılmadı."), status=404)
    try:
        guest_roster.remove_guest_student(
            offering=offering,
            enrollment=enrollment,
            by_user=request.user,
            reason=_field(data, "reason"),
        )
    except ValidationError as exc:
        return _error("; ".join(exc.messages))
    return JsonResponse({"ok": True, "message": pgettext(_CTX, "Tələbə jurnaldan çıxarıldı.")})


def _error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)
