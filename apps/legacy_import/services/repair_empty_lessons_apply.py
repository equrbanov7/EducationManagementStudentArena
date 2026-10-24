"""Məzmunsuz keçmiş jurnal sütunlarının SİLİNMƏSİ (qayda: :mod:`.repair_empty_lessons`).

Təhlükəsizlik
-------------
* Dəstə-dəstə (``batch_size``), hər dəstə öz atomik blokunda (``scoped_atomic`` — tenant RLS
  konteksti həmin tranzaksiyada lokal qurulur, bypass YOXDUR).
* Dərs sətirləri ``SELECT … FOR UPDATE`` ilə kilidlənir və şərtlər KİLİD ALTINDA yenidən
  yoxlanır; paralel YENİ xana yazısı dərsin FK kilidində gözləyir və uğursuz olur (sətir itmir).
* Dərsin mövcud «qb» xanaları da ``FOR UPDATE`` ilə kilidlənir və statusu/balı kilid altında
  oxunur: arada «iə»/bal yazılmış (UPDATE) xananın dərsi dəstədən DÜŞÜR — real məzmun silinmir.
* DB qoruyucuları: ``trg_journal_mark_guard`` (0024/0089) yalnız UPDATE-ə bağlıdır, DELETE-ə
  yox (kaskad yolu qəsdən açıqdır) — ``journal_unlock`` LAZIM DEYİL. Düzəliş cədvəlləri
  (``JournalCorrection``/``LessonCorrection``) UPDATE/DELETE-ə bağlıdır (0043); düzəlişli dərs
  namizəd olmadığı üçün kaskad onların ``SET NULL`` yoluna heç vaxt toxunmur.

Aqreqatlar
----------
Tətbiqin öz silmə yolu (``gradebook_lessons.delete_lesson``) kimi: xanası silinən hər qeydiyyatın
``Enrollment.absence_hours``-u ``gradebook.recompute_absence_hours_many`` ilə (öz «qb» xanaları +
alt qrup birləşməsindən köçən saat) yenidən hesablanır. Əlavə olaraq həmin qeydiyyatı ƏVƏZ EDƏN
(``superseded_by``) cari qeydiyyat da hesablanır — onun köçən saatı məhz sələfin xanalarından
oxunur (``guest_merge.carry_over_map``). Digər «cache»-lər (analitika, «Keçilmiş dərslər» KPI)
qısa TTL-lidir (300 s) və mənbədən yenidən qurulur; ``read_memo`` yalnız sorğu daxilindədir.

Audit
-----
Hər dəstə açılış başına bir ``AuditLog`` (``resource_type=legacy_import.empty_lesson``) yazır:
silinən dərsin id/tarix/saat/növ/otaq/müəllim/``created_by`` izi, növü (``category``) və silinən
«qb» xanaları (xana id, qeydiyyat id, tələbə id, status) ``old_values``-dədir. Ledger
(``LegacyEntityMap.target_pk``) silinmir — o, silinməyən sübut qatıdır. İdempotentdir: ikinci
icra 0 namizəd tapır.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from django.apps import apps as django_apps

from core.audit import log_actions
from core.constants import AuditAction

from .repair_empty_lessons import (
    ABSENT,
    AUDIT_REASON,
    AUDIT_RESOURCE,
    CATEGORY_ABSENT_ONLY,
    CATEGORY_EMPTY,
    CATEGORY_TEACHER,
    DEFAULT_BATCH_SIZE,
    Scope,
    candidate_lessons,
    category_of,
)
from .repair_support import RepairContext, scoped_atomic

_SNAPSHOT_FIELDS = (
    "id",
    "offering_id",
    "date",
    "start_time",
    "end_time",
    "kind",
    "hours",
    "room_id",
    "instructor_id",
    "created_by_id",
    "is_legacy_synthesised",
    "created_at",
)


def _model(name: str):
    return django_apps.get_model("registrar", name)


def _plain(value):
    return value if isinstance(value, (bool, int)) or value is None else str(value)


def _snapshot(row: dict) -> dict:
    return {key: _plain(value) for key, value in row.items()}


@dataclass
class DeleteResult:
    deleted: int = 0
    offerings: int = 0
    batches: int = 0
    marks: int = 0
    absence_hours: int = 0
    enrollments_recomputed: int = 0
    by_category: dict = field(default_factory=lambda: {CATEGORY_EMPTY: 0, CATEGORY_ABSENT_ONLY: 0, CATEGORY_TEACHER: 0})


def _locked_marks(lesson_ids) -> dict:
    """``{lesson_id: [xana]}`` — xanalar ``FOR UPDATE`` ilə kilidlənir (status kilid altında oxunur)."""

    rows = (
        _model("LessonMark")
        .objects.filter(lesson_id__in=lesson_ids)
        .select_for_update(of=("self",))
        .order_by("lesson_id", "id")
        .values("id", "lesson_id", "enrollment_id", "enrollment__student_id", "status", "score")
    )
    by_lesson: dict = defaultdict(list)
    for row in rows:
        by_lesson[row["lesson_id"]].append(row)
    return by_lesson


def _keeps_content(marks, scope: Scope) -> bool:
    if marks and not scope.include_absent_only:
        return True
    return any(mark["score"] is not None or mark["status"] != ABSENT for mark in marks)


def _recompute_absence(enrollment_ids) -> int:
    """Xanası silinən qeydiyyatlar + onları əvəz edən cari qeydiyyatlar (alt qrup birləşməsi)."""

    if not enrollment_ids:
        return 0
    enrollment_model = _model("Enrollment")
    touched = list(enrollment_model.objects.filter(pk__in=enrollment_ids))
    successor_ids = {row.superseded_by_id for row in touched if row.superseded_by_id} - set(enrollment_ids)
    if successor_ids:
        touched.extend(enrollment_model.objects.filter(pk__in=successor_ids))
    from apps.registrar.public import gradebook

    gradebook.recompute_absence_hours_many(touched)
    return len(touched)


def delete_empty_lessons(
    context: RepairContext,
    scope: Scope,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> DeleteResult:
    """Namizədləri dəstə-dəstə sil + açılış başına audit + qayıb saatının yenidən hesabı."""

    lesson_model = _model("Lesson")
    batch_size = max(1, int(batch_size))
    result = DeleteResult()
    touched_offerings: set = set()
    while True:
        remaining = context.limit - result.deleted if context.limit else batch_size
        size = min(batch_size, remaining)
        if size <= 0:
            break
        with scoped_atomic(context):
            candidates = candidate_lessons(context.organization, scope)
            ids = list(
                candidates.order_by("offering_id", "date", "start_time", "id").values_list("id", flat=True)[:size]
            )
            if not ids:
                break
            # Kilid altında yenidən yoxla: arada mövzu/düzəliş/real xana yazılmış sətir düşür.
            locked = list(
                candidate_lessons(context.organization, scope)
                .filter(pk__in=ids)
                .select_for_update(of=("self",))
                .values_list("id", flat=True)
            )
            marks_by_lesson = _locked_marks(locked)
            rows = [
                row
                for row in lesson_model.objects.filter(pk__in=locked)
                .order_by("date", "start_time")
                .values(*_SNAPSHOT_FIELDS)
                if not _keeps_content(marks_by_lesson.get(row["id"], []), scope)
            ]
            if not rows:
                continue  # dəstənin hamısı arada məzmun alıb — növbəti sorğu onları artıq görmür
            by_offering: dict = defaultdict(list)
            enrollment_ids: set = set()
            batch_marks = batch_hours = 0
            for row in rows:
                marks = marks_by_lesson.get(row["id"], [])
                category = category_of(created_by_id=row["created_by_id"], has_marks=bool(marks))
                result.by_category[category] += 1
                batch_marks += len(marks)
                batch_hours += len(marks) * int(row["hours"] or 0)
                enrollment_ids.update(mark["enrollment_id"] for mark in marks)
                snapshot = _snapshot(row)
                snapshot["category"] = category
                snapshot["marks"] = [
                    {
                        "id": _plain(mark["id"]),
                        "enrollment_id": _plain(mark["enrollment_id"]),
                        "student_id": _plain(mark["enrollment__student_id"]),
                        "status": mark["status"],
                    }
                    for mark in marks
                ]
                by_offering[row["offering_id"]].append(snapshot)
            log_actions(
                {
                    "action": AuditAction.DELETE,
                    "user": context.actor,
                    "organization": context.organization,
                    "old_values": {
                        "lessons": lessons,
                        "count": len(lessons),
                        "marks": sum(len(lesson["marks"]) for lesson in lessons),
                    },
                    "reason": AUDIT_REASON,
                    "resource_type": AUDIT_RESOURCE,
                    "resource_id": str(offering_id),
                    "resource_repr": f"{len(lessons)} məzmunsuz jurnal sütunu",
                }
                for offering_id, lessons in by_offering.items()
            )
            # Xanalar dərslə KASKADLA silinir (``LessonMark.lesson`` CASCADE) — tətbiqin ``delete_lesson`` yolu.
            lesson_model.objects.filter(pk__in=[row["id"] for row in rows]).delete()
            result.enrollments_recomputed += _recompute_absence(enrollment_ids)
        result.deleted += len(rows)
        result.marks += batch_marks
        result.absence_hours += batch_hours
        result.batches += 1
        touched_offerings.update(by_offering)
    result.offerings = len(touched_offerings)
    return result


__all__ = ["DeleteResult", "delete_empty_lessons"]
