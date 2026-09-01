"""Fənn təhvili bölməsinin OXU endpoint-ləri (JSON).

Dörd endpoint, dörd fərqli yenilənmə tezliyi ilə — ``people`` kataloqu ilə eyni
səbəbdən ayrılıb (filtr açılışları hər səhifə keçidində təkrar sorğulanmasın):

* ``handover_teachers``   — müəllim seçicisi (axtarışlı, səhifəli, iki rejim:
  ``source`` = əhatədə fənni olanlar, ``target`` = bal yaza bilən aktiv üzvlər);
* ``handover_offerings``  — seçilmiş müəllimin açılışları + blokerlər + təsir sayları;
* ``handover_options``    — semestr/fakültə/kafedra süzgəcləri (nadir dəyişir);
* ``handover_history``    — əhatədəki təhvil tarixçəsi (geri qaytarma düyməsi ilə).

Hamısı fail-closed: icazəsi olmayan aktor ``has_access: false`` və boş data alır.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.registrar import handover as handover_read

from .labels import REVERT, blocker_labels
from .policy import offering_row, period_label, person_name, resolve_actor

#: Cədvəl səhifəsinin defolt/maksimum ölçüsü.
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

_EMPTY = {
    "has_access": False,
    "results": [],
    "page": 1,
    "num_pages": 1,
    "total": 0,
    "has_next": False,
    "has_previous": False,
}


def _int(value, default, *, minimum=1, maximum=None):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if number < minimum:
        return default
    if maximum is not None and number > maximum:
        return maximum
    return number


def _page(queryset, request, *, default_size=DEFAULT_PAGE_SIZE):
    size = _int(request.GET.get("page_size"), default_size, maximum=MAX_PAGE_SIZE)
    paginator = Paginator(queryset, size)
    page = paginator.get_page(_int(request.GET.get("page"), 1))
    return page, paginator


def _paged_payload(page, paginator, results) -> dict:
    return {
        "has_access": True,
        "results": results,
        "page": page.number,
        "num_pages": paginator.num_pages,
        "total": paginator.count,
        "has_next": page.has_next(),
        "has_previous": page.has_previous(),
    }


# ── Müəllim seçicisi ─────────────────────────────────────────────────────────


@never_cache
@login_required
@require_GET
def handover_teachers(request):
    """Axtarışlı + LAZY səhifəli müəllim seçicisi.

    Cavab müqaviləsi QƏSDƏN cədvəl endpoint-lərindən FƏRQLİDİR: burada
    ``EMSSearchableSelect`` (static/js/searchable_select.js) oxuyur, o isə
    ``?q=&limit=&offset=`` göndərib ``{results: [{id, text, hint}], has_more}``
    gözləyir. Öz seçicimizi yazmaq əvəzinə mövcud komponent təkrar işlədilir —
    debounce, infinite-scroll, kəsilmə-önləyən yerləşdirmə və skeleton onsuz da
    orada həll olunub.

    ``?role=source`` — aktorun ƏHATƏSİNDƏ ən azı bir açılışı olan müəllimlər
    («kimdən» seçicisi). Fərq vacibdir: dekan yalnız öz fakültəsində dərs deyən
    adamı seçə bilməlidir, bütün universiteti yox.

    ``?role=target`` — bal yaza bilən (``grade.input``) AKTİV üzvlər («kimə»).
    Hədəf siyahısı QƏSDƏN əhatə ilə daraldılmır: kafedra müdiri fənni başqa
    kafedradan gələn müəllimə də verə bilməlidir (ortaq fənlər real haldır).
    """
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse({"has_access": False, "results": [], "has_more": False, "total": 0})

    search = (request.GET.get("q") or "").strip()
    role = (request.GET.get("role") or "target").strip()
    exclude = (request.GET.get("exclude") or "").strip()

    if role == "source":
        queryset = _source_teachers(actor, search)
    else:
        queryset = handover_read.target_queryset(
            actor.organization, search=search, exclude_ids=[exclude] if exclude else ()
        )

    limit = _int(request.GET.get("limit"), 10, maximum=MAX_PAGE_SIZE)
    offset = _int(request.GET.get("offset"), 0, minimum=0)
    total = queryset.count()
    rows = list(queryset[offset : offset + limit])
    return _json(
        {
            "has_access": True,
            "results": [
                {"id": str(user.pk), "text": person_name(user), "hint": _teacher_subtitle(user)} for user in rows
            ],
            "has_more": offset + len(rows) < total,
            "total": total,
        }
    )


def _source_teachers(actor, search):
    """Aktorun əhatəsindəki açılışların CARİ müəllimləri (təkrarsız, axtarışlı)."""
    from django.contrib.auth import get_user_model

    instructor_ids = (
        handover_read.scoped_offerings(actor.user, actor.organization)
        .filter(instructor_id__isnull=False)
        .values_list("instructor_id", flat=True)
        .distinct()
    )
    queryset = get_user_model().objects.filter(pk__in=list(instructor_ids))
    term = (search or "").strip()
    if term:
        queryset = queryset.filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(username__icontains=term)
            | Q(email__icontains=term)
        )
    return queryset.order_by("last_name", "first_name", "username")


def _teacher_subtitle(user) -> str:
    """Seçicidə adın altındakı ikinci sətir — eyniadlı müəllimləri ayırır."""
    return str(getattr(user, "username", "") or "")


# ── Açılış cədvəli ───────────────────────────────────────────────────────────


@never_cache
@login_required
@require_GET
def handover_offerings(request):
    """Seçilmiş müəllimin (və ya bütün əhatənin) açılışları + blokerlər."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse(_EMPTY)

    queryset = handover_read.scoped_offerings(actor.user, actor.organization)
    queryset = _apply_filters(queryset, request, actor)
    queryset = (
        queryset.select_related("subject", "period", "group", "instructor")
        .annotate(
            student_count=Count("enrollments", filter=Q(enrollments__status="enrolled"), distinct=True),
            lesson_count=Count("lessons", distinct=True),
        )
        .order_by("-period__start_date", "subject__code", "group__name")
    )

    page, paginator = _page(queryset, request)
    offerings = list(page.object_list)
    payload = _paged_payload(page, paginator, _serialize_offerings(offerings, actor))
    payload["capabilities"] = {"can_reassign": True}
    return _json(payload)


