"""Nəticə analitikası — xülasə, müəllim cədvəli, paylanma (hamısı SQL aqreqasiyası).

k-ANONİMLİK (hər funksiyada eyni qayda):

1. ``n < k`` olan hər qrupun QİYMƏTLƏRİ ``None``-dur, ``suppressed=True`` (say ``n``
   qalır — o, cavabın məzmununu yox, iştirakı bildirir).
2. **Tamamlayıcı qayda** — daraldıcı filtr (fənn/qrup/ixtisas/kurs) varsa, eyni
   müəllimin (və ya dəstin) daralmamış ümumi sayı ilə fərq ``0 < N−n < k`` olarsa
   da gizlədilir: əks halda «ümumi − süzülmüş» çıxma əməliyyatı qalan az sayda
   tələbənin cavabını açardı (differencing hücumu).
3. Heç bir funksiya cavab id-si, qəbz, tələbə və ya vaxt qaytarmır.

Ölçülər: ``avg_overall`` (1–10, ``scale10`` sualı), ``likert_index`` (1–5, indeksə
daxil Likert sualları; ``likert_index_pct`` = (x−1)/4·100), ``top2`` (4–5 cavab
payı, 0–1), ``recommend_top2`` (``recommend`` sualı üzrə).
"""

from __future__ import annotations

from django.db.models import Avg, Count, Q

from ..constants import QuestionKind, Section
from ..models import SurveyAnswer, SurveyQuestion
from . import filters as flt
from .participation import participation

_OVERALL_Q = Q(answers__question__kind=QuestionKind.SCALE10)
_INDEX_Q = Q(answers__question__kind=QuestionKind.LIKERT5, answers__question__in_index=True)
_RECOMMEND_Q = Q(answers__question__code="recommend", answers__score__isnull=False)
_RECOMMEND_TOP_Q = Q(answers__question__code="recommend", answers__score__gte=4)


def _round(value, digits=2):
    return round(float(value), digits) if value is not None else None


def index_pct(likert_index):
    return _round((likert_index - 1) / 4 * 100, 1) if likert_index is not None else None


def is_visible(n, k, baseline=None) -> bool:
    """k-qaydası + tamamlayıcı qayda (``baseline`` — daralmamış ümumi say)."""
    if n < k:
        return False
    if baseline is not None and 0 < baseline - n < k:
        return False
    return True


def _metric_annotations():
    return {
        "n": Count("id", distinct=True),
        "avg_overall": Avg("answers__score", filter=_OVERALL_Q),
        "likert_index": Avg("answers__score", filter=_INDEX_Q),
        "recommend_n": Count("answers", filter=_RECOMMEND_Q),
        "recommend_top": Count("answers", filter=_RECOMMEND_TOP_Q),
    }


def _metrics(row, visible) -> dict:
    likert = _round(row.get("likert_index")) if visible else None
    recommend_n = row.get("recommend_n") or 0
    return {
        "n": row.get("n") or 0,
        "suppressed": not visible,
        "avg_overall": _round(row.get("avg_overall")) if visible else None,
        "likert_index": likert,
        "likert_index_pct": index_pct(likert) if visible else None,
        "recommend_top2": _round(row.get("recommend_top", 0) / recommend_n, 4) if visible and recommend_n else None,
    }


def aggregate_metrics(queryset) -> dict:
    return queryset.aggregate(**_metric_annotations())


def question_stats(queryset, *, visible) -> list:
    """Hər ballı sual üzrə orta + n + top2 (``visible`` yalan → yalnız sual siyahısı)."""
    rows = (
        SurveyAnswer.objects.filter(response__in=queryset.values("pk"), score__isnull=False)
        .values("question__code", "question__kind", "question__text", "question__order", "question__section")
        .annotate(
            n=Count("id"),
            avg=Avg("score"),
            top=Count("id", filter=Q(score__gte=4, question__kind=QuestionKind.LIKERT5)),
        )
        .order_by("question__order", "question__code")
    )
    from django.utils.translation import pgettext

    items = []
    for row in rows:
        is_likert = row["question__kind"] == QuestionKind.LIKERT5
        items.append(
            {
                "code": row["question__code"],
                "kind": row["question__kind"],
                "section": row["question__section"],
                "text": pgettext("surveys.question", row["question__text"]),
                "n": row["n"],
                "avg": _round(row["avg"]) if visible else None,
                "top2": _round(row["top"] / row["n"], 4) if visible and is_likert and row["n"] else None,
            }
        )
    return items


