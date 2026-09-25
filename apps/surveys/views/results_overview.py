"""«Ümumi baxış» tabı — qrafiklərin məlumatı (JSON adası) + eyni rəqəmlərin cədvəlləri.

Hər qrafikin cədvəl qarşılığı SERVERDƏ render olunur (JS olmadan da oxunur, ekran
oxuyucusu üçün əsas mənbə); JS yalnız eyni rəqəmləri Chart.js ilə çəkir.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .. import public
from .results_filters import campaign_label
from .results_labels import likert_labels, short_label

CTX = "surveys.results"


def _pct_list(buckets, total):
    return [round(count * 100 / total, 1) if total else 0 for count in buckets]


def _question_rows(summary, distributions, benchmarks):
    dist = {row["code"]: row for row in distributions}
    rows = []
    for row in summary["questions"]:
        if row["section"] != public.Section.TEACHER or row["kind"] != "likert5":
            continue
        rows.append(
            {
                "code": row["code"],
                "label": short_label(row["code"], row["text"]),
                "text": row["text"],
                "n": row["n"],
                "avg": row["avg"],
                "top2": round(row["top2"] * 100) if row["top2"] is not None else None,
                "bottom2": (
                    round(dist[row["code"]]["bottom2"] * 100)
                    if dist.get(row["code"], {}).get("bottom2") is not None
                    else None
                ),
                "org": benchmarks["org"].get(row["code"]),
                "department": benchmarks["department"].get(row["code"]),
            }
        )
    return rows


def likert_row(code, text, buckets, total, **extra) -> dict:
    """Diverging Likert sətri: saylar, faizlər və cədvəl xanaları (``cells``)."""
    pct = _pct_list(buckets, total)
    return {
        "code": code,
        "label": short_label(code, text),
        "text": text,
        "n": total,
        "counts": list(buckets),
        "pct": pct,
        "cells": [{"count": count, "pct": share} for count, share in zip(buckets, pct)],
        **extra,
    }


def _likert_rows(distributions):
    return [
        likert_row(row["code"], row["text"], row["buckets"], row["n"])
        for row in distributions
        if row["kind"] == "likert5"
    ]


def _histogram(distributions, code):
    row = next((item for item in distributions if item["code"] == code), None)
    if row is None:
        row = next((item for item in distributions if item["kind"] == "scale10"), None)
    if row is None:
        return None
    high = len(row["buckets"])
    return {
        "code": row["code"],
        "label": short_label(row["code"], row["text"]),
        "text": row["text"],
        "n": row["n"],
        "avg": row["avg"],
        "scores": list(range(1, high + 1)),
        "counts": row["buckets"],
        "pct": _pct_list(row["buckets"], row["n"]),
        "rows": [
            {"score": score, "count": count, "pct": pct}
            for score, count, pct in zip(range(1, high + 1), row["buckets"], _pct_list(row["buckets"], row["n"]))
        ],
    }


def trend_block(organization, scope, filters):
    """Dövrlər üzrə dinamika: seçim (+ kafedra) + universitet (kontekst) xətləri."""
    from apps.organizations.public import ORG_WIDE_SCOPE

    selection = public.trend(
        organization,
        scope,
        teacher_id=filters.teacher_id,
        department_id=filters.department_id,
        faculty_id=filters.faculty_id,
    )
    if filters.teacher_id is not None:
        # Müəllim xətti: dövrdə dərc olunmayan müəllimin nöqtəsi gizlədilir (bax analytics_publish).
        published = public.publishable_by_campaign(organization, [point["campaign_id"] for point in selection])
        for point in selection:
            if not point.get("suppressed") and filters.teacher_id not in published.get(point["campaign_id"], set()):
                public.hide_row(point, secondary=True)
    series = [{"key": "selection", "label": pgettext(CTX, "Seçim"), "points": selection}]
    has_units = filters.teacher_id or filters.department_id or filters.faculty_id or not scope.is_org_wide
    if filters.teacher_id and filters.department_id:
        department = public.trend(organization, scope, department_id=filters.department_id)
        series.append({"key": "department", "label": pgettext(CTX, "Kafedra"), "points": department})
    if has_units:
        series.append(
            {"key": "org", "label": pgettext(CTX, "Universitet"), "points": public.trend(organization, ORG_WIDE_SCOPE)}
        )
    labels = [campaign_label(point) for point in selection]
    rows = []
    for index, label in enumerate(labels):
        cells = []
        for item in series:
            point = item["points"][index] if index < len(item["points"]) else {"n": 0, "suppressed": True}
            cells.append(
                {
                    "n": point.get("n", 0),
                    "suppressed": point.get("suppressed", True),
                    "overall": point.get("avg_overall"),
                    "index": point.get("likert_index"),
                }
            )
        rows.append({"label": label, "cells": cells})
    chart = {
        "labels": labels,
        "series": [
            {
                "key": item["key"],
                "label": item["label"],
                "overall": [point.get("avg_overall") for point in item["points"]],
                "index": [point.get("likert_index") for point in item["points"]],
                "n": [point.get("n", 0) for point in item["points"]],
            }
            for item in series
        ],
    }
    return {"series": [{"key": item["key"], "label": item["label"]} for item in series], "rows": rows, "chart": chart}


def _breakdown_rows(data):
    rows = []
    for row in data["rows"]:
        rows.append(
            {
                "key": str(row["key"]) if row["key"] is not None else "",
                "label": row["label"] or pgettext(CTX, "Təyin olunmayıb"),
                "n": row["n"],
                "suppressed": row["suppressed"],
                "secondary": row.get("secondary", False),
                "overall": row["avg_overall"],
                "index": row["likert_index"],
                "recommend": round(row["recommend_top2"] * 100) if row["recommend_top2"] is not None else None,
            }
        )
    visible = sorted((row for row in rows if not row["suppressed"]), key=lambda r: -(r["overall"] or 0))
    hidden = [row for row in rows if row["suppressed"]]
    return visible + hidden


def _breakdown_chart(rows):
    visible = [row for row in rows if not row["suppressed"] and row["overall"] is not None]
    return {
        "labels": [row["label"] for row in visible],
        "values": [row["overall"] for row in visible],
        "n": [row["n"] for row in visible],
        "hidden": len(rows) - len(visible),
    }


def overview_tab(organization, scope, filters, summary, query) -> dict:
    """``{"overview": {...}, "overview_chart": {...}}`` — gizli dəstdə yalnız dinamika qalır."""
    trend = trend_block(organization, scope, filters)
    if summary["suppressed"]:
        return {"overview": {"visible": False, "trend": trend}, "overview_chart": {"trend": trend["chart"]}}
    total_n = summary["n"]
    distributions = public.question_distributions(organization, scope, filters)["questions"]
    narrower = filters.teacher_id is not None or filters.is_narrowed
    benchmarks = public.question_benchmarks(
        organization,
        scope,
        summary["campaign_ids"],
        department_id=filters.department_id if narrower else None,
    )
    questions = _question_rows(summary, distributions, benchmarks)
    likert = _likert_rows(distributions)
    histogram = _histogram(distributions, filters.question_code or "overall")
    faculties = _breakdown_rows(public.safe_breakdown(organization, scope, filters, by="faculty", total_n=total_n))
    departments = _breakdown_rows(public.safe_breakdown(organization, scope, filters, by="department", total_n=total_n))
    default_level = "department" if filters.faculty_id or len(faculties) <= 1 else "faculty"
    org_avg = None
    if not scope.is_org_wide or filters.faculty_id or filters.department_id or filters.teacher_id:
        org_avg = benchmarks["org"].get("overall")
    chart = {
        "questions": {
            "labels": [row["label"] for row in questions],
            "values": [row["avg"] for row in questions],
            "org": [row["org"] for row in questions],
            "department": [row["department"] for row in questions] if narrower and filters.department_id else [],
            "n": [row["n"] for row in questions],
        },
        "likert": {
            "labels": [row["label"] for row in likert],
            "counts": [row["counts"] for row in likert],
            "pct": [row["pct"] for row in likert],
            "scale": [label for _score, label in likert_labels()],
        },
        "histogram": histogram,
        "trend": trend["chart"],
        "breakdown": {
            "default": default_level,
            "faculty": _breakdown_chart(faculties),
            "department": _breakdown_chart(departments),
            "org_avg": org_avg,
        },
    }
    return {
        "overview": {
            "visible": True,
            "questions": questions,
            "likert": likert,
            "likert_scale": likert_labels(),
            "histogram": histogram,
            "trend": trend,
            "faculties": faculties,
            "departments": departments,
            "breakdown_levels": [("faculty", faculties), ("department", departments)],
            "breakdown_default": default_level,
            "show_department_ref": bool(narrower and filters.department_id),
        },
        "overview_chart": chart,
    }
