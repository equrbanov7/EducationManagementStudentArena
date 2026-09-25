"""«Ümumi təkliflər» tabı — ümumi bölmə: məmnunluq/şərait, bölgülər, təkliflər, açar sözlər.

Ümumi bölmə cavabı tələbənin öz qrupu/ixtisası/fakültəsi ilə saxlanılır (müəllim
bölməsindən fərqli olaraq), ona görə k-həddi burada xüsusilə vacibdir: bölgü
sətirləri ``safe_breakdown`` (k + tamamlayıcı — burada HƏR filtr daraldıcıdır — +
qardaş xanalar + iç-içə dövr dəstləri), təkliflər isə ``suggestion_digest`` (KAMPANİYA
BAŞINA k) ilə açılır. Saylar səbətlə, paylanma yalnız faizlə (``analytics_guard``).
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .. import public
from ..services import analytics_guard as guard
from .results_labels import likert_labels
from .results_overview import likert_row

CTX = "surveys.results"

LEVELS = ("faculty", "program", "course_year")


def _level_rows(data, level):
    rows = []
    for row in data["rows"]:
        label = row["label"]
        if level == "course_year" and row["key"] is not None:
            label = pgettext(CTX, "Kurs %(year)s") % {"year": row["key"]}
        rows.append(
            {
                "label": str(label) if label not in (None, "") else pgettext(CTX, "Təyin olunmayıb"),
                "n": guard.count_bucket(row["n"]) if not row["suppressed"] else None,
                "suppressed": row["suppressed"],
                "secondary": row.get("secondary", False),
                "satisfaction": row["satisfaction"],
                "facilities": row["facilities"],
            }
        )
    visible = [row for row in rows if not row["suppressed"]]
    visible.sort(key=lambda row: -(row["satisfaction"] or 0))
    return visible + [row for row in rows if row["suppressed"]]


def _level_chart(rows):
    visible = [row for row in rows if not row["suppressed"]]
    return {
        "labels": [row["label"] for row in visible],
        "satisfaction": [row["satisfaction"] for row in visible],
        "facilities": [row["facilities"] for row in visible],
        "n": [row["n"] for row in visible],
        "hidden": len(rows) - len(visible),
    }


def general_tab(organization, scope, filters, summary, *, family=None) -> dict:
    visible = not summary["general_suppressed"]
    digest = public.suggestion_digest(organization, scope, filters, query=filters.text_query)
    digest["total_label"] = guard.count_bucket(digest["total"]) if not digest["suppressed"] else None
    block = {
        "visible": visible,
        "n": guard.count_bucket(summary["general_n"]),
        "has_n": bool(summary["general_n"]),
        "complement_blocked": summary["general_complement_blocked"],
        "questions": [],
        "likert": [],
        "levels": {},
        "level_default": "faculty",
        "digest": digest,
        "likert_scale": likert_labels(),
    }
    chart = {"likert": {"labels": [], "pct": [], "scale": [label for _s, label in likert_labels()]}}
    if visible:
        total_n = summary["general_n"]
        distributions = public.question_distributions(
            organization, scope, filters, section=public.Section.GENERAL, visible=True
        )
        likert = [
            likert_row(
                row["code"],
                row["text"],
                row["buckets"],
                row["n"],
                avg=row["avg"],
                top2=round(row["top2"] * 100) if row["top2"] is not None else None,
            )
            for row in distributions["questions"]
            if row["kind"] == "likert5"
        ]
        levels = {}
        for level in LEVELS:
            data = public.safe_breakdown(
                organization, scope, filters, by=level, section=public.Section.GENERAL, total_n=total_n, family=family
            )
            levels[level] = _level_rows(data, level)
        block.update(
            likert=likert,
            levels=levels,
            level_default=next((level for level in LEVELS if len(levels[level]) > 1), "faculty"),
        )
        chart["likert"].update(labels=[row["label"] for row in likert], pct=[row["pct"] for row in likert])
        chart["levels"] = {level: _level_chart(rows) for level, rows in levels.items()}
        chart["level_default"] = block["level_default"]
    return {"general": block, "general_chart": chart}