def summary(organization, scope, filters=None) -> dict:
    """Filtrlənmiş dəstin ümumi göstəriciləri + iştirak (bax modul sənədi)."""
    filters = filters or flt.ResultFilters()
    campaign_ids = flt.campaign_ids_for(organization, filters)
    k = flt.k_threshold(campaign_ids) if campaign_ids else 0
    if not campaign_ids or not scope.has_structure_access:
        return {"k": k, "campaign_ids": campaign_ids, "n": 0, "suppressed": True, "questions": [], "participation": {}}
    base = flt.responses(organization, scope, filters, campaign_ids)
    row = aggregate_metrics(base)
    baseline = None
    if filters.is_narrowed:
        baseline = flt.responses(organization, scope, filters.without_narrowing(), campaign_ids).count()
    visible = is_visible(row["n"] or 0, k, baseline)
    general = flt.responses(organization, scope, filters, campaign_ids, section=Section.GENERAL)
    general_n = general.count()
    general_baseline = None
    if filters.is_narrowed:
        general_baseline = flt.responses(
            organization, scope, filters.without_narrowing(), campaign_ids, section=Section.GENERAL
        ).count()
    return {
        "k": k,
        "campaign_ids": campaign_ids,
        **_metrics(row, visible),
        "teachers": base.values("teacher_id").distinct().count(),
        "questions": question_stats(base, visible=visible),
        "general_n": general_n,
        "general_questions": question_stats(general, visible=is_visible(general_n, k, general_baseline)),
        "participation": participation(organization, scope, filters, campaign_ids),
    }


def _baseline_counts(organization, scope, filters, campaign_ids, key) -> dict:
    rows = (
        flt.responses(organization, scope, filters.without_narrowing(), campaign_ids)
        .values(key)
        .annotate(n=Count("id"))
    )
    return {row[key]: row["n"] for row in rows}


def _names(user_ids) -> dict:
    from django.contrib.auth import get_user_model

    return {
        pk: (f"{first} {last}".strip() or username)
        for pk, first, last, username in get_user_model()
        .objects.filter(pk__in=set(user_ids))
        .values_list("pk", "first_name", "last_name", "username")
    }


def _unit_names(unit_ids) -> dict:
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return dict(OrgUnit.objects.filter(pk__in={pk for pk in unit_ids if pk}).values_list("pk", "name"))


def department_benchmarks(organization, campaign_ids, k) -> dict:
    """``{department_id: metrics}`` + ``"__org__"`` açarında təşkilat ortası (əhatədən asılı DEYİL).

    Bench — aqreqat müqayisə nöqtəsidir (≥ k cavab), fərdi məlumat vermir.
    """
    from apps.organizations.public import ORG_WIDE_SCOPE

    base = flt.responses(organization, ORG_WIDE_SCOPE, flt.ResultFilters(), campaign_ids)
    result = {}
    for row in base.values("teacher_department_id").annotate(**_metric_annotations()):
        result[row["teacher_department_id"]] = _metrics(row, (row["n"] or 0) >= k)
    org_row = aggregate_metrics(base)
    result["__org__"] = _metrics(org_row, (org_row["n"] or 0) >= k)
    return result


def _delta(value, bench):
    if value is None or bench is None:
        return None
    return _round(value - bench)


