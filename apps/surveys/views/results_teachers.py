"""«Müəllimlər» tabı — reytinq cədvəli (sıralama, top/bottom 10, minimum n, axtarış).

Server bütün sətirləri (≤ 500, F1 ``teacher_table`` tavanı) ilkin ``er_sort`` sırası
ilə render edir; kliyent (``results_table.js``) eyni sətirləri sıralayır, süzür və
səhifələyir — hər klikdə server sorğusu yoxdur. Gizli sətirlər (``n < k``,
tamamlayıcı və ikinci dərəcəli qayda) yalnız cavab sayını göstərir.
"""

from __future__ import annotations

from .. import public
from .results_labels import DEFAULT_SORT, MIN_N_CHOICES, PAGE_SIZE, short_label


def _sort_value(row, key):
    if key == "teacher_name":
        return (row.get("teacher_name") or "").lower()
    return row.get(key)


def sort_rows(rows, sort) -> list:
    """``sort`` = açar və ya ``-açar``; boş dəyərlər istiqamətdən asılı olmayaraq sonda."""
    sort = sort or DEFAULT_SORT
    key, reverse = sort.lstrip("-"), sort.startswith("-")
    present = [row for row in rows if _sort_value(row, key) is not None]
    missing = [row for row in rows if _sort_value(row, key) is None]
    present.sort(key=lambda row: (_sort_value(row, key), row.get("teacher_name") or ""), reverse=reverse)
    missing.sort(key=lambda row: row.get("teacher_name") or "")
    return present + missing


def _pct(value):
    return None if value is None else round(float(value) * 100)


def teachers_tab(organization, scope, filters, summary, query, urls, published=None) -> dict:
    campaign_ids = summary["campaign_ids"]
    participation = public.participation_rows(organization, scope, filters, campaign_ids)
    table = public.teacher_table(organization, scope, filters)
    k = table["k"] or summary["k"]
    rows = table["rows"]
    if published is None:
        published = public.publishable_teachers(organization, campaign_ids)
    for row in rows:
        if not row["suppressed"] and row["teacher_id"] not in published:
            public.hide_row(row, secondary=True)
    question = filters.question_code
    scores = public.teacher_question_scores(organization, scope, filters, question) if question else {}
    approximate = participation.get("approximate")
    for row in rows:
        part = participation["teachers"].get(row["teacher_id"], {})
        row["receipts"] = part.get("receipts", 0)
        row["expected"] = part.get("expected", 0)
        row["rate"] = None if approximate else part.get("rate")
        score = scores.get(row["teacher_id"]) if question and not row["suppressed"] else None
        row["question_avg"] = score["avg"] if score and score["n"] >= k else None
    public.secondary_suppress(
        rows, k=k, total_n=None if summary["suppressed"] else summary["n"], label_key="teacher_name"
    )
    ranked = sorted(
        (row for row in rows if not row["suppressed"] and row["avg_overall"] is not None),
        key=lambda row: (-row["avg_overall"], -(row["likert_index"] or 0), row["teacher_name"]),
    )
    for position, row in enumerate(ranked, start=1):
        row["rank"] = position
    detail_base, detail_qs = urls["detail_base"], urls["detail_qs"]
    items = []
    for row in sort_rows(rows, query.sort):
        items.append(
            {
                "id": row["teacher_id"],
                "name": row["teacher_name"] or "—",
                "department": row["department_name"] or "",
                "n": row["n"],
                "receipts": row["receipts"],
                "expected": row["expected"],
                "rate": _pct(row["rate"]),
                "rate_raw": row["rate"],
                "overall": row["avg_overall"],
                "index": row["likert_index"],
                "recommend": _pct(row["recommend_top2"]),
                "delta_department": row["delta_department_overall"],
                "delta_org": row["delta_org_overall"],
                "question_avg": row["question_avg"],
                "suppressed": row["suppressed"],
                "secondary": row.get("secondary", False),
                "rank": row.get("rank"),
                "detail_url": (
                    f"{detail_base}{row['teacher_id']}/?{detail_qs}"
                    if detail_qs
                    else f"{detail_base}{row['teacher_id']}/"
                ),
            }
        )
    visible = len(ranked)
    data = [
        {
            "name": item["name"],
            "department": item["department"],
            "n": item["n"],
            "rate": item["rate_raw"],
            "avg_overall": item["overall"],
            "likert_index": item["index"],
            "recommend_top2": item["recommend"],
            "delta_department_overall": item["delta_department"],
            "delta_org_overall": item["delta_org"],
            "question_avg": item["question_avg"],
            "rank": item["rank"],
            "visible": not item["suppressed"],
        }
        for item in items
    ]
    return {
        "participation": participation,
        "teachers": {
            "rows": items,
            "data": data,
            "k": k,
            "visible": visible,
            "hidden": len(items) - visible,
            "truncated": summary["teachers"] > len(items),
            "question": question,
            "question_label": short_label(question) if question else "",
            "sort": query.sort,
            "min_choices": MIN_N_CHOICES,
            "page_size": PAGE_SIZE,
            "top_n": min(10, visible),
            "rate_hidden": bool(approximate),
        },
    }
