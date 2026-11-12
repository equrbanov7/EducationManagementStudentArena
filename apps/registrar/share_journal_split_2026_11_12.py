"""Bölünmüş jurnalın PAYINI ayrıca alt qrup jurnalına çıxarmaq (sahib 2026-11-12, MR-000188) — ``split_share_journal_20261112``.

434 R «İxtisasyönümlü xarici dil-3»: qrup iki alt qrupa bölünüb (köhnə sistemdə 14702 — Yeganə Hidayətova, 14703 —
Günay Əmirova). EMS-də BİR jurnal (sahibi Yeganə) var, Günayın 9 tələbəsi orada ``JournalShare`` ilə ona verilib
(:mod:`.applications_repair_2026_11_07b`). Nəticədə jurnalın sahibi hər iki müəllimdə Yeganə görünür, dərs sütunları
bir-birinin tələbələrinə düşür. Sahib: «Ayrı jurnala böl» — Günayın tələbələri üçün AYRICA alt qrup jurnalı (sahibi
Günay), onun keçdiyi dərslərin xanaları və tələbələrin balları ora köçsün, Yeganədə yalnız onun tələbələri qalsın.
Dərs yükü sətri (hər birinə 105 saat seminar) artıq bölünüb — ona TOXUNULMUR.

Qaydalar (hamısı bir tranzaksiyada; qoruyucu pozularsa ``Blocked`` → heç nə yazılmır):

* mənbə jurnal aktiv, açıq, sahibi :data:`OWNER`; müəllimin aktiv payı var; :data:`STUDENTS`-in hamısı mənbədə
  ``enrolled``-dir; onların yekun qiyməti / kurs işi / təkrar imtahanı / rubrik balı yoxdur; köçən xanalarda və
  silinən dərslərdə rəsmi düzəliş (``JournalCorrection`` / ``LessonCorrection``) yoxdur;
* YENİ qrup — ``OrgUnit(group)`` ana qrupla eyni ixtisas altında, ``settings.parent_group`` = ana qrup (reyestrdə alt
  qrup kimi görünür), ``settings.share_split`` = işarə. Tələbələrin AKADEMİK qrupu DƏYİŞMİR (başqa fənlərinə toxunulmur)
  — yeni jurnala «alt qrupdan əlavə» (``source_group`` = ana qrup) qeydiyyatı ilə düşürlər;
* YENİ jurnal — eyni fənn + dövr, müəllim :data:`TEACHER`, saat / «Praktiki məşğələ» / qiymətləndirmə sxemi və
  komponentləri (Midterm) mənbədən;
* dərs: mənbənin həmin tələbələrin xanası olan HƏR dərsi — müəllimi :data:`TEACHER`-dir və ya müəllimsizdir (köhnə
  sistem; payın müəllimi keçib) — yeni jurnalda eyni sahələrlə yeni dərs olur və bu tələbələrin xanaları ora
  kopyalanır (``created_at`` köhnəsi). BAŞQA müəllimin dərsindəki xanalar köçmür (sayılır, tarixçədə qalır);
* mənbədə xanası qalmayan, müəllimi :data:`TEACHER` və ya boş olan, başqa istinadı olmayan dərs SİLİNİR (Yeganənin
  jurnalında boş Günay sütunları qalmasın) — tam surəti (xanaları ilə) manifestdədir, ``undo`` eyni id ilə bərpa edir;
* komponent balı (Midterm …) eyni adlı komponentə kopyalanır; mənbə qeydiyyatları ``dropped`` (silinmir, imtahan
  sübutları onlara bağlı qalır), müəllimin və sahibin mənbədəki aktiv payları passiv (sahib tək qalır → tam baxış);
* cədvəl: mənbənin müəllimi :data:`TEACHER` olan slotları yeni jurnala keçir (köhnəsi yumşaq silinir).

Paket id-si ``sharesplit-YYYYMMDD-HHMMSS-xxxx`` audit sətrinin ``resource_id``-sidir; tam manifest həmin sətrin
``changes``-indədir. Geri qaytarma — :mod:`.share_journal_split_undo_2026_11_12`. Şəxsi məlumat yoxdur — YALNIZ id-lər.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_merge import _LESSON_FIELDS, _SLOT_FIELDS
from .twin_relocate import closed, copy_mark, corrected_lesson_ids, corrected_mark_ids, recompute_absences

REASON = "Sahib 2026-11-12 (MR-000188): 434 R payı ayrıca alt qrup jurnalına çıxarıldı — Günay Əmirovanın tələbələri"
RESOURCE = "registrar.share_journal_split"
MARKER = "MR-000188"

OFFERING = "dee9eb13-fbec-49e4-9178-0c3fda81bf94"  # 434 R «İxtisasyönümlü xarici dil-3» (QKU-107)
OWNER = 8227  # Yeganə Hidayətova — mənbə jurnalın sahibi qalır
TEACHER = 8373  # Günay Əmirova — yeni alt qrup jurnalının sahibi
STUDENTS = (5405, 5407, 5408, 5277, 5286, 5281, 5271, 5285, 5287)  # köhnə 14703 + 29.10 midterm siyahısı
GROUP_NAME = "434 R-2"

#: Bunlardan biri varsa tələbə köçmür (yekun nəticə — RİM ayrıca baxır).
_FINAL_MODELS = ("FinalGrade", "CourseWork", "ResitRecord", "CriterionScore")
#: Silinən dərsin surətinə yazılan əlavə sahələr (``_LESSON_FIELDS``-dən kənar).
_LESSON_EXTRA = ("lab_group", "seminar_group")
_SPEC = {
    "offering": OFFERING,
    "owner": OWNER,
    "teacher": TEACHER,
    "students": STUDENTS,
    "group_name": GROUP_NAME,
}


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
    return f"sharesplit-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"


def existing_split(organization, spec):
    """Əvvəlki (geri qaytarılmamış) tətbiqin yeni jurnalı — idempotentlik üçün."""
    return (
        _model("CourseOffering")
        .objects.filter(
            organization=organization,
            is_active=True,
            group__settings__share_split=MARKER,
            group__settings__share_split_source=str(spec["offering"]),
        )
        .first()
    )


class Splitter:
    def __init__(self, *, organization, actor, counts, spec=None):
        self.organization, self.actor, self.counts = organization, actor, counts
        self.spec = dict(spec or _SPEC)
        self.manifest = defaultdict(list)
        self.batch = ""

    # ── giriş ─────────────────────────────────────────────────────────────
    def run(self) -> None:
        if existing_split(self.organization, self.spec) is not None:
            self.counts["already_split"] += 1
            return
        source, share, rows = self._guard()
        lessons, marks, other = self._plan(source, rows)
        self._guard_corrections(marks, lessons)
        self.batch = new_batch()
        group = self._group(source)
        target = self._offering(source, group)
        components = self._components(source, target)
        by_source = self._enrollments(source, target, rows)
        self._moving = {row.pk for row in rows}
        self._lessons(target, lessons, marks, by_source)
        self.counts["marks_other_teacher_kept"] += other
        self._scores(components, by_source)
        self._delete_emptied(lessons)
        self._retire(source, share, rows)
        self._slots(source, target)
        recompute_absences(list(rows) + list(by_source.values()))
        self.counts["journals_split"] += 1
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            obj=target,
            new_values={"source": str(source.pk), "target": str(target.pk), "teacher": self.spec["teacher"]},
            changes={"manifest": dict(self.manifest), "source": str(source.pk), "target": str(target.pk)},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=self.batch,
        )

    # ── qoruyucular ───────────────────────────────────────────────────────
    def _guard(self):
        Offering, Share, Enrollment = _model("CourseOffering"), _model("JournalShare"), _model("Enrollment")
        source = (
            Offering.objects.select_for_update(of=("self",))
            .select_related("group", "period")
            .filter(organization=self.organization, pk=self.spec["offering"])
            .first()
        )
        if source is None or not source.is_active or source.group_id is None:
            raise Blocked("source_missing_or_inactive")
        if source.instructor_id != self.spec["owner"]:
            raise Blocked("source_owner_changed")
        if source.period.locked_at is not None or closed([source.pk]):
            raise Blocked("source_closed")
        teacher = _teacher(self.organization, self.spec["teacher"])
        if teacher is None:
            raise Blocked("teacher_inactive")
        share = (
            Share.objects.select_for_update()
            .filter(organization=self.organization, offering=source, teacher_id=teacher.pk, is_active=True)
            .first()
        )
        if share is None:
            raise Blocked("teacher_share_missing")
        rows = list(
            Enrollment.objects.select_for_update(of=("self",))
            .filter(offering=source, student_id__in=self.spec["students"], status="enrolled")
            .order_by("pk")
        )
        if len(rows) != len(set(self.spec["students"])):
            raise Blocked("roster_changed")
        limited = set(share.enrollments.values_list("pk", flat=True))
        if limited and limited != {row.pk for row in rows}:
            raise Blocked("share_roster_differs")
        for name in _FINAL_MODELS:
            if _model(name).objects.filter(enrollment__in=rows).exists():
                raise Blocked("students_have_final_results")
        name_taken = (
            _model("OrgUnit", "organizations")
            .objects.filter(
                organization=self.organization, parent_id=source.group.parent_id, name=self.spec["group_name"]
            )
            .exists()
        )
        if name_taken:
            raise Blocked("group_name_taken")
        self.teacher = teacher
        return source, share, rows

    def _plan(self, source, rows):
        """Köçən dərslər (sıra ilə) və onların bu tələbələrə aid xanaları; başqa müəllimin dərsindəki xana sayı."""
        LessonMark = _model("LessonMark")
        marks = defaultdict(list)
        lessons, other = {}, 0
        query = (
            LessonMark.objects.select_for_update(of=("self",))
            .filter(enrollment__in=rows)
            .select_related("lesson")
            .order_by("lesson__date", "lesson__start_time", "lesson__created_at", "created_at")
        )
        for mark in query:
            lesson = mark.lesson
            if lesson.instructor_id not in (None, self.spec["teacher"]):
                other += 1
                continue
            lessons.setdefault(lesson.pk, lesson)
            marks[lesson.pk].append(mark)
        return list(lessons.values()), marks, other

    def _guard_corrections(self, marks, lessons) -> None:
        ids = [mark.pk for rows in marks.values() for mark in rows]
        if corrected_mark_ids(ids) or corrected_lesson_ids([lesson.pk for lesson in lessons]):
            raise Blocked("corrected_cells")

    # ── yaratma ───────────────────────────────────────────────────────────
    def _group(self, source):
        OrgUnit = _model("OrgUnit", "organizations")
        parent = source.group
        raw = parent.settings if isinstance(parent.settings, dict) else {}
        keys = ("language_sector", "course_year", "admission_year", "curriculum_id", "capacity", "education_form")
        settings = {key: raw.get(key, "") for key in keys}
        settings.update(
            parent_group=str(parent.pk),
            share_split=MARKER,
            share_split_source=str(source.pk),
            share_split_batch=self.batch,
        )
        group = OrgUnit.objects.create(
            organization=self.organization,
            parent_id=parent.parent_id,
            unit_type="group",
            name=self.spec["group_name"],
            slug=f"share-split-{uuid.uuid4().hex}",
            code="",
            settings=settings,
            is_active=True,
        )
        self.manifest["group_created"].append(str(group.pk))
        return group

    def _offering(self, source, group):
        Offering, Scheme = _model("CourseOffering"), _model("AssessmentScheme")
        target = Offering.objects.create(
            organization=self.organization,
            subject_id=source.subject_id,
            period_id=source.period_id,
            group=group,
            course_id=source.course_id,
            instructor=self.teacher,
            lesson_hours=source.lesson_hours,
            seminar_is_practical=source.seminar_is_practical,
        )
        self.manifest["target_created"].append(str(target.pk))
        scheme = Scheme.objects.filter(offering=source).first()
        if scheme is not None:
            Scheme.objects.create(
                organization=self.organization,
                offering=target,
                entry_score_max=scheme.entry_score_max,
                pass_threshold=scheme.pass_threshold,
                min_final_exam_score=scheme.min_final_exam_score,
            )
        self.counts["journals_created"] += 1
        return target

    def _components(self, source, target) -> dict:
        Component = _model("AssessmentComponent")
        mapping = {}
        for row in Component.objects.filter(offering=source).order_by("order", "name"):
            mapping[row.pk] = Component.objects.create(
                organization=self.organization,
                offering=target,
                name=row.name,
                kind=row.kind,
                held_on=row.held_on,
                max_score=row.max_score,
                rubric_id=row.rubric_id,
                order=row.order,
            )
            self.counts["components_created"] += 1
        return mapping

    def _enrollments(self, source, target, rows) -> dict:
        Enrollment = _model("Enrollment")
        now = timezone.now()
        by_source = {}
        for row in rows:
            by_source[row.pk] = Enrollment.objects.create(
                organization=self.organization,
                offering=target,
                student_id=row.student_id,
                kind=row.kind,
                status="enrolled",
                source_group_id=source.group_id,
                added_by=self.actor,
                added_at=now,
            )
            self.manifest["enrollments_created"].append(str(by_source[row.pk].pk))
        self.counts["students_moved"] += len(by_source)
        return by_source

    def _lessons(self, target, lessons, marks, by_source) -> None:
        Lesson = _model("Lesson")
        for lesson in lessons:
            twin = Lesson.objects.create(
                organization=self.organization,
                offering=target,
                **{name: getattr(lesson, name) for name in _LESSON_FIELDS},
            )
            Lesson.objects.filter(pk=twin.pk).update(created_at=lesson.created_at)
            self.manifest["lessons_created"].append(str(twin.pk))
            self.counts["lessons_created"] += 1
            for mark in marks[lesson.pk]:
                created = copy_mark(mark, lesson=twin, enrollment=by_source[mark.enrollment_id])
                self.manifest["marks_created"].append(str(created.pk))
                self.counts["marks_copied"] += 1

    def _scores(self, components, by_source) -> None:
        Score = _model("ComponentScore")
        for score in Score.objects.filter(enrollment_id__in=list(by_source)).order_by("created_at"):
            component = components.get(score.component_id)
            if component is None:
                self.counts["scores_without_component_kept"] += 1
                continue
            created = Score.objects.create(
                organization=self.organization,
                component=component,
                enrollment=by_source[score.enrollment_id],
                score=score.score,
                entered_by_id=score.entered_by_id,
                exam_source=score.exam_source,
            )
            Score.objects.filter(pk=created.pk).update(created_at=score.created_at)
            self.manifest["scores_created"].append(str(created.pk))
            self.counts["scores_copied"] += 1

    # ── mənbənin təmizlənməsi ─────────────────────────────────────────────
    def _delete_emptied(self, lessons) -> None:
        """Bütün xanaları köçən (müəllimi bu müəllim / boş) dərs mənbədən silinir — surəti manifestdə."""
        Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
        moving = self._moving
        for lesson in lessons:
            marks = list(LessonMark.objects.filter(lesson=lesson))
            if any(mark.enrollment_id not in moving for mark in marks):
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

    def _retire(self, source, share, rows) -> None:
        Share, Enrollment = _model("JournalShare"), _model("Enrollment")
        ids = [row.pk for row in rows]
        Enrollment.objects.filter(pk__in=ids).update(status="dropped", updated_at=timezone.now())
        self.manifest["source_enrollments_dropped"].extend(str(pk) for pk in ids)
        self.counts["source_enrollments_dropped"] += len(ids)
        retire = [share.pk]
        others = Share.objects.filter(offering=source, is_active=True).exclude(pk=share.pk)
        # Sahib tək qalırsa onun öz (alt qrup siyahılı) payı da lazım deyil — sahib payı olmadan TAM görür.
        if all(row.teacher_id == source.instructor_id for row in others):
            retire.extend(row.pk for row in others)
        Share.objects.filter(pk__in=retire).update(is_active=False, updated_at=timezone.now())
        self.manifest["shares_retired"].extend(str(pk) for pk in retire)
        self.counts["shares_retired"] += len(retire)
        from .journal_shares import forget

        forget(source)

    def _slots(self, source, target) -> None:
        Slot = _model("ScheduleSlot")
        from .schedule_lock import lock_schedule

        lock_schedule(self.organization.pk, source.period_id)
        own = list(Slot.objects.select_for_update().filter(offering=source, instructor_id=self.spec["teacher"]))
        if not own:
            self.counts["slots_none_for_teacher"] += 1
            return
        now = timezone.now()
        Slot.all_objects.filter(pk__in=[slot.pk for slot in own]).update(
            is_deleted=True, deleted_at=now, updated_at=now
        )
        self.manifest["slots_soft_deleted"].extend(str(slot.pk) for slot in own)
        for slot in own:
            created = Slot.objects.create(
                organization=self.organization,
                offering=target,
                is_parked=slot.is_parked,
                **{name: getattr(slot, name) for name in _SLOT_FIELDS},
            )
            self.manifest["slots_created"].append(str(created.pk))
            self.counts["slots_moved"] += 1


def _plain(value):
    """JSON-a yazılan dəyər: tarix/saat → ISO, Decimal → str, qalanı olduğu kimi."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is not None and type(value).__name__ == "Decimal":
        return str(value)
    return value


def _referenced(lesson) -> bool:
    """Dərsə xanadan başqa istinad (düzəliş və s.) varmı — varsa silinmir."""
    for relation in lesson._meta.related_objects:
        if relation.related_name == "marks":
            continue
        accessor = relation.related_model._base_manager.filter(**{relation.field.name: lesson})
        if accessor.exists():
            return True
    return False


def _teacher(organization, pk):
    """Aktiv və bu təşkilatda qiymət yazmaq səlahiyyətli müəllim (yoxdursa ``None``)."""
    from django.contrib.auth import get_user_model

    from .integrity import is_authorized_instructor

    user = get_user_model().objects.filter(pk=pk, is_active=True).first()
    if user is None or not is_authorized_instructor(organization=organization, instructor=user):
        return None
    return user


__all__ = ["Blocked", "GROUP_NAME", "MARKER", "OFFERING", "REASON", "RESOURCE", "STUDENTS", "Splitter"]
