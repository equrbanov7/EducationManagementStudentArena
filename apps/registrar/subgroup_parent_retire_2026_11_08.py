"""Ana qrup jurnalını yığışdırmaq — alt qruplar görünsün (sahib 2026-11-08) — ``resolve_subgroup_families_20261108``.

Sahib: «müqayisə zamanı yazılan günlərdə fərq çıxacaqsa … 2 alt qrupu göstərəcəksənsə ana qrupu sil, yox ana qrupu
göstərəcəksənsə digərlərini sil … birləşdirmə zamanı hansısa xana itəcək, dərs pozulacaqsa — onda ana qrupu silərsən,
alt qruplar görünər». Birləşmə (:mod:`.subgroup_journal_merge_2026_11_08`) qoruyucudan keçmirsə (alt qrupların dərsləri
fərqlidir, mühazirələr ayrı saatdadır, müəllimlər fərqlidir) bu modul ANA jurnalın qeydlərini alt qrup jurnallarına
KOPYALAYIR (yalnız boş xanaya; alt qrupun dolu xanası qalır) və ana jurnalı passiv edir — silinmir, xanaları qalır.

Qoruyucular (``Blocked`` → ailə toxunulmur): ana jurnal aktiv və açıqdır; ana jurnalda bölünmüş pay, rəsmi düzəliş,
yekun nəticə, lab bölgüsü, başqa moduldan istinad yoxdur; ana jurnalın HƏR aktiv tələbəsi bir alt qrup jurnalına düşür
(orada aktiv sətri və ya reyestr qrupu); köçürmə alt qruplarda boş xana sayını ARTIRMIR. Dərs yükü saatlarına və
cədvəl slotlarına toxunulmur. Manifest audit sətrindədir — :func:`undo` yalnız sonradan data yaranmayıbsa qaytarır.
"""

from __future__ import annotations

from collections import defaultdict

from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .subgroup_journal_merge_2026_11_08 import _FINAL_MODELS, Blocked, _empty_cells, _model
from .twin_merge import _LESSON_FIELDS, linked_elsewhere
from .twin_relocate import closed, copy_mark, corrected_lesson_ids, corrected_mark_ids, recompute_absences

REASON = "Sahib 2026-11-08: birləşmə xananı itirərdi — ana qrup jurnalı yığışdırıldı, alt qruplar görünür"
RESOURCE = "registrar.subgroup_parent_retire"


