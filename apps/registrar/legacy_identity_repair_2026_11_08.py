"""Başqasının FİN-i ilə köçmüş xana və qeydiyyatların düzəlişi (sahib 2026-11-08) — ``repair_legacy_identity_20261108``.

Köhnə sistemdə bəzi tələbə sətirlərinə BAŞQA tələbənin FİN-i yazılıb; delta köçürməsi FİN ilə tutduğu üçün bir adamın
xanaları və alt qrup qeydiyyatları FİN sahibinin hesabına düşüb (qarşısı: :func:`apps.legacy_import.services.delta.
resolve.fin_owner`). Plan lokal qurulur (2026-11-02 prod nüsxəsi + köhnə sistem) və YALNIZ id-lərdir::

    {"format": "legacy-identity/1",
     "cases": [{"key": "a", "legacy_wrong": <köhnə sətir id>, "holder": <FİN sahibinin hesabı>,
                "person": <adamın öz hesabı | null>,
                "items": [{"offering": uuid, "date": "2026-09-22", "start_time": "13:35",
                           "holder_enrollment": uuid, "value": {"status", "score"},
                           "holder_value": {"status", "score"} | null, "holder_fix": bool,
                           "holder_own": {"status", "score"} | null}],
                "releases": [{"enrollment": uuid, "offering": uuid}]}]}

Prod-da hər şey sabit açarla yenidən tapılır (açılış + dərs tarixi + başlama saatı, qeydiyyat uuid-i / açılış +
hesab); tapılmayan sayılır (``…_missing``), təxmin edilmir. Hər hal üçün:

* **qeydiyyatın azad edilməsi** (``releases``) — FİN sahibinin səhv alt qrup qeydiyyatı «Alt qrupdan əlavə»nin öz
  geri götürmə yolu ilə (:func:`guest_roster.remove_guest_student`: ``dropped``, öz qrup qeydiyyatı bərpa olunur,
  xanalar silinmir). Müəllimin yazdığı xana / komponent balı varsa toxunulmur (``release_teacher_work_kept``);
* **adamın xanası** — dərsin adamın öz qeydiyyatındakı BOŞ xanasına eyni dəyər (fill-only; dolu xana dəyişmir:
  eyni dəyər ``person_cell_same``, başqa dəyər ``person_cell_conflict``);
* **FİN sahibinin xanası** (``holder_fix``) — yalnız köçürmənin yazdığı və heç vaxt dəyişməmiş xana (``entered_by``
  boş, ``updated_at`` ≈ ``created_at``, audit izi yoxdur): köhnə sistemdə sahibin öz dəyəri varsa o yazılır, yoxdursa
  xana silinir. Müəllimin yazdığı / düzəldilmiş xana yalnız sayılır;
* adamın hesabı yoxdursa (``person: null``) xanalar YALNIZ sayılır — hesab yaradılmır.

``--undo`` audit sətrindən geri qaytarır (dəyişməmiş olanları). Qayıb saatı yenidən hesablanır.
"""

from __future__ import annotations

import datetime
import json
from collections import Counter
from decimal import Decimal

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.rls import journal_unlock

from . import lab_groups
from .gradebook import lesson_allows_score
from .twin_relocate import closed, recompute_absences

FORMAT = "legacy-identity/1"
REASON = "Sahib 2026-11-08: köhnə sistemdə başqasının FİN-i — xana və qeydiyyatlar düzgün adama"
UNDO_REASON = "Sahib 2026-11-08: FİN qarışığı düzəlişinin geri qaytarılması"
RESOURCE = "registrar.legacy_identity_repair"
#: Köçürmənin yazdığı xana: yaradılandan sonra bu qədər saniyədən gec dəyişməyib.
UNEDITED_SECONDS = 5


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def load_plan(path) -> list:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise CommandError("legacy_identity_file_unreadable") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise CommandError("legacy_identity_format_unknown")
    cases = [case for case in data.get("cases") or [] if isinstance(case, dict)]
    if any(not str(case.get("key") or "").isalpha() for case in cases):
        raise CommandError("legacy_identity_case_key_invalid")
    return cases


