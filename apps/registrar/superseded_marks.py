"""Köçürülmüş tələbənin köhnə qeydiyyatında qalmış xanalarını varis jurnala daşıyır (RİM MR-000010 / MR-000030.1).

Mexanizm (diaqnoz 2026-10-27): köhnə sistem deltası (10-24) tələbənin başqa qrupun legacy jurnalındakı xanalarını
onun o vaxtkı qeydiyyatına yazdı — ana jurnalda həmin tarixlər üçün «fantom» dərs sütunları yarandı. 10-25
``registry_sync`` tələbəni rəsmi köçürdü (``transfer_student_group``: köhnə qeydiyyat ``dropped`` + ``superseded_by``,
xanalar dizayn üzrə KÖÇMÜR). Nəticə: köhnə jurnalda yalnız çıxmış tələbənin xanası olan sütunlar, varis jurnalda isə
həmin tarixlərdə tələbənin xanası boş.

Namizəd xana (cari dövr):

* qeydiyyatı ``dropped`` və ``superseded_by`` dolu; zəncirin sonu ``enrolled`` (varis);
* dərs köçürmədir (``created_by`` boş) və dərsdə heç bir ``enrolled`` qeydiyyatın xanası YOXDUR (fantom sütun);
* xanaya rəsmi düzəliş (``JournalCorrection``) bağlı deyil;
* varis açılışda hədəf dərs: eyni tarix + saat (tək); yoxdursa eyni gün + eyni növ (tək);
* varis açılış aktivdir, jurnalı bağlı deyil.

Qərar: hədəf xana BOŞDUR → xana daşınır (eyni id, status, bal, ``entered_by``, ``created_at``; köhnə sətir silinir —
``LessonMark`` dərs/qeydiyyatı dəyişməzdir); hədəfdə EYNİ dəyər var → mənbə sətri silinir (``target_same``); hədəfdə
FƏRQLİ dəyər → heç nə yazılmır (``conflict_kept``). Hər iki qeydiyyatın qayıb saatı yenidən hesablanır. Paketin
manifesti BİR audit sətrindədir (``registrar.superseded_marks_batch``) — ``undo`` mənbə dərsi hələ varsa xananı geri
qaytarır. Boşalan fantom sütunları sonra ``legacy_repair_empty_lessons --since 2026-09-15`` silir.

Plan (``superseded-marks/1``) yalnız id-lərdir: ``{"mark", "lesson", "enrollment"}`` — tətbiqdə hər sətir canlı
hesablama ilə yenidən yoxlanılır (fərq → ``plan_mismatch``, yazılmır).
"""

from __future__ import annotations

import json
import secrets
from collections import Counter, defaultdict
from decimal import Decimal

from django.apps import apps as django_apps
from django.db import connection
from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.http_ids import parse_uuid

from .models import CourseOffering, Enrollment, JournalCorrection, Lesson, LessonMark

FORMAT = "superseded-marks/1"
BATCH_RESOURCE = "registrar.superseded_marks_batch"
MAX_CHAIN = 6
SHOWN = (
    "candidates",
    "moved",
    "target_same",
    "conflict_kept",
    "no_target_lesson",
    "ambiguous_target_lesson",
    "successor_not_enrolled",
    "corrected_skipped",
    "target_closed",
    "plan_rows",
    "plan_mismatch",
    "plan_missing",
    "lessons_emptied",
    "enrollments_recomputed",
)


class PlanError(Exception):
    """Plan faylı oxunmadı / formatı səhvdir (kod stdout-a çıxır)."""


def new_batch() -> str:
    return f"supmarks-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _successor(enrollment_id, enrollments: dict):
    current = enrollments.get(enrollment_id)
    for _step in range(MAX_CHAIN):
        if current is None or current.superseded_by_id is None:
            return current
        current = enrollments.get(current.superseded_by_id)
    return None


