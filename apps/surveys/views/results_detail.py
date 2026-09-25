"""Müəllim kartı — çekməcə fraqmenti və çap səhifəsi.

* ``/sorgu/neticeler/muellim/<id>/`` — HTML fraqment (kabinetdəki çekməcəyə JS ilə
  yerləşdirilir); ``…/cap/`` — eyni məzmun müstəqil, çapa hazır səhifədə.
* Filtrlər eyni ``er_*`` parametrləridir (bölmənin cari URL-i ötürülür).
* İcazə FAIL-CLOSED: əhatəsiz → 403; müəllim əhatədə deyil / cavabı yoxdur → 404
  (F1 ``teacher_detail`` ``found=False`` qaytarır — başqa kafedranın müəllimi üçün
  heç bir rəqəm, hətta cavab sayı da verilmir).
* Şərhlər yalnız dəst ``k``-nı keçəndə, identifikatorsuz və tarixsiz göstərilir.
"""

from __future__ import annotations

from dataclasses import replace

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .. import public
from ..services.analytics_extra import buckets_for
from .results_filters import query_string, resolve
from .results_labels import likert_labels, short_label
from .results_overview import likert_row, trend_block

CTX = "surveys.results"


def _pct(value):
    return None if value is None else round(float(value) * 100)


def _comments(items):
    groups = {"strengths": [], "improve": [], "other": []}
    for item in items:
        groups.get(item["question_code"], groups["other"]).append(item["text"])
    return [
        {
            "code": code,
            "label": short_label(code) if code != "other" else pgettext(CTX, "Digər şərhlər"),
            "items": texts,
            "keywords": public.keyword_frequency(texts, top=10),
        }
        for code, texts in groups.items()
        if texts
    ]


def _offerings(detail):
    rows = [
        {
            "label": " · ".join(part for part in (row["subject_name"], row["group_name"]) if part) or "—",
            "subject": row["subject_name"] or "—",
            "group": row["group_name"] or "—",
            "n": row["n"],
            "suppressed": row["suppressed"],
            "secondary": row.get("secondary", False),
            "avg_overall": row["avg_overall"],
            "likert_index": row["likert_index"],
            "recommend_top2": row["recommend_top2"],
        }
        for row in detail["offerings"]
    ]
    public.secondary_suppress(rows, k=detail["k"], total_n=None if detail["suppressed"] else detail["n"])
    for row in rows:
        row["recommend"] = _pct(row["recommend_top2"])
    return rows


def _questions(detail, benchmarks):
    rows = []
    for row in detail["questions"]:
        if row["section"] != public.Section.TEACHER or row["kind"] != "likert5":
            continue
        rows.append(
            {
                "code": row["code"],
                "label": short_label(row["code"], row["text"]),
                "text": row["text"],
                "n": row["n"],
                "avg": row["avg"],
                "top2": _pct(row["top2"]),
                "department": benchmarks["department"].get(row["code"]),
                "org": benchmarks["org"].get(row["code"]),
            }
        )
    return rows


def _likert(detail, questions):
    rows = []
    for row in questions:
        counts = detail["distributions"].get(row["code"])
        if counts:
            data = buckets_for(counts, "likert5")
            rows.append(likert_row(row["code"], row["text"], data["buckets"], data["n"]))
    return rows


def _withhold_detail(detail):
    """Dərc olunmayan müəllim (analytics_publish): yalnız say qalır, heç bir göstərici/şərh yox."""
    public.hide_row(detail, secondary=True)
    detail.update(distributions={}, comments=[])
    detail["questions"] = [{**row, "avg": None, "top2": None} for row in detail.get("questions", [])]
    for row in detail.get("offerings", []):
        public.hide_row(row, secondary=True)


