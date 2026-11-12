"""Dublikat fənn kartının jurnalını (W) əsas jurnala (T) birləşdirmək — heç bir xana / bal İTMƏDƏN (sahib 2026-11-11).

Sahib: «Kompüterlərin diaqnostikası iki dəfə çıxır … tələbədə iki kart. Hamısı BİR jurnalda olsun, heç bir tələbənin
qiyməti, midtermi, jurnal nəticəsi itməsin, dəyişməsin. Müəllimin jurnalına bax, əsasən orada düz olmalıdır. Bəzilərində
eyni tarixlər belə ola bilər.» ``merge_twin_offerings`` fərqli dəyərli xanada mənbənin dəyərini SƏSSİZ atır, komponent
balı fərqlidirsə dayanır və geri qaytarılmır. Bu modul eyni işi KOPYALA-VƏ-PASSİV-ET üsulu ilə görür
(:mod:`.subgroup_journal_merge_2026_11_08` naxışı): W-nin heç bir sətri silinmir.

Qaydalar (cüt öz savepoint-ində; qoruyucudan keçməyən cüt bütövlükdə geri qaytarılır və səbəbi sayılır):

* W və T eyni dövr + qrup, ikisi də açıq; W aktiv (passivdirsə ``already_merged``), T aktiv. Fənn adları normallaşdırılmış
  halda EYNİ olmalıdır (``pair_names_differ``) — yalnız cütdə ``"reviewed": true`` (sahibin təsdiqi) varsa oxşar ad keçir;
* W boş əkizdirsə (:func:`.twin_inert.is_empty_twin`) mövcud :class:`.twin_merge_empty.EmptyTwinMerge` işləyir;
* müəllimlər fərqlidirsə (``pair_instructors_differ``), W-də lab / seminar alt qrupu, rəsmi sənədli düzəliş, yekun
  nəticə, səviyyə kohortu, imtahan vərəqi varsa cüt TOXUNULMUR. W / qeydiyyata baxan HƏR əlaqə :data:`OFFERING_POLICY` /
  :data:`ENROLLMENT_POLICY`-də açıq təsnif olunub; təsnifsiz əlaqə → ``unclassified_relation`` (yeni FK unudulmasın);
* **tələbə** — W-nin hər aktiv (və ya datalı) tələbəsi üçün T-də sətir: varsa o, ``dropped`` idisə bərpa, yoxdursa yeni;
* **dərs** — T-nin eyni tarix + saat + növ dərsi (müəllimləri fərqli deyilsə); saat uyğun gəlmirsə həmin gün + növdə
  T-nin TƏK dərsi; yoxdursa T-də yeni dərs (eyni sahələr, ``created_at`` köhnə). T dərsinin boş mövzu / otaq / müəllim
  sahəsi W-dən dolur;
* **xana** — T-də boşdursa kopyalanır; eynidirsə heç nə; FƏRQLİDİRSƏ **T-nin dəyəri qalır** («müəllimin öz jurnalı
  doğrudur» — T yükü, cədvəli olan, müəllimin işlədiyi jurnaldır), W-nin dəyəri isə İTMİR: W xanası yerində qalır,
  hər iki dəyər audit manifestində (``conflicts``) və T jurnalının qiymət tarixçəsində görünən qeyd kimi yazılır;
* **komponent balı (Midterm …)** — eyni növ + adlı komponentə; T-də yoxdursa kopyalanır (mənbə cəhd id-si eyni qalır —
  imtahanın təkrar sinxronu heç nə yazmır); fərqlidirsə: yalnız BİRİ imtahandan avtomatikdirsə (``exam_source``) o
  qalır (rəsmi imtahan nəticəsi), əks halda T-ninki; hər iki dəyər manifestdə + qiymət tarixçəsində;
* imtahan bağı (``Exam.journal_offerings``) W → T; cədvəl slotu, jurnal payı, sillabus (T-də yoxdursa paylaşılır);
* W SİLİNMİR: qeydiyyatları ``dropped``, jurnal passiv. Tam manifest audit sətrindədir (``RESOURCE``) —
  geri qaytarma :mod:`.duplicate_journal_merge_undo_2026_11_11`.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .duplicate_journal_scores_2026_11_11 import REASON, Blocked, ScoreSteps
from .subject_duplicates import normalized_subject_key
from .twin_inert import is_empty_twin
from .twin_merge import _LESSON_FIELDS, _SLOT_FIELDS
from .twin_merge_empty import EmptyTwinMerge, repoint_exam_links
from .twin_relocate import closed, copy_mark, corrected_lesson_ids, corrected_mark_ids, recompute_absences

RESOURCE = "registrar.duplicate_journal_merge"
KIND = "duplicate_journal_merge"

COPY, STAY, BLOCK = "copy", "stay", "block"
#: W-yə (``CourseOffering``) baxan HƏR əlaqə: ``copy`` — T-yə köçürülür / kopyalanır; ``stay`` — passiv W-də tarixçə
#: kimi qalır (W silinmir, FK etibarlıdır); ``block`` — varsa cüt toxunulmur.
OFFERING_POLICY = {
    "registrar.Enrollment.offering": COPY,
    "registrar.Lesson.offering": COPY,
    "registrar.AssessmentComponent.offering": COPY,
    "registrar.ScheduleSlot.offering": COPY,
    "registrar.JournalShare.offering": COPY,
    "exams.Exam.journal_offerings": COPY,
    "syllabus.Syllabus.offering": COPY,
    "syllabus.SyllabusShare.offering": COPY,
    "registrar.AssessmentScheme.offering": STAY,
    "registrar.SelfWorkTopic.offering": STAY,
    "registrar.TeachingHandover.offering": STAY,
    "registrar.SubgroupPlacementEvent.offering": STAY,
    "registrar.RetakeApplication.target_offering": STAY,
    "surveys.SurveyReceipt.offering": STAY,
    "surveys.SurveyResponse.offering": STAY,
    "timetable.TimetableDraftSlot.offering": STAY,
    "subject_folder.FolderAssignment.offering": STAY,
    "registrar.LabGroup.offering": BLOCK,
    "registrar.PassiveHour.offering": BLOCK,  # 2026-11-12: passiv saat — birləşmə əl ilə həll olunur
    "registrar.SeminarGroup.offering": BLOCK,
    "registrar.ExamScoreSheet.offering": BLOCK,
    "registrar.LanguageLevelCohort.offering": BLOCK,
    "registrar.LanguageLevelCohort.source_offering": BLOCK,
    "workload.TeachingTaskRow.intensive_offering": BLOCK,
}
#: W qeydiyyatına (``Enrollment``) baxan HƏR əlaqə — eyni mənalar.
ENROLLMENT_POLICY = {
    "registrar.LessonMark.enrollment": COPY,
    "registrar.ComponentScore.enrollment": COPY,
    "registrar.JournalShare.enrollments": COPY,
    "registrar.Enrollment.superseded_by": STAY,
    "registrar.LegacyGradeFact.enrollment": STAY,
    "registrar.GuestRosterDocument.enrollment": STAY,
    "registrar.JournalHygieneDecision.enrollment": STAY,
    "registrar.JournalRemoval.enrollment": STAY,
    "registrar.SubgroupPlacementEvent.enrollment": STAY,
    "registrar.CriterionScore.enrollment": BLOCK,
    "registrar.SelfWorkMark.enrollment": BLOCK,
    "registrar.CourseWork.enrollment": BLOCK,
    "registrar.FinalGrade.enrollment": BLOCK,
    "registrar.ResitRecord.enrollment": BLOCK,
    "registrar.SelfWorkCorrection.enrollment": BLOCK,
    "registrar.CourseWorkCorrection.enrollment": BLOCK,
    "registrar.ComponentScoreCorrection.enrollment": BLOCK,
    "registrar.AbsenceCredit.enrollment": BLOCK,
    "registrar.ExamScoreEntry.enrollment": BLOCK,
    "registrar.RetakeApplication.enrollment": BLOCK,
    "registrar.RetakeApplication.placement_enrollment": BLOCK,
    "registrar.ExternalCreditRecognition.enrollment": BLOCK,
    "registrar.LanguageLevelPlacement.source_enrollment": BLOCK,
    "registrar.LanguageLevelPlacement.target_enrollment": BLOCK,
    "subject_folder.Submission.enrollment": BLOCK,
}


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def relations(model) -> dict:
    """``{"app.Model.sahə": əlaqə}`` — modelə baxan bütün FK / M2M-lər (avtomatik ara cədvəl xaric)."""
    found = {}
    for item in model._meta.get_fields(include_hidden=True):
        if not (item.is_relation and item.auto_created and not item.concrete):
            continue
        if item.related_model._meta.auto_created:
            continue
        found[f"{item.related_model._meta.label}.{item.field.name}"] = item
    return found


def unclassified_relations() -> set:
    return (set(relations(_model("CourseOffering"))) - set(OFFERING_POLICY)) | (
        set(relations(_model("Enrollment"))) - set(ENROLLMENT_POLICY)
    )


def _slug(label: str) -> str:
    return "".join(ch if ch.isalpha() else "_" for ch in label.split(".")[1].lower())


def _policy_block(policy, model, ids) -> str:
    """Təsnifsiz əlaqə və ya ``block`` əlaqəsində sətir varsa — dayanma kodu (rəqəmsiz)."""
    found = relations(model)
    if set(found) - set(policy):
        return "unclassified_relation"
    for key, item in found.items():
        if policy[key] != BLOCK:
            continue
        if item.related_model._base_manager.filter(**{f"{item.field.name}__in": ids}).exists():
            return f"source_has_{_slug(key)}"
    return ""


def retired_source_ids(organization, offering_ids) -> set:
    """Bu modulla passiv edilmiş (və geri qaytarılmamış) W jurnalları — ``merge_subjects`` onları arxiv kartda saxlayır."""
    ids = [str(pk) for pk in offering_ids]
    if not ids:
        return set()
    rows = (
        _model("AuditLog", "audit")
        .objects.filter(organization=organization, resource_type=RESOURCE, resource_id__in=ids, changes__kind=KIND)
        .values_list("resource_id", flat=True)
    )
    retired = set(rows)
    if not retired:
        return set()
    still = _model("CourseOffering")._base_manager.filter(pk__in=retired, is_active=False)
    return {str(pk) for pk in still.values_list("pk", flat=True)}


class JournalMerge(ScoreSteps):
    def __init__(self, *, organization, actor, counts, batch):
        self.organization, self.actor, self.counts, self.batch = organization, actor, counts, batch
        self.report = []  # cüt başına saylar (stdout: ``twin_merge: pair=N açar=say …``)

    def run(self, pairs) -> None:
        for index, pair in enumerate(pairs, start=len(self.report) + 1):
            before = dict(self.counts)
            reason = ""
            try:
                with transaction.atomic():
                    self._pair(dict(pair))
            except Blocked as exc:
                reason = exc.reason
            except IntegrityError:
                reason = "pair_integrity_error"
            if reason:  # geri qaytarılmış cütün sayları hesabatı şişirtməsin
                self.counts.clear()
                self.counts.update(before)
                self.counts[reason] += 1
            delta = {
                key: value - before.get(key, 0) for key, value in self.counts.items() if value != before.get(key, 0)
            }
            self.report.append((index, delta))

    # ── yoxlamalar ────────────────────────────────────────────────────────
    def _load(self, pair):
        CourseOffering = _model("CourseOffering")
        rows = {
            str(row.pk): row
            for row in CourseOffering.objects.select_for_update(of=("self",))
            .select_related("subject")
            .filter(organization=self.organization, pk__in=[pair.get("source"), pair.get("target")])
        }
        source, target = rows.get(str(pair.get("source"))), rows.get(str(pair.get("target")))
        if source is None or target is None:
            raise Blocked("pair_missing")
        if source.pk == target.pk or (source.period_id, source.group_id) != (target.period_id, target.group_id):
            raise Blocked("pair_invalid")
        if not source.is_active:
            raise Blocked("already_merged")
        if not target.is_active or closed([source.pk, target.pk]):
            raise Blocked("pair_closed_or_inactive")
        same_name = normalized_subject_key(source.subject.name) == normalized_subject_key(target.subject.name)
        if not same_name and not pair.get("reviewed"):
            raise Blocked("pair_names_differ")
        from .duplicate_subjects_rules_2026_11_11 import shared_curricula

        # Oxşar adlı cüt (2026-11-12): kartlar başqa qruplarda ayrı fənlər ola bilər — yalnız QRUPUN planları yoxlanılır.
        if shared_curricula([source.subject_id, target.subject_id], only=pair.get("curricula")):
            raise Blocked("pair_curriculum_both")  # eyni tədris planında iki ayrı sətir — həqiqətən fərqli fənlər
        return source, target

    def _check(self, source, target) -> None:
        Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
        lessons = Lesson.objects.filter(offering=source)
        enrollments = Enrollment.objects.filter(offering=source)
        taught = lessons.exists() or _model("ComponentScore").objects.filter(enrollment__offering=source).exists()
        if taught and source.instructor_id and target.instructor_id and source.instructor_id != target.instructor_id:
            raise Blocked("pair_instructors_differ")  # dərsi / balı olmayan (siyahı) jurnalda müəllim fərqi maneə deyil
        if (
            lessons.filter(lab_group__isnull=False).exists()
            or lessons.filter(seminar_group__isnull=False).exists()
            or enrollments.filter(lab_group__isnull=False).exists()
            or enrollments.filter(seminar_group__isnull=False).exists()
        ):
            raise Blocked("source_has_subgroups")
        mark_ids = list(LessonMark.objects.filter(lesson__offering=source).values_list("pk", flat=True))
        if corrected_lesson_ids(list(lessons.values_list("pk", flat=True))) or corrected_mark_ids(mark_ids):
            raise Blocked("source_corrected")
        # Bitmiş semestrin jurnalına toxunulmur: hədəfdə yekun nəticə varsa qayıb saatı / giriş balı dəyişə bilməz.
        finished = Enrollment.objects.filter(offering=target)
        if any(_model(name).objects.filter(enrollment__in=finished).exists() for name in ("FinalGrade", "ResitRecord")):
            raise Blocked("target_has_final_results")
        blocked = _policy_block(OFFERING_POLICY, type(source), [source.pk]) or _policy_block(
            ENROLLMENT_POLICY, Enrollment, list(enrollments.values_list("pk", flat=True))
        )
        if blocked:
            raise Blocked(blocked)

    # ── cüt ───────────────────────────────────────────────────────────────
    def _pair(self, pair) -> None:
        source, target = self._load(pair)
        manifest = defaultdict(list)
        empty = source if is_empty_twin(source) else None
        if empty is None and pair.get("auto") and is_empty_twin(target):
            # Avtomatik aşkarlanan (keçmiş dövr) qutu: saxlanılan kartın jurnalı BOŞDUR, data mənbə kartın
            # jurnalındadır — boş jurnal passiv olur, datalı jurnal kataloq birləşməsində saxlanılan karta keçir.
            empty, source, target = target, target, source
        if empty is not None:
            EmptyTwinMerge(organization=self.organization, actor=self.actor, counts=self.counts).merge(
                source, target, pair
            )
            if source.is_active:  # EmptyTwinMerge dayandı (öz sayğacı ilə) — heç nə yazılmayıb
                raise Blocked("empty_twin_not_merged")
            manifest["empty_twin"].append(str(source.pk))
            self._receipt(source, target, manifest, [])
            return
        self._check(source, target)
        conflicts = []
        by_student = self._enrollments(source, target, manifest)
        self._lessons(source, target, by_student, manifest, conflicts)
        self._scores(source, target, by_student, manifest, conflicts)
        for link in repoint_exam_links(source.pk, target.pk):
            manifest["exam_links"].append(link)
            self.counts["exam_links_repointed"] += 1
        self._slots(source, target, manifest)
        manifest["shares"] = EmptyTwinMerge(
            organization=self.organization, actor=self.actor, counts=self.counts
        )._shares(source, target, by_student, True)
        self._syllabus(source, target, manifest)
        self._retire(source, manifest)
        recompute_absences(list({row.pk: row for row in by_student.values()}.values()))
        self._conflict_history(target, conflicts)
        self.counts["pairs_merged"] += 1
        self.counts["students_on_target"] += len(by_student)
        self._receipt(source, target, manifest, conflicts)

    def _receipt(self, source, target, manifest, conflicts) -> None:
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            new_values={
                "source": str(source.pk),
                "target": str(target.pk),
                "source_subject": str(source.subject_id),
                "target_subject": str(target.subject_id),
                "conflicts": len(conflicts),
            },
            changes={
                "kind": KIND,
                "batch": self.batch,
                "source": str(source.pk),
                "target": str(target.pk),
                "manifest": dict(manifest),
                "conflicts": conflicts,
            },
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(source.pk),
        )

    # ── köçürmə ───────────────────────────────────────────────────────────
    def _enrollments(self, source, target, manifest) -> dict:
        """``{tələbə id → T qeydiyyatı}`` — W-də ``dropped`` OLMAYAN və ya datalı (xana / bal) hər tələbə üçün.

        Dondurulmuş (``suspended`` …) sətir də T-yə EYNİ statusla keçir — passiv W-də qalsaydı tələbə ikinci kartı
        görməyə davam edərdi. ``legacy_qb_fail`` (köhnə sistemin q/b kəsilməsi) T sətrinə daşınır."""
        Enrollment = _model("Enrollment")
        existing = {row.student_id: row for row in Enrollment.objects.select_for_update().filter(offering=target)}
        out = {}
        rows = Enrollment.objects.select_for_update().filter(offering=source).order_by("created_at", "pk")
        for row in rows:
            live = row.status != "dropped"
            if not live and not (row.lesson_marks.exists() or row.component_scores.exists()):
                continue
            found = existing.get(row.student_id)
            if found is None:
                if not live:  # W-dən çıxmış tələbənin datası W-də qalır — T-yə yeni tələbə əlavə olunmur
                    self.counts["departed_students_left_on_source"] += 1
                    continue
                guest = row.source_group_id is not None and row.source_group_id != target.group_id
                try:
                    with transaction.atomic():
                        found = Enrollment.objects.create(
                            organization=self.organization,
                            student_id=row.student_id,
                            offering=target,
                            kind=row.kind,
                            status=row.status,
                            legacy_qb_fail=row.legacy_qb_fail,
                            source_group_id=row.source_group_id if guest else None,
                            added_by=self.actor if guest else None,
                            added_at=timezone.now() if guest else None,
                        )
                except IntegrityError:
                    raise Blocked("target_enrollment_blocked") from None
                existing[row.student_id] = found
                manifest["enrollments_created"].append(str(found.pk))
                self.counts["enrollments_created"] += 1
            elif found.status == "dropped" and live:
                manifest["enrollments_reactivated"].append([str(found.pk), str(found.superseded_by_id or "")])
                Enrollment.objects.filter(pk=found.pk).update(
                    status=row.status, superseded_by=None, updated_at=timezone.now()
                )
                found.status, found.superseded_by_id = row.status, None
                self.counts["enrollments_reactivated"] += 1
            elif found.status != "enrolled" and row.status == "enrolled":
                raise Blocked("target_enrollment_not_active")
            if row.legacy_qb_fail and not found.legacy_qb_fail:
                Enrollment.objects.filter(pk=found.pk).update(legacy_qb_fail=True, updated_at=timezone.now())
                found.legacy_qb_fail = True
                manifest["qb_fail_set"].append(str(found.pk))
                self.counts["legacy_qb_fail_carried"] += 1
            out[row.student_id] = found
        return out

    def _match(self, lesson, by_slot, by_day, used):
        def fits(twin):
            teachers = {lesson.instructor_id, twin.instructor_id} - {None}
            return twin.pk not in used and len(teachers) < 2

        twin = by_slot.get((lesson.date, lesson.start_time, lesson.kind))
        if twin is not None and fits(twin):
            return twin
        same_day = [row for row in by_day.get((lesson.date, lesson.kind), []) if fits(row)]
        if len(same_day) == 1:
            self.counts["lessons_matched_by_day"] += 1
            return same_day[0]
        return None

    def _fill_fields(self, twin, lesson, manifest) -> None:
        filled = {
            name: getattr(lesson, name)
            for name in ("topic", "room_id", "instructor_id", "end_time")
            if getattr(lesson, name) and not getattr(twin, name)
        }
        if filled:
            _model("Lesson").objects.filter(pk=twin.pk).update(**filled, updated_at=timezone.now())
            manifest["lesson_fields_filled"].append([str(twin.pk), sorted(filled)])
            self.counts["lesson_fields_filled"] += 1

    def _fill_score(self, mark_id, mark, manifest) -> None:
        from core.rls import journal_unlock

        with journal_unlock():
            _model("LessonMark").objects.filter(pk=mark_id, score__isnull=True).update(
                score=mark.score, updated_at=timezone.now()
            )
        manifest["marks_score_filled"].append([str(mark_id), str(mark.score)])
        self.counts["marks_score_filled"] += 1

    def _lessons(self, source, target, by_student, manifest, conflicts) -> None:
        Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
        by_slot, by_day = {}, defaultdict(list)
        own = Lesson.objects.select_for_update().filter(offering=target, seminar_group__isnull=True, lab_group=None)
        for lesson in own.order_by("created_at"):
            by_slot.setdefault((lesson.date, lesson.start_time, lesson.kind), lesson)
            by_day[(lesson.date, lesson.kind)].append(lesson)
        kept = {
            (lesson_id, enrollment_id): (pk, status, score)
            for pk, lesson_id, enrollment_id, status, score in LessonMark.objects.filter(
                lesson__offering=target
            ).values_list("pk", "lesson_id", "enrollment_id", "status", "score")
        }
        used = set()
        for lesson in Lesson.objects.filter(offering=source).order_by("date", "start_time", "created_at"):
            twin = self._match(lesson, by_slot, by_day, used)
            if twin is None:
                twin = Lesson.objects.create(
                    organization=self.organization,
                    offering=target,
                    **{name: getattr(lesson, name) for name in _LESSON_FIELDS},
                )
                Lesson.objects.filter(pk=twin.pk).update(created_at=lesson.created_at)
                by_slot.setdefault((lesson.date, lesson.start_time, lesson.kind), twin)
                by_day[(lesson.date, lesson.kind)].append(twin)
                manifest["lessons_created"].append(str(twin.pk))
                self.counts["lessons_created"] += 1
            else:
                self.counts["lessons_deduplicated"] += 1
                self._fill_fields(twin, lesson, manifest)
            used.add(twin.pk)
            for mark in lesson.marks.select_related("enrollment").order_by("created_at"):
                enrollment = by_student.get(mark.enrollment.student_id)
                if enrollment is None:
                    self.counts["marks_of_departed_students_left_on_source"] += 1
                    continue
                current = kept.get((twin.pk, enrollment.pk))
                if current is None:
                    created = copy_mark(mark, lesson=twin, enrollment=enrollment)
                    kept[(twin.pk, enrollment.pk)] = (created.pk, mark.status, mark.score)
                    manifest["marks_created"].append(str(created.pk))
                    self.counts["marks_copied"] += 1
                elif current[1:] == (mark.status, mark.score):
                    self.counts["marks_identical"] += 1
                elif current[1] == mark.status and mark.score is None:
                    self.counts["marks_target_has_score_source_none"] += 1  # hədəf daha doludur — itki yoxdur
                elif current[1] == mark.status and current[2] is None:
                    # Balsız «iştirak» açıq xanadır (DB trigger-i də belə sayır) — mənbənin balı hədəfə YAZILIR.
                    self._fill_score(current[0], mark, manifest)
                    kept[(twin.pk, enrollment.pk)] = (current[0], mark.status, mark.score)
                else:
                    conflicts.append(
                        {
                            "type": "mark",
                            "student": mark.enrollment.student_id,
                            "date": lesson.date.isoformat(),
                            "lesson_kind": lesson.kind,
                            "source_lesson": str(lesson.pk),
                            "target_lesson": str(twin.pk),
                            "source_mark": str(mark.pk),
                            "target_mark": str(current[0]),
                            "source_value": [mark.status, None if mark.score is None else str(mark.score)],
                            "target_value": [current[1], None if current[2] is None else str(current[2])],
                            "kept": "target",
                            "target_enrollment": str(enrollment.pk),
                        }
                    )
                    self.counts["marks_conflict_target_kept"] += 1

    def _slots(self, source, target, manifest) -> None:
        from .schedule_lock import lock_schedule
        from .subgroup_merge_slot_scope import slot_key

        ScheduleSlot = _model("ScheduleSlot")
        own = list(ScheduleSlot.objects.select_for_update().filter(offering=source).select_related("offering"))
        if not own:
            return
        lock_schedule(self.organization.pk, target.period_id)
        covered = {
            slot_key(slot)
            for slot in ScheduleSlot.objects.select_for_update().filter(offering=target).select_related("offering")
        }
        now = timezone.now()
        ScheduleSlot.all_objects.filter(pk__in=[slot.pk for slot in own]).update(
            is_deleted=True, deleted_at=now, updated_at=now
        )
        manifest["slots_soft_deleted"].extend(str(slot.pk) for slot in own)
        self.counts["slots_soft_deleted"] += len(own)
        for slot in own:
            key = slot_key(slot)
            if key in covered:
                continue
            covered.add(key)
            created = ScheduleSlot.objects.create(
                organization=self.organization,
                offering=target,
                is_parked=slot.is_parked,
                **{name: getattr(slot, name) for name in _SLOT_FIELDS},
            )
            manifest["slots_created"].append(str(created.pk))
            self.counts["slots_moved"] += 1

    def _syllabus(self, source, target, manifest) -> None:
        """T-nin öz / paylaşılan sillabusu yoxdursa W-nin sillabusu T-yə KEÇİR (fənni də T-ninki olur; əvvəlki bağ
        manifestdədir). «Reuse» zəncirindəki sillabus yerindən tərpənmir — o halda T-yə paylaşılır (surət yox)."""
        from apps.syllabus.public import link_legacy_share

        Syllabus, Share = _model("Syllabus", "syllabus"), _model("SyllabusShare", "syllabus")
        own = list(Syllabus.objects.select_for_update().filter(offering=source).order_by("created_at"))
        shared = [row.syllabus for row in Share.objects.filter(offering=source).select_related("syllabus")]
        if not own and not shared:
            return
        if Syllabus.objects.filter(offering=target).exists() or Share.objects.filter(offering=target).exists():
            self.counts["syllabus_target_has_own_source_kept"] += 1
            return
        own.sort(key=lambda row: (not row.versions.filter(status="approved").exists(), row.created_at))
        for row in own:
            if row.reused_from_id is None and not Syllabus.objects.filter(reused_from=row).exists():
                manifest["syllabi_moved"].append([str(row.pk), str(source.pk), str(row.subject_id)])
                Syllabus.objects.filter(pk=row.pk).update(
                    offering=target, subject_id=target.subject_id, updated_at=timezone.now()
                )
                self.counts["syllabi_moved"] += 1
                return
        outcome = link_legacy_share(syllabus=(own + shared)[0], offering=target, user=self.actor)
        if outcome == "linked":
            manifest["syllabus_shares_created"].append(str(Share.objects.get(offering=target).pk))
            self.counts["syllabus_shared"] += 1
        else:
            self.counts[f"syllabus_not_shared_{outcome}"] += 1

    def _retire(self, source, manifest) -> None:
        Enrollment = _model("Enrollment")
        rows = list(Enrollment.objects.filter(offering=source).exclude(status="dropped").values_list("pk", "status"))
        Enrollment.objects.filter(pk__in=[pk for pk, _status in rows]).update(
            status="dropped", updated_at=timezone.now()
        )
        manifest["source_enrollments_dropped"].extend([str(pk), status] for pk, status in rows)
        self.counts["source_enrollments_dropped"] += len(rows)
        source.is_active = False
        source.save(update_fields=["is_active", "updated_at"])
        self.counts["sources_retired"] += 1


__all__ = [
    "ENROLLMENT_POLICY",
    "KIND",
    "OFFERING_POLICY",
    "REASON",
    "RESOURCE",
    "Blocked",
    "JournalMerge",
    "retired_source_ids",
    "unclassified_relations",
]
