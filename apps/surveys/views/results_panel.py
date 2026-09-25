"""«Sorğu nəticələri» kabinet bölməsinin konteksti (``survey_results_panel`` tag-ı çağırır).

Bölmə AJAX-safe-dir: filtr paneli (``filter_bar.js`` müqaviləsi) və tab linkləri
paneli ``EMSProfileLoadSection`` ilə yerində yeniləyir; bütün vəziyyət URL-dədir
(``er_*``, bax ``results_filters``). Hər tab YALNIZ öz məlumatını hesablayır —
sorğu sayı tabdan asılı sabitdir (cavab/müəllim sayından asılı deyil).

İcazə FAIL-CLOSED: ``results_scope`` əhatəsizdirsə heç bir aqreqat çağırılmır.
Açıqlama nəzarəti (``services/analytics_guard``): nəticə yalnız BAĞLI kampaniyalardan
(M-1 — davam edən kampaniyada yalnız iştirak, səbət/5%-lə); say heç yerdə dəqiq
göstərilmir; gizli sətrin aqreqatı verilmir; qardaş xanalar və iç-içə dövr dəstləri
çıxmaya qarşı qorunur (M-2). Bu modul xam cavab sətri oxumur.
"""

from __future__ import annotations

from dataclasses import replace

from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import pgettext

from .. import public
from ..services import analytics_guard as guard
from .results_filters import effective_params, period_options, query_string, resolve
from .results_labels import TAB_GENERAL, TAB_LABELS, TAB_OVERVIEW, TAB_TEACHERS, TABS, short_label

CTX = "surveys.results"

SECTION = "evaluation-results"


def _pct(value):
    return None if value is None else round(float(value) * 100)


def delta_info(current, previous, *, digits=2) -> dict | None:
    """KPI dəyişməsi: ``{"value", "abs", "direction": up|down|flat}`` (hər iki tərəf görünəndə)."""
    if current is None or previous is None:
        return None
    value = round(float(current) - float(previous), digits)
    direction = "flat" if abs(value) < 0.05 else ("up" if value > 0 else "down")
    return {"value": value, "abs": abs(value), "direction": direction}


def participation_view(participation) -> dict:
    """İştirakın GÖSTƏRİLƏN forması: faiz 5-ə yuvarlaq, saylar səbətlə (M-1/M-2)."""
    participation = participation or {}
    approximate = bool(participation.get("approximate"))
    return {
        "rate": None if approximate else guard.round5(participation.get("rate")),
        "receipts": guard.count_bucket(participation.get("receipts")) if participation else "—",
        "expected": guard.count_bucket(participation.get("expected")) if participation else "—",
        "has_expected": bool(participation.get("expected")),
        "approximate": approximate,
    }


def _options(items, *, all_label) -> list:
    """Seçim siyahısı — cavab SAYI göstərilmir (canlı/dəqiq say sızmasın)."""
    return [{"value": "", "label": all_label}] + [
        {"value": str(item["id"]), "label": item["label"] or "—"} for item in items
    ]


def _question_options(catalog) -> list:
    options = [{"value": "", "label": str(short_label("overall"))}]
    for row in catalog:
        if row["section"] == public.Section.TEACHER and row["kind"] == "likert5":
            options.append({"value": row["code"], "label": short_label(row["code"], row["text"])})
    return options


def _latest_campaign(organization, campaign_ids):
    from ..models import SurveyCampaign

    return (
        SurveyCampaign.objects.filter(organization=organization, pk__in=list(campaign_ids))
        .select_related("template")
        .order_by("-period__start_date", "-created_at")
        .first()
    )


def _select(name, label, options, value, *, wide=False) -> dict:
    return {
        "name": f"er_{name}",
        "label": label,
        "kind": "select",
        "options": options,
        "value": "" if value is None else str(value),
        "searchable": len(options) > 8,
        "wide": wide,
    }


def _filter_fields(resolved, filters, question_options, urls) -> list:
    period = _select(
        "period", pgettext(CTX, "Dövr"), period_options(resolved.campaigns), resolved.query.period.value, wide=True
    )
    if resolved.live or resolved.choices is None:
        return [period]
    choices, all_label = resolved.choices, pgettext(CTX, "Hamısı")
    fields = [
        period,
        _select(
            "faculty", pgettext(CTX, "Fakültə"), _options(choices["faculties"], all_label=all_label), filters.faculty_id
        ),
        _select(
            "department",
            pgettext(CTX, "Kafedra"),
            _options(choices["departments"], all_label=all_label),
            filters.department_id,
        ),
        {
            "name": "er_teacher",
            "label": pgettext(CTX, "Müəllim"),
            "kind": "teacher",
            "value": "" if filters.teacher_id is None else str(filters.teacher_id),
            "text": resolved.teacher_name if filters.teacher_id is not None else "",
            "search_url": urls["teacher_search"],
            "wide": True,
        },
        _select(
            "subject", pgettext(CTX, "Fənn"), _options(choices["subjects"], all_label=all_label), filters.subject_id
        ),
        _select("group", pgettext(CTX, "Qrup"), _options(choices["groups"], all_label=all_label), filters.group_id),
    ]
    if choices["programs"]:
        options = _options(choices["programs"], all_label=all_label)
        fields.append(_select("program", pgettext(CTX, "İxtisas"), options, filters.program_id))
    if choices["course_years"]:
        options = _options(choices["course_years"], all_label=all_label)
        fields.append(_select("course_year", pgettext(CTX, "Kurs"), options, filters.course_year))
    fields.append(_select("question", pgettext(CTX, "Sual"), question_options, filters.question_code))
    fields.append(
        {
            "name": "er_q",
            "label": pgettext(CTX, "Şərhlərdə axtar"),
            "kind": "search",
            "value": filters.text_query,
            "placeholder": pgettext(CTX, "söz və ya ifadə…"),
        }
    )
    return fields