def detail_context(request, teacher_id):
    """``(context, status)`` — ``context`` ``None``-dursa ``status`` 403/404-dür."""
    resolved = resolve(request)
    if resolved is None:
        return None, 403
    if not resolved.campaigns:
        return None, 404
    organization, scope, query = resolved.organization, resolved.scope, resolved.query
    filters = replace(resolved.filters, teacher_id=None)
    detail = public.teacher_detail(organization, scope, teacher_id, filters)
    if not detail.get("found"):
        return None, 404
    campaign_ids = resolved.campaign_ids
    if not detail["suppressed"] and teacher_id not in public.publishable_teachers(organization, campaign_ids):
        _withhold_detail(detail)
    visible = not detail["suppressed"]
    benchmarks = public.question_benchmarks(organization, scope, campaign_ids, department_id=detail["department_id"])
    questions = _questions(detail, benchmarks) if visible else []
    likert = _likert(detail, questions) if visible else []
    teacher_filters = replace(filters, teacher_id=teacher_id, department_id=detail["department_id"])
    trend = trend_block(organization, scope, teacher_filters)
    participation = public.participation_rows(organization, scope, teacher_filters, campaign_ids, per_teacher=False)
    rate = None if participation.get("approximate") else participation.get("rate")
    qs = query_string(query, filters, state=False)
    chart = {
        "questions": {
            "labels": [row["label"] for row in questions],
            "values": [row["avg"] for row in questions],
            "department": [row["department"] for row in questions],
            "org": [row["org"] for row in questions],
            "n": [row["n"] for row in questions],
        },
        "likert": {
            "labels": [row["label"] for row in likert],
            "counts": [row["counts"] for row in likert],
            "pct": [row["pct"] for row in likert],
            "scale": [label for _score, label in likert_labels()],
        },
        "trend": trend["chart"],
    }
    context = {
        "teacher": {
            "id": teacher_id,
            "name": detail["teacher_name"] or "—",
            "department": detail["department_name"] or "",
            "n": detail["n"],
            "k": detail["k"],
            "suppressed": detail["suppressed"],
            "complement_blocked": detail["n"] >= detail["k"] and detail["suppressed"],
            "secondary": bool(detail.get("secondary")),
        },
        "period_label": query.period.label,
        "narrowed": filters.is_narrowed,
        "kpis": {
            "overall": detail["avg_overall"],
            "index": detail["likert_index"],
            "index_pct": round(detail["likert_index_pct"]) if detail["likert_index_pct"] is not None else None,
            "recommend": _pct(detail["recommend_top2"]),
            "delta_department_value": detail["delta_department_overall"],
            "delta_org_value": detail["delta_org_overall"],
            "rate": _pct(rate),
            "receipts": participation.get("receipts", 0),
            "expected": participation.get("expected", 0),
        },
        "questions": questions,
        "likert": likert,
        "likert_scale": likert_labels(),
        "offerings": _offerings(detail),
        "trend": trend,
        "comments": _comments(detail["comments"]) if visible else [],
        "comment_count": len(detail["comments"]) if visible else 0,
        "chart": chart,
        "print_url": f"{reverse('surveys:results_teacher_print', args=[teacher_id])}?{qs}",
        "section_url": f"{reverse('accounts:profile')}?section=evaluation-results&{qs}",
    }
    return context, 200


def _error_fragment(request, status):
    message = (
        pgettext(CTX, "Bu məlumata baxmaq üçün icazəniz yoxdur.")
        if status == 403
        else pgettext(CTX, "Seçilmiş filtrlərdə bu müəllim üçün cavab yoxdur və ya o, sizin əhatənizdə deyil.")
    )
    html = render_to_string("surveys/results/_detail_error.html", {"message": message}, request=request)
    return HttpResponse(html, status=status)


@never_cache
@login_required
@require_GET
def teacher_drawer(request, teacher_id):
    context, status = detail_context(request, teacher_id)
    if context is None:
        return _error_fragment(request, status)
    return HttpResponse(render_to_string("surveys/results/_teacher_detail.html", context, request=request))


@never_cache
@login_required
@require_GET
def teacher_print(request, teacher_id):
    context, status = detail_context(request, teacher_id)
    if context is None:
        return render(
            request,
            "surveys/results/teacher_print.html",
            {
                "error": True,
                "status": status,
                "section_url": f"{reverse('accounts:profile')}?section=evaluation-results",
            },
            status=status,
        )
    return render(request, "surveys/results/teacher_print.html", {**context, "is_print": True})
