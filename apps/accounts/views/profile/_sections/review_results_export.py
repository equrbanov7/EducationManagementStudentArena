"""«Dəyərləndirilmiş nəticələr» — Excel ixracının sətirləri (sahib 2026-10-27).

Sətirlər kollektorun (``_collect_evaluated_review_items``) ekranda göstərdiyi SİYAHININ özüdür —
eyni əhatə (müəllimin / imtahan mərkəzinin imtahanları, tenant), eyni süzgəclər və sıralama,
yalnız səhifələmə yoxdur. Sütunlar imtahanın öz nəticə səhifəsinin ixracı ilə eynidir
(``apps.exams.public.build_results_xlsx`` → ``COLUMNS``):

* imtahan sətri — ``results_export_attempt_rows`` (bal / maks / faiz, «Yoxlayan» qaydası, zal +
  kompüter, başlama / bitmə / müddət, status, apellyasiya); cəhdlər HİSSƏ-HİSSƏ (200) işlənir ki,
  böyük mərkəz siyahısında cavab sətirləri yaddaşda yığılmasın;
* tapşırıq / kurs işi / lab sətri — kollektorun öz sahələri (bal, yoxlayan, təhvil / yoxlanma anı).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .review_results_ui import _type_label

CHUNK_SIZE = 200


def _score_value(text):
    try:
        number = float(Decimal(str(text)))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    return int(number) if number.is_integer() else round(number, 2)


def _task_row(item, patronymics):
    student = item["student"]
    evaluator = item.get("evaluator_display") or ""
    return {
        "groups": item.get("group_name") or "",
        "parent_group": "",
        "student": student.get_full_name() or student.username,
        "username": student.username,
        "patronymic": patronymics.get(student.pk, ""),
        "email": student.email or "",
        "title": item.get("title") or "",
        "subject": item.get("subject_title") or "",
        "kind": _type_label(item),
        "score": _score_value(item.get("score_display")),
        "checked_by": "" if evaluator == "-" else evaluator,
        "checked_at": item.get("reviewed_at"),
        "finished_at": item.get("submitted_at"),
        "status": item.get("status_display") or "",
    }


def build_review_export_rows(items) -> list[dict]:
    from apps.exams.public import results_export_attempt_rows, results_export_patronymic_map

    group_by_user = {item["student"].pk: item.get("group_name") or "" for item in items}

    def group_lookup(user_id):
        return group_by_user.get(user_id, ""), ""

    exam_items = [item for item in items if item.get("attempt") is not None]
    exam_rows: dict[int, dict] = {}
    for start in range(0, len(exam_items), CHUNK_SIZE):
        chunk = [item["attempt"] for item in exam_items[start : start + CHUNK_SIZE]]
        exam_rows.update(results_export_attempt_rows(chunk, group_lookup=group_lookup))
        for attempt in chunk:  # cavab keşini burax — yaddaş hissə ölçüsü ilə məhdud qalsın
            attempt._prefetched_objects_cache = {}

    patronymics = results_export_patronymic_map(
        item["student"].pk for item in items if item.get("attempt") is None and item.get("student") is not None
    )
    rows = []
    for item in items:
        if item.get("attempt") is not None:
            row = exam_rows.get(item["attempt_id"])
            if row is not None:
                rows.append(row)
            continue
        rows.append(_task_row(item, patronymics))
    return rows


__all__ = ["CHUNK_SIZE", "build_review_export_rows"]
