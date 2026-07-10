"""exam_center paketi — statistika qrafikləri + AI analiz endpointləri.

``exam_center_stats_data`` ilə eyni filtrləri qəbul edir (q, subjects, groups,
units, type, year) və bütün filtrlənmiş nəticələr üzərində DB-side aqreqatlar
qaytarır — cədvəl səhifələnməsindən asılı deyil.

Faiz metrikası test imtahanları üzrə ``correct_count/(correct+wrong)``
düsturudur (müəllim statistikası səhifəsi ilə eyni yanaşma) — bütün cəhdləri
Python-a yükləmədən miqyaslanır. Apellyasiya bonusları bu aqreqatlara daxil
deyil (cədvəldəki fərdi faizlərdən cüzi fərqlənə bilər).

AI analiz: mövcud ``ai_summary`` servisi — data-hash keş + istifadəçi-başına
rate limit orada tətbiq olunur (dəyişməyən data üçün API çağırışı sərf olunmur).
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, F, FloatField, Q, Value
from django.db.models.functions import Floor, NullIf, TruncMonth
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.exams.models import Exam
from apps.exams.services.ai_summary import generate_exam_statistics_summary

from .statistics import _filtered_attempts, _stats_org

# Keçmə həddi (faizlə) — müəllim statistikası səhifəsindəki default ilə eyni.
_PASS_THRESHOLD = 50

# Test cəhdi faizi: correct*100/(correct+wrong); cavabsız cəhd (0+0) → NULL.
_PCT = F("correct_count") * 100.0 / NullIf(F("correct_count") + F("wrong_count"), Value(0))


def _scored(qs):
    """Faizi hesablana bilən (test tipli, ən azı 1 cavablı) cəhdlər."""
    return qs.filter(exam__exam_type="test").annotate(pct=_PCT).filter(pct__isnull=False)


def _rnd(value):
    return round(value, 1) if value is not None else None


def _distribution(scored):
    """10 faizlik zolaqlar üzrə cəhd sayı (90-100 son zolaqda birləşir)."""
    rows = (
        scored.annotate(bucket=Floor(F("pct") / Value(10.0), output_field=FloatField()))
        .values("bucket")
        .annotate(n=Count("id", distinct=True))
        .order_by("bucket")
    )
    counts = [0] * 10
    for row in rows:
        bucket = min(9, max(0, int(row["bucket"] or 0)))
        counts[bucket] += row["n"]
    labels = [f"{i * 10}-{i * 10 + 9}" for i in range(9)] + ["90-100"]
    return {"labels": labels, "counts": counts}


def _monthly(qs, limit=24):
    """Ay üzrə cəhd sayı + orta faiz (son ``limit`` ay)."""
    rows = list(
        qs.annotate(month=TruncMonth("started_at"))
        .values("month")
        .annotate(
            n=Count("id", distinct=True),
            avg_pct=Avg(_PCT, filter=Q(exam__exam_type="test")),
        )
        .order_by("month")
    )[-limit:]
    return {
        "labels": [row["month"].strftime("%Y-%m") for row in rows if row["month"]],
        "counts": [row["n"] for row in rows if row["month"]],
        "avg": [_rnd(row["avg_pct"]) for row in rows if row["month"]],
    }


def _by_type(qs):
    label_map = dict(Exam.EXAM_TYPE_EXTENDED_CHOICES)
    rows = (
        qs.values("exam__exam_type_extended")
        .annotate(
            n=Count("id", distinct=True),
            avg_pct=Avg(_PCT, filter=Q(exam__exam_type="test")),
        )
        .order_by("-n")
    )
    labels, counts, avg = [], [], []
    for row in rows:
        raw = row["exam__exam_type_extended"]
        labels.append(str(label_map.get(raw, raw or "—")))
        counts.append(row["n"])
        avg.append(_rnd(row["avg_pct"]))
    return {"labels": labels, "counts": counts, "avg": avg}


def _by_subject(qs, limit=10):
    rows = (
        qs.exclude(exam__subject__isnull=True)
        .values("exam__subject__code", "exam__subject__name")
        .annotate(
            n=Count("id", distinct=True),
            avg_pct=Avg(_PCT, filter=Q(exam__exam_type="test")),
        )
        .order_by("-n")[:limit]
    )
    labels, counts, avg = [], [], []
    for row in rows:
        labels.append(f"{row['exam__subject__code']} — {row['exam__subject__name']}")
        counts.append(row["n"])
        avg.append(_rnd(row["avg_pct"]))
    return {"labels": labels, "counts": counts, "avg": avg}


def _chart_payload(qs):
    scored = _scored(qs)
    pass_count = scored.filter(pct__gte=_PASS_THRESHOLD).count()
    fail_count = scored.filter(pct__lt=_PASS_THRESHOLD).count()
    return {
        "distribution": _distribution(scored),
        "monthly": _monthly(qs),
        "by_type": _by_type(qs),
        "by_subject": _by_subject(qs),
        "pass_fail": {
            "threshold": _PASS_THRESHOLD,
            "pass": pass_count,
            "fail": fail_count,
        },
        "avg_percent": _rnd(scored.aggregate(v=Avg("pct"))["v"]),
    }


@login_required
@require_GET
def exam_center_stats_charts(request):
    """Filtrlənmiş nəticələr üzrə qrafik aqreqatları (JSON)."""
    organization = _stats_org(request)
    qs = _filtered_attempts(request, organization)
    return JsonResponse(_chart_payload(qs))


@login_required
@require_GET
def exam_center_stats_ai(request):
    """Filtrlənmiş statistikanın AI ümumiləşdirməsi (keş + rate limit servisdə)."""
    organization = _stats_org(request)
    qs = _filtered_attempts(request, organization)
    payload = _chart_payload(qs)

    total = payload["pass_fail"]["pass"] + payload["pass_fail"]["fail"]
    stats = {
        "scope": "exam center — aggregated results across many exams",
        "total_attempts": qs.count(),
        "distinct_students": qs.values("user_id").distinct().count(),
        "distinct_exams": qs.values("exam_id").distinct().count(),
        "avg_percent": payload["avg_percent"],
        "pass_threshold_percent": _PASS_THRESHOLD,
        "pass_count": payload["pass_fail"]["pass"],
        "fail_count": payload["pass_fail"]["fail"],
        "pass_rate": _rnd(payload["pass_fail"]["pass"] * 100 / total) if total else None,
        "score_distribution": [
            {"range_percent": lbl, "count": n}
            for lbl, n in zip(payload["distribution"]["labels"], payload["distribution"]["counts"])
        ],
        "monthly_trend": [
            {"month": m, "attempts": n, "avg_percent": a}
            for m, n, a in zip(payload["monthly"]["labels"], payload["monthly"]["counts"], payload["monthly"]["avg"])
        ],
        "by_exam_type": [
            {"type": t, "attempts": n, "avg_percent": a}
            for t, n, a in zip(payload["by_type"]["labels"], payload["by_type"]["counts"], payload["by_type"]["avg"])
        ],
        "top_subjects": [
            {"subject": s, "attempts": n, "avg_percent": a}
            for s, n, a in zip(
                payload["by_subject"]["labels"], payload["by_subject"]["counts"], payload["by_subject"]["avg"]
            )
        ],
        "applied_filters": {
            "year": (request.GET.get("year") or "").strip(),
            "exam_type": (request.GET.get("type") or "").strip(),
            "student_search": (request.GET.get("q") or "").strip(),
        },
    }
    result = generate_exam_statistics_summary(
        exam_title=f"{organization.name} — imtahan mərkəzi statistikası",
        exam_type="exam-center aggregate",
        stats=stats,
        user_id=request.user.pk,
    )
    return JsonResponse(result)


__all__ = [
    "exam_center_stats_ai",
    "exam_center_stats_charts",
]