def _rate_tile(view) -> dict:
    return {
        "key": "rate",
        "label": pgettext(CTX, "Cavab faizi"),
        "value": f"≈ {view['rate']}%" if view["rate"] is not None else "—",
        "note": (
            pgettext(CTX, "%(done)s / %(expected)s hədəf") % {"done": view["receipts"], "expected": view["expected"]}
            if not view["approximate"]
            else pgettext(CTX, "ixtisas/kurs filtrində hesablanmır")
        ),
    }


def _kpis(summary, participation, previous) -> list:
    hidden, secondary = summary["suppressed"], bool(summary.get("secondary"))
    return [
        {
            "key": "n",
            "label": pgettext(CTX, "Cavab sayı"),
            "value": guard.count_bucket(summary["n"]),
            "note": pgettext(CTX, "ümumi bölmə: %(n)s") % {"n": guard.count_bucket(summary["general_n"])},
        },
        _rate_tile(participation_view(participation)),
        {
            "key": "overall",
            "label": pgettext(CTX, "Orta ümumi bal"),
            "value": summary["avg_overall"],
            "unit": "/ 10",
            "delta": delta_info(summary["avg_overall"], previous.get("avg_overall")),
            "suppressed": hidden,
            "secondary": secondary,
        },
        {
            "key": "index",
            "label": pgettext(CTX, "Likert indeksi"),
            "value": summary["likert_index"],
            "unit": "/ 5",
            "note": f"{round(summary['likert_index_pct'])}%" if summary["likert_index_pct"] is not None else "",
            "delta": delta_info(summary["likert_index"], previous.get("likert_index")),
            "suppressed": hidden,
            "secondary": secondary,
        },
        {
            "key": "recommend",
            "label": pgettext(CTX, "Tövsiyə edənlər"),
            "value": f"{_pct(summary['recommend_top2'])}%" if summary["recommend_top2"] is not None else None,
            "note": pgettext(CTX, "«razıyam» və «tamamilə razıyam»"),
            "suppressed": hidden,
            "secondary": secondary,
        },
        {
            "key": "teachers",
            "label": pgettext(CTX, "Nəticəsi görünən müəllimlər"),
            "value": summary["teachers_visible"],
            "note": pgettext(CTX, "cəmi %(n)s müəllim") % {"n": summary["teachers"]},
        },
    ]


def _urls(query, filters, base_url) -> dict:
    qs = query_string(query, filters, state=False)
    search_qs = query_string(query, filters, state=False, teacher="")
    export_csv = reverse("surveys:results_export", args=["csv"])
    return {
        "section": f"{base_url}?section={SECTION}",
        "teacher_search": f"{reverse('surveys:results_teachers')}?{search_qs}",
        "detail_base": reverse("surveys:results_teacher", args=[0]).rsplit("0/", 1)[0],
        "detail_qs": qs,
        "export_xlsx": f"{reverse('surveys:results_export', args=['xlsx'])}?{qs}",
        "export_csv": [
            {"key": key, "label": label, "url": f"{export_csv}?{qs}{'&' if qs else ''}dataset={key}"}
            for key, label in (
                ("teachers", pgettext(CTX, "Müəllimlər")),
                ("questions", pgettext(CTX, "Suallar və paylanma")),
                ("departments", pgettext(CTX, "Fakültə və kafedralar")),
                ("trend", pgettext(CTX, "Dinamika")),
                ("general", pgettext(CTX, "Ümumi bölmə")),
                ("keywords", pgettext(CTX, "Açar sözlər")),
            )
        ],
        "campaigns": f"{base_url}?section=evaluation-campaigns",
        "chartjs": static("vendor/chartjs/chart.umd.min.js"),
    }


def _tabs(query, filters, base_url) -> list:
    return [
        {
            "key": key,
            "label": TAB_LABELS[key],
            "current": key == query.tab,
            "url": f"{base_url}?section={SECTION}&{query_string(replace(query, tab=key), filters)}",
        }
        for key in TABS
    ]


def scope_label(scope) -> str:
    if scope.is_org_wide:
        return pgettext(CTX, "Bütün universitet")
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    names = sorted(OrgUnit.objects.filter(pk__in=list(scope.unit_ids)).values_list("name", flat=True))
    return ", ".join(names) or pgettext(CTX, "Struktur əhatəniz")


