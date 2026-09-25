"""Nəticə analitikası (II) — müəllim kartı, dinamika, ümumi təkliflər, filtr seçimləri.

k-anonimlik və tamamlayıcı qayda ``analytics`` modulundakı ilə EYNİDİR. Sərbəst
mətn (şərh/təklif) YALNIZ dəst ``k``-nı keçəndə qaytarılır; heç bir şərh fənn,
qrup, tarix və ya hər hansı identifikatorla birlikdə verilmir, sırası təsadüfi
UUID-ə görədir (daxiletmə sırası deyil).
"""

from __future__ import annotations

from dataclasses import replace

from django.db.models import Avg, Count, Q

from core.search_text import tolerant_q

from ..constants import QuestionKind, Section
from ..models import SurveyAnswer, SurveyCampaign
from . import filters as flt
from .analytics import (
    _delta,
    _metric_annotations,
    _metrics,
    _names,
    _round,
    _unit_names,
    aggregate_metrics,
    department_benchmarks,
    is_visible,
    question_stats,
)

MAX_COMMENTS = 200


def _comments(queryset, codes, query="", *, limit=MAX_COMMENTS, offset=0) -> list:
    answers = SurveyAnswer.objects.filter(
        response__in=queryset.values("pk"), question__code__in=codes, question__kind=QuestionKind.TEXT
    ).exclude(text="")
    text_q = tolerant_q(query, ("text",))
    if text_q is not None:
        answers = answers.filter(text_q)
    rows = answers.order_by("pk").values_list("question__code", "text")[offset : offset + limit]
    return [{"question_code": code, "text": text} for code, text in rows]


def teacher_detail(organization, scope, teacher_id, filters=None) -> dict:
    """Müəllim kartı (bax ``public.py``): ``found``, ``k``, göstəricilər, suallar,
    paylanmalar, fənn×qrup üzrə sətirlər, kafedra/təşkilat müqayisəsi, şərhlər."""
    filters = replace(filters or flt.ResultFilters(), teacher_id=teacher_id)
    campaign_ids = flt.campaign_ids_for(organization, filters)
    if not campaign_ids or not scope.has_structure_access:
        return {"found": False}
    base = flt.responses(organization, scope, filters, campaign_ids)
    row = aggregate_metrics(base)
    n = row["n"] or 0
    if not n:
        return {"found": False}
    k = flt.k_threshold(campaign_ids)
    baseline = None
    if filters.is_narrowed:
        baseline = flt.responses(organization, scope, filters.without_narrowing(), campaign_ids).count()
    visible = is_visible(n, k, baseline)
    department_id = (
        base.values("teacher_department_id")
        .annotate(c=Count("id"))
        .order_by("-c")
        .values_list("teacher_department_id", flat=True)
    ).first()
    bench = department_benchmarks(organization, campaign_ids, k)
    dept, org = bench.get(department_id, {}), bench["__org__"]
    metrics = _metrics(row, visible)
    offerings = []
    teacher_total = n if not filters.is_narrowed else baseline
    for item in base.values("subject_id", "subject__name", "group_id", "group__name").annotate(**_metric_annotations()):
        offerings.append(
            {
                "subject_id": item["subject_id"],
                "subject_name": item["subject__name"] or "",
                "group_id": item["group_id"],
                "group_name": item["group__name"] or "",
                **_metrics(item, is_visible(item["n"] or 0, k, teacher_total)),
            }
        )
    distributions = {}
    if visible:
        for code, score, count in (
            SurveyAnswer.objects.filter(response__in=base.values("pk"), score__isnull=False)
            .values("question__code", "score")
            .annotate(c=Count("id"))
            .values_list("question__code", "score", "c")
        ):
            distributions.setdefault(code, {})[score] = count
    return {
        "found": True,
        "k": k,
        "teacher_id": teacher_id,
        "teacher_name": _names([teacher_id]).get(teacher_id, ""),
        "department_id": department_id,
        "department_name": _unit_names([department_id]).get(department_id, ""),
        **metrics,
        "delta_department_overall": _delta(metrics["avg_overall"], dept.get("avg_overall")),
        "delta_org_overall": _delta(metrics["avg_overall"], org.get("avg_overall")),
        "delta_department_index": _delta(metrics["likert_index"], dept.get("likert_index")),
        "delta_org_index": _delta(metrics["likert_index"], org.get("likert_index")),
        "questions": question_stats(base, visible=visible),
        "distributions": distributions,
        "offerings": sorted(offerings, key=lambda r: (r["subject_name"], r["group_name"])),
        "comments": _comments(base, ("strengths", "improve"), filters.text_query) if visible else [],
        "trend": trend(organization, scope, teacher_id=teacher_id),
    }


