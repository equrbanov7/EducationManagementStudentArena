"""Birləşmiş qrup jurnalını qruplara ayırmaq (sahib 2026-11-12, MR-000317) — ``split_group_journal_20261112``.

635 Q «Mülki müdafiə» (Elşən Əmrahov): köhnə sistemdə iki ayrı jurnal idi (14346 — 635 Q, 14341 — 635 İ; mühazirə
ortaq 15:15, 635 İ seminarı 16:45/16:55). EMS-də hər iki qrupun 48 tələbəsi 635 Q jurnalında (``31a04416``)
qalıb, 635 İ jurnalı (``0156cf86``) boşdur. Sahib: «İ qrupunun jurnalı ayrılsın».

Parametrik (``--source`` / ``--target`` / ``--group``; defolt — 635 Q → 635 İ). Qaydalar (hamısı bir tranzaksiyada;
qoruyucu pozularsa ``Blocked`` → heç nə yazılmır):

* mənbə və hədəf aktiv, açıq (bağlı / kilidli dövr deyil), eyni fənn + dövr; hədəfin qrupu ``--group``-dur;
  hədəfdə hələ dərs yoxdur; köçən tələbələrin yekun qiyməti / kurs işi / təkrar imtahanı / rubrik balı yoxdur;
  köçən xanalarda və silinən dərslərdə rəsmi düzəliş yoxdur;
* KÖÇƏN tələbələr — mənbədə ``enrolled`` olan və AKADEMİK qrupu ``--group`` olanlar. Hədəfdə yazılışı varsa
  (məs. ``dropped``) ``enrolled`` edilir (əvvəlki status manifestdə), yoxdursa yaradılır;
* MÜHAZİRƏ (``lecture``) — qrupların ortaq dərsidir: köçən tələbənin xanası olan hər mühazirə hədəfdə eyni sahələrlə
  yaradılır və həmin xanalar ora kopyalanır; mənbədəki mühazirə qalır;
* SEMİNAR / LAB — xanalarının ÇOXU köçən tələbələrindirsə həmin qrupun dərsidir: hədəfdə yaradılır, köçən xanalar
  kopyalanır; mənbədə başqa xana qalmırsa dərs SİLİNİR (tam surəti manifestdə, ``undo`` eyni id ilə bərpa edir),
  qalırsa saxlanılır (``source_lessons_kept_shared``). Köçən tələbənin AZLIQDA olduğu (digər qrupun) dərsindəki
  xanası köçmür — tarixçədə qalır (``marks_minority_kept``);
* komponent balı (Midterm …) hədəfin eyni adlı komponentinə (yoxdursa yaradılır) kopyalanır; mənbə qeydiyyatları
  ``dropped`` (silinmir — tarixçə və sübutlar onlara bağlı qalır);
* cədvəl: hədəfdə mühazirə slotu YOXDURSA mənbənin (ortaq) mühazirə slotu hədəfə kopyalanır; seminar / lab slotu
  qrupun özünündür — kopyalanmır (hesabatda ``slots_target_kept``); hədəfin öz slotlarına toxunulmur.

Dərs yükü sətirlərinə TOXUNULMUR (hesabatda ayrıca). Paket id-si ``groupsplit-YYYYMMDD-HHMMSS-xxxx`` audit sətrinin
``resource_id``-sidir; tam manifest ``changes``-dədir. Geri qaytarma — :mod:`.group_journal_split_undo_2026_11_12`.
Şəxsi məlumat yoxdur — YALNIZ id-lər.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .share_journal_split_2026_11_12 import _LESSON_EXTRA, _plain, _referenced
from .twin_merge import _LESSON_FIELDS, _SLOT_FIELDS
from .twin_relocate import closed, copy_mark, corrected_lesson_ids, corrected_mark_ids, recompute_absences

REASON = "Sahib 2026-11-12 (MR-000317): birləşmiş qrup jurnalı qruplara ayrıldı (635 Q → 635 İ)"
RESOURCE = "registrar.group_journal_split"

SOURCE = "31a04416-e4a8-4fb2-8298-36793660f63d"  # 635 Q «Mülki müdafiə» — hər iki qrupun 48 tələbəsi
TARGET = "0156cf86-feb7-4c22-b26e-7a57324aebf4"  # 635 İ «Mülki müdafiə» — boş
GROUP = "5fc85a2c-7ef5-41ad-9846-b207aaf7117f"  # 635 İ

#: Bunlardan biri varsa tələbə köçmür (yekun nəticə — RİM ayrıca baxır).
_FINAL_MODELS = ("FinalGrade", "CourseWork", "ResitRecord", "CriterionScore")
_SHARED_KINDS = ("lecture",)


class Blocked(Exception):
    """Qoruyucu pozuldu — heç nə yazılmır; ``code`` yalnız ``[a-z_]`` (prod-data-ops süzgəci)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def _iso(value):
    return value.isoformat() if value is not None else None


