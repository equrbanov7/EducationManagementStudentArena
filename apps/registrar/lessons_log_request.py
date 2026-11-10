"""«Keçilmiş dərslər» — sorğu parametrlərinin TƏK həlli (bölmə + tənbəl uclar + müəllim cədvəli).

Bölmə (`accounts…_sections.lessons_log`), tənbəl KPI / «qeydə alınmayıb» ucu, «Daha çox göstər» səhifəsi və
«Cədvəl formasında bax» (müəllim cədvəli, Excel) EYNİ əhatə + dövr + süzgəc zəncirindən keçməlidir — əks halda
modaldakı rəqəm səhifədəki siyahı ilə uyğun gəlməz. Bu modul həmin zənciri bir yerdə saxlayır:

    əhatə (`scoped_lessons`) → dövr / aralıq (`resolve_selection`) → fakültə / kafedra (`unit_filter_state`)
    → `apply_filters`

Parametr ad fəzası ``ll_`` (bölmənin filtr paneli ilə eyni). CSV ixracı (`lessons_log_views.lessons_log_csv`)
öz köhnə həllini saxlayır (davranışı dəyişmir).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q

from core.http_ids import parse_uuid

#: Filtr parametrlərinin ad fəzası (`ems_ui/_filter_bar.html` müqaviləsi).
PREFIX = "ll_"


def param(request, name: str, default: str = "") -> str:
    return (request.GET.get(PREFIX + name) or default).strip()[:80]


def teacher_q(teacher_id) -> Q:
    """Dərsi KEÇƏN müəllim: dərsin öz ``instructor``-u, boşdursa açılışın müəllimi (``apply_filters`` ilə eyni)."""
    return Q(instructor_id=teacher_id) | Q(instructor__isnull=True, offering__instructor_id=teacher_id)


def parse_user_id(raw):
    """Sorğudan gələn istifadəçi id-si → pk dəyəri; pozuq dəyər → ``None`` (500 yox)."""
    if not raw:
        return None
    try:
        return get_user_model()._meta.pk.to_python(raw)
    except Exception:  # noqa: BLE001 — istənilən pozuq dəyər «tapılmadı» deməkdir
        return None


def resolve_request(request, organization, *, with_options: bool = True) -> dict:
    """Sorğunun effektiv seçimi.

    Qaytarır:
        ``supervisor``, ``current`` (cari dövr), ``selection``, ``window``, ``values`` (effektiv filtr dəyərləri),
        ``units`` (`unit_filter_state`), ``unit_filters`` (`apply_filters` üçün), ``lessons_all`` (əhatə, dövrsüz),
        ``option_source`` (seçicilərin mənbəyi), ``scoped_window`` (əhatə + dövr/aralıq, süzgəcsiz),
        ``lessons`` (bütün süzgəclərlə), ``teacher_raw`` (sorğudakı müəllim id-si — nəzarətçi olmayanda
        ``values["teacher"]`` BOŞDUR, çağıran 403 verib-verməməyi özü seçir).
    """
    from apps.registrar import lessons_log as service
    from apps.registrar import schedule as schedule_service

    user = request.user
    supervisor = service.is_supervisor(user, organization)
    legacy_period = param(request, "period")
    current = schedule_service.resolve_display_period(organization, requested=legacy_period)["period"]
    selection = service.resolve_selection(
        organization,
        current=current,
        year=param(request, "year"),
        season=param(request, "season"),
        legacy_period=legacy_period,
        range_key=param(request, "range", service.RANGE_SEMESTER),
        start_raw=param(request, "from"),
        end_raw=param(request, "to"),
    )
    window = selection["window"]

    lessons_all = service.scoped_lessons(user, organization, supervisor=supervisor)
    scoped_window = lessons_all.filter(date__gte=window["start"], date__lte=window["end"])
    if selection["apply_period_filter"]:
        scoped_window = scoped_window.filter(offering__period__in=selection["periods"])

    teacher_raw = param(request, "teacher")
    # Pozuq id (əl ilə yazılmış URL) süzgəc kimi SAYILMIR — ORM-ə çatıb 500 verməsin.
    teacher_id = parse_user_id(teacher_raw)
    offering_raw = param(request, "offering")
    values = {
        "q": param(request, "q"),
        "offering": offering_raw if parse_uuid(offering_raw) is not None else "",
        "kind": param(request, "kind"),
        "group": param(request, "group"),
        "teacher": str(teacher_id) if supervisor and teacher_id is not None else "",
        "form": param(request, "form"),
        "range": window["key"],
        "year": selection["year"],
        "season": selection["season"],
    }
    # Seçici siyahıları SEÇİLMİŞ dövrlərə görə daralır (yoxsa bütün əhatə).
    option_source = lessons_all
    if selection["periods"] is not None:
        option_source = option_source.filter(offering__period__in=selection["periods"])
    # Fakültə / Kafedra (sahib, 2026-09-25) — tərif, əhatə və kaskad `registrar.lessons_log_units`-dədir.
    units = service.unit_filter_state(
        user,
        organization,
        option_source,
        supervisor=supervisor,
        faculty_raw=param(request, "faculty"),
        kafedra_raw=param(request, "kafedra"),
        with_options=with_options,
    )
    values["faculty"], values["kafedra"] = units["faculty_value"], units["kafedra_value"]
    unit_filters = {"faculty_unit": units["faculty"], "kafedra_unit": units["kafedra"]}
    lessons = service.apply_filters(
        scoped_window,
        q=values["q"],
        offering=values["offering"],
        kind=values["kind"],
        group=values["group"],
        teacher=values["teacher"],
        form=values["form"],
        supervisor=supervisor,
        **unit_filters,
    )
    if units["invalid"]:
        # Seçilmiş fakültə/kafedra tapılmadı — «hamısı» göstərilmir. `.none()` YOX: KPI keş açarı
        # sorğunun SQL mətnindən qurulur (`totals_cache_key`), boş queryset isə SQL vermir.
        lessons = lessons.filter(pk__isnull=True)
    return {
        "supervisor": supervisor,
        "current": current,
        "selection": selection,
        "window": window,
        "values": values,
        "units": units,
        "unit_filters": unit_filters,
        "lessons_all": lessons_all,
        "option_source": option_source,
        "scoped_window": scoped_window,
        "lessons": lessons,
        "teacher_raw": teacher_raw,
        "only_flagged": param(request, "flagged") == "1",
    }


def unrecorded_for(request, organization, ctx, *, cached_only: bool = False):
    """«Cədvəldə var, qeydə alınmayıb» — sorğunun effektiv seçimi ilə (bölmə və tənbəl uc eyni açarı işlədir)."""
    from apps.registrar import lessons_log_unrecorded

    selection = ctx["selection"]
    return lessons_log_unrecorded.unrecorded_slots(
        request.user,
        organization,
        supervisor=ctx["supervisor"],
        window=ctx["window"],
        periods=selection["periods"] if selection["apply_period_filter"] else None,
        filters=dict(ctx["values"], invalid_unit=ctx["units"]["invalid"], **ctx["unit_filters"]),
        cached_only=cached_only,
    )


__all__ = ["PREFIX", "param", "parse_user_id", "resolve_request", "teacher_q", "unrecorded_for"]