def teacher_table(organization, scope, filters=None, *, order_by="-avg_overall", limit=500) -> dict:
    """Müəllim üzrə sətirlər: ``{"k", "rows": [...], "org": metrics}`` (bax modul sənədi).

    Sətir: ``teacher_id``, ``teacher_name``, ``department_id``, ``department_name``,
    ``n``, ``suppressed``, ``avg_overall``, ``likert_index``, ``likert_index_pct``,
    ``recommend_top2``, ``delta_department_overall``, ``delta_org_overall``,
    ``delta_department_index``, ``delta_org_index``.
    """
    filters = filters or flt.ResultFilters()
    campaign_ids = flt.campaign_ids_for(organization, filters)
    if not campaign_ids or not scope.has_structure_access:
        return {"k": 0, "rows": [], "org": {}}
    k = flt.k_threshold(campaign_ids)
    base = flt.responses(organization, scope, filters, campaign_ids).exclude(teacher__isnull=True)
    grouped = list(base.values("teacher_id").annotate(**_metric_annotations()))
    baseline = _baseline_counts(organization, scope, filters, campaign_ids, "teacher_id") if filters.is_narrowed else {}
    departments = {}
    for row in base.values("teacher_id", "teacher_department_id").annotate(c=Count("id")).order_by("-c"):
        departments.setdefault(row["teacher_id"], row["teacher_department_id"])
    bench = department_benchmarks(organization, campaign_ids, k)
    names = _names(row["teacher_id"] for row in grouped)
    unit_names = _unit_names(departments.values())
    rows = []
    for row in grouped:
        teacher_id = row["teacher_id"]
        visible = is_visible(row["n"] or 0, k, baseline.get(teacher_id) if filters.is_narrowed else None)
        metrics = _metrics(row, visible)
        department_id = departments.get(teacher_id)
        dept = bench.get(department_id, {})
        org = bench["__org__"]
        rows.append(
            {
                "teacher_id": teacher_id,
                "teacher_name": names.get(teacher_id, ""),
                "department_id": department_id,
                "department_name": unit_names.get(department_id, ""),
                **metrics,
                "delta_department_overall": _delta(metrics["avg_overall"], dept.get("avg_overall")),
                "delta_org_overall": _delta(metrics["avg_overall"], org.get("avg_overall")),
                "delta_department_index": _delta(metrics["likert_index"], dept.get("likert_index")),
                "delta_org_index": _delta(metrics["likert_index"], org.get("likert_index")),
            }
        )
    reverse = order_by.startswith("-")
    key = order_by.lstrip("-")
    if key == "teacher_name":
        rows.sort(key=lambda r: r["teacher_name"].lower(), reverse=reverse)
    else:
        rows.sort(key=lambda r: (r.get(key) is None, -(r.get(key) or 0) if reverse else (r.get(key) or 0)))
    return {"k": k, "rows": rows[:limit], "org": bench["__org__"]}


def distribution(organization, scope, question_code, filters=None) -> dict:
    """Bir sualın cavab paylanması: ``{"code", "kind", "n", "suppressed", "buckets": [{"score", "count"}]}``."""
    filters = filters or flt.ResultFilters()
    campaign_ids = flt.campaign_ids_for(organization, filters)
    if not campaign_ids or not scope.has_structure_access:
        return {"code": question_code, "n": 0, "suppressed": True, "buckets": []}
    k = flt.k_threshold(campaign_ids)
    meta = (
        SurveyQuestion.objects.filter(code=question_code, template__campaigns__in=campaign_ids)
        .values_list("section", "kind")
        .first()
    )
    if meta is None:
        return {"code": question_code, "n": 0, "suppressed": True, "buckets": []}
    section, kind = meta
    base = flt.responses(organization, scope, filters, campaign_ids, section=section)
    answers = SurveyAnswer.objects.filter(response__in=base.values("pk"), question__code=question_code)
    answers = answers.filter(score__isnull=False)
    n = answers.count()
    baseline = None
    if filters.is_narrowed:
        wide = flt.responses(organization, scope, filters.without_narrowing(), campaign_ids, section=section)
        baseline = SurveyAnswer.objects.filter(
            response__in=wide.values("pk"), question__code=question_code, score__isnull=False
        ).count()
    visible = is_visible(n, k, baseline)
    buckets = []
    if visible:
        counts = dict(answers.values("score").annotate(c=Count("id")).values_list("score", "c"))
        high = 10 if kind == QuestionKind.SCALE10 else 5
        buckets = [{"score": score, "count": counts.get(score, 0)} for score in range(1, high + 1)]
    return {"code": question_code, "kind": kind, "k": k, "n": n, "suppressed": not visible, "buckets": buckets}