def new_batch() -> str:
    return f"groupsplit-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"


def applied_batches(organization, source, target) -> list:
    """Bu cüt üçün tətbiq olunmuş və geri qaytarılmamış audit sətirləri (yenidən köhnəyə)."""
    rows = _model("AuditLog", "audit").objects.filter(
        organization=organization, resource_type=RESOURCE, changes__source=str(source), changes__target=str(target)
    )
    undone = set(
        _model("AuditLog", "audit")
        .objects.filter(organization=organization, resource_type=RESOURCE, new_values__undo=True)
        .values_list("resource_id", flat=True)
    )
    return [row for row in rows.order_by("-created_at") if row.resource_id not in undone]


def home_groups(organization, student_ids) -> dict:
    """Tələbə → akademik qrup (aktiv qeyd üstün)."""
    Record = _model("StudentAcademicRecord")
    out = {}
    rows = (
        Record.objects.filter(organization=organization, student_id__in=list(student_ids), group__isnull=False)
        .order_by("student_id", "-is_active", "-updated_at")
        .values_list("student_id", "group_id")
    )
    for student_id, group_id in rows:
        out.setdefault(student_id, group_id)
    return out


class GroupSplitter:
    def __init__(self, *, organization, actor, counts, source=SOURCE, target=TARGET, group=GROUP):
        self.organization, self.actor, self.counts = organization, actor, counts
        self.source_id, self.target_id, self.group_id = str(source), str(target), str(group)
        self.manifest = defaultdict(list)
        self.batch = ""

    # ── giriş ─────────────────────────────────────────────────────────────
    def run(self) -> None:
        if applied_batches(self.organization, self.source_id, self.target_id):
            self.counts["already_split"] += 1
            return
        source, target, rows = self._guard()
        shared, own, marks = self._plan(rows)
        self._guard_corrections(marks, shared + own)
        self.batch = new_batch()
        by_source = self._enrollments(target, rows)
        self._moving = {row.pk for row in rows}
        self._copy_lessons(target, shared, marks, by_source, "lessons_shared_created")
        self._copy_lessons(target, own, marks, by_source, "lessons_moved_created")
        self._scores(source, target, by_source)
        self._delete_emptied(own)
        self._retire(rows)
        self._slots(source, target)
        recompute_absences(list(rows) + list(by_source.values()))
        self.counts["journals_split"] += 1
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            obj=target,
            new_values={"source": self.source_id, "target": self.target_id, "group": self.group_id},
            changes={"manifest": dict(self.manifest), "source": self.source_id, "target": self.target_id},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=self.batch,
        )

    # ── qoruyucular ───────────────────────────────────────────────────────
    def _offering(self, pk, code):
        row = (
            _model("CourseOffering")
            .objects.select_for_update(of=("self",))
            .select_related("period")
            .filter(organization=self.organization, pk=pk)
            .first()
        )
        if row is None or not row.is_active:
            raise Blocked(f"{code}_missing_or_inactive")
        if row.period.locked_at is not None or closed([row.pk]):
            raise Blocked(f"{code}_closed")
        return row

    def _guard(self):
        source = self._offering(self.source_id, "source")
        target = self._offering(self.target_id, "target")
        if (source.subject_id, source.period_id) != (target.subject_id, target.period_id):
            raise Blocked("subject_or_period_differs")
        if str(target.group_id) != self.group_id or str(source.group_id) == self.group_id:
            raise Blocked("target_group_mismatch")
        if _model("Lesson").objects.filter(offering=target).exists():
            raise Blocked("target_has_lessons")
        Enrollment = _model("Enrollment")
        enrolled = list(
            Enrollment.objects.select_for_update(of=("self",)).filter(offering=source, status="enrolled").order_by("pk")
        )
        homes = home_groups(self.organization, [row.student_id for row in enrolled])
        rows = [row for row in enrolled if str(homes.get(row.student_id) or "") == self.group_id]
        if not rows:
            raise Blocked("no_students_of_group")
        if len(rows) == len(enrolled):
            raise Blocked("source_would_be_empty")
        for name in _FINAL_MODELS:
            if _model(name).objects.filter(enrollment__in=rows).exists():
                raise Blocked("students_have_final_results")
        self.counts["source_students_staying"] += len(enrolled) - len(rows)
        return source, target, rows

    def _plan(self, rows):
        """``(ortaq mühazirələr, qrupun öz dərsləri, {dərs: köçən xanalar})`` — tarix sırası ilə."""
        LessonMark = _model("LessonMark")
        moving = {row.pk for row in rows}
        marks = defaultdict(list)
        others = defaultdict(int)
        lessons = {}
        query = (
            LessonMark.objects.select_for_update(of=("self",))
            .filter(lesson__offering_id=self.source_id)
            .select_related("lesson")
            .order_by("lesson__date", "lesson__start_time", "lesson__created_at", "created_at")
        )
        for mark in query:
            lessons.setdefault(mark.lesson_id, mark.lesson)
            if mark.enrollment_id in moving:
                marks[mark.lesson_id].append(mark)
            else:
                others[mark.lesson_id] += 1
        shared, own = [], []
        for pk, lesson in lessons.items():
            mine = len(marks.get(pk, ()))
            if not mine:
                continue
            if lesson.kind in _SHARED_KINDS:
                shared.append(lesson)
            elif mine > others[pk]:
                own.append(lesson)
            else:
                self.counts["marks_minority_kept"] += mine
                marks.pop(pk)
        return shared, own, marks

    def _guard_corrections(self, marks, lessons) -> None:
        ids = [mark.pk for rows in marks.values() for mark in rows]
        if corrected_mark_ids(ids) or corrected_lesson_ids([lesson.pk for lesson in lessons]):
            raise Blocked("corrected_cells")

    # ── yazı ──────────────────────────────────────────────────────────────
    def _enrollments(self, target, rows) -> dict:
        Enrollment = _model("Enrollment")
        existing = {
            row.student_id: row
            for row in Enrollment.objects.select_for_update().filter(
                offering=target, student_id__in=[r.student_id for r in rows]
            )
        }
        by_source = {}
        for row in rows:
            found = existing.get(row.student_id)
            if found is None:
                found = Enrollment.objects.create(
                    organization=self.organization,
                    offering=target,
                    student_id=row.student_id,
                    kind=row.kind,
                    status="enrolled",
                )
                self.manifest["enrollments_created"].append(str(found.pk))
                self.counts["target_enrollments_created"] += 1
            elif found.status != "enrolled":
                self.manifest["enrollments_reactivated"].append(
                    {"id": str(found.pk), "status": found.status, "superseded_by": str(found.superseded_by_id or "")}
                )
                Enrollment.objects.filter(pk=found.pk).update(
                    status="enrolled", superseded_by=None, updated_at=timezone.now()
                )
                found.status = "enrolled"
                self.counts["target_enrollments_reactivated"] += 1
            else:
                self.counts["target_enrollments_already"] += 1
            by_source[row.pk] = found
        self.counts["students_moved"] += len(by_source)
        return by_source

    def _copy_lessons(self, target, lessons, marks, by_source, key) -> None:
        Lesson = _model("Lesson")
        for lesson in lessons:
            twin = Lesson.objects.create(
                organization=self.organization,
                offering=target,
                **{name: getattr(lesson, name) for name in _LESSON_FIELDS},
            )
            Lesson.objects.filter(pk=twin.pk).update(created_at=lesson.created_at)
            self.manifest["lessons_created"].append(str(twin.pk))
            self.counts[key] += 1
            for mark in marks[lesson.pk]:
                created = copy_mark(mark, lesson=twin, enrollment=by_source[mark.enrollment_id])
                self.manifest["marks_created"].append(str(created.pk))
                self.counts["marks_copied"] += 1

    def _scores(self, source, target, by_source) -> None:
        Component, Score = _model("AssessmentComponent"), _model("ComponentScore")
        mine = {row.name: row for row in Component.objects.filter(offering=target)}
        mapping = {}
        for row in Component.objects.filter(offering=source).order_by("order", "name"):
            if row.name not in mine:
                mine[row.name] = Component.objects.create(
                    organization=self.organization,
                    offering=target,
                    name=row.name,
                    kind=row.kind,
                    held_on=row.held_on,
                    max_score=row.max_score,
                    rubric_id=row.rubric_id,
                    order=row.order,
                )
                self.manifest["components_created"].append(str(mine[row.name].pk))
                self.counts["components_created"] += 1
            mapping[row.pk] = mine[row.name]
        for score in Score.objects.filter(enrollment_id__in=list(by_source)).order_by("created_at"):
            component = mapping.get(score.component_id)
            enrollment = by_source[score.enrollment_id]
            if component is None or Score.objects.filter(component=component, enrollment=enrollment).exists():
                self.counts["scores_kept"] += 1
                continue
            created = Score.objects.create(
                organization=self.organization,
                component=component,
                enrollment=enrollment,
                score=score.score,
                entered_by_id=score.entered_by_id,
                exam_source=score.exam_source,
            )
            Score.objects.filter(pk=created.pk).update(created_at=score.created_at)
            self.manifest["scores_created"].append(str(created.pk))
            self.counts["scores_copied"] += 1

    def _delete_emptied(self, lessons) -> None:
        """Bütün xanaları köçən qrup dərsi mənbədən silinir — surəti (xanaları ilə) manifestdə."""
        Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
        for lesson in lessons:
            marks = list(LessonMark.objects.filter(lesson=lesson))
            if any(mark.enrollment_id not in self._moving for mark in marks):
                self.counts["source_lessons_kept_shared"] += 1
                continue
            if _referenced(lesson):
                self.counts["source_lessons_kept_referenced"] += 1
                continue
            snapshot = {name: _plain(getattr(lesson, name)) for name in (*_LESSON_FIELDS, *_LESSON_EXTRA)}
            snapshot.update(id=str(lesson.pk), offering_id=str(lesson.offering_id), created_at=_iso(lesson.created_at))
            snapshot["marks"] = [
                {
                    "id": str(mark.pk),
                    "enrollment_id": str(mark.enrollment_id),
                    "status": mark.status,
                    "score": _plain(mark.score),
                    "entered_by_id": mark.entered_by_id,
                    "created_at": _iso(mark.created_at),
                }
                for mark in marks
            ]
            self.manifest["source_lessons_deleted"].append(snapshot)
            Lesson.objects.filter(pk=lesson.pk).delete()
            self.counts["source_lessons_deleted"] += 1

    def _retire(self, rows) -> None:
        ids = [row.pk for row in rows]
        _model("Enrollment").objects.filter(pk__in=ids).update(status="dropped", updated_at=timezone.now())
        self.manifest["source_enrollments_dropped"].extend(str(pk) for pk in ids)
        self.counts["source_enrollments_dropped"] += len(ids)

    def _slots(self, source, target) -> None:
        Slot = _model("ScheduleSlot")
        from .schedule_lock import lock_schedule

        lock_schedule(self.organization.pk, source.period_id)
        have = set(Slot.objects.filter(offering=target).values_list("kind", flat=True))
        for slot in Slot.objects.filter(offering=source, kind__in=_SHARED_KINDS).order_by("weekday", "start_time"):
            if slot.kind in have:
                self.counts["slots_target_kept"] += 1
                continue
            created = Slot.objects.create(
                organization=self.organization,
                offering=target,
                is_parked=slot.is_parked,
                **{name: getattr(slot, name) for name in _SLOT_FIELDS},
            )
            self.manifest["slots_created"].append(str(created.pk))
            self.counts["slots_copied"] += 1


__all__ = ["Blocked", "GROUP", "GroupSplitter", "REASON", "RESOURCE", "SOURCE", "TARGET", "applied_batches"]