def apply_publishing(summary, filters, published) -> dict:
    """Dərc olunmayan müəllimə aid dəst gizlədilir; «görünən müəllim» sayı dərc qaydası ilə."""
    teacher_id = filters.teacher_id
    if teacher_id is not None and teacher_id not in published and not summary["suppressed"]:
        public.withhold(summary)
    summary["teachers_visible"] = sum(
        1
        for teacher, count in summary.get("teacher_counts", {}).items()
        if teacher in published and count >= summary["k"]
    )
    return summary


def _base(resolved, request, base_url, filters, urls) -> dict:
    scope = resolved.scope
    return {
        "is_org_wide": scope.is_org_wide,
        "scope_label": scope_label(scope),
        "can_manage": public.can_manage_campaigns(request.user, resolved.organization, request=request),
        "period": resolved.query.period,
        "filters": filters,
        "base_url": base_url,
        "urls": urls,
        "section": SECTION,
    }


def _live_context(resolved, request, base_url) -> dict:
    """M-1: davam edən kampaniya — YALNIZ iştirak (5%-lik faiz, səbətli saylar)."""
    # Canlı rejimdə yalnız dövr seçilir — URL-də qalmış digər filtrlər iştiraka da tətbiq olunmur.
    filters = public.ResultFilters(campaign_ids=tuple(resolved.campaign_ids))
    urls = _urls(resolved.query, filters, base_url)
    participation = public.participation_rows(
        resolved.organization, resolved.scope, filters, resolved.campaign_ids, per_teacher=False
    )
    view = participation_view(participation)
    return {
        **_base(resolved, request, base_url, filters, urls),
        "state": "live",
        "k": 0,
        "tabs": [],
        "filter_fields": _filter_fields(resolved, filters, [], urls),
        "participation": view,
        "kpis": [
            _rate_tile(view),
            {"key": "receipts", "label": pgettext(CTX, "Doldurulmuş hədəf"), "value": view["receipts"]},
            {"key": "expected", "label": pgettext(CTX, "Gözlənilən hədəf"), "value": view["expected"]},
        ],
    }


def panel_context(context) -> dict:
    request = context.get("request")
    resolved = resolve(request, with_choices=True) if request is not None else None
    if resolved is None:
        return {"state": "forbidden"}
    organization, scope, query = resolved.organization, resolved.scope, resolved.query
    base_url = context.get("profile_base_url") or reverse("accounts:profile")
    if not resolved.campaigns or not resolved.campaign_ids:
        return {
            "state": "no_campaign",
            "can_manage": public.can_manage_campaigns(request.user, organization, request=request),
            "campaigns_url": f"{base_url}?section=evaluation-campaigns",
        }
    if resolved.live:
        return _live_context(resolved, request, base_url)
    filters, family = resolved.filters, resolved.family
    latest = _latest_campaign(organization, resolved.campaign_ids)
    question_options = _question_options(public.question_catalog(latest) if latest is not None else [])
    if filters.question_code not in {option["value"] for option in question_options}:
        filters = replace(filters, question_code="")
    urls = _urls(query, filters, base_url)

    teacher_tab = query.tab == TAB_TEACHERS
    summary = public.results_summary(organization, scope, filters, with_participation=not teacher_tab, family=family)
    published = public.publishable_teachers(organization, resolved.campaign_ids)
    apply_publishing(summary, filters, published)
    participation, extra = summary["participation"], {}
    if teacher_tab:
        from .results_teachers import teachers_tab

        extra = teachers_tab(organization, scope, filters, summary, query, urls, published, family=family)
        participation = extra["participation"]
    elif query.tab == TAB_OVERVIEW:
        from .results_overview import overview_tab

        extra = overview_tab(organization, scope, filters, summary, query, family=family, campaigns=resolved.campaigns)
    elif query.tab == TAB_GENERAL:
        from .results_general import general_tab

        extra = general_tab(organization, scope, filters, summary, family=family)
    previous = {}
    if query.period.previous_ids and not summary["suppressed"]:
        previous_ids = list(query.period.previous_ids)
        previous_filters = replace(filters, campaign_ids=tuple(previous_ids))
        previous = public.set_metrics(organization, scope, previous_filters, previous_ids, family=family)
    params = effective_params(query, filters)
    return {
        **_base(resolved, request, base_url, filters, urls),
        "state": "ready",
        "tab": query.tab,
        "tabs": _tabs(query, filters, base_url),
        "k": summary["k"],
        "previous_label": query.period.previous_label if previous and not previous.get("suppressed") else "",
        "filter_fields": _filter_fields(resolved, filters, question_options, urls),
        "is_filtered": bool(set(params) - {"er_period"}),
        "subject_note": filters.subject_id is not None or filters.group_id is not None,
        "summary": summary,
        "participation": participation_view(participation),
        "kpis": _kpis(summary, participation, previous),
        **extra,
    }
