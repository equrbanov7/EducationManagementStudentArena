"""Profil "unit-exams" («Bölmə imtahanları») bölməsi üçün context qurucusu.

Dekan / dekan müavini / kafedra müdiri üçün öz alt-ağacının imtahanlarına OXU-ONLY baxış:
KPI sırası + avto filtr paneli + sıralanan cədvəl + «Ətraflı» çekmecəsi (2026-10-14 redizayn).
Sorğular ``unit_exams_query``-də, etiket/sətir forması ``unit_exams_ui``-dədir.

Köhnə açarlar (``unit_exams_page_obj`` — ``Exam`` obyektləri, ``unit_exams_total_count`` …)
testlər və geriyə-uyğunluq üçün saxlanılır; şablon ``unit_exams_section``-u işlədir.
"""

from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.utils.translation import pgettext

from apps.accounts.views._helpers.tenant import _get_active_organization

from . import unit_exams_query as q
from . import unit_exams_ui as ui

PAGE_SIZE = 20


def _defaults() -> dict:
    return {
        "unit_exams_page_obj": None,
        "unit_exams_search_query": "",
        "unit_exams_total_count": 0,
        "unit_exams_pagination_query": "",
        "unit_exams_section": {"has_scope": False},
    }


def _scope_roots(subtree) -> list[str]:
    """Əhatənin kök vahidlərinin adları (alt başlıq üçün) — valideyni alt-ağacda olmayanlar."""
    rows = list(subtree.values_list("pk", "parent_id", "name"))
    inside = {pk for pk, _parent, _name in rows}
    return sorted(name for _pk, parent, name in rows if parent not in inside)


def _options(org, subtree):
    from apps.organizations.models import AcademicPeriod

    chairs = [
        {"value": str(pk), "label": name}
        for pk, name in subtree.filter(unit_type__in=q.CHAIR_TYPES).order_by("name").values_list("pk", "name")
    ]
    periods = {
        str(period.pk): period
        for period in AcademicPeriod.objects.filter(organization=org, is_active=True).order_by("-start_date")[:12]
    }
    period_options = [{"value": key, "label": f"{p.name} · {p.academic_year}"} for key, p in periods.items()]
    return chairs, periods, period_options


def build_unit_exams_context(request, *, allowed_sections, active_section) -> dict:
    """Unit imtahanları bölməsi üçün ``context`` açarları. Bölmə aktiv deyil / org yoxdur → default.

    Əhatə yoxdursa ``unit_exams_section.has_scope`` False olur (şablon «əhatə təyin edilməyib»
    deyir) — «imtahan yoxdur» halından AYRI (2026-10-14: iki hal eyni boş mesajı göstərirdi).
    """
    if not (active_section == "unit-exams" and "unit-exams" in allowed_sections):
        return _defaults()

    from apps.exams.models import Exam

    org = _get_active_organization(request)
    if org is None:
        return _defaults()
    subtree = q.resolve_unit_subtree(request, org)
    if subtree is None:
        return _defaults()

    filters = q.read_filters(request)
    chair_options, periods, period_options = _options(org, subtree)
    scoped = q.scoped_exams(org, subtree)
    kpi = q.kpi_counts(scoped)

    rows_qs = q.apply_filters(scoped, org, filters, chair_ids={opt["value"] for opt in chair_options}, periods=periods)
    rows_qs = q.order_rows(q.annotate_rows(rows_qs), filters["sort"]).select_related(
        "author", "subject", "subject__chair_unit", "course"
    )
    from apps.organizations.models import OrgUnit

    rows_qs = rows_qs.prefetch_related(
        Prefetch("allowed_units", queryset=OrgUnit.objects.only("pk", "name").order_by("name")),
        "allowed_groups",
    )
    page = Paginator(rows_qs, PAGE_SIZE).get_page(request.GET.get("ue_page") or request.GET.get("unit_exam_page"))
    exams = list(page.object_list)
    page.object_list = exams

    kind_labels = ui._choice_labels(Exam.EXAM_TYPE_EXTENDED_CHOICES)
    form_labels = ui._choice_labels(Exam.EXAM_TYPE_CHOICES)
    statuses = ui.status_labels()
    params = ui.base_params(filters)
    filtered = any(value for key, value in params.items() if key != "section")
    count = page.paginator.count
    section = {
        "has_scope": True,
        "scope_label": ", ".join(_scope_roots(subtree)),
        "kpi_tiles": ui.kpi_tiles(kpi, filters),
        "filter_fields": ui.filter_fields(
            filters,
            chair_options=chair_options,
            period_options=period_options,
            kind_labels=kind_labels,
            form_labels=form_labels,
        ),
        "filter_count_label": pgettext(ui.CTX, "Nəticə: %(count)d imtahan") % {"count": count},
        "columns": ui.columns(params, filters["sort"]),
        "table_rows": [
            ui.table_row(exam, kind_labels=kind_labels, form_labels=form_labels, statuses=statuses) for exam in exams
        ],
        "table_state": "ready" if exams else "empty",
        "drawer_rows": [
            ui.drawer_row(exam, user=request.user, kind_labels=kind_labels, form_labels=form_labels, statuses=statuses)
            for exam in exams
        ],
        "page_obj": page,
        "pagination_query": ui.pagination_query(params, filters["sort"]),
        "is_filtered": filtered,
        "total_count": kpi["total"],
    }
    if filtered:
        section["state_title"] = pgettext(ui.CTX, "Süzgəcə uyğun imtahan tapılmadı")
        section["state_body"] = pgettext(ui.CTX, "Süzgəcləri dəyişin və ya «Sıfırla» düyməsini basın.")
    else:
        section["state_title"] = pgettext(ui.CTX, "Bölmənizə aid imtahan hələ yoxdur")
        section["state_body"] = pgettext(
            ui.CTX,
            "Əhatəniz təyin olunub. Fakültə/kafedra müəllimləri imtahan yaradıb onu fənnə, "
            "qrupa və ya kafedraya bağladıqda burada görünəcək.",
        )
    return {
        "unit_exams_page_obj": page,
        "unit_exams_search_query": filters["search"],
        "unit_exams_total_count": kpi["total"],
        "unit_exams_pagination_query": section["pagination_query"],
        "unit_exams_section": section,
    }