def _apply_filters(queryset, request, actor):
    teacher = (request.GET.get("teacher") or "").strip()
    if teacher == "__none__":
        queryset = queryset.filter(instructor__isnull=True)
    elif teacher:
        queryset = queryset.filter(instructor_id=teacher)

    period = (request.GET.get("period") or "").strip()
    if period:
        queryset = queryset.filter(period_id=period)

    for param, field in (("faculty", "group"), ("kafedra", "group")):
        unit_id = (request.GET.get(param) or "").strip()
        if unit_id:
            queryset = queryset.filter(**{f"{field}__in": _unit_subtree_ids(actor.organization, unit_id)})

    term = (request.GET.get("q") or "").strip()
    if term:
        queryset = queryset.filter(
            Q(subject__name__icontains=term) | Q(subject__code__icontains=term) | Q(group__name__icontains=term)
        )

    if (request.GET.get("scope") or "").strip() == "open":
        # «Yalnız təhvil oluna bilənlər» — cari dövr süzgəci (ucuz ön-daraltma;
        # dəqiq bloker hesablaması onsuz da sətir səviyyəsində aparılır).
        queryset = queryset.filter(period__is_current=True, is_active=True)
    return queryset


def _unit_subtree_ids(organization, unit_id):
    """Fakültə/kafedra alt-ağacındakı OrgUnit id-ləri (tanınmayan id → boş)."""
    from django.apps import apps as django_apps

    org_unit = django_apps.get_model("organizations", "OrgUnit")
    unit = org_unit.objects.filter(organization=organization, pk=unit_id).only("id", "path").first()
    if unit is None:
        return []
    condition = Q(pk=unit.pk)
    if unit.path:
        condition |= Q(path__startswith=f"{unit.path}/")
    return list(org_unit.objects.filter(organization=organization).filter(condition).values_list("pk", flat=True))