def _load_successors(source_ids) -> dict:
    """Mənbə qeydiyyatları + bütün varis zənciri (bir neçə toplu sorğu)."""
    enrollments: dict = {}
    pending = set(source_ids)
    for _step in range(MAX_CHAIN + 1):
        pending -= set(enrollments)
        if not pending:
            break
        rows = Enrollment.objects.filter(pk__in=pending).only("id", "status", "superseded_by_id", "offering_id")
        for row in rows:
            enrollments[row.pk] = row
        pending = {row.superseded_by_id for row in rows if row.superseded_by_id}
    return enrollments


def _target_index(offering_ids) -> dict:
    index: dict = defaultdict(list)
    for lesson in Lesson.objects.filter(offering_id__in=list(offering_ids)).only(
        "id", "offering_id", "date", "start_time", "kind"
    ):
        index[(lesson.offering_id, lesson.date)].append(lesson)
    return index


def _pick_target(day_lessons, source):
    exact = [lesson for lesson in day_lessons if lesson.start_time == source.start_time]
    if len(exact) == 1:
        return exact[0], ""
    if exact:
        return None, "ambiguous_target_lesson"
    same_kind = [lesson for lesson in day_lessons if lesson.kind == source.kind]
    if len(same_kind) == 1:
        return same_kind[0], ""
    return None, "ambiguous_target_lesson" if same_kind else "no_target_lesson"


def candidate_marks(organization, period):
    """Fantom sütunlardakı əvəzlənmiş qeydiyyat xanaları (``LessonMark`` sorğusu)."""
    live = LessonMark.objects.filter(lesson_id=OuterRef("lesson_id"), enrollment__status=Enrollment.Status.ENROLLED)
    return (
        LessonMark.objects.filter(
            organization=organization,
            lesson__offering__period=period,
            lesson__created_by__isnull=True,
            enrollment__status=Enrollment.Status.DROPPED,
            enrollment__superseded_by__isnull=False,
        )
        .filter(~Exists(live))
        .select_related("lesson")
        .order_by("lesson__offering_id", "lesson__date", "lesson__start_time", "pk")
    )


def build_moves(organization, period, *, only_mark_ids=None, lock: bool = False) -> tuple[list, Counter]:
    """``[(mark, source_lesson, target_lesson | None, successor | None, verdict)]`` + saylar."""
    from .handover import closed_offering_ids

    counts: Counter = Counter()
    marks = candidate_marks(organization, period)
    if only_mark_ids is not None:
        marks = marks.filter(pk__in=list(only_mark_ids))
    if lock:
        marks = marks.select_for_update(of=("self",))
    marks = list(marks)
    counts["candidates"] = len(marks)
    corrected = set(
        JournalCorrection.objects.filter(lesson_mark_id__in=[mark.pk for mark in marks]).values_list(
            "lesson_mark_id", flat=True
        )
    )
    enrollments = _load_successors({mark.enrollment_id for mark in marks})
    successors = {mark.enrollment_id: _successor(mark.enrollment_id, enrollments) for mark in marks}
    target_offerings = {succ.offering_id for succ in successors.values() if succ is not None}
    active = set(
        CourseOffering.objects.filter(pk__in=target_offerings, is_active=True).values_list("pk", flat=True)
    ) - closed_offering_ids(list(target_offerings))
    index = _target_index(target_offerings)
    existing = {
        (row["lesson_id"], row["enrollment_id"]): (row["status"], row["score"])
        for row in LessonMark.objects.filter(
            lesson__offering_id__in=list(target_offerings),
            enrollment_id__in=[succ.pk for succ in successors.values() if succ is not None],
        ).values("lesson_id", "enrollment_id", "status", "score")
    }
    moves = []
    for mark in marks:
        succ = successors.get(mark.enrollment_id)
        target, verdict = None, ""
        if mark.pk in corrected:
            verdict = "corrected_skipped"
        elif succ is None or succ.status != Enrollment.Status.ENROLLED:
            verdict = "successor_not_enrolled"
        elif succ.offering_id not in active:
            verdict = "target_closed"
        else:
            target, verdict = _pick_target(index.get((succ.offering_id, mark.lesson.date), []), mark.lesson)
        if target is not None:
            stored = existing.get((target.pk, succ.pk))
            if stored is None:
                verdict = "moved"
                existing[(target.pk, succ.pk)] = (mark.status, mark.score)
            elif stored[0] == mark.status and _same(stored[1], mark.score):
                verdict = "target_same"
            else:
                verdict = "conflict_kept"
        counts[verdict] += 1
        moves.append((mark, target, succ, verdict))
    return moves, counts