def trend(organization, scope, *, teacher_id=None, department_id=None, faculty_id=None, limit=12) -> list:
    """Dövrlər üzrə dinamika (köhnədən yeniyə): ``[{"campaign_id", "period_id",
    "period_name", "academic_year", "k", ...metrics}]`` — hər kampaniya öz ``k``-sı ilə."""
    if not scope.has_structure_access:
        return []
    campaigns = list(
        SurveyCampaign.objects.filter(organization=organization)
        .select_related("period")
        .order_by("-period__start_date")[:limit]
    )
    filters = flt.ResultFilters(teacher_id=teacher_id, department_id=department_id, faculty_id=faculty_id)
    base = flt.responses(organization, scope, filters, [c.pk for c in campaigns])
    rows = {row["campaign_id"]: row for row in base.values("campaign_id").annotate(**_metric_annotations())}
    result = []
    for campaign in reversed(campaigns):
        row = rows.get(campaign.pk, {"n": 0})
        result.append(
            {
                "campaign_id": campaign.pk,
                "period_id": campaign.period_id,
                "period_name": campaign.period.name,
                "academic_year": campaign.period.academic_year,
                "k": campaign.min_group_size,
                **_metrics(row, (row.get("n") or 0) >= campaign.min_group_size),
            }
        )
    return result


def general_suggestions(organization, scope, filters=None, *, query="", limit=50, offset=0) -> dict:
    """Ümumi bölmənin təklifləri: ``{"k", "n", "suppressed", "items": [{"question_code", "text"}]}``."""
    filters = filters or flt.ResultFilters()
    campaign_ids = flt.campaign_ids_for(organization, filters)
    if not campaign_ids or not scope.has_structure_access:
        return {"k": 0, "n": 0, "suppressed": True, "items": []}
    k = flt.k_threshold(campaign_ids)
    base = flt.responses(organization, scope, filters, campaign_ids, section=Section.GENERAL)
    n = base.count()
    baseline = None
    if filters.is_narrowed:
        baseline = flt.responses(
            organization, scope, filters.without_narrowing(), campaign_ids, section=Section.GENERAL
        ).count()
    visible = is_visible(n, k, baseline)
    items = []
    if visible:
        codes = list(
            SurveyAnswer.objects.filter(response__in=base.values("pk"), question__kind=QuestionKind.TEXT)
            .values_list("question__code", flat=True)
            .distinct()
        )
        items = _comments(base, codes, query or filters.text_query, limit=limit, offset=offset)
    return {"k": k, "n": n, "suppressed": not visible, "items": items}