def _value(spec):
    """Plan dəyəri → ``(status, Decimal | None)``; yoxdursa ``None``."""
    if not isinstance(spec, dict) or not spec.get("status"):
        return None
    score = spec.get("score")
    return str(spec["status"]), (None if score is None else Decimal(str(score)))


def _same(mark, value) -> bool:
    if mark is None or value is None:
        return False
    stored = None if mark.score is None else Decimal(mark.score)
    return mark.status == value[0] and stored == value[1]


def _dump(mark) -> dict:
    return {"status": mark.status, "score": None if mark.score is None else str(mark.score)}


def imported_unedited(mark) -> bool:
    """Xananı köçürmə yazıb və ondan sonra heç kim dəyişməyib."""
    if mark.entered_by_id is not None:
        return False
    if (mark.updated_at - mark.created_at).total_seconds() >= UNEDITED_SECONDS:
        return False
    return not _model("AuditLog", "audit").objects.filter(resource_id=str(mark.pk)).exists()


class Repair:
    def __init__(self, *, organization, actor, counts: Counter):
        self.organization = organization
        self.actor = actor
        self.counts = counts
        self.touched: dict = {}
        self.manifest = {"person_created": [], "holder_restored": [], "holder_deleted": [], "released": []}
        self._shut: dict = {}

    def count(self, case, name, amount=1) -> None:
        self.counts[f"{case}_{name}"] += amount

    def _closed(self, offering) -> bool:
        if offering.pk not in self._shut:
            self._shut[offering.pk] = not offering.is_active or str(offering.pk) in closed([offering.pk])
        return self._shut[offering.pk]

    # ── icra ──────────────────────────────────────────────────────────────
    def run(self, cases) -> None:
        for case in cases:
            key = case["key"]
            self.counts["cases"] += 1
            if case.get("person") is None:
                self.count(key, "no_person_account")
            for spec in case.get("releases") or []:
                self._release(key, case, spec)
            for item in case.get("items") or []:
                self._item(key, case, item if isinstance(item, dict) else {})
        recompute_absences(list(self.touched.values()))
        if any(self.manifest.values()):
            log_action(
                AuditAction.UPDATE,
                user=self.actor,
                organization=self.organization,
                new_values={name: len(rows) for name, rows in self.manifest.items()},
                changes=self.manifest,
                reason=REASON,
                resource_type=RESOURCE,
                resource_id=timezone.now().strftime("%Y%m%d%H%M%S"),
            )

    def _release(self, key, case, spec) -> None:
        from . import guest_roster

        Enrollment, LessonMark = _model("Enrollment"), _model("LessonMark")
        enrollment = (
            Enrollment.objects.select_for_update(of=("self",))
            .select_related("offering")
            .filter(organization=self.organization, pk=spec.get("enrollment"))
            .first()
        )
        if (
            enrollment is None
            or enrollment.student_id != case.get("holder")
            or str(enrollment.offering_id) != str(spec.get("offering"))
        ):
            self.count(key, "release_missing")
        elif enrollment.status != Enrollment.Status.ENROLLED:
            self.count(key, "release_already_dropped")
        elif enrollment.source_group_id is None:
            self.count(key, "release_not_guest_kept")
        elif (
            LessonMark.objects.filter(enrollment=enrollment, entered_by__isnull=False).exists()
            or _model("ComponentScore").objects.filter(enrollment=enrollment, entered_by__isnull=False).exists()
        ):
            self.count(key, "release_teacher_work_kept")
        else:
            restored = [
                str(pk)
                for pk in Enrollment.objects.filter(
                    superseded_by=enrollment, status=Enrollment.Status.DROPPED
                ).values_list("pk", flat=True)
            ]
            try:
                with transaction.atomic():
                    guest_roster.remove_guest_student(
                        offering=enrollment.offering, enrollment=enrollment, by_user=self.actor, reason=REASON
                    )
            except ValidationError:
                self.count(key, "release_blocked")
                return
            self.manifest["released"].append({"enrollment": str(enrollment.pk), "restored": restored})
            for row in Enrollment.objects.filter(pk__in=restored):
                self.touched[row.pk] = row
            self.count(key, "released")
            self.count(key, "release_restored_own", len(restored))

    def _lesson(self, key, item):
        try:
            day = datetime.date.fromisoformat(str(item.get("date")))
            start = datetime.time.fromisoformat(str(item.get("start_time")))
        except ValueError:
            self.count(key, "item_invalid")
            return None
        lessons = list(
            _model("Lesson")
            .objects.select_related("offering")
            .filter(organization=self.organization, offering_id=item.get("offering"), date=day, start_time=start)[:2]
        )
        if len(lessons) != 1:
            self.count(key, "lesson_missing" if not lessons else "lesson_ambiguous")
            return None
        return lessons[0]

    def _item(self, key, case, item) -> None:
        self.count(key, "items")
        value = _value(item.get("value"))
        lesson = self._lesson(key, item) if value is not None else None
        if lesson is None:
            if value is None:
                self.count(key, "item_invalid")
            return
        if case.get("person") is None:
            # Adamın hesabı yoxdur — xana yalnız hesabatdadır (hesab yaradılmır).
            self.count(key, "no_account_cells")
            return
        self._person(key, case, lesson, value)
        if item.get("holder_fix"):
            self._holder(key, case, lesson, item)
        else:
            self.count(key, "holder_untouched")

    def _person(self, key, case, lesson, value) -> None:
        Enrollment, LessonMark = _model("Enrollment"), _model("LessonMark")
        enrollment = (
            Enrollment.objects.select_for_update(of=("self",))
            .filter(
                organization=self.organization,
                offering_id=lesson.offering_id,
                student_id=case["person"],
                status=Enrollment.Status.ENROLLED,
            )
            .first()
        )
        existing = LessonMark.objects.filter(lesson=lesson, enrollment=enrollment).first() if enrollment else None
        if enrollment is None:
            self.count(key, "person_not_in_offering")
        elif existing is not None:
            self.count(key, "person_cell_same" if _same(existing, value) else "person_cell_conflict")
        elif self._closed(lesson.offering):
            self.count(key, "person_journal_closed")
        elif not lab_groups.applies(lesson, enrollment):
            self.count(key, "person_other_subgroup")
        elif value[1] is not None and not lesson_allows_score(lesson):
            self.count(key, "person_score_not_allowed")
        else:
            mark = LessonMark.objects.create(
                organization=self.organization, lesson=lesson, enrollment=enrollment, status=value[0], score=value[1]
            )
            self.manifest["person_created"].append(str(mark.pk))
            self.touched[enrollment.pk] = enrollment
            self.count(key, "person_filled")

    def _holder(self, key, case, lesson, item) -> None:
        Enrollment, LessonMark = _model("Enrollment"), _model("LessonMark")
        enrollment = Enrollment.objects.filter(organization=self.organization, pk=item.get("holder_enrollment")).first()
        if (
            enrollment is None
            or enrollment.student_id != case.get("holder")
            or enrollment.offering_id != lesson.offering_id
        ):
            self.count(key, "holder_enrollment_missing")
            return
        if enrollment.status != Enrollment.Status.ENROLLED:
            self.count(key, "holder_enrollment_released")  # qeydiyyat azad edilib — xanası tarixçədə qalır
            return
        mark = LessonMark.objects.select_for_update().filter(lesson=lesson, enrollment=enrollment).first()
        own = _value(item.get("holder_own"))
        if mark is None:
            self.count(key, "holder_cell_empty")
        elif own is not None and _same(mark, own):
            self.count(key, "holder_already_own")
        elif not _same(mark, _value(item.get("holder_value"))):
            self.count(key, "holder_changed_kept")
        elif not imported_unedited(mark):
            self.count(key, "holder_teacher_or_edited_kept")
        elif self._closed(lesson.offering):
            self.count(key, "holder_journal_closed")
        elif own is not None:
            before = {**_dump(mark), "updated_at": mark.updated_at.isoformat()}
            mark.status, mark.score = own
            with journal_unlock():  # köçmüş xananın düzəlişi (``trg_journal_mark_guard`` pəncərəsi)
                mark.save(update_fields=["status", "score", "updated_at"])
            self.manifest["holder_restored"].append({"mark": str(mark.pk), "from": before, "to": _dump(mark)})
            self.touched[enrollment.pk] = enrollment
            self.count(key, "holder_restored_own")
        else:
            self.manifest["holder_deleted"].append(
                {"lesson": str(lesson.pk), "enrollment": str(enrollment.pk), **_dump(mark)}
            )
            with journal_unlock():
                mark.delete()
            self.touched[enrollment.pk] = enrollment
            self.count(key, "holder_deleted")