def _serialize_offerings(offerings, actor):
    """Sətirləri N+1-siz serializasiya edir (bloker + sayğaclar toplu hesablanır)."""
    from django.utils import timezone

    if not offerings:
        return []
    ids = [offering.pk for offering in offerings]
    closed_ids = handover_read.closed_offering_ids(ids)
    today = timezone.localdate()
    labels = blocker_labels()
    counts = _impact_counts(offerings, ids)

    rows = []
    for offering in offerings:
        codes = handover_read.blockers(
            offering,
            actor=actor.user,
            organization=actor.organization,
            closed_ids=closed_ids,
            today=today,
        )
        rows.append(offering_row(offering, blocker_codes=codes, blocker_labels=labels, counts=counts))
    return rows


def _impact_counts(offerings, ids) -> dict:
    """«Neçə tələbə / dərs / bal təsirlənir» — təsdiq xülasəsinin rəqəmləri.

    Tələbə və dərs sayı cədvəl sorğusunda annotasiya ilə gəlir; bal və yekun
    qiymət sayı isə AYRICA iki aqreqatdır (join partlamasın deyə).
    """
    from apps.registrar.models import FinalGrade, LessonMark

    marks = dict(
        LessonMark.objects.filter(lesson__offering_id__in=ids)
        .values_list("lesson__offering_id")
        .annotate(total=Count("id"))
    )
    finals = dict(
        FinalGrade.objects.filter(enrollment__offering_id__in=ids)
        .values_list("enrollment__offering_id")
        .annotate(total=Count("id"))
    )
    return {
        offering.pk: {
            "students": getattr(offering, "student_count", 0) or 0,
            "lessons": getattr(offering, "lesson_count", 0) or 0,
            "marks": marks.get(offering.pk, 0),
            "finals": finals.get(offering.pk, 0),
        }
        for offering in offerings
    }


# ── Süzgəc açılışları ────────────────────────────────────────────────────────


@never_cache
@login_required
@require_GET
def handover_options(request):
    """Semestr + fakültə + kafedra süzgəcləri (aktorun əhatəsi daxilində)."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse({"has_access": False, "periods": [], "faculties": [], "kafedras": []})

    from django.apps import apps as django_apps

    from core.constants import OrgUnitType

    academic_period = django_apps.get_model("organizations", "AcademicPeriod")
    org_unit = django_apps.get_model("organizations", "OrgUnit")

    periods = [
        {"id": str(period.pk), "label": period_label(period), "is_current": period.is_current}
        for period in academic_period.objects.filter(organization=actor.organization).order_by("-start_date")[:40]
    ]
    scope = handover_read.actor_scope(actor.user, actor.organization)
    units = org_unit.objects.filter(organization=actor.organization, is_active=True)
    if not scope.is_org_wide:
        units = units.filter(scope.unit_subtree_q())
    return _json(
        {
            "has_access": True,
            "periods": periods,
            "faculties": _unit_rows(units, OrgUnitType.FACULTY),
            "kafedras": _unit_rows(units, OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT),
        }
    )


def _unit_rows(queryset, *unit_types):
    return [
        {"id": str(row["id"]), "label": row["name"], "parent_id": str(row["parent_id"] or "")}
        for row in queryset.filter(unit_type__in=unit_types).order_by("name").values("id", "name", "parent_id")
    ]


# ── Tarixçə ──────────────────────────────────────────────────────────────────


@never_cache
@login_required
@require_GET
def handover_history(request):
    """Əhatədəki təhvil tarixçəsi — «kim, nə vaxt, kimdən kimə, niyə»."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse(_EMPTY)

    queryset = handover_read.scoped_history(actor.user, actor.organization)
    offering_id = (request.GET.get("offering") or "").strip()
    if offering_id:
        queryset = queryset.filter(offering_id=offering_id)

    page, paginator = _page(queryset, request, default_size=20)
    records = list(page.object_list)
    context = _revert_context(records, organization=actor.organization)
    results = [_history_row(record, **context) for record in records]
    return _json(_paged_payload(page, paginator, results))


def _revert_context(records, *, organization) -> dict:
    """Səhifə üzrə TOPLU geri-qaytarma konteksti (bağlı jurnallar + etiketlər).

    Blokerlər sətir-sətir hesablansa da bağlı-jurnal dəsti, bugünkü tarix və
    təşkilat bir dəfə oxunur — 20 sətirlik səhifədə N+1 olmamalıdır
    (``_serialize_offerings`` ilə eyni naxış).
    """
    from django.utils import timezone

    offering_ids = [record.offering_id for record in records if not record.is_reverted]
    return {
        "closed_ids": handover_read.closed_offering_ids(offering_ids),
        "today": timezone.localdate(),
        "labels": blocker_labels(action=REVERT),
        "organization": organization,
    }