def breakdown(organization, scope, filters=None, *, by="faculty", section=Section.TEACHER) -> dict:
    """Ölçü üzrə qruplaşma (``faculty`` | ``department`` | ``subject`` | ``program`` |
    ``course_year`` | ``group``): ``{"k", "rows": [{"key", "label", ...metrics}]}``."""
    fields = {
        "faculty": ("faculty_id", "faculty__name"),
        "department": ("teacher_department_id", "teacher_department__name"),
        "subject": ("subject_id", "subject__name"),
        "program": ("program_id", "program__name"),
        "course_year": ("course_year", "course_year"),
        "group": ("group_id", "group__name"),
    }
    if by not in fields:
        raise ValueError(f"naməlum qruplaşma: {by}")
    filters = filters or flt.ResultFilters()
    campaign_ids = flt.campaign_ids_for(organization, filters)
    if not campaign_ids or not scope.has_structure_access:
        return {"k": 0, "rows": []}
    k = flt.k_threshold(campaign_ids)
    key, label = fields[by]
    base = flt.responses(organization, scope, filters, campaign_ids, section=section)
    values = (key, label) if key != label else (key,)
    annotations = {
        **_metric_annotations(),
        "satisfaction": Avg("answers__score", filter=Q(answers__question__code="satisfaction")),
        "facilities": Avg("answers__score", filter=Q(answers__question__code="facilities")),
    }
    rows = []
    for row in base.values(*values).annotate(**annotations).order_by(label):
        visible = (row["n"] or 0) >= k
        rows.append(
            {
                "key": row[key],
                "label": row[label] if row[label] is not None else "",
                **_metrics(row, visible),
                "satisfaction": _round(row["satisfaction"]) if visible else None,
                "facilities": _round(row["facilities"]) if visible else None,
            }
        )
    return {"k": k, "rows": rows}


def filter_options(organization, scope, campaign_ids=None) -> dict:
    """Filtr seçimləri — YALNIZ əhatədəki cavablarda mövcud olan dəyərlər (sayı ilə)."""
    campaign_ids = list(campaign_ids or flt.campaign_ids_for(organization, flt.ResultFilters()))
    if not campaign_ids or not scope.has_structure_access:
        return {key: [] for key in ("faculties", "departments", "teachers", "subjects", "groups", "programs")}
    base = flt.responses(organization, scope, flt.ResultFilters(), campaign_ids)
    general = flt.responses(organization, scope, flt.ResultFilters(), campaign_ids, section=Section.GENERAL)

    def _options(queryset, key, label):
        return [
            {"id": row[key], "label": row[label] or "", "n": row["n"]}
            for row in queryset.exclude(**{f"{key}__isnull": True})
            .values(key, label)
            .annotate(n=Count("id"))
            .order_by(label)
        ]

    teachers = list(base.exclude(teacher__isnull=True).values("teacher_id").annotate(n=Count("id")))
    names = _names(row["teacher_id"] for row in teachers)
    return {
        "faculties": _options(base, "faculty_id", "faculty__name"),
        "departments": _options(base, "teacher_department_id", "teacher_department__name"),
        "teachers": sorted(
            ({"id": row["teacher_id"], "label": names.get(row["teacher_id"], ""), "n": row["n"]} for row in teachers),
            key=lambda item: item["label"].lower(),
        ),
        "subjects": _options(base, "subject_id", "subject__name"),
        "groups": _options(base, "group_id", "group__name"),
        "programs": _options(general, "program_id", "program__name"),
    }


def search_teachers(organization, scope, query, campaign_ids=None, *, limit=20) -> list:
    """Əhatədəki (cavabı olan) müəllimlər arasında dözümlü ad axtarışı."""
    name_q = tolerant_q(query, ("teacher__first_name", "teacher__last_name", "teacher__username"))
    if name_q is None:
        return []
    campaign_ids = list(campaign_ids or flt.campaign_ids_for(organization, flt.ResultFilters()))
    base = flt.responses(organization, scope, flt.ResultFilters(), campaign_ids).exclude(teacher__isnull=True)
    rows = list(base.filter(name_q).values("teacher_id").annotate(n=Count("id")).order_by("-n")[:limit])
    names = _names(row["teacher_id"] for row in rows)
    return [{"id": row["teacher_id"], "label": names.get(row["teacher_id"], ""), "n": row["n"]} for row in rows]