class Splitter:
    def __init__(self, *, organization, actor, counts):
        self.organization, self.actor, self.counts = organization, actor, counts

    def split(self, parent, children, name) -> None:
        self._check(parent, children)
        empty_before = sum(_empty_cells(offering) for offering in [parent, *children])
        manifest = defaultdict(list)
        placed = self._enrollments(parent, children, manifest)
        self._lessons(parent, children, placed, manifest)
        self._component_scores(parent, placed, manifest)
        self._retire(parent, manifest)
        recompute_absences(list({row.pk: row for row in placed.values()}.values()))
        if sum(_empty_cells(child) for child in children) > empty_before:
            raise Blocked("split_adds_empty_cells")
        self._syllabus(parent, children, manifest)
        self.counts["parents_retired"] += 1
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            obj=parent,
            new_values={"family": name, "children": [str(child.pk) for child in children]},
            changes={"manifest": dict(manifest), "parent": str(parent.pk)},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(parent.pk),
        )

    def _check(self, parent, children) -> None:
        Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
        if not parent.is_active or not children or any(not child.is_active for child in children):
            raise Blocked("split_inactive")
        if closed([parent.pk, *[child.pk for child in children]]):
            raise Blocked("split_closed")
        if _model("JournalShare").objects.filter(offering=parent, is_active=True).exists():
            raise Blocked("parent_has_shares")
        lessons = Lesson.objects.filter(offering=parent)
        if (
            lessons.filter(lab_group__isnull=False).exists()
            or Enrollment.objects.filter(offering=parent, lab_group__isnull=False).exists()
        ):
            raise Blocked("parent_has_lab_groups")
        mark_ids = list(LessonMark.objects.filter(lesson__offering=parent).values_list("pk", flat=True))
        if corrected_lesson_ids(list(lessons.values_list("pk", flat=True))) or corrected_mark_ids(mark_ids):
            raise Blocked("parent_corrected")
        enrollment_ids = list(Enrollment.objects.filter(offering=parent).values_list("pk", flat=True))
        if any(_model(name).objects.filter(enrollment_id__in=enrollment_ids).exists() for name in _FINAL_MODELS):
            raise Blocked("parent_has_final_results")
        if linked_elsewhere(parent):
            raise Blocked("parent_linked_elsewhere")

    def _enrollments(self, parent, children, manifest) -> dict:
        """``{ana jurnal qeydiyyatı pk → alt qrup jurnalının qeydiyyatı}`` — hər aktiv tələbə bir alt qrupa düşməlidir."""
        Enrollment, Record = _model("Enrollment"), _model("StudentAcademicRecord")
        rows = list(Enrollment.objects.select_for_update().filter(offering=parent, status="enrolled"))
        students = [row.student_id for row in rows]
        by_group = {child.group_id: child for child in children}
        existing = defaultdict(dict)
        for row in Enrollment.objects.select_for_update().filter(offering__in=children, student_id__in=students):
            existing[row.student_id][row.offering_id] = row
        groups = dict(
            Record.objects.filter(organization=self.organization, student_id__in=students, is_active=True).values_list(
                "student_id", "group_id"
            )
        )
        placed = {}
        for row in rows:
            mine = existing.get(row.student_id, {})
            active = [found for found in mine.values() if found.status == "enrolled"]
            if len(active) > 1:
                raise Blocked("parent_student_in_two_subgroups", {"blocked_enrollment": str(row.pk)[:8]})
            if active:
                placed[row.pk] = active[0]
                continue
            child = by_group.get(groups.get(row.student_id))
            if child is None:
                raise Blocked("parent_student_unplaced", {"blocked_enrollment": str(row.pk)[:8]})
            found = mine.get(child.pk)
            if found is None:
                found = Enrollment.objects.create(
                    organization=self.organization,
                    student_id=row.student_id,
                    offering=child,
                    kind=row.kind,
                    status="enrolled",
                )
                manifest["enrollments_created"].append(str(found.pk))
                self.counts["enrollments_created"] += 1
            elif found.status == "dropped":
                manifest["enrollments_reactivated"].append([str(found.pk), str(found.superseded_by_id or "")])
                Enrollment.objects.filter(pk=found.pk).update(
                    status="enrolled", superseded_by=None, updated_at=timezone.now()
                )
                found.status, found.superseded_by_id = "enrolled", None
                self.counts["enrollments_reactivated"] += 1
            else:
                raise Blocked("child_enrollment_not_active", {"blocked_enrollment": str(found.pk)[:8]})
            placed[row.pk] = found
        return placed

    def _lessons(self, parent, children, placed, manifest) -> None:
        """Ana jurnalın hər dərsi — tələbəsi olan hər alt qrup jurnalına (eyni tarix + saat + növ dərsi varsa ona)."""
        Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
        numbers = {row.number: row.unit_id for row in _model("SeminarGroup").objects.filter(offering=parent)}
        by_slot = {}
        for lesson in Lesson.objects.filter(offering__in=children, seminar_group__isnull=True, lab_group=None).order_by(
            "created_at"
        ):
            by_slot.setdefault((lesson.offering_id, lesson.date, lesson.start_time, lesson.kind), lesson)
        filled = set(LessonMark.objects.filter(lesson__offering__in=children).values_list("lesson_id", "enrollment_id"))
        audience = defaultdict(set)  # alt qrup → ana jurnaldan gələn tələbələri olan qeydiyyatlar
        for row in placed.values():
            audience[row.offering_id].add(row.pk)
        for lesson in Lesson.objects.filter(offering=parent).order_by("date", "start_time", "created_at"):
            unit = numbers.get(lesson.seminar_group) if lesson.seminar_group else None
            marks = {mark.enrollment_id: mark for mark in lesson.marks.all()}
            for child in children:
                if not audience.get(child.pk) or (unit is not None and unit != child.group_id):
                    continue
                key = (child.pk, lesson.date, lesson.start_time, lesson.kind)
                twin = by_slot.get(key)
                if twin is None:
                    twin = Lesson.objects.create(
                        organization=self.organization,
                        offering=child,
                        **{name: getattr(lesson, name) for name in _LESSON_FIELDS},
                    )
                    Lesson.objects.filter(pk=twin.pk).update(created_at=lesson.created_at)
                    by_slot[key] = twin
                    manifest["lessons_created"].append(str(twin.pk))
                    self.counts["lessons_created"] += 1
                else:
                    self.counts["lessons_matched"] += 1
                for source_pk, target in placed.items():
                    mark = marks.get(source_pk)
                    if mark is None or target.offering_id != child.pk:
                        continue
                    if (twin.pk, target.pk) in filled:
                        self.counts["marks_child_kept"] += 1
                        continue
                    created = copy_mark(mark, lesson=twin, enrollment=target)
                    filled.add((twin.pk, target.pk))
                    manifest["marks_created"].append(str(created.pk))
                    self.counts["marks_copied"] += 1

    def _component_scores(self, parent, placed, manifest) -> None:
        Component, Score = _model("AssessmentComponent"), _model("ComponentScore")
        own = {(row.offering_id, row.name): row for row in Component.objects.filter(offering__in=_offerings(placed))}
        taken = set(
            Score.objects.filter(component__offering__in=_offerings(placed)).values_list(
                "component_id", "enrollment_id"
            )
        )
        for score in Score.objects.filter(component__offering=parent).select_related("component"):
            target = placed.get(score.enrollment_id)
            if target is None:
                self.counts["scores_of_inactive_kept_in_parent"] += 1
                continue
            source = score.component
            component = own.get((target.offering_id, source.name))
            if component is None:
                component = Component.objects.create(
                    organization=self.organization,
                    offering_id=target.offering_id,
                    name=source.name,
                    kind=source.kind,
                    held_on=source.held_on,
                    max_score=source.max_score,
                    order=source.order,
                )
                own[(target.offering_id, source.name)] = component
                manifest["components_created"].append(str(component.pk))
                self.counts["components_created"] += 1
            if (component.pk, target.pk) in taken:
                self.counts["scores_child_kept"] += 1
                continue
            created = Score.objects.create(
                organization=self.organization,
                component=component,
                enrollment=target,
                score=score.score,
                entered_by_id=score.entered_by_id,
                exam_source=score.exam_source,
            )
            taken.add((component.pk, target.pk))
            manifest["scores_created"].append(str(created.pk))
            self.counts["scores_copied"] += 1

    def _syllabus(self, parent, children, manifest) -> None:
        """Alt qrup jurnalının sillabusu yoxdursa ana jurnalınkı ÖZ YERİNDƏ paylaşılır (surət yox)."""
        from apps.syllabus.public import link_legacy_share

        Syllabus, Share = _model("Syllabus", "syllabus"), _model("SyllabusShare", "syllabus")
        found = list(Syllabus.objects.filter(offering=parent)) + [
            row.syllabus for row in Share.objects.filter(offering=parent).select_related("syllabus")
        ]
        if not found:
            return
        found.sort(key=lambda row: (not row.versions.filter(status="approved").exists(), row.created_at))
        for child in children:
            if Syllabus.objects.filter(offering=child).exists() or Share.objects.filter(offering=child).exists():
                continue
            if link_legacy_share(syllabus=found[0], offering=child, user=self.actor) == "linked":
                manifest["syllabus_shares_created"].append(str(Share.objects.get(offering=child).pk))
                self.counts["syllabus_shared"] += 1

    def _retire(self, parent, manifest) -> None:
        Enrollment = _model("Enrollment")
        ids = list(Enrollment.objects.filter(offering=parent, status="enrolled").values_list("pk", flat=True))
        Enrollment.objects.filter(pk__in=ids).update(status="dropped", updated_at=timezone.now())
        manifest["parent_enrollments_dropped"].extend(str(pk) for pk in ids)
        parent.is_active = False
        parent.save(update_fields=["is_active", "updated_at"])
        manifest["parent_retired"].append(str(parent.pk))


