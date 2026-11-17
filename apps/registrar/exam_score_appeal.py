"""İmtahan balı + APELLYASİYA balı — iki xana, apellyasiya üstündür (sahib 2026-11-17).

Sahib: «imtahan balının daxil edilməsi — balın yanında appel xanası da olsun, yəni 2 xana. Appelyasiya xanasından
gələn bal əsas götürülür.»

YENİ HƏQİQƏT MƏNBƏYİ YOXDUR. Hər iki xana mövcud append-only ``ExamScoreEntry`` jurnalından oxunur və effektiv bal
əvvəlki kimi tək yerdədir (final → ``FinalGrade.exam_score``, midterm → jurnalın «Midterm» ``ComponentScore``-u) —
yekun bal, transkript, kabinet və jurnal heç nəyi ayrıca hesablamır:

* **Apellyasiya balı** — sətrin (qeydiyyat × imtahan) ƏN SON yazısı ``kind=appeal``-dırsa onun ``new_score``-u.
  Rəqəmsal apellyasiyanın jurnal sətri (``exam_score_entry.record_appeal_score_change``) də eyni növdədir.
* **İmtahan balı** — apellyasiyadan əvvəlki bal: sonuncu ``kind != appeal`` sətrinin ``new_score``-u; belə sətir
  yoxdursa (onlayn imtahan + rəqəmsal apellyasiya) apellyasiya zəncirinin ilk sətrinin ``old_score``-u.
  Apellyasiya yoxdursa imtahan balı = effektiv bal.
* **Üstünlük** — apellyasiya balı yazılandan sonra imtahan xanası KİLİDLİDİR (forma onu göndərmir; server də
  dəyişikliyi rədd edir — :func:`guard_exam_rows`). Belə olduqda effektiv bal həmişə apellyasiya balıdır:
  «son sətir apellyasiyadırsa effektiv = apellyasiya» invariantı pozulmur.
* **Yazı** — apellyasiya xanası ``kind=appeal`` sətri kimi MÖVCUD yazıcılardan keçir (``exam_score_bulk`` /
  ``exam_score_midterm``): icazə (İmtahan Mərkəzinin / RİM rəhbəri, superadmin), apellyasiya SƏNƏDİ və bitmiş dövr
  qaydası ``exam_score_assessment.decide_after_window`` / ``change_decision`` ilə eynidir. İmtahan balı hələ
  yazılmayıbsa apellyasiya yazılmır (``appeal_cell`` bayrağı — ilkin daxiletmə apellyasiya kimi düşməsin).
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.utils.translation import pgettext

from .models import Enrollment, ExamScoreEntry, ExamScoreEntryKind

_CTX = "registrar.exam_score_entry"

APPEAL = ExamScoreEntryKind.APPEAL
#: POST açarı: ``appeal__<enrollment_id>`` — imtahan balının ``score__<enrollment_id>`` qardaşı.
FIELD_PREFIX = "appeal__"


# ── Göstəriş: iki xananın dəyərləri ─────────────────────────────────────────


def split_entries(entries) -> tuple:
    """``(imtahan, apellyasiya)`` — ``entries`` ən yenidən köhnəyə (``entry_row`` lüğətləri: ``kind``/``old``/``new``).

    Apellyasiya yoxdursa ``(None, None)`` — çağıran effektiv balı imtahan balı kimi göstərir.
    """
    if not entries or entries[0].get("kind") != APPEAL:
        return None, None
    appeal = entries[0].get("new")
    for entry in entries:
        if entry.get("kind") != APPEAL:
            return entry.get("new"), appeal
    return entries[-1].get("old"), appeal


def _display(value) -> str:
    return "" if value in (None, "", "—") else str(value)


def attach_row(row) -> None:
    """Siyahı sətrinə ``appeal_display`` / ``appeal_set`` qoyur; apellyasiya varsa ``exam_display`` = imtahan balı.

    Sual bölgüsü də imtahan sətrindən götürülür (apellyasiya sətrində sual balları yoxdur).
    ``_attach_question_cells``-dən ƏVVƏL çağırılır.
    """
    entries = row.get("entries") or []
    exam, appeal = split_entries(entries)
    row["appeal_set"] = appeal not in (None, "", "—")
    row["appeal_display"] = _display(appeal) if row["appeal_set"] else ""
    if not row["appeal_set"]:
        return
    row["exam_base_display"] = _display(exam)
    for entry in entries:
        if entry.get("kind") != APPEAL:
            row["question_scores"] = list(entry.get("question_scores") or [])
            break
    else:
        row["question_scores"] = []


# ── Yazı: sətirlərin ayrılması və qoruyucu ──────────────────────────────────


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def latest_appeals(enrollment_ids, assessment) -> dict:
    """``{enrollment_id: new_score}`` — ən son yazısı apellyasiya olan sətirlər (BİR sorğu, Postgres DISTINCT ON)."""
    ids = [value for value in (_uuid(raw) for raw in enrollment_ids) if value is not None]
    if not ids:
        return {}
    rows = (
        ExamScoreEntry.objects.filter(enrollment_id__in=ids, assessment=assessment)
        .order_by("enrollment_id", "-created_at")
        .distinct("enrollment_id")
        .values_list("enrollment_id", "kind", "new_score")
    )
    return {str(enrollment_id): new_score for enrollment_id, kind, new_score in rows if kind == APPEAL}


def _decimal(raw):
    text = str(raw).strip() if raw is not None else ""
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _blank_questions(values) -> bool:
    return not values or all(not str(value or "").strip() for value in values)


def appeal_locked_message() -> str:
    return pgettext(
        _CTX,
        "Bu tələbənin apellyasiya balı var — əsas bal apellyasiya balıdır. Dəyişikliyi «Apellyasiya balı» xanasında edin.",
    )


def guard_exam_rows(rows, appeals) -> tuple:
    """İmtahan xanası sətirləri → ``(yazılacaq sətirlər, rədd olunan {enrollment_id: mesaj})``.

    Apellyasiya balı olan sətirdə imtahan balı dəyişmir: eyni bal (köhnə forma / idxal) səssizcə atılır,
    fərqli bal rədd olunur. Boş sətir toxunulmadan keçir (yazıcı onu onsuz da ötürür).
    """
    kept, rejected = [], {}
    for row in rows:
        key = str(row.get("enrollment_id") or "")
        if key not in appeals:
            kept.append(row)
            continue
        questions = row.get("question_scores")
        score = _decimal(row.get("score"))
        if _blank_questions(questions) and score is None:
            kept.append(row)
            continue
        if _blank_questions(questions) and score == appeals[key]:
            continue
        rejected[key] = appeal_locked_message()
    return kept, rejected


def appeal_rows(post, *, reason="", note="") -> list:
    """``appeal__<id>`` sahələri → yazıcı sətirləri (``kind=appeal``, ``appeal_cell``); boş xana atılır.

    Cari apellyasiya balı ilə EYNİ dəyər :func:`save_rows`-da atılır (forma hər sətrin cari dəyərini göndərir).
    """
    rows = []
    for key, raw in post.items():
        if not key.startswith(FIELD_PREFIX) or str(raw or "").strip() == "":
            continue
        rows.append(
            {
                "enrollment_id": key[len(FIELD_PREFIX) :],
                "score": raw,
                "question_scores": None,
                "kind": APPEAL,
                "appeal_cell": True,
                "reason": reason,
                "note": note,
                "evidence": None,
            }
        )
    return rows


def no_exam_score_message() -> str:
    return pgettext(_CTX, "Apellyasiya balı yalnız imtahan balı yazılmış tələbəyə yazılır.")


def _empty_result() -> dict:
    return {"written": 0, "skipped": 0, "failed": 0, "total": 0, "errors": [], "failed_by_enrollment": {}}


def save_rows(writer, *, offering, rows, by_user, request, sheet, policy, rules) -> dict:
    """``save_roster_scores``-un yazısı: əvvəl imtahan xanaları, sonra apellyasiya xanaları (eyni yazıcı).

    ``writer`` — ``exam_score_bulk`` (final) və ya ``exam_score_midterm``. Apellyasiyası olan sətrin imtahan
    balı dəyişmir (:func:`guard_exam_rows`); cari apellyasiya balı ilə eyni xana yazılmır.
    """
    assessment = getattr(sheet, "assessment", None) or "final"
    cells = [row for row in rows if row.get("appeal_cell")]
    exam = [row for row in rows if not row.get("appeal_cell")]
    appeals = latest_appeals([row.get("enrollment_id") for row in rows], assessment)
    exam, rejected = guard_exam_rows(exam, appeals)
    cells = [
        row
        for row in cells
        if not (str(row["enrollment_id"]) in appeals and _decimal(row["score"]) == appeals[str(row["enrollment_id"])])
    ]
    common = {"offering": offering, "by_user": by_user, "request": request, "sheet": sheet, "policy": policy}
    first = writer.save_rows(rows=exam, rules=rules, **common) if exam else _empty_result()
    second = writer.save_rows(rows=cells, rules=rules, **common) if cells else None
    return merge_results(first, second, rejected=rejected, offering=offering)


def merge_results(first, second, *, rejected=None, offering=None) -> dict:
    """İki yazının (imtahan + apellyasiya) nəticəsini bir ``save_roster_scores`` nəticəsinə birləşdirir."""
    result = {
        "written": first["written"] + (second["written"] if second else 0),
        "skipped": first["skipped"] + (second["skipped"] if second else 0),
        "failed": first["failed"] + (second["failed"] if second else 0),
        "total": first["total"] + (second["total"] if second else 0),
        "errors": list(first["errors"]) + (list(second["errors"]) if second else []),
        "failed_by_enrollment": {**first["failed_by_enrollment"], **(second["failed_by_enrollment"] if second else {})},
        "written_ids": list(first.get("written_ids", [])) + (list(second.get("written_ids", [])) if second else []),
    }
    if rejected:
        names = _student_names(offering, rejected)
        for key, message in rejected.items():
            result["errors"].append((names.get(key, key), message))
            result["failed_by_enrollment"][key] = message
            result["failed"] += 1
            result["total"] += 1
    return result


def _student_names(offering, rejected) -> dict:
    ids = [value for value in (_uuid(key) for key in rejected) if value is not None]
    if not ids or offering is None:
        return {}
    names = {}
    for enrollment in Enrollment.objects.filter(offering=offering, pk__in=ids).select_related("student"):
        student = enrollment.student
        names[str(enrollment.pk)] = student.get_full_name() or student.username
    return names


__all__ = [
    "APPEAL",
    "FIELD_PREFIX",
    "appeal_locked_message",
    "appeal_rows",
    "attach_row",
    "guard_exam_rows",
    "latest_appeals",
    "merge_results",
    "no_exam_score_message",
    "save_rows",
    "split_entries",
]
