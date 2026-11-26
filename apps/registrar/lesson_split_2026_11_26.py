"""MR-000807 / MR-000802 (sahib 2026-11-26, «Yes, split it»): 435 R ing «İxtisasyönümlü xarici dil-1» — ortaq dərslər.

Jurnal (``20d52521``) iki müəllim tərəfindən paralel keçilir: Aytac Salmanlı (8361) öz 14 tələbəsi, Günay Əmirova
(8373) qalan 13 tələbə ilə. 24.11-ə qədər hər məşğələ hər iki yarım üçün BİR dərs kimi açılıb və yalnız bir müəllimin
adına yazılıb (``Lesson.instructor``); 23–25.11 dərsləri artıq ayrıdır. Hər iki müəllim eyni dərsləri öz adına istəyir.

Nəticə (jurnal daxilində iki seminar alt qrupu — :mod:`apps.registrar.seminar_groups`):

* ``SeminarGroup`` 1 = Aytac xanımın yarısı, 2 = Günay xanımın yarısı; tələbənin ``Enrollment.seminar_group``-u;
* hər ORTAQ dərs (hər iki yarının xanası olan) İKİ dərs olur: əsli öz müəlliminin yarısında qalır
  (``seminar_group`` qoyulur), eyni tarix / saat / növ / saat sayı / mövzu / otaqla surəti (müəllimi = digər müəllim,
  ``created_by`` = aktor, ``created_at`` = əslinki — redaktə pəncərəsi yenidən açılmır) digər yarının xanalarını alır;
* yalnız bir yarının xanası olan dərsə həmin yarının nömrəsi qoyulur; müəllimi o yarının müəllimi deyilsə SAYILIR
  (``instructor_mismatch``), müəllim DƏYİŞDİRİLMİR; xanasız dərs müəlliminin yarısına düşür;
* siyahıdan kənar (düşürülmüş) qeydiyyatların xanaları əsl dərsdə qalır (``marks_outside_roster_kept``).

Xananın KÖÇÜRÜLMƏSİ: ``LessonMark.lesson`` DB səviyyəsində dəyişməz identikdir (``registrar_reference_identity_guard``,
0045) — FK-nı yenidən yönəltmək mümkün deyil. Layihənin köçürmə yolu (:func:`apps.registrar.twin_relocate.copy_mark`)
işlədilir: eyni ``status`` / ``score`` / ``entered_by`` / ``created_at`` / ``updated_at`` ilə yeni sətir, köhnəsi
silinir; köhnə → yeni id cütləri audit sətrindədir (``undo`` onları geri köçürür). Komponent / Midterm / yekun
toxunulmur; qayıb saatı :func:`apps.registrar.gradebook.recompute_absence_hours_many` ilə yenidən hesablanır.

Yarılar: hər iki müəllimin bu jurnalda aktiv, SƏTİR-MƏHDUD payı varsa — paylardan; yoxsa xanaların müəllifindən
(``LessonMark.entered_by`` çoxluğu; bərabərlik / xanasız tələbə → imtina). Sətir-məhdud TƏK pay varsa xanalardan
çıxan yarı ilə üst-üstə düşməlidir. İmtina (:class:`SplitRefused`, heç nə yazılmır): yarıya düşməyən tələbə, seminar
olmayan / lab qruplu dərs, gözlənilən 14/13-dən fərqli say (``ignore_counts`` ilə keçilir), rəsmi düzəlişli köçən
xana, dil səviyyəsi kohortu, bağlı jurnal, mövcud alt qrup bölgüsü ilə ziddiyyət. İkinci qaçış heç nə yazmır.
"""

from __future__ import annotations

import secrets
from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.lesson_split_20261126"
REASON = "MR-000807/802: 435 R ing «İxtisasyönümlü xarici dil-1» — ortaq dərslər iki seminar alt qrupuna bölündü"
UNDO_REASON = "MR-000807/802: ortaq dərslərin bölünməsinin geri qaytarılması"