def _offerings(placed) -> set:
    return {row.offering_id for row in placed.values()}


def undo(*, organization, actor, counts) -> None:
    """Manifestdəkini geri qaytarır; köçürmədən sonra alt qrupda yaranan dərs / dəyişən xana varsa — toxunulmur."""
    from django.db import transaction

    AuditLog = _model("AuditLog", "audit")
    Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
    Component, Score = _model("AssessmentComponent"), _model("ComponentScore")
    rows = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON)
    for row in rows.order_by("-created_at"):
        manifest = (row.changes or {}).get("manifest") or {}
        parent = _model("CourseOffering").objects.filter(pk=(row.changes or {}).get("parent")).first()
        if parent is None or parent.is_active:
            counts["undo_already"] += 1
            continue
        marks = LessonMark.objects.filter(pk__in=manifest.get("marks_created", []))
        later = LessonMark.objects.filter(lesson_id__in=manifest.get("lessons_created", [])).exclude(
            pk__in=manifest.get("marks_created", [])
        )
        if later.exists() or any((mark.updated_at - mark.created_at).total_seconds() > 5 for mark in marks):
            counts["undo_blocked_post_split_data"] += 1
            continue
        with transaction.atomic():
            Score.objects.filter(pk__in=manifest.get("scores_created", [])).delete()
            Component.objects.filter(pk__in=manifest.get("components_created", []), scores__isnull=True).delete()
            touched = list(marks.values_list("enrollment_id", flat=True))
            marks.delete()
            Lesson.objects.filter(pk__in=manifest.get("lessons_created", []), marks__isnull=True).delete()
            _model("SyllabusShare", "syllabus").objects.filter(
                pk__in=manifest.get("syllabus_shares_created", [])
            ).delete()
            Enrollment.objects.filter(
                pk__in=manifest.get("enrollments_created", []), lesson_marks__isnull=True, component_scores__isnull=True
            ).delete()
            for pk, superseded in manifest.get("enrollments_reactivated", []):
                Enrollment.objects.filter(pk=pk).update(
                    status="dropped", superseded_by_id=superseded or None, updated_at=timezone.now()
                )
            Enrollment.objects.filter(pk__in=manifest.get("parent_enrollments_dropped", [])).update(
                status="enrolled", updated_at=timezone.now()
            )
            parent.is_active = True
            parent.save(update_fields=["is_active", "updated_at"])
            recompute_absences(list(Enrollment.objects.filter(pk__in=touched)))
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                obj=parent,
                changes={"undo_of": str(row.pk)},
                reason="Sahib 2026-11-08: ana qrup jurnalının yığışdırılmasının geri qaytarılması",
                resource_type=RESOURCE,
                resource_id=str(parent.pk),
            )
        counts["parents_restored"] += 1
