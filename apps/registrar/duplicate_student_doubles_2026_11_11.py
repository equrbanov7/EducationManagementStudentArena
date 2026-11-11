"""Tələbənin EYNİ fəndən iki jurnalı — bir kart qalsın, heç bir xana itməsin (sahib 2026-11-11 səhər).

Sahib: «dublikat qalmamış olsun»; koordinator: hər tələbə üçün ÖZ qrupunun jurnalındakı qeydiyyat qalır (öz qrupu yoxdursa
— datası olan TƏK qeydiyyat), digər jurnaldakı xanalar ona köçür (eyni münaqişə qaydası), digər qeydiyyat ``dropped``
olur. Xana HEÇ VAXT silinmir. Cütlər planda açıqdır (``doubles: [{"name", "offerings": [A, B]}]``, YALNIZ id-lər).

Hər tələbə öz savepoint-ində; aşağıdakı hallarda tələbəyə TOXUNULMUR (səbəb sayılır, iki kart qalır — sahibin qərarı):

* ``double_keep_ambiguous`` — öz qrupunun jurnalı yoxdur və iki qeydiyyatın ikisində də data var;
* ``double_unmatched_marks`` — digər jurnalın xanası saxlanılan jurnalda eyni tarix + növ dərsə düşmür (köçürülsəydi
  tələbə onu görməzdi; dərs yaratmaq bütöv qrupa boş xana əlavə edərdi);
* ``double_other_has_<əlaqə>`` — digər qeydiyyatda yekun nəticə / düzəliş / təkrar imtahan … (``ENROLLMENT_POLICY`` block);
* ``double_component_missing`` / ``double_component_max_differs`` — komponent balının yeri yoxdur / tavanı fərqlidir.

Cüt səviyyəsində: jurnallar eyni dövrdə, aktiv, açıq olmalı; fənlər EYNİ və ya bir plan qrupunun kartları olmalı; qruplar
ana / alt qrup əlaqəsindədirsə cüt toxunulmur (``double_parent_subgroup`` — «ana qrup alt qrupların cəmidir» qaydası).
Digər jurnalda sonda aktiv tələbə, dərs və canlı cədvəl slotu qalmırsa o passiv olur (boş əkiz). Hər şey paket qəbzindədir
(``RESOURCE``); :func:`undo` birləşmədən sonra saxlanılan jurnalda yeni data yoxdursa hamısını qaytarır.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .duplicate_journal_merge_2026_11_11 import BLOCK, ENROLLMENT_POLICY, relations
from .duplicate_journal_scores_2026_11_11 import CONFLICT_NOTE, Blocked
from .subject_duplicates import normalized_subject_key
from .twin_inert import is_empty_twin
from .twin_relocate import closed, copy_mark, recompute_absences

RESOURCE = "registrar.duplicate_student_double"
KIND = "duplicate_student_double"
REASON = "Sahib 2026-11-11: tələbənin eyni fəndən iki jurnalı — öz qrupunun jurnalı qaldı, xanalar köçdü"


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def _slug(label: str) -> str:
    return "".join(ch if ch.isalpha() else "_" for ch in label.split(".")[1].lower())


def _ancestors(unit_id) -> set:
    OrgUnit = _model("OrgUnit", "organizations")
    seen, current = set(), unit_id
    while current and current not in seen and len(seen) < 12:
        seen.add(current)
        current = OrgUnit.objects.filter(pk=current).values_list("parent_id", flat=True).first()
    return seen


class Doubles:
    def __init__(self, *, organization, actor, counts, batch, period):
        self.organization, self.actor, self.counts = organization, actor, counts
        self.batch, self.period = batch, period

    def run(self, items, groups, lines) -> None:
        families = [{keeper.pk, *(source.pk for source in sources)} for keeper, sources, _pairs, _meta in groups]
        for item in items:
            name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(item.get("name") or "double"))
            before = dict(self.counts)
            manifest = defaultdict(list)
            try:
                with transaction.atomic():
                    self._pair(item.get("offerings") or [], families, manifest)
                    if manifest.get("dropped"):
                        self._receipt(item, manifest)
            except Blocked as exc:
                self.counts[exc.reason] += 1
            delta = {
                key: value - before.get(key, 0) for key, value in self.counts.items() if value != before.get(key, 0)
            }
            lines.append(f"double={name.lower()[:60]} " + " ".join(f"{k}={v}" for k, v in sorted(delta.items())))

    # ── cüt ───────────────────────────────────────────────────────────────
    def _load(self, ids, families):
        CourseOffering = _model("CourseOffering")
        rows = list(
            CourseOffering.objects.select_for_update(of=("self",))
            .select_related("subject")
            .filter(organization=self.organization, pk__in=list(ids))
        )
        if len(ids) != 2 or len(rows) != 2:
            raise Blocked("double_pair_missing")
        left, right = rows
        if self.period is None or {left.period_id, right.period_id} != {self.period.pk}:
            raise Blocked("double_not_current_period")
        if not (left.is_active and right.is_active) or closed([left.pk, right.pk]):
            raise Blocked("double_closed_or_inactive")
        same = left.subject_id == right.subject_id or any({left.subject_id, right.subject_id} <= f for f in families)
        if not same and normalized_subject_key(left.subject.name) != normalized_subject_key(right.subject.name):
            raise Blocked("double_subjects_differ")
        if left.group_id in _ancestors(right.group_id) or right.group_id in _ancestors(left.group_id):
            raise Blocked("double_parent_subgroup")
        return {row.pk: row for row in rows}

    def _pair(self, ids, families, manifest) -> None:
        offerings = self._load(ids, families)
        Enrollment, Record = _model("Enrollment"), _model("StudentAcademicRecord")
        rows = defaultdict(list)
        for row in (
            Enrollment.objects.select_for_update().filter(offering__in=list(offerings)).exclude(status="dropped")
        ):
            rows[row.student_id].append(row)
        groups = dict(
            Record.objects.filter(organization=self.organization, student_id__in=list(rows), is_active=True)
            .order_by("created_at")
            .values_list("student_id", "group_id")
        )
        kept = []
        for student_id, items in sorted(rows.items()):
            if len(items) != 2:
                continue
            self.counts["double_students_seen"] += 1
            try:
                with transaction.atomic():
                    keep = self._student(items, offerings, groups.get(student_id), manifest)
                    kept.append(keep)
            except Blocked as exc:
                self.counts[exc.reason] += 1
        recompute_absences(kept)
        self._retire_empty(offerings.values(), manifest)

    def _keep(self, items, offerings, group_id):
        own = [row for row in items if offerings[row.offering_id].group_id == group_id]
        if len(own) == 1:
            return own[0]
        with_data = [row for row in items if row.lesson_marks.exists() or row.component_scores.exists()]
        if len(with_data) == 1:
            return with_data[0]
        raise Blocked("double_keep_ambiguous")

    def _student(self, items, offerings, group_id, manifest):
        keep = self._keep(items, offerings, group_id)
        other = next(row for row in items if row.pk != keep.pk)
        for key, relation in relations(_model("Enrollment")).items():
            if (
                ENROLLMENT_POLICY.get(key) == BLOCK
                and relation.related_model._base_manager.filter(**{relation.field.name: other}).exists()
            ):
                raise Blocked(f"double_other_has_{_slug(key)}")
        plan = self._mark_plan(other, keep)
        conflicts = []
        for mark, lesson, current in plan:
            self._mark(mark, lesson, keep, current, manifest, conflicts)
        self._scores(other, keep, manifest, conflicts)
        self._history(offerings[keep.offering_id], keep, conflicts)
        _model("Enrollment").objects.filter(pk=other.pk).update(status="dropped", updated_at=timezone.now())
        manifest["dropped"].append([str(other.pk), other.status, str(keep.pk)])
        manifest["conflicts"].extend(conflicts)
        self.counts["double_enrollments_dropped"] += 1
        return keep

    def _mark_plan(self, other, keep) -> list:
        """``[(xana, saxlanılan dərs, saxlanılan xana | None)]`` — uyğunu olmayan xana varsa tələbə toxunulmur."""
        Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
        by_slot, by_day = {}, defaultdict(list)
        for lesson in Lesson.objects.filter(offering_id=keep.offering_id, lab_group=None).order_by("created_at"):
            if lesson.seminar_group and lesson.seminar_group != keep.seminar_group:
                continue
            by_slot.setdefault((lesson.date, lesson.start_time, lesson.kind), lesson)
            by_day[(lesson.date, lesson.kind)].append(lesson)
        current = {row.lesson_id: row for row in LessonMark.objects.filter(enrollment=keep)}
        plan, missing = [], 0
        for mark in LessonMark.objects.filter(enrollment=other).select_related("lesson").order_by("lesson__date"):
            lesson = by_slot.get((mark.lesson.date, mark.lesson.start_time, mark.lesson.kind))
            if lesson is None:
                same_day = by_day.get((mark.lesson.date, mark.lesson.kind), [])
                lesson = same_day[0] if len(same_day) == 1 else None
            if lesson is None:
                missing += 1
                continue
            plan.append((mark, lesson, current.get(lesson.pk)))
        if missing:
            raise Blocked("double_unmatched_marks")
        return plan

    def _mark(self, mark, lesson, keep, current, manifest, conflicts) -> None:
        from core.rls import journal_unlock

        if current is None:
            created = copy_mark(mark, lesson=lesson, enrollment=keep)
            manifest["marks_created"].append(str(created.pk))
            self.counts["double_marks_copied"] += 1
        elif (current.status, current.score) == (mark.status, mark.score):
            self.counts["double_marks_identical"] += 1
        elif current.status == mark.status and current.score is None and mark.score is not None:
            with journal_unlock():
                _model("LessonMark").objects.filter(pk=current.pk, score__isnull=True).update(
                    score=mark.score, updated_at=timezone.now()
                )
            manifest["marks_score_filled"].append([str(current.pk), str(mark.score)])
            self.counts["double_marks_score_filled"] += 1
        elif current.status == mark.status and mark.score is None:
            self.counts["double_marks_target_has_score"] += 1
        else:
            conflicts.append(
                {
                    "type": "mark",
                    "student": keep.student_id,
                    "date": lesson.date.isoformat(),
                    "lesson_kind": lesson.kind,
                    "source_mark": str(mark.pk),
                    "target_mark": str(current.pk),
                    "source_value": [mark.status, None if mark.score is None else str(mark.score)],
                    "target_value": [current.status, None if current.score is None else str(current.score)],
                    "kept": "target",
                    "target_enrollment": str(keep.pk),
                }
            )
            self.counts["double_marks_conflict_target_kept"] += 1

    def _scores(self, other, keep, manifest, conflicts) -> None:
        from core.rls import journal_unlock

        from .interim_components import ensure_kollokviums

        Score, Component = _model("ComponentScore"), _model("AssessmentComponent")
        rows = list(Score.objects.filter(enrollment=other).select_related("component"))
        if not rows:
            return
        with journal_unlock():
            for row in rows:
                lookup = Component.objects.filter(offering_id=keep.offering_id, kind=row.component.kind)
                component = lookup.filter(name__iexact=row.component.name.strip()).first()
                if component is None and row.component.kind == "kollokvium":
                    ensure_kollokviums(_model("CourseOffering").objects.get(pk=keep.offering_id))
                    component = lookup.filter(name__iexact=row.component.name.strip()).first()
                if component is None:
                    raise Blocked("double_component_missing")
                if component.max_score != row.component.max_score:
                    raise Blocked("double_component_max_differs")
                existing = Score.objects.filter(component=component, enrollment=keep).first()
                if existing is None:
                    created = Score.objects.create(
                        organization=self.organization,
                        component=component,
                        enrollment=keep,
                        score=row.score,
                        entered_by_id=row.entered_by_id,
                        exam_source=row.exam_source,
                    )
                    manifest["scores_created"].append(str(created.pk))
                    self.counts["double_scores_copied"] += 1
                elif existing.score != row.score:
                    conflicts.append(
                        {
                            "type": "score",
                            "student": keep.student_id,
                            "component": component.name,
                            "source_score": str(row.pk),
                            "target_score": str(existing.pk),
                            "source_value": str(row.score),
                            "target_value": str(existing.score),
                            "kept": "target",
                        }
                    )
                    self.counts["double_scores_conflict_target_kept"] += 1

    def _history(self, offering, keep, conflicts) -> None:
        from . import grade_audit

        changes = [
            {
                "student": grade_audit.student_label(keep),
                "item": f"{item['date']} · {item['lesson_kind']}" if item["type"] == "mark" else item["component"],
                "old": (
                    grade_audit.mark_repr(*item["source_value"])
                    if item["type"] == "mark"
                    else grade_audit.score_repr(Decimal(item["source_value"]))
                ),
                "new": (
                    grade_audit.mark_repr(*item["target_value"])
                    if item["type"] == "mark"
                    else grade_audit.score_repr(Decimal(item["target_value"]))
                ),
                "source": f"duplicate_double:{item['source_mark'] if item['type'] == 'mark' else item['source_score']}",
                "note": CONFLICT_NOTE,
            }
            for item in conflicts
        ]
        grade_audit.log_grade_changes(
            offering=offering, by_user=self.actor, kind="mark", changes=changes, fail_closed=True, reason=REASON
        )

    def _retire_empty(self, offerings, manifest) -> None:
        Enrollment, Slot = _model("Enrollment"), _model("ScheduleSlot")
        for offering in offerings:
            if Enrollment.objects.filter(offering=offering).exclude(status="dropped").exists():
                continue
            if _model("Lesson").objects.filter(offering=offering).exists() or not is_empty_twin(offering):
                continue
            if Slot.objects.filter(offering=offering).exists():
                self.counts["double_empty_journal_kept_has_slots"] += 1
                continue
            offering.is_active = False
            offering.save(update_fields=["is_active", "updated_at"])
            manifest["offerings_retired"].append(str(offering.pk))
            self.counts["double_empty_journals_retired"] += 1

    def _receipt(self, item, manifest) -> None:
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            new_values={"offerings": list(item.get("offerings") or []), "dropped": len(manifest["dropped"])},
            changes={"kind": KIND, "batch": self.batch, "manifest": dict(manifest)},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=self.batch,
        )


def undo(*, organization, actor, counts, batch) -> None:
    """Paketin bütün «iki jurnal» düzəlişlərini qaytarır; sonradan yeni data varsa sayğac (çağıran rollback edir)."""
    from core.rls import journal_unlock

    AuditLog = _model("AuditLog", "audit")
    entries = AuditLog.objects.filter(
        organization=organization, resource_type=RESOURCE, resource_id=batch, changes__kind=KIND
    ).order_by("-created_at", "-pk")
    Enrollment, LessonMark, Score = _model("Enrollment"), _model("LessonMark"), _model("ComponentScore")
    for entry in entries:
        manifest = (entry.changes or {}).get("manifest") or {}
        kept = [item[2] for item in manifest.get("dropped") or []]
        created = set(manifest.get("marks_created") or [])
        later = LessonMark.objects.filter(enrollment_id__in=kept, updated_at__gt=entry.created_at)
        scores = Score.objects.filter(enrollment_id__in=kept, updated_at__gt=entry.created_at)
        if (
            any(str(pk) not in created for pk in later.values_list("pk", flat=True))
            or scores.exclude(pk__in=manifest.get("scores_created") or []).exists()
        ):
            counts["undo_doubles_blocked_post_merge_data"] += 1
            continue
        with journal_unlock():
            counts["undo_double_scores_deleted"] += Score.objects.filter(
                pk__in=manifest.get("scores_created") or []
            ).delete()[0]
            for mark_id, score in manifest.get("marks_score_filled") or []:
                LessonMark.objects.filter(pk=mark_id, score=Decimal(score)).update(
                    score=None, updated_at=timezone.now()
                )
        counts["undo_double_marks_deleted"] += LessonMark.objects.filter(pk__in=created).delete()[0]
        for enrollment_id, status, _keep in manifest.get("dropped") or []:
            try:
                with transaction.atomic():
                    Enrollment.objects.filter(pk=enrollment_id, status="dropped").update(
                        status=status, updated_at=timezone.now()
                    )
            except IntegrityError:
                counts["undo_doubles_blocked_post_merge_data"] += 1
        _model("CourseOffering").objects.filter(pk__in=manifest.get("offerings_retired") or []).update(
            is_active=True, updated_at=timezone.now()
        )
        recompute_absences(list(Enrollment.objects.filter(pk__in=kept)))
        counts["undo_double_pairs"] += 1


__all__ = ["KIND", "REASON", "RESOURCE", "Doubles", "undo"]