def _same(left, right) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return Decimal(left) == Decimal(right)


def plan_rows(moves) -> list:
    return [
        {"mark": str(mark.pk), "lesson": str(target.pk), "enrollment": str(succ.pk)}
        for mark, target, succ, verdict in moves
        if verdict in ("moved", "target_same")
    ]


def load_plan(path: str) -> tuple:
    """``(dövr_id, {xana: (hədəf dərs, varis qeydiyyat)})``."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise PlanError("file_unreadable") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("moves"), list):
        raise PlanError("bad_format")
    rows = {}
    for row in data["moves"]:
        ids = (
            [parse_uuid((row or {}).get(key)) for key in ("mark", "lesson", "enrollment")]
            if isinstance(row, dict)
            else []
        )
        if len(ids) != 3 or None in ids:
            raise PlanError("bad_row")
        rows[ids[0]] = (ids[1], ids[2])
    return str(data.get("period") or ""), rows


def apply_moves(organization, period, *, actor, batch, plan=None, write: bool = True) -> Counter:
    """Planı (yoxdursa canlı namizədləri) tətbiq et — çağıranın tranzaksiyasında."""
    moves, counts = build_moves(
        organization, period, only_mark_ids=list(plan) if plan is not None else None, lock=write
    )
    if plan is not None:
        counts["plan_rows"] = len(plan)
        seen = {mark.pk for mark, *_rest in moves}
        counts["plan_missing"] = len(set(plan) - seen)
        checked = []
        for mark, target, succ, verdict in moves:
            expected = plan.get(mark.pk)
            if verdict in ("moved", "target_same") and expected != (target.pk, succ.pk):
                counts[verdict] -= 1
                counts["plan_mismatch"] += 1
                continue
            checked.append((mark, target, succ, verdict))
        moves = checked
    todo = [
        (mark, target, succ, verdict) for mark, target, succ, verdict in moves if verdict in ("moved", "target_same")
    ]
    if not write or not todo:
        return counts
    manifest = _write(todo)
    touched = {mark.enrollment_id for mark, *_rest in todo} | {succ.pk for _mark, _target, succ, _verdict in todo}
    from .gradebook_marks import recompute_absence_hours_many

    recompute_absence_hours_many(list(Enrollment.objects.filter(pk__in=touched)))
    counts["enrollments_recomputed"] = len(touched)
    source_lessons = {mark.lesson_id for mark, *_rest in todo}
    counts["lessons_emptied"] = len(
        source_lessons
        - set(LessonMark.objects.filter(lesson_id__in=source_lessons).values_list("lesson_id", flat=True))
    )
    _audit(organization, actor, batch, manifest, counts)
    return counts


def _write(todo) -> list:
    manifest = []
    LessonMark.objects.filter(pk__in=[mark.pk for mark, *_rest in todo]).delete()
    fresh = []
    for mark, target, succ, verdict in todo:
        manifest.append(
            {
                "mark": str(mark.pk),
                "verdict": verdict,
                "from_lesson": str(mark.lesson_id),
                "from_enrollment": str(mark.enrollment_id),
                "to_lesson": str(target.pk),
                "to_enrollment": str(succ.pk),
                "status": mark.status,
                "score": None if mark.score is None else str(mark.score),
                "entered_by": mark.entered_by_id,
                "created_at": mark.created_at.isoformat(),
            }
        )
        if verdict == "moved":
            fresh.append(_clone(mark, lesson_id=target.pk, enrollment_id=succ.pk))
    LessonMark.objects.bulk_create(fresh, batch_size=500)
    _restore_created_at([(mark.pk, mark.created_at) for mark, _target, _succ, verdict in todo if verdict == "moved"])
    return manifest


def _clone(mark, *, lesson_id, enrollment_id):
    return LessonMark(
        id=mark.pk,
        organization_id=mark.organization_id,
        lesson_id=lesson_id,
        enrollment_id=enrollment_id,
        status=mark.status,
        score=mark.score,
        entered_by_id=mark.entered_by_id,
        created_at=mark.created_at,
    )


def _restore_created_at(pairs) -> None:
    """``auto_now_add`` yeni vaxt yazır — köhnə xananın yaranma vaxtı (kilid pəncərəsi ondan sayılır) qaytarılır.
    Yeni yaranmış sətrin UPDATE-i ``trg_journal_mark_guard``-ın pəncərəsi daxilindədir."""
    if not pairs:
        return
    with connection.cursor() as cursor:
        for start in range(0, len(pairs), 500):
            part = pairs[start : start + 500]
            values = ", ".join(["(%s::uuid, %s::timestamptz)"] * len(part))
            params = [value for pk, created in part for value in (str(pk), created)]
            cursor.execute(
                f"UPDATE registrar_lessonmark m SET created_at = v.created FROM (VALUES {values}) AS v(id, created) "
                "WHERE m.id = v.id",
                params,
            )


def _audit(organization, actor, batch, manifest, counts) -> None:
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={"counts": {key: counts.get(key, 0) for key in SHOWN}, "moves": manifest},
        reason=f"relocate_superseded_marks {batch}",
        resource_type=BATCH_RESOURCE,
        resource_id=batch,
        resource_repr=batch,
    )


def undo_batch(organization, batch: str) -> Counter:
    """Daşınmış xananı geri qaytar: hədəfdəki xana hələ eyni dəyərdədirsə və mənbə dərsi mövcuddursa."""
    audit_model = django_apps.get_model("audit", "AuditLog")
    entry = (
        audit_model.objects.filter(organization=organization, resource_type=BATCH_RESOURCE, resource_id=batch)
        .order_by("-created_at")
        .first()
    )
    if entry is None:
        raise PlanError("batch_not_found")
    counts: Counter = Counter()
    rows = list((entry.new_values or {}).get("moves") or [])
    lessons = set(Lesson.objects.filter(pk__in={row["from_lesson"] for row in rows}).values_list("pk", flat=True))
    current = {
        str(mark.pk): mark
        for mark in LessonMark.objects.filter(pk__in=[row["mark"] for row in rows]).select_for_update(of=("self",))
    }
    restore, delete_ids, touched = [], [], set()
    for row in rows:
        if parse_uuid(row["from_lesson"]) not in lessons:
            counts["undo_source_lesson_missing"] += 1
            continue
        mark = current.get(row["mark"])
        if row["verdict"] == "moved":
            if mark is None or str(mark.lesson_id) != row["to_lesson"] or mark.status != row["status"]:
                counts["undo_target_changed"] += 1
                continue
            delete_ids.append(mark.pk)
        elif mark is not None:
            counts["undo_source_exists"] += 1
            continue
        restore.append(
            LessonMark(
                id=row["mark"],
                organization=organization,
                lesson_id=row["from_lesson"],
                enrollment_id=row["from_enrollment"],
                status=row["status"],
                score=None if row["score"] is None else Decimal(row["score"]),
                entered_by_id=row["entered_by"],
            )
        )
        touched |= {row["from_enrollment"], row["to_enrollment"]}
    LessonMark.objects.filter(pk__in=delete_ids).delete()
    LessonMark.objects.bulk_create(restore, batch_size=500)
    by_id = {str(row["mark"]): row for row in rows}
    _restore_created_at([(mark.pk, parse_datetime(by_id[str(mark.pk)]["created_at"])) for mark in restore])
    if touched:
        from .gradebook_marks import recompute_absence_hours_many

        recompute_absence_hours_many(list(Enrollment.objects.filter(pk__in=touched)))
    counts["undo_restored"] = len(restore)
    return counts


__all__ = [
    "BATCH_RESOURCE",
    "FORMAT",
    "SHOWN",
    "PlanError",
    "apply_moves",
    "build_moves",
    "candidate_marks",
    "load_plan",
    "new_batch",
    "plan_rows",
    "undo_batch",
]