def _revert_blocker_codes(record, *, closed_ids, today, organization) -> list:
    """Bu sətrin geri qaytarılmasına mane olan kodlar (boş = düymə aktivdir).

    ⚠️ Bu funksiya OLMADIĞI üçün müqavilə pozulurdu: ``can_revert`` yalnız
    «geri qaytarılmayıb + zəncir yerindədir» şərtini yoxlayırdı və dövr bitmiş
    (yaxud jurnalı bağlanmış) sətirdə də ``True`` qaytarırdı. Nəticədə JS düyməni
    AKTİV çəkirdi, POST isə ``handover_actions.revert``-in
    :data:`~apps.registrar.handover_actions.REVERT_BLOCKER_CODES` qapısında
    409 verirdi — düymə HƏMİŞƏ xəta verən düymə idi.

    Tərif TƏKRAR YAZILMIR: kodlar oxu qatından (``handover.blockers``) gəlir və
    mutasiyanın süzgəci ilə eyni siyahıya daraldılır. ``actor`` ötürülMÜR —
    əhatə ``scoped_history`` ilə onsuz da daraldılıb və ``blockers`` aktor
    verildikdə mutasiyanın QƏBUL etdiyi kodları da qaytarardı (bax
    ``REVERT_BLOCKER_CODES`` şərhi).
    """
    from apps.registrar.handover_actions import REVERT_BLOCKER_CODES

    offering = record.offering
    codes = [
        code
        # ⚠️ ``organization`` MÜTLƏQ ötürülür.  ``blockers`` onu
        # ``organization or offering.organization`` ilə həll edir, yəni
        # ötürülMƏSƏ FK sətir başına yüklənir — məhz qaçmaq istədiyimiz N+1.
        # (``scoped_history`` ``offering__organization``-ı select_related ETMİR;
        # aktorun təşkilatı isə onsuz da əldədir və əhatə ona görə darlanıb.)
        for code in handover_read.blockers(offering, organization=organization, closed_ids=closed_ids, today=today)
        if code in REVERT_BLOCKER_CODES
    ]
    # Zəncir irəli getdikdə server ``chain_moved`` ilə 409 verir; bu da sətrin
    # geri qaytarıla bilməmə SƏBƏBİDİR və istifadəçiyə deyilməlidir.
    if offering.instructor_id != record.to_instructor_id:
        codes.append("chain_moved")
    return codes


def _history_row(record, *, closed_ids, today, labels, organization) -> dict:
    offering = record.offering
    # Geri qaytarılmış sətirdə bloker sorğulamağın mənası yoxdur (düymə onsuz da
    # yoxdur) — «geri qaytarılıb» etiketi göstərilir.
    codes = (
        []
        if record.is_reverted
        else _revert_blocker_codes(record, closed_ids=closed_ids, today=today, organization=organization)
    )
    return {
        "id": str(record.pk),
        "offering_id": str(record.offering_id),
        "subject": getattr(offering.subject, "name", "") or getattr(offering.subject, "code", ""),
        "group": getattr(offering.group, "name", "") or "",
        "period": period_label(offering.period),
        "from_name": record.from_instructor_name or "—",
        "to_name": record.to_instructor_name or "—",
        "performed_by": person_name(record.performed_by),
        "created_at": record.created_at.isoformat(),
        "reason": record.reason,
        "is_reverted": record.is_reverted,
        "revert_reason": record.revert_reason,
        # Səbəblər sətirlə birlikdə gəlir ki, UI «—» əvəzinə NİYƏ olmadığını desin.
        "revert_blockers": [{"code": code, "label": labels.get(code, code)} for code in codes],
        # MÜQAVİLƏ: düymə yalnız serverin həqiqətən qəbul edəcəyi sətirdə aktivdir.
        "can_revert": (not record.is_reverted) and not codes,
    }


def _json(payload):
    return JsonResponse(payload)


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "handover_history",
    "handover_offerings",
    "handover_options",
    "handover_teachers",
]