def run(*, organization, actor, counts, cases) -> None:
    Repair(organization=organization, actor=actor, counts=counts).run(cases)


def undo(*, organization, actor, counts) -> None:
    from . import guest_merge

    AuditLog = _model("AuditLog", "audit")
    Enrollment, LessonMark = _model("Enrollment"), _model("LessonMark")
    done = set(
        AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=UNDO_REASON).values_list(
            "resource_id", flat=True
        )
    )
    touched: dict = {}
    for row in AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON):
        if row.resource_id in done:
            counts["undo_already_done"] += 1
            continue
        changes = row.changes or {}
        created = list(
            LessonMark.objects.select_related("enrollment").filter(pk__in=changes.get("person_created") or [])
        )
        fresh = [mark for mark in created if imported_unedited(mark)]
        counts["undo_person_changed_kept"] += len(created) - len(fresh)
        touched.update({mark.enrollment_id: mark.enrollment for mark in fresh})
        counts["undo_person_deleted"] += LessonMark.objects.filter(pk__in=[mark.pk for mark in fresh]).delete()[0]
        for entry in changes.get("holder_restored") or []:
            mark = LessonMark.objects.select_related("enrollment").filter(pk=entry.get("mark")).first()
            if mark is None or not _same(mark, _value(entry.get("to"))):
                counts["undo_holder_changed_kept"] += 1
                continue
            status, score = _value(entry.get("from"))
            # Xana əvvəlki halına qayıdır — ``updated_at`` da (yenidən tətbiqdə «köçmüş, dəyişməmiş» sayılsın).
            stamp = datetime.datetime.fromisoformat(entry["from"].get("updated_at") or mark.updated_at.isoformat())
            with journal_unlock():
                LessonMark.objects.filter(pk=mark.pk).update(status=status, score=score, updated_at=stamp)
            touched[mark.enrollment_id] = mark.enrollment
            counts["undo_holder_reverted"] += 1
        for entry in changes.get("holder_deleted") or []:
            enrollment = Enrollment.objects.filter(pk=entry.get("enrollment")).first()
            if (
                enrollment is None
                or LessonMark.objects.filter(lesson_id=entry.get("lesson"), enrollment=enrollment).exists()
            ):
                counts["undo_holder_cell_filled_kept"] += 1
                continue
            status, score = _value(entry)
            LessonMark.objects.create(
                organization=organization, lesson_id=entry["lesson"], enrollment=enrollment, status=status, score=score
            )
            touched[enrollment.pk] = enrollment
            counts["undo_holder_recreated"] += 1
        for entry in changes.get("released") or []:
            _undo_release(entry, actor=actor, counts=counts, touched=touched, guest_merge=guest_merge)
        recompute_absences(list(touched.values()))
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"undone": row.resource_id},
            reason=UNDO_REASON,
            resource_type=RESOURCE,
            resource_id=row.resource_id,
        )


def _undo_release(entry, *, actor, counts, touched, guest_merge) -> None:
    Enrollment = _model("Enrollment")
    enrollment = Enrollment.objects.select_for_update(of=("self",)).filter(pk=entry.get("enrollment")).first()
    if enrollment is None or enrollment.status != Enrollment.Status.DROPPED:
        counts["undo_release_changed_kept"] += 1
        return
    enrollment.status = Enrollment.Status.ENROLLED
    enrollment.save(update_fields=["status", "updated_at"])
    touched[enrollment.pk] = enrollment
    counts["undo_reenrolled"] += 1
    for source in Enrollment.objects.select_related("offering").filter(
        pk__in=entry.get("restored") or [], status=Enrollment.Status.ENROLLED, superseded_by__isnull=True
    ):
        try:
            with transaction.atomic():
                guest_merge.release_source(source=source, target=enrollment, by_user=actor, reason=UNDO_REASON)
        except ValidationError:
            counts["undo_source_release_blocked"] += 1
            continue
        touched[source.pk] = source
        counts["undo_source_released"] += 1


__all__ = ["FORMAT", "imported_unedited", "load_plan", "run", "undo"]
