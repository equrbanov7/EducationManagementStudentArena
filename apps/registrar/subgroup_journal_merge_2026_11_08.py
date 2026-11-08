"""Alt qrup jurnallarını ana qrupun jurnalına birləşdirmək (sahib 2026-11-08) — ``merge_subgroup_journals_20261108``.

Sahib: «ana qrup alt qrupların cəmidir … ana qrup hamısı olanda elə görünsün, mühazirə olanda da; seminar seçiləndə
bölünən, lab seçəndə bölünənlər … müəllimin yazdıqlarını dağıtmasın, yükü pozmasın». Köhnə sistem bir fənni alt qrup
adlı jurnallara bölmüşdü (536 MU1 / 536 MU2, 135 Si-1 / 135Si-2 …) — EMS-də bir fənn üçün 2–3 jurnal görünürdü. Bu
modul hər ailədə alt qrup jurnallarının tələbələrini, xanalarını və komponent ballarını ANA qrupun jurnalına
KOPYALAYIR; alt qrup bu jurnalda seminar alt qrupu olur (:mod:`apps.registrar.seminar_groups`).

Ailələr :data:`PLAN`-dadır (JSON, sabit id-lər). Hər ailə öz savepoint-ində; qoruyucudan keçməyən ailə BÜTÖVLÜKDƏ geri
qaytarılır və səbəbi sayılır (heç nə yazılmır):

* açılışlar aktiv, eyni fənn + dövr, bağlı deyil; ana jurnal (plandakı və ya fənn + dövr + ana qrup üzrə mövcud)
  aktiv və açıqdır — yoxdursa yaradılır;
* jurnalların müəllimi BİRDİR (``family_instructors_differ``) və alt qrup jurnalının bölünmüş payı yoxdur — fərqli
  müəllimli alt qruplar ayrı siniflərdir, birləşdirilmir;
* alt qrup jurnalında rəsmi düzəliş, yekun qiymət / kurs işi / təkrar imtahan / rubrik balı, lab bölgüsü, başqa
  moduldan istinad yoxdur;
* mühazirələr AYRI saatda keçməyib (``family_lectures_separate``): bir gündə hər alt qrupun öz tək-qruplu mühazirəsi
  varsa bu patok deyil, ayrı sinifdir — birləşdirilmir (sahib: «fərqli saatdadırsa bu patok deyil»);
* ana jurnalda tələbənin ``dropped`` sətri varsa (köhnə alt qrup köçürməsi) o, yenidən ``enrolled`` olur; başqa
  aktiv olmayan vəziyyət (dondurulmuş …) — ailə toxunulmur.

Köçürmə: tələbə — ana jurnalda sətri yoxdursa yaradılır («alt qrupdan əlavə» forması), reyestr qrupu ailənin alt
qrupudursa ``seminar_group`` (yalnız boşdursa); dərs — ana jurnalın BÖLÜNMƏMİŞ eyni tarix + saat + növ dərsinə (eyni
mənbədən ikinci dəfə yox), yoxdursa yeni dərs; xana YENİ sətir (``created_at`` köhnə), ana jurnalın dolu xanası QALIR;
xanaları tək alt qrupda olan seminar dərsi o alt qrupa bağlanır; komponent balı eyni adlı komponentə (yoxdursa eyni
sahələrlə yaradılır), ana jurnalda bal varsa o qalır. Alt qrup jurnalı SİLİNMİR: qeydiyyatları ``dropped``, jurnal
passiv; cədvəl slotları ana jurnala; dərs yükü saatlarına TOXUNULMUR — yalnız sətrə ana qrup əlavə olunur (jurnal
siyahısı). Tam manifest audit sətrindədir — geri qaytarma :mod:`.subgroup_journal_merge_undo_2026_11_08`.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_merge import _LESSON_FIELDS, _SLOT_FIELDS, linked_elsewhere
from .twin_relocate import closed, copy_mark, corrected_lesson_ids, corrected_mark_ids, recompute_absences

REASON = "Sahib 2026-11-08: alt qrup jurnalları ana qrupun jurnalına (seminar alt qrupu kimi) birləşdirildi"
RESOURCE = "registrar.subgroup_journal_merge"
#: ``[{"name", "target": ana açılış | null, "group": ana qrup, "sources": [alt qrup açılışları]}]`` — jurnal siyahısının
#: inventarı 2026-11-08 (alt qrup adlı ≥ 2 jurnalı olan ailələr; tək alt qrup jurnallı ailələr — fənn adı alt qruplarda
#: fərqli kodlaşdırılıb — qəsdən YOXDUR).
PLAN = tuple(json.loads((Path(__file__).with_suffix(".json")).read_text(encoding="utf-8")))
#: Alt qrup qeydiyyatında bunlar varsa ailə birləşdirilmir (kopyalanmır — yalnız komponent balı kopyalanır).
_FINAL_MODELS = ("FinalGrade", "CourseWork", "ResitRecord", "CriterionScore")


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def _empty_cells(offering) -> int:
    """Bu günədək dərslərdə tələbəyə AİD, amma boş xana sayı (lab / seminar alt qrupu nəzərə alınır)."""
    from .lab_groups import applies

    lessons = list(_model("Lesson").objects.filter(offering=offering, date__lte=timezone.localdate()))
    rows = list(_model("Enrollment").objects.filter(offering=offering, status="enrolled"))
    if not lessons or not rows:
        return 0
    filled = set(
        _model("LessonMark").objects.filter(lesson__offering=offering).values_list("lesson_id", "enrollment_id")
    )
    return sum(1 for lesson in lessons for row in rows if applies(lesson, row) and (lesson.pk, row.pk) not in filled)


class Blocked(Exception):
    """Ailə toxunulmur — savepoint geri qaytarılır, ``reason`` sayılır; ``detail`` — yalnız id/kod (şəxsi məlumat yox)."""

    def __init__(self, reason, detail=None):
        super().__init__(reason, detail)
        self.reason, self.detail = reason, dict(detail or {})


def _constraint(exc) -> str:
    """IntegrityError-un DB qaydasının adı (və ya SQLSTATE) — hesabat üçün, mətni yox."""
    diag = getattr(getattr(exc, "__cause__", None), "diag", None)
    name = getattr(diag, "constraint_name", None) or getattr(getattr(exc, "__cause__", None), "sqlstate", None)
    return "".join(ch for ch in str(name or "unknown").lower() if ch.isalnum() or ch in "_-")[:60] or "unknown"


class Merger:
    def __init__(self, *, organization, actor, counts):
        self.organization, self.actor, self.counts = organization, actor, counts
        self.report = []  # ailə başına saylar (stdout: ``subgroup_merge: family=N açar=say …``)

    def run(self, plan=None) -> None:
        for index, family in enumerate(PLAN if plan is None else plan, start=1):
            before = dict(self.counts)
            reason, detail = "", {}
            try:
                with transaction.atomic():
                    self._family(family)
            except Blocked as exc:
                reason, detail = exc.reason, exc.detail
            except IntegrityError:
                reason = "family_integrity_error"
            if reason:  # geri qaytarılmış ailənin sayları hesabatı şişirtməsin
                self.counts.clear()
                self.counts.update(before)
                self.counts[reason] += 1
            delta = {
                key: value - before.get(key, 0) for key, value in self.counts.items() if value != before.get(key, 0)
            }
            self.report.append((index, {**delta, **detail}))

    # ── yoxlamalar ────────────────────────────────────────────────────────
    def _load(self, family):
        CourseOffering = _model("CourseOffering")
        ids = [pk for pk in (family.get("target"), *family["sources"]) if pk]
        rows = {
            str(row.pk): row
            for row in CourseOffering.objects.select_for_update(of=("self",))
            .select_related("group", "subject", "period")
            .filter(organization=self.organization, pk__in=ids)
        }
        sources = [rows.get(str(pk)) for pk in family["sources"]]
        if any(source is None for source in sources):
            raise Blocked("family_missing")
        live = [source for source in sources if source.is_active]
        if not live:
            raise Blocked("already_merged")
        if len({(source.subject_id, source.period_id) for source in live}) != 1:
            raise Blocked("family_invalid")
        target = rows.get(str(family.get("target") or ""))
        if target is None and not family.get("target"):
            target = (
                CourseOffering.objects.select_for_update(of=("self",))
                .filter(
                    organization=self.organization,
                    subject_id=live[0].subject_id,
                    period_id=live[0].period_id,
                    group_id=family.get("group"),
                )
                .first()
            )
        elif target is None:
            raise Blocked("family_missing")
        if target is not None and (
            target in live
            or (target.subject_id, target.period_id) != (live[0].subject_id, live[0].period_id)
            or not target.is_active
        ):
            raise Blocked("family_target_inactive_or_invalid")
        if closed([source.pk for source in live] + ([target.pk] if target is not None else [])):
            raise Blocked("family_closed")
        return target, live

    def _check_sources(self, target, live) -> None:
        Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
        teachers = {source.instructor_id for source in live if source.instructor_id}
        if target is not None and target.instructor_id:
            teachers.add(target.instructor_id)
        if len(teachers) > 1:
            raise Blocked("family_instructors_differ")
        if _model("JournalShare").objects.filter(offering__in=live, is_active=True).exists():
            raise Blocked("source_has_shares")
        lessons = Lesson.objects.filter(offering__in=live)
        if (
            lessons.filter(lab_group__isnull=False).exists()
            or Enrollment.objects.filter(offering__in=live, lab_group__isnull=False).exists()
        ):
            raise Blocked("source_has_lab_groups")
        mark_ids = list(LessonMark.objects.filter(lesson__offering__in=live).values_list("pk", flat=True))
        if corrected_lesson_ids(list(lessons.values_list("pk", flat=True))) or corrected_mark_ids(mark_ids):
            raise Blocked("source_corrected")
        enrollment_ids = list(Enrollment.objects.filter(offering__in=live).values_list("pk", flat=True))
        if any(_model(name).objects.filter(enrollment_id__in=enrollment_ids).exists() for name in _FINAL_MODELS):
            raise Blocked("source_has_final_results")
        if any(linked_elsewhere(source) for source in live):
            raise Blocked("source_linked_elsewhere")

    # ── ailə ──────────────────────────────────────────────────────────────
    def _family(self, family) -> None:
        target, live = self._load(family)
        self._check_sources(target, live)
        empty_before = sum(_empty_cells(offering) for offering in [*live, *([target] if target else [])])
        manifest = defaultdict(list)
        if target is None:
            target = self._create_target(family, live[0], manifest)
        numbers = self._seminar_groups(target, live, manifest)
        by_student = self._enrollments(target, live, numbers, manifest, family.get("student_alias") or {})
        if family.get("seminar_default_source"):
            self._seminar_default(target, live, numbers, family["seminar_default_source"], manifest)
        touched = self._lessons(target, live, by_student, manifest)
        self._tag_seminars(touched, numbers, manifest)
        self._component_scores(target, live, by_student, manifest)
        self._slots(target, live, manifest)
        self._load_rows(target, live, manifest)
        self._retire(live, manifest)
        recompute_absences(list({row.pk: row for row in by_student.values()}.values()))
        # Sahib: «boş xana olmasın» — bir alt qrupun dərsləri o birinin tələbələrinə BOŞ xana kimi düşürsə (məs. F2-nin
        # jurnalında 6, F1-də 26 dərs) birləşmə görünüşü pozur → ailə toxunulmur.
        if _empty_cells(target) > empty_before:
            raise Blocked("family_adds_empty_cells")
        self._syllabus(target, live, manifest)
        self.counts["families_merged"] += 1
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            obj=target,
            new_values={"family": family["name"], "sources": [str(source.pk) for source in live]},
            changes={"manifest": dict(manifest), "target": str(target.pk)},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(target.pk),
        )

    def _create_target(self, family, sample, manifest):
        from .services import get_or_create_offering

        group = (
            _model("OrgUnit", "organizations")
            .objects.filter(organization=self.organization, pk=family.get("group"))
            .first()
        )
        if group is None:
            raise Blocked("target_group_missing")
        target = get_or_create_offering(
            organization=self.organization, subject=sample.subject, period=sample.period, group=group
        )
        if sample.instructor_id and target.instructor_id is None:
            target.instructor_id = sample.instructor_id
            target.save(update_fields=["instructor", "updated_at"])
        manifest["target_created"].append(str(target.pk))
        self.counts["targets_created"] += 1
        return target

    def _seminar_groups(self, target, live, manifest) -> dict:
        """``{alt qrup id → nömrə}`` — mövcud ``SeminarGroup`` (eyni qrup) saxlanılır, yoxdursa yaradılır."""
        SeminarGroup = _model("SeminarGroup")
        existing = {row.unit_id: row.number for row in SeminarGroup.objects.filter(offering=target)}
        used = set(existing.values())
        numbers = {}
        for group in sorted({source.group for source in live}, key=lambda unit: unit.name):
            if group.pk in existing:
                numbers[group.pk] = existing[group.pk]
                continue
            number = min(n for n in range(1, 10) if n not in used)
            used.add(number)
            row = SeminarGroup.objects.create(
                organization=self.organization, offering=target, number=number, name=group.name[:40], unit=group
            )
            manifest["seminar_groups_created"].append(str(row.pk))
            numbers[group.pk] = number
            self.counts["seminar_groups_created"] += 1
        return numbers

    def _enrollments(self, target, live, numbers, manifest, alias=None) -> dict:
        """``{tələbə id → ana jurnal qeydiyyatı}`` — alt qrup jurnalında ``enrolled`` olan hər tələbə üçün.

        ``alias`` — ``{dublikat hesab id: əsas hesab id}`` (sahibin təsdiqi): bloklanmış dublikat hesabın alt qrup
        jurnalındakı xanaları əsas hesabın ana jurnal sətrinə yazılır (o sətir ana jurnalda AKTİV olmalıdır)."""
        Enrollment, Record = _model("Enrollment"), _model("StudentAcademicRecord")
        existing = {row.student_id: row for row in Enrollment.objects.select_for_update().filter(offering=target)}
        out = {}
        for duplicate, keep in (alias or {}).items():
            found = existing.get(int(keep))
            if found is None or found.status != "enrolled":
                raise Blocked("alias_target_not_enrolled")
            out[int(duplicate)] = found
            self.counts["student_alias_mapped"] += 1
        rows = list(
            Enrollment.objects.select_for_update()
            .filter(offering__in=live, status="enrolled")
            .exclude(student_id__in=list(out))
        )
        groups = dict(
            Record.objects.filter(
                organization=self.organization, student_id__in=[row.student_id for row in rows], is_active=True
            ).values_list("student_id", "group_id")
        )
        for row in sorted(rows, key=lambda item: (item.created_at, item.pk)):
            if row.student_id in out:
                continue
            found = existing.get(row.student_id)
            if found is None:
                group_id = groups.get(row.student_id)
                guest = group_id is not None and group_id != target.group_id
                try:
                    with transaction.atomic():
                        found = Enrollment.objects.create(
                            organization=self.organization,
                            student_id=row.student_id,
                            offering=target,
                            kind=row.kind,
                            status="enrolled",
                            source_group_id=group_id if guest else None,
                            added_by=self.actor if guest else None,
                            added_at=timezone.now() if guest else None,
                        )
                except IntegrityError as exc:
                    raise Blocked(
                        "target_enrollment_blocked",
                        {"blocked_enrollment": str(row.pk)[:8], "blocked_rule": _constraint(exc)},
                    ) from None
                manifest["enrollments_created"].append(str(found.pk))
                self.counts["enrollments_created"] += 1
            elif found.status == "dropped":
                manifest["enrollments_reactivated"].append([str(found.pk), str(found.superseded_by_id or "")])
                Enrollment.objects.filter(pk=found.pk).update(
                    status="enrolled", superseded_by=None, updated_at=timezone.now()
                )
                found.status, found.superseded_by_id = "enrolled", None
                self.counts["enrollments_reactivated"] += 1
            elif found.status != "enrolled":
                raise Blocked("target_enrollment_not_active", {"blocked_enrollment": str(found.pk)[:8]})
            number = numbers.get(groups.get(row.student_id))
            if number and found.seminar_group is None:
                Enrollment.objects.filter(pk=found.pk).update(seminar_group=number, updated_at=timezone.now())
                found.seminar_group = number
                manifest["seminar_group_set"].append(str(found.pk))
                self.counts["seminar_group_set"] += 1
            out[row.student_id] = found
        return out

    def _seminar_default(self, target, live, numbers, source_pk, manifest) -> None:
        """Ana jurnalda alt qrupu olmayan hər tələbə bu mənbənin alt qrupuna (sahib 2026-11-08: 536 Bi 1 ana qrupda
        saxlanmışdı — ana qrupun öz tələbələri həmin alt qrupdur)."""
        source = next((row for row in live if str(row.pk) == str(source_pk)), None)
        number = numbers.get(source.group_id) if source is not None else None
        if number is None:
            raise Blocked("family_invalid")
        Enrollment = _model("Enrollment")
        rows = Enrollment.objects.filter(offering=target, status="enrolled", seminar_group__isnull=True)
        ids = [str(pk) for pk in rows.values_list("pk", flat=True)]
        rows.update(seminar_group=number, updated_at=timezone.now())
        manifest["seminar_group_set"].extend(ids)
        self.counts["seminar_group_set"] += len(ids)

    def _lessons(self, target, live, by_student, manifest) -> set:
        Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
        by_slot, by_day = {}, defaultdict(list)
        own = Lesson.objects.select_for_update().filter(offering=target, seminar_group__isnull=True, lab_group=None)
        for lesson in own.order_by("created_at"):
            by_slot.setdefault((lesson.date, lesson.start_time, lesson.kind), lesson)
            by_day[(lesson.date, lesson.kind)].append(lesson)
        filled = set(LessonMark.objects.filter(lesson__offering=target).values_list("lesson_id", "enrollment_id"))
        used, touched = set(), set()
        for lesson in Lesson.objects.filter(offering__in=live).order_by("date", "start_time", "created_at"):
            twin = by_slot.get((lesson.date, lesson.start_time, lesson.kind))
            same_day = by_day.get((lesson.date, lesson.kind), [])
            if twin is None and (lesson.start_time is None or same_day and same_day[0].start_time is None):
                twin = same_day[0] if len(same_day) == 1 else None
            if twin is not None and (twin.pk, lesson.offering_id) in used:
                twin = None  # eyni alt qrup jurnalının ikinci dərsi — bir dərsə yığılmır
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
                self.counts["lessons_matched"] += 1
            used.add((twin.pk, lesson.offering_id))
            touched.add(twin.pk)
            for mark in lesson.marks.select_related("enrollment").order_by("created_at"):
                enrollment = by_student.get(mark.enrollment.student_id)
                if enrollment is None:
                    self.counts["marks_of_departed_students_kept_in_source"] += 1
                    continue
                if (twin.pk, enrollment.pk) in filled:
                    self.counts["marks_target_kept"] += 1
                    continue
                created = copy_mark(mark, lesson=twin, enrollment=enrollment)
                filled.add((twin.pk, enrollment.pk))
                manifest["marks_created"].append(str(created.pk))
                self.counts["marks_copied"] += 1
        return touched

    def _tag_seminars(self, touched, numbers, manifest) -> None:
        """Xanaları tək alt qrupda olan seminar dərsi həmin alt qrupa bağlanır. Mühazirə bağlanmır (seminar alt qrupu
        yalnız seminara aiddir); hər alt qrupun bir gündə öz ayrı mühazirəsi varsa ailə ayrı sinifdir → toxunulmur."""
        Lesson = _model("Lesson")
        lessons = list(
            Lesson.objects.filter(pk__in=touched, kind__in=("seminar", "lecture"), seminar_group__isnull=True)
            .prefetch_related("marks__enrollment")
            .order_by("date", "start_time")
        )
        corrected = corrected_lesson_ids([lesson.pk for lesson in lessons])
        family = set(numbers.values())
        lecture_days = defaultdict(set)
        for lesson in lessons:
            groups = {mark.enrollment.seminar_group for mark in lesson.marks.all()}
            single = groups.pop() if len(groups) == 1 and None not in groups else None
            if lesson.kind == "lecture":
                if single is not None:
                    lecture_days[lesson.date].add(single)
                continue
            if single is None or str(lesson.pk) in corrected:
                continue
            Lesson.objects.filter(pk=lesson.pk).update(seminar_group=single, updated_at=timezone.now())
            manifest["seminar_lessons_tagged"].append(str(lesson.pk))
            self.counts["seminar_lessons_tagged"] += 1
        if len(family) > 1 and any(family <= days for days in lecture_days.values()):
            raise Blocked("family_lectures_separate")
        # Fərqli GÜNLƏRDƏ keçən ayrı mühazirələr: hər alt qrupun yalnız özünə aid mühazirəsi var və onlar birgə
        # mühazirələrdən az deyil — ayrı sinifdir (boşluq olsa adətən yalnız BİR alt qrupda olur).
        singles = [lesson for lesson in lessons if lesson.kind == "lecture" and self._single(lesson) is not None]
        joint = sum(1 for lesson in lessons if lesson.kind == "lecture" and self._single(lesson) is None)
        if len({self._single(lesson) for lesson in singles}) > 1 and len(singles) >= joint:
            raise Blocked("family_lectures_separate")

    @staticmethod
    def _single(lesson):
        groups = {mark.enrollment.seminar_group for mark in lesson.marks.all()}
        return groups.pop() if len(groups) == 1 and None not in groups else None

    def _component_scores(self, target, live, by_student, manifest) -> None:
        Component, Score = _model("AssessmentComponent"), _model("ComponentScore")
        own = {row.name: row for row in Component.objects.filter(offering=target)}
        taken = set(Score.objects.filter(component__offering=target).values_list("component_id", "enrollment_id"))
        for score in Score.objects.filter(component__offering__in=live).select_related("component", "enrollment"):
            enrollment = by_student.get(score.enrollment.student_id)
            if enrollment is None:
                self.counts["scores_of_departed_students_kept_in_source"] += 1
                continue
            source = score.component
            component = own.get(source.name)
            if component is None:
                component = Component.objects.create(
                    organization=self.organization,
                    offering=target,
                    name=source.name,
                    kind=source.kind,
                    held_on=source.held_on,
                    max_score=source.max_score,
                    order=source.order,
                )
                own[source.name] = component
                manifest["components_created"].append(str(component.pk))
                self.counts["components_created"] += 1
            if (component.pk, enrollment.pk) in taken:
                self.counts["scores_target_kept"] += 1
                continue
            created = Score.objects.create(
                organization=self.organization,
                component=component,
                enrollment=enrollment,
                score=score.score,
                entered_by_id=score.entered_by_id,
                exam_source=score.exam_source,
            )
            taken.add((component.pk, enrollment.pk))
            manifest["scores_created"].append(str(created.pk))
            self.counts["scores_copied"] += 1

    def _syllabus(self, target, live, manifest) -> None:
        """Ana jurnalın öz / paylaşılan sillabusu yoxdursa alt qrup jurnalının sillabusu ÖZ YERİNDƏ paylaşılır
        (surət yox; təsdiqlənmiş üstündür) — müəllim jurnalda birdən «Sillabus yarat» görməsin."""
        from apps.syllabus.public import link_legacy_share

        Syllabus, Share = _model("Syllabus", "syllabus"), _model("SyllabusShare", "syllabus")
        if Syllabus.objects.filter(offering=target).exists() or Share.objects.filter(offering=target).exists():
            return
        found = list(Syllabus.objects.filter(offering__in=live)) + [
            row.syllabus for row in Share.objects.filter(offering__in=live).select_related("syllabus")
        ]
        if not found:
            self.counts["target_without_syllabus"] += 1
            return
        found.sort(key=lambda row: (not row.versions.filter(status="approved").exists(), row.created_at))
        outcome = link_legacy_share(syllabus=found[0], offering=target, user=self.actor)
        if outcome == "linked":
            share = Share.objects.get(offering=target)
            manifest["syllabus_shares_created"].append(str(share.pk))
            self.counts["syllabus_shared"] += 1
        else:
            self.counts[f"syllabus_not_shared_{outcome}"] += 1

    def _slots(self, target, live, manifest) -> None:
        ScheduleSlot = _model("ScheduleSlot")
        own = list(ScheduleSlot.objects.select_for_update().filter(offering__in=live))
        if not own:
            return
        from .schedule_lock import lock_schedule

        lock_schedule(self.organization.pk, target.period_id)
        keep_target = ScheduleSlot.objects.filter(offering=target).exists()
        now = timezone.now()
        ScheduleSlot.all_objects.filter(pk__in=[slot.pk for slot in own]).update(
            is_deleted=True, deleted_at=now, updated_at=now
        )
        manifest["slots_soft_deleted"].extend(str(slot.pk) for slot in own)
        self.counts["slots_soft_deleted"] += len(own)
        if keep_target:
            return
        seen = set()
        for slot in own:
            key = tuple(getattr(slot, name) for name in ("weekday", "start_time", "kind", "week_type"))
            if key in seen:
                continue
            seen.add(key)
            created = ScheduleSlot.objects.create(
                organization=self.organization,
                offering=target,
                is_parked=slot.is_parked,
                **{name: getattr(slot, name) for name in _SLOT_FIELDS},
            )
            manifest["slots_created"].append(str(created.pk))
            self.counts["slots_moved"] += 1

    def _load_rows(self, target, live, manifest) -> None:
        """Dərs yükü SAATLARINA toxunulmur — alt qrupu olan sətrə yalnız ana qrup əlavə olunur (jurnal siyahısı)."""
        Row = _model("TeachingTaskRow", "workload")
        rows = (
            Row.objects.filter(
                organization=self.organization,
                subject_id=target.subject_id,
                period_id=target.period_id,
                groups__in=[source.group_id for source in live],
            )
            .exclude(groups=target.group_id)
            .distinct()
        )
        for row in rows:
            row.groups.add(target.group_id)
            manifest["load_rows_group_added"].append(str(row.pk))
            self.counts["load_rows_group_added"] += 1

    def _retire(self, live, manifest) -> None:
        Enrollment = _model("Enrollment")
        ids = list(Enrollment.objects.filter(offering__in=live, status="enrolled").values_list("pk", flat=True))
        Enrollment.objects.filter(pk__in=ids).update(status="dropped", updated_at=timezone.now())
        manifest["source_enrollments_dropped"].extend(str(pk) for pk in ids)
        self.counts["source_enrollments_dropped"] += len(ids)
        for source in live:
            source.is_active = False
            source.save(update_fields=["is_active", "updated_at"])
            manifest["sources_retired"].append(str(source.pk))
            self.counts["sources_retired"] += 1


def undo(*, organization, actor, counts) -> None:
    from .subgroup_journal_merge_undo_2026_11_08 import undo as run_undo

    run_undo(organization=organization, actor=actor, counts=counts)


__all__ = ["PLAN", "Blocked", "Merger", "undo"]
