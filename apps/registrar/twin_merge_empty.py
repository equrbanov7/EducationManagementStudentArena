"""BOŞ əkiz açılışın DATALI saxlanılan açılışa birləşdirilməsi — ``merge_twin_offerings`` K1 (sahib 2026-11-04).

Dublikat fənn kartları (QKU-2577 / QKU-2693 «VoİP …», QKU-452 / QKU-2436 «coğrafi xəritələr» …) eyni qrup + dövr
üçün İKİ cari jurnal yaradıb: saxlanılan (T) — dərs, xana, sillabus, dərs yükü; əkiz (W) — yalnız eyni tələbələrin
siyahısı + cədvəl slotları. Köhnə qayda (:mod:`.twin_merge`) datanı YALNIZ W→T aparır və T-də xana varsa dayanır
(``both_have_marks``). Bu modul tərs halı həll edir: W BOŞDUR (:func:`.twin_inert.offering_blockers` — 0 dərs,
datasız qeydiyyatlar, sillabus/imtahan vərəqi/qovluq … yoxdur), ona görə T-yə heç bir QİYMƏT köçmür.

Qaydalar (cüt öz savepoint-ində, hər şey kilid altında):

* **qeydiyyat** — W-nin ``enrolled`` tələbəsi T-də varsa heç nə; yoxdursa T-də yaradılır (W sətrinin növü, alt qrup
  provenansı ilə). T-dəki sətri ``dropped``/``suspended`` olan tələbə → cüt DAYANIR (``target_enrollment_inactive``,
  siyahı qərarıdır). W sətirləri ``dropped`` olur (fənn fərqlidir — ``superseded_by`` mümkün deyil);
* **cədvəl** — slotlar SƏSSİZ itmir: W-nin canlı slotu T-də EKVİVALENTİ (eyni gün, kəsişən saat, kəsişən həftə;
  parklanmış T slotu canlı W slotunu udmur) varsa yumşaq silinir (``slots_dropped_equivalent``), yoxdursa T-yə
  köçürülür (yeni sətir, eyni sahələr + park vəziyyəti; ``slots_moved``). Hər biri manifestdə;
* **jurnal payı** — defolt W-də QALIR (``shares_left_on_source``; ləğv olunmuş jurnalda görünmür). Plan cütündə
  ``"move_shares": true`` → T-yə köçür, tələbə siyahısı T qeydiyyatlarına çevrilir; müəllim T-nin sahibidirsə və
  ya T-də artıq aktiv payı varsa köçmür (``shares_teacher_on_target``);
* **imtahan** — ``Exam.journal_offerings``-də W → T (T artıq bağlıdırsa yalnız W bağı çıxır). Ləğv olunmuş jurnala
  bağlı imtahan QALMIR;
* W ``is_active=False``; W və T üçün audit — ``changes.manifest`` geri qaytarma üçün kifayət edən tam izdir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

KIND = "twin_merge_empty"
REASON = (
    "Boş əkiz jurnalın datalı jurnala birləşdirilməsi: dublikat fənn kartı ikinci jurnal açıb — sahib 2026-11-04 (K1)"
)
_SLOT_FIELDS = (
    "weekday",
    "start_time",
    "end_time",
    "room",
    "week_type",
    "kind",
    "created_by_id",
    "instructor_id",
    "is_parked",
    "parked_at",
    "parked_by_id",
    "park_reason",
)
_INACTIVE = ("dropped", "suspended")


def _model(name: str):
    return django_apps.get_model("registrar", name)


def exam_through():
    return _model("CourseOffering")._meta.get_field("linked_exams").through


def repoint_exam_links(source_id, target_id) -> list:
    """``Exam.journal_offerings``: ``source`` → ``target``. Qaytarır: ``[{"exam", "target_added"}]``."""

    through = exam_through()
    rows = list(through.objects.filter(courseoffering_id=source_id).values_list("exam_id", flat=True))
    out = []
    for exam_id in rows:
        added = False
        if target_id is not None and not through.objects.filter(exam_id=exam_id, courseoffering_id=target_id).exists():
            through.objects.create(exam_id=exam_id, courseoffering_id=target_id)
            added = True
        out.append({"exam": str(exam_id), "target_added": added})
    through.objects.filter(courseoffering_id=source_id).delete()
    return out


def _weeks_overlap(left: str, right: str) -> bool:
    return left == "all" or right == "all" or left == right


def equivalent_slot(slot, candidates):
    """T-də ``slot``-u əvəz edən canlı slot (eyni gün, kəsişən saat və həftə) və ya ``None``."""

    for other in candidates:
        if other.is_parked and not slot.is_parked:
            continue  # parklanmış (cədvəldə görünməyən) slot canlı yerləşdirməni udmur
        if (
            other.weekday == slot.weekday
            and other.start_time < slot.end_time
            and slot.start_time < other.end_time
            and _weeks_overlap(other.week_type, slot.week_type)
        ):
            return other
    return None


class EmptyTwinMerge:
    def __init__(self, *, organization, actor, counts):
        self.organization = organization
        self.actor = actor
        self.counts = counts

    def merge(self, source, target, pair) -> None:
        manifest = {"source": str(source.pk), "target": str(target.pk)}
        enrollments = self._enrollments(source, target, manifest)
        if enrollments is None:
            transaction.set_rollback(True)
            return
        manifest["slots"] = self._slots(source, target)
        manifest["shares"] = self._shares(source, target, enrollments, bool(pair.get("move_shares")))
        manifest["exam_links"] = repoint_exam_links(source.pk, target.pk)
        self.counts["exam_links_repointed"] += len(manifest["exam_links"])
        source.is_active = False
        source.save(update_fields=["is_active", "updated_at"])
        self.counts["offerings_cancelled"] += 1
        self.counts["pairs_merged"] += 1
        self.counts["pairs_merged_empty_source"] += 1
        self._audit(source, target, manifest)

    # ── qeydiyyat ─────────────────────────────────────────────────────────
    def _enrollments(self, source, target, manifest):
        """``{tələbə id → T qeydiyyatı}`` (W-nin aktiv tələbələri üçün); dayanma halında ``None``."""

        Enrollment = _model("Enrollment")
        existing = {row.student_id: row for row in Enrollment.objects.select_for_update().filter(offering=target)}
        rows = list(Enrollment.objects.select_for_update().filter(offering=source).order_by("created_at", "pk"))
        mapping, created, dropped = {}, [], []
        for row in rows:
            if row.status != "enrolled":
                continue
            found = existing.get(row.student_id)
            if found is not None and found.status in _INACTIVE:
                self.counts["target_enrollment_inactive"] += 1
                return None
            if found is None:
                guest = row.source_group_id is not None and row.source_group_id != target.group_id
                try:
                    with transaction.atomic():
                        found = Enrollment.objects.create(
                            organization=self.organization,
                            student_id=row.student_id,
                            offering=target,
                            kind=row.kind,
                            status="enrolled",
                            source_group_id=row.source_group_id if guest else None,
                            added_by=self.actor if guest else None,
                            added_at=timezone.now() if guest else None,
                        )
                except IntegrityError:
                    self.counts["target_enrollment_blocked"] += 1
                    return None
                existing[row.student_id] = found
                created.append(str(found.pk))
            else:
                self.counts["enrollments_already_in_target"] += 1
            mapping[row.student_id] = found
            dropped.append(str(row.pk))
        Enrollment.objects.filter(pk__in=dropped).update(status="dropped", updated_at=timezone.now())
        self.counts["enrollments_created"] += len(created)
        self.counts["source_enrollments_dropped"] += len(dropped)
        manifest["enrollments_created"] = created
        manifest["source_enrollments_dropped"] = dropped
        return mapping

    # ── cədvəl ────────────────────────────────────────────────────────────
    def _slots(self, source, target) -> list:
        from .schedule_lock import lock_schedule

        ScheduleSlot = _model("ScheduleSlot")
        own = list(ScheduleSlot.objects.select_for_update().filter(offering=source).order_by("weekday", "start_time"))
        if not own:
            return []
        lock_schedule(self.organization.pk, source.period_id)
        keep = list(ScheduleSlot.objects.select_for_update().filter(offering=target))
        now = timezone.now()
        out = []
        for slot in own:
            twin = equivalent_slot(slot, keep)
            entry = {"slot": str(slot.pk)}
            if twin is not None:
                entry.update(action="dropped_equivalent", equivalent=str(twin.pk))
                self.counts["slots_dropped_equivalent"] += 1
            else:
                moved = ScheduleSlot.objects.create(
                    organization=self.organization,
                    offering=target,
                    **{name: getattr(slot, name) for name in _SLOT_FIELDS},
                )
                keep.append(moved)
                entry.update(action="moved", new_slot=str(moved.pk))
                self.counts["slots_moved"] += 1
                if slot.instructor_id is None and source.instructor_id != target.instructor_id:
                    self.counts["slots_moved_owner_differs"] += 1
            ScheduleSlot.all_objects.filter(pk=slot.pk).update(is_deleted=True, deleted_at=now, updated_at=now)
            out.append(entry)
        return out

    # ── jurnal payı ───────────────────────────────────────────────────────
    def _shares(self, source, target, enrollments, move: bool) -> list:
        JournalShare = _model("JournalShare")
        rows = list(JournalShare.objects.select_for_update().filter(offering=source, is_active=True).order_by("pk"))
        if not rows:
            return []
        if not move:
            self.counts["shares_left_on_source"] += len(rows)
            return [{"share": str(row.pk), "action": "left_on_source"} for row in rows]
        taken = set(
            JournalShare.objects.filter(offering=target, is_active=True).values_list("teacher_id", flat=True)
        ) | {target.instructor_id}
        out = []
        for row in rows:
            if row.teacher_id in taken:
                self.counts["shares_teacher_on_target"] += 1
                out.append({"share": str(row.pk), "action": "teacher_on_target"})
                continue
            old = [str(pk) for pk in row.enrollments.values_list("pk", flat=True)]
            students = row.enrollments.values_list("student_id", flat=True)
            new = [enrollments[student].pk for student in students if student in enrollments]
            if old and not new:  # boş siyahı = «bütün tələbələr» — pay genişlənməsin
                self.counts["shares_unmappable_kept"] += 1
                out.append({"share": str(row.pk), "action": "unmappable_kept"})
                continue
            JournalShare.objects.filter(pk=row.pk).update(offering=target, updated_at=timezone.now())
            row.enrollments.set(new)
            taken.add(row.teacher_id)
            self.counts["shares_moved"] += 1
            out.append({"share": str(row.pk), "action": "moved", "old_enrollments": old})
        return out

    def _audit(self, source, target, manifest) -> None:
        summary = {
            "mode": "empty_source",
            "source_subject": str(source.subject_id),
            "target_subject": str(target.subject_id),
            "enrollments_created": len(manifest["enrollments_created"]),
            "source_enrollments_dropped": len(manifest["source_enrollments_dropped"]),
            "slots": len(manifest["slots"]),
            "exam_links": len(manifest["exam_links"]),
        }
        for obj, old in ((source, {"is_active": True}), (target, {})):
            log_action(
                action=AuditAction.UPDATE,
                user=self.actor,
                organization=self.organization,
                obj=obj,
                reason=f"registrar: twin offering merge — {REASON}",
                old_values=old,
                new_values=summary,
                changes={"kind": KIND, "manifest": manifest},
            )


__all__ = ["KIND", "EmptyTwinMerge", "equivalent_slot", "exam_through", "repoint_exam_links"]