OFFERING_ID = "20d52521-f9c0-41e6-b777-761c1dcb49f1"  # 435 R ing «İxtisasyönümlü xarici dil-1»
SUBJECT_MARK = "xtisasyönümlü xarici dil"  # «İ».casefold() = «i̇» — baş hərf daxil edilmir
#: (müəllim id, alt qrup nömrəsi, gözlənilən tələbə sayı)
SECTIONS = (
    (8361, 1, 14),  # Aytac Salmanlı
    (8373, 2, 13),  # Günay Əmirova
)
SEMINAR = "seminar"
#: Say açarlarında rəqəm olmur (prod-data-ops xülasə / rədd kodu süzgəci ``[a-z_]+``).
_WORD = {1: "one", 2: "two"}
NAME_MAX = 40
_CLONE_FIELDS = (
    "date",
    "kind",
    "topic",
    "syllabus_week",
    "hours",
    "start_time",
    "end_time",
    "room_id",
    "is_legacy_synthesised",
    "off_schedule_reason",
    "is_passive",
)


class SplitRefused(Exception):
    """Qoruyucu pozuldu — heç nə yazılmır (əmr ``CommandError: lesson_split_refused_<kod>`` verir)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"lsplit-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _offering(organization, offering_id):
    offering = (
        _model("CourseOffering")
        .objects.select_for_update(of=("self",))
        .filter(organization=organization, pk=offering_id or OFFERING_ID)
        .select_related("subject", "group")
        .first()
    )
    if offering is None or not offering.is_active:
        raise SplitRefused("offering_missing")
    if SUBJECT_MARK not in str(offering.subject.name).casefold():
        raise SplitRefused("offering_subject_invalid")
    from .handover import closed_offering_ids

    if closed_offering_ids([offering.pk]):
        raise SplitRefused("journal_closed")
    if _model("LanguageLevelCohort").objects.filter(offering=offering).exists():
        raise SplitRefused("language_cohort_offering")  # kohort saat trigger-i alt qrupları tanımır
    return offering


def _majority(tally: Counter) -> int:
    ranked = tally.most_common()
    if not ranked:
        raise SplitRefused("student_without_teacher_marks")
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        raise SplitRefused("student_marks_tie")
    return ranked[0][0]


def _halves(organization, offering, roster_ids: set, teachers: tuple, counts: Counter) -> dict:
    """``{qeydiyyat_id: müəllim_id}`` — paylardan (hər ikisi sətir-məhdud) və ya xana müəllifindən."""
    shares = _model("JournalShare").objects.filter(
        organization=organization, offering=offering, is_active=True, teacher_id__in=teachers
    )
    limited = {}
    for share in shares:
        rows = set(share.enrollments.values_list("pk", flat=True)) & roster_ids
        if rows:
            limited[share.teacher_id] = rows
    if len(limited) == len(teachers):
        counts["halves_source_shares"] += 1
        halves = {}
        for teacher_id, rows in limited.items():
            for enrollment_id in rows:
                if enrollment_id in halves:
                    raise SplitRefused("student_in_both_shares")
                halves[enrollment_id] = teacher_id
        if set(halves) != roster_ids:
            raise SplitRefused("student_in_no_share")
        return halves
    counts["halves_source_marks"] += 1
    tally: dict = defaultdict(Counter)
    marks = _model("LessonMark").objects.filter(
        lesson__offering=offering, enrollment_id__in=roster_ids, entered_by_id__in=teachers
    )
    for enrollment_id, author_id in marks.values_list("enrollment_id", "entered_by_id"):
        tally[enrollment_id][author_id] += 1
    halves = {enrollment_id: _majority(tally.get(enrollment_id, Counter())) for enrollment_id in roster_ids}
    for teacher_id, rows in limited.items():
        if rows != {pk for pk, owner in halves.items() if owner == teacher_id}:
            raise SplitRefused("share_disagrees_with_marks")
    counts["shares_cross_checked"] += len(limited)
    return halves


def _check_sections(offering, roster, halves, numbers: dict) -> dict:
    """Mövcud alt qrup bölgüsü planla üst-üstə düşməlidir; ``{nömrə: SeminarGroup}``."""
    existing = {row.number: row for row in _model("SeminarGroup").objects.select_for_update().filter(offering=offering)}
    if set(existing) - set(numbers.values()):
        raise SplitRefused("other_seminar_groups_exist")
    if any(row.unit_id for row in existing.values()):
        raise SplitRefused("seminar_group_bound_to_registry")
    for row in roster:
        if row.lab_group is not None:
            raise SplitRefused("journal_has_lab_groups")
        if row.seminar_group not in (None, numbers[halves[row.pk]]):
            raise SplitRefused("student_section_conflict")
    return existing


def _lesson_plan(offering, lessons, marks_by_lesson, halves, numbers, teachers, counts) -> list:
    """``[(əməl, dərs, nömrə, köçən_xanalar)]``; əməl: ``split`` | ``tag``."""
    from .twin_relocate import corrected_mark_ids

    teacher_by_number = {number: teacher_id for teacher_id, number in numbers.items()}
    plan, moving = [], []
    for lesson in lessons:
        if lesson.kind != SEMINAR:
            raise SplitRefused("lesson_kind_not_seminar")
        if lesson.lab_group is not None:
            raise SplitRefused("lesson_has_lab_group")
        marks = marks_by_lesson.get(lesson.pk, [])
        own = [mark for mark in marks if mark.enrollment_id in halves]
        counts["marks_outside_roster_kept"] += len(marks) - len(own)
        present = {halves[mark.enrollment_id] for mark in own}
        teacher_id = lesson.instructor_id or offering.instructor_id
        if lesson.seminar_group is not None:
            if present - {teacher_by_number.get(lesson.seminar_group)}:
                raise SplitRefused("lesson_section_conflict")
            counts["lessons_already_sectioned"] += 1
            continue
        if len(present) == len(teachers):
            if teacher_id not in teachers:
                raise SplitRefused("shared_lesson_unknown_instructor")
            other = next(pk for pk in teachers if pk != teacher_id)
            moved = [mark for mark in own if halves[mark.enrollment_id] == other]
            moving.extend(mark.pk for mark in moved)
            plan.append(("split", lesson, numbers[teacher_id], moved))
            counts["lessons_shared"] += 1
            continue
        if present:
            half = next(iter(present))
        elif teacher_id in teachers:
            half = teacher_id
            counts["lessons_empty_by_instructor"] += 1
        else:
            raise SplitRefused("empty_lesson_unknown_instructor")
        if teacher_id != half:
            counts["instructor_mismatch"] += 1
        plan.append(("tag", lesson, numbers[half], []))
        counts["lessons_single_half"] += 1
    if corrected_mark_ids([str(pk) for pk in moving]):
        raise SplitRefused("moving_marks_have_corrections")
    return plan


def move_mark(mark, *, lesson):
    """Xananı başqa dərsə köçür: eyni sahələrlə yeni sətir (``created_at`` / ``updated_at`` köhnə), köhnəsi silinir."""
    from core.rls import journal_unlock

    LessonMark = _model("LessonMark")
    with journal_unlock(local=True):
        created = LessonMark.objects.create(
            organization_id=lesson.organization_id,
            lesson=lesson,
            enrollment_id=mark.enrollment_id,
            status=mark.status,
            score=mark.score,
            entered_by_id=mark.entered_by_id,
        )
        LessonMark.objects.filter(pk=created.pk).update(created_at=mark.created_at, updated_at=mark.updated_at)
        LessonMark.objects.filter(pk=mark.pk).delete()
    return created


def _audit(actor, organization, resource_id, repr_, new_values) -> None:
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=str(resource_id),
        resource_repr=repr_,
        old_values={},
        new_values=new_values,
    )


def _section_name(offering, teacher) -> str:
    person = (teacher.get_full_name() or teacher.username).strip()
    group = offering.group.name if offering.group_id else ""
    return (f"{group} — {person}" if group else person)[:NAME_MAX]


def _apply_sections(ctx, existing, roster, halves) -> None:
    offering, counts = ctx["offering"], ctx["counts"]
    SeminarGroup, Enrollment = _model("SeminarGroup"), _model("Enrollment")
    users = {user.pk: user for user in get_user_model().objects.filter(pk__in=ctx["numbers"])}
    created = []
    for teacher_id, number in ctx["numbers"].items():
        if number in existing:
            counts["sections_existing"] += 1
            continue
        row = SeminarGroup.objects.create(
            organization_id=offering.organization_id,
            offering=offering,
            number=number,
            name=_section_name(offering, users[teacher_id]),
        )
        created.append(str(row.pk))
    counts["sections_created"] += len(created)
    changed = []
    for row in roster:
        number = ctx["numbers"][halves[row.pk]]
        if row.seminar_group == number:
            counts["students_already_placed"] += 1
            continue
        row.seminar_group = number
        changed.append(row)
    if changed:
        Enrollment.objects.bulk_update(changed, ["seminar_group"])
    counts["students_placed"] += len(changed)
    if created or changed:
        placed = defaultdict(list)
        for row in changed:
            placed[str(row.seminar_group)].append(str(row.pk))
        _audit(
            ctx["actor"],
            ctx["organization"],
            offering.pk,
            "Jurnalda iki seminar alt qrupu yaradıldı, tələbələr yerləşdirildi",
            {
                "batch": ctx["batch"],
                "op": "sections",
                "offering": str(offering.pk),
                "created": created,
                "placed": placed,
            },
        )


def _apply_lessons(ctx, plan) -> set:
    Lesson = _model("Lesson")
    counts, numbers, now = ctx["counts"], ctx["numbers"], timezone.now()
    teacher_by_number = {number: teacher_id for teacher_id, number in numbers.items()}
    touched = set()
    for op, lesson, number, moved in plan:
        Lesson.objects.filter(pk=lesson.pk).update(seminar_group=number, updated_at=now)
        values = {"batch": ctx["batch"], "op": op, "lesson": str(lesson.pk), "number": number, "old_number": None}
        if op == "tag":
            counts["lessons_tagged"] += 1
            _audit(ctx["actor"], ctx["organization"], lesson.pk, "Dərsə seminar alt qrupu qoyuldu", values)
            continue
        other_number = next(n for n in teacher_by_number if n != number)
        clone = Lesson.objects.create(
            organization_id=lesson.organization_id,
            offering_id=lesson.offering_id,
            created_by=ctx["actor"],
            instructor_id=teacher_by_number[other_number],
            seminar_group=other_number,
            **{name: getattr(lesson, name) for name in _CLONE_FIELDS},
        )
        Lesson.objects.filter(pk=clone.pk).update(created_at=lesson.created_at)
        pairs = []
        for mark in moved:
            pairs.append([str(mark.pk), str(move_mark(mark, lesson=clone).pk)])
            touched.add(mark.enrollment_id)
        counts["lessons_cloned"] += 1
        counts["marks_moved"] += len(pairs)
        values.update(clone=str(clone.pk), clone_number=other_number, marks=pairs)
        _audit(ctx["actor"], ctx["organization"], lesson.pk, "Ortaq dərs iki alt qrupa bölündü", values)
    return touched


def run(*, organization, actor, counts: Counter, batch: str, offering_id=None, ignore_counts=False) -> str:
    batch = batch or new_batch()
    offering = _offering(organization, offering_id)
    numbers = {teacher_id: number for teacher_id, number, _expected in SECTIONS}
    teachers = tuple(numbers)
    if offering.instructor_id not in teachers:
        raise SplitRefused("owner_not_one_of_teachers")
    Enrollment = _model("Enrollment")
    roster = list(Enrollment.objects.select_for_update().filter(offering=offering, status=Enrollment.Status.ENROLLED))
    roster_ids = {row.pk for row in roster}
    counts["students_enrolled"] += len(roster)
    halves = _halves(organization, offering, roster_ids, teachers, counts)
    sizes = Counter(halves.values())
    for teacher_id, number, expected in SECTIONS:
        counts[f"students_section_{_WORD[number]}"] += sizes[teacher_id]
        if sizes[teacher_id] != expected and not ignore_counts:
            raise SplitRefused(f"section_{_WORD[number]}_count_mismatch")
    existing = _check_sections(offering, roster, halves, numbers)
    lessons = list(
        _model("Lesson")
        .objects.select_for_update()
        .filter(offering=offering)
        .order_by("date", "start_time", "created_at")
    )
    counts["lessons_total"] += len(lessons)
    marks_by_lesson = defaultdict(list)
    for mark in _model("LessonMark").objects.select_for_update(of=("self",)).filter(lesson__offering=offering):
        marks_by_lesson[mark.lesson_id].append(mark)
    plan = _lesson_plan(offering, lessons, marks_by_lesson, halves, numbers, teachers, counts)
    ctx = {
        "organization": organization,
        "actor": actor,
        "counts": counts,
        "batch": batch,
        "offering": offering,
        "numbers": numbers,
    }
    _apply_sections(ctx, existing, roster, halves)
    touched = _apply_lessons(ctx, plan)
    if touched:
        from .gradebook import recompute_absence_hours_many

        recompute_absence_hours_many([row for row in roster if row.pk in touched])
        counts["absences_recomputed"] += len(touched)
    if not plan and not counts["sections_created"] and not counts["students_placed"]:
        counts["nothing_to_split"] += 1
    return batch


__all__ = ["OFFERING_ID", "RESOURCE", "SECTIONS", "SplitRefused", "move_mark", "new_batch", "run"]
