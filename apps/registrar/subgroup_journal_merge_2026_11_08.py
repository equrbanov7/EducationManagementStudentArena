"""Alt qrup jurnallarını ana qrupun jurnalına birləşdirmək (sahib 2026-11-08) — ``merge_subgroup_journals_20261108``.

Sahib: «ana qrup hamısı olanda elə görünsün, mühazirə olanda da; seminar seçiləndə bölünən, lab seçəndə bölünənlər …
köhnə DB-dən dataları çəkib gətir, jurnal yazılmış olsun, içi boş olmasın». Köhnə sistem bir fənni alt qrup adlı
jurnallara bölmüşdü (536 MU1 / 536 MU2 …) — EMS-də bir fənn üçün 2–3 jurnal görünürdü. Bu modul hər ailədə alt qrup
jurnallarının tələbələrini və xanalarını ANA qrupun jurnalına KOPYALAYIR; alt qrup bu jurnalda seminar alt qrupu olur
(:mod:`apps.registrar.seminar_groups`).

Ailələr :data:`PLAN`-dadır (sabit id-lər; Mülki müdafiə kimi alt qrupları ayrı saatda dərs keçən ailələr qəsdən YOXDUR).
Hər ailə öz savepoint-ində, hər şey kilid altında yenidən yoxlanılır:

* qoruyucular — açılışlar aktiv, eyni fənn + dövr, bağlı deyil; alt qrup jurnalında rəsmi düzəlişli xana / dərs,
  yekun qiymət və ya komponent balı, ya da başqa moduldan istinad varsa ailəyə TOXUNULMUR (sayılır);
* ana jurnal yoxdursa (``target`` boş) eyni fənn + dövr + ana qrup üçün yaradılır (müəllim — alt qrupun müəllimi);
* seminar alt qrupu — hər alt qrup jurnalının qrupu üçün bir ``SeminarGroup`` (ad = qrupun adı, ad sırası ilə nömrə);
* tələbə — ana jurnalda sətri varsa o, yoxdursa yaradılır («alt qrupdan əlavə» forması); reyestr qrupu ailənin alt
  qrupudursa ``seminar_group`` YALNIZ boşdursa yazılır;
* dərs — ana jurnalda eyni tarix + saat + növdə dərs varsa ona (saatı boşdursa: həmin gün + növdə TƏK dərs), yoxdursa
  eyni sahələrlə YENİ dərs; xana YENİ sətir kimi kopyalanır (``created_at`` köhnə), ana jurnalda artıq dolu xana QALIR;
* seminar dərsinin bütün xanaları bir seminar alt qrupunun tələbələrinindirsə dərs həmin alt qrupa bağlanır;
* alt qrup jurnalının xanaları SİLİNMİR: qeydiyyatları ``dropped``, jurnal passiv olur (geri qaytarmada olduğu kimi
  bərpa olunur); cədvəl slotları ana jurnala köçür (anada slot varsa yumşaq silinir);
* dərs yükü — alt qrupu olan, ana qrupu olmayan eyni fənn + dövr sətrinə ana qrup əlavə olunur (jurnal siyahısı).

Hər ailə üçün audit sətrində tam manifest (yaradılan xana / dərs / qeydiyyat, dəyişən sahələr) — ``--undo`` YALNIZ
manifestdəkini geri qaytarır. İdempotentdir: ikinci qaçışda alt qrup jurnalı passivdir → ``already_merged``.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_merge import _LESSON_FIELDS, _SLOT_FIELDS, linked_elsewhere
from .twin_relocate import closed, copy_mark, corrected_lesson_ids, corrected_mark_ids, has_scores, recompute_absences

REASON = "Sahib 2026-11-08: alt qrup jurnalları ana qrupun jurnalına (seminar alt qrupu kimi) birləşdirildi"
UNDO_REASON = "Sahib 2026-11-08: alt qrup jurnallarının birləşdirilməsinin geri qaytarılması"
RESOURCE = "registrar.subgroup_journal_merge"
#: ``{"name", "target": ana açılış | None, "group": ana qrup (target boşdursa), "sources": [alt qrup açılışları]}``
PLAN = (
    {
        "name": "536 MU · Azərbaycan tarixi",
        "target": "ece2f80c-a19f-43da-bab9-c0eb334ba62a",
        "sources": ("3f86ac7b-d4fe-4534-a64e-316e727924fc", "12575862-ba44-4ccd-afb6-ab357f7067d9"),
    },
    {
        "name": "536 MU · İqtisadiyyata giriş",
        "target": "547d6cdd-07fd-49d4-b30e-501ae20b6af7",
        "sources": ("7a62f438-d684-4710-a29c-ed867f7ee30b", "de94fc77-9188-4bc1-9527-5c240a5d56c8"),
    },
    {
        "name": "536 MU · Xətti cəbr və riyazi analiz",
        "target": "0f7f3cc3-e22c-4da5-a4d2-07f11bacd711",
        "sources": ("d16d484e-85ef-40af-8429-04183268116d", "de9425ac-d44a-4c12-8dfc-352ca48113ed"),
    },
    {
        "name": "536 Bİ · Xətti cəbr və riyazi analiz",
        "target": "6435c594-a301-4361-9d2d-8dd976b76ccb",
        "sources": ("f418c305-2d54-445f-8007-3e3476230a7f", "50edc68d-5247-4aad-baea-99e8b1207a8d"),
    },
    {
        "name": "536 Bİ · İqtisadiyyata giriş",
        "target": None,
        "group": "b7bc07b8-c91f-47fb-bd38-f712ae99c1db",
        "sources": ("61798b47-0ec5-4afa-8724-b60b23ce1a08", "ea80e556-0d88-483a-822b-4ffce23a1d54"),
    },
    # Sahib 2026-11-08: «alt qrupda tələbə var, ana qrup 0 göstərirsə problem var — ana qrup alt qrupların cəmidir».
    {
        "name": "135 Sİ · Mülki müdafiə",
        "target": "d2aa339c-64b3-4302-b1a6-ccbe72139475",
        "sources": ("da7c6573-edc7-489f-943e-3454abf61c1b", "48a8981b-9a23-4d29-9baf-9a00937698fc"),
    },
    {
        "name": "336 T · Mülki müdafiə",
        "target": "6c6a7276-958b-4f6e-8231-94f66a41e837",
        "sources": ("e6765887-51df-4e06-938a-4de5305f38a5", "a8066378-17b3-4e49-b992-8bb853e78f20"),
    },
    {
        "name": "135 TSPX · Mülki müdafiə və ilkin tibbi yardım",
        "target": "1990bea4-ebce-4b21-86d9-6a7f1c26eee6",
        "sources": ("9eeefcd5-e28c-4e36-86df-139d5400b6c6", "2e86391e-9a60-4aa1-8373-86254a14d893"),
        "split_all": True,
    },
    {
        "name": "336 F · Mülki müdafiə",
        "target": "e6eb947a-b498-4eca-823f-0fbfd746ed6b",
        "sources": ("c8bddaad-99b2-476e-80e0-5d87562ec676", "6a4ffa61-dbb9-464f-80d0-4b99745a081c"),
        "split_all": True,
    },
    {
        "name": "3/336 F · Müasir informasiya-kommunikasiya texnologiyaları",
        "target": "c8832119-e21e-40b8-956b-538acd12442c",
        "sources": ("6f7ed532-a850-444f-b2b6-5180e57fe90b",),
    },
)


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


class Merger:
    def __init__(self, *, organization, actor, counts):
        self.organization, self.actor, self.counts = organization, actor, counts

    def run(self, plan=None) -> None:
        for family in PLAN if plan is None else plan:
            try:
                with transaction.atomic():
                    self._family(family)
            except IntegrityError:
                self.counts["family_integrity_error"] += 1

    # ── yoxlamalar ────────────────────────────────────────────────────────
    def _offerings(self, family):
        CourseOffering = _model("CourseOffering")
        ids = [pk for pk in (family.get("target"), *family["sources"]) if pk]
        rows = {
            str(row.pk): row
            for row in CourseOffering.objects.select_for_update(of=("self",))
            .select_related("group")
            .filter(organization=self.organization, pk__in=ids)
        }
        return rows.get(str(family.get("target") or "")), [rows.get(str(pk)) for pk in family["sources"]]

    def _blocked(self, target, sources) -> str:
        if any(source is None for source in sources):
            return "family_missing"
        if not any(source.is_active for source in sources):
            return "already_merged"
        live = [source for source in sources if source.is_active]
        keys = {(source.subject_id, source.period_id) for source in live}
        if target is not None:
            keys.add((target.subject_id, target.period_id))
        if len(keys) != 1 or (target is not None and (not target.is_active or target in live)):
            return "family_invalid"
        if closed([source.pk for source in live] + ([target.pk] if target is not None else [])):
            return "family_closed"
        Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
        lesson_ids = list(Lesson.objects.filter(offering__in=live).values_list("pk", flat=True))
        mark_ids = list(LessonMark.objects.filter(lesson__offering__in=live).values_list("pk", flat=True))
        if corrected_lesson_ids(lesson_ids) or corrected_mark_ids(mark_ids):
            return "source_corrected"
        if has_scores(Enrollment.objects.filter(offering__in=live).values_list("pk", flat=True)):
            return "source_has_scores"
        if any(linked_elsewhere(source) for source in live):
            return "source_linked_elsewhere"
        return ""

    # ── ailə ──────────────────────────────────────────────────────────────
    def _family(self, family) -> None:
        target, sources = self._offerings(family)
        blocked = self._blocked(target, sources)
        if blocked:
            self.counts[blocked] += 1
            return
        sources = [source for source in sources if source.is_active]
        manifest = defaultdict(list)
        if target is None:
            target = self._create_target(family, sources[0], manifest)
            if target is None:
                self.counts["target_group_missing"] += 1
                return
        numbers = self._seminar_groups(target, sources, manifest)
        enrollments = self._enrollments(target, sources, numbers, manifest)
        if enrollments is None:
            self.counts["target_enrollment_blocked"] += 1
            transaction.set_rollback(True)
            return
        lessons = self._lessons(target, sources, enrollments, manifest)
        self._tag_seminars(target, lessons, manifest, every_kind=family.get("split_all", False))
        self._slots(target, sources, manifest)
        self._load_rows(target, sources, manifest)
        self._retire(sources, manifest)
        recompute_absences(list({row.pk: row for row in enrollments.values()}.values()))
        self.counts["families_merged"] += 1
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            obj=target,
            new_values={"family": family["name"], "sources": [str(source.pk) for source in sources]},
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
            return None
        target = get_or_create_offering(
            organization=self.organization, subject=sample.subject, period=sample.period, group=group
        )
        if target.instructor_id is None and sample.instructor_id:
            target.instructor_id = sample.instructor_id
            target.save(update_fields=["instructor", "updated_at"])
        manifest["target_created"].append(str(target.pk))
        self.counts["targets_created"] += 1
        return target

    def _seminar_groups(self, target, sources, manifest) -> dict:
        """``{alt qrup id → nömrə}`` — mövcud ``SeminarGroup`` (eyni qrup) saxlanılır, yoxdursa yaradılır."""
        SeminarGroup = _model("SeminarGroup")
        existing = {row.unit_id: row.number for row in SeminarGroup.objects.filter(offering=target)}
        used = set(existing.values())
        numbers = {}
        for group in sorted({source.group for source in sources}, key=lambda unit: unit.name):
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

    def _enrollments(self, target, sources, numbers, manifest):
        """``{alt qrup qeydiyyatı id → ana jurnal qeydiyyatı}`` (DB qapısı rədd etsə ``None``)."""
        Enrollment, Record = _model("Enrollment"), _model("StudentAcademicRecord")
        existing = {row.student_id: row for row in Enrollment.objects.select_for_update().filter(offering=target)}
        rows = list(Enrollment.objects.select_for_update().filter(offering__in=sources, status="enrolled"))
        groups = dict(
            Record.objects.filter(
                organization=self.organization, student_id__in=[row.student_id for row in rows], is_active=True
            ).values_list("student_id", "group_id")
        )
        out = {}
        for row in sorted(rows, key=lambda item: (item.created_at, item.pk)):
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
                except IntegrityError:
                    return None
                existing[row.student_id] = found
                manifest["enrollments_created"].append(str(found.pk))
                self.counts["enrollments_created"] += 1
            elif found.status != "enrolled":
                self.counts["target_enrollment_not_active"] += 1
            number = numbers.get(groups.get(row.student_id))
            if number and found.seminar_group is None:
                Enrollment.objects.filter(pk=found.pk).update(seminar_group=number, updated_at=timezone.now())
                found.seminar_group = number
                manifest["seminar_group_set"].append(str(found.pk))
                self.counts["seminar_group_set"] += 1
            out[row.pk] = found
        return out

    def _lessons(self, target, sources, enrollments, manifest) -> set:
        Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
        by_slot, by_day = {}, defaultdict(list)
        for lesson in Lesson.objects.select_for_update().filter(offering=target).order_by("created_at"):
            by_slot.setdefault((lesson.date, lesson.start_time, lesson.kind), lesson)
            by_day[(lesson.date, lesson.kind)].append(lesson)
        filled = set(LessonMark.objects.filter(lesson__offering=target).values_list("lesson_id", "enrollment_id"))
        touched = set()
        for lesson in Lesson.objects.filter(offering__in=sources).order_by("date", "start_time", "created_at"):
            twin = by_slot.get((lesson.date, lesson.start_time, lesson.kind))
            same_day = by_day.get((lesson.date, lesson.kind), [])
            if twin is None and (lesson.start_time is None or same_day and same_day[0].start_time is None):
                twin = same_day[0] if len(same_day) == 1 else None
            if twin is None:
                twin = Lesson.objects.create(
                    organization=self.organization,
                    offering=target,
                    lab_group=lesson.lab_group,
                    **{name: getattr(lesson, name) for name in _LESSON_FIELDS},
                )
                Lesson.objects.filter(pk=twin.pk).update(created_at=lesson.created_at)
                by_slot[(lesson.date, lesson.start_time, lesson.kind)] = twin
                by_day[(lesson.date, lesson.kind)].append(twin)
                manifest["lessons_created"].append(str(twin.pk))
                self.counts["lessons_created"] += 1
            else:
                self.counts["lessons_matched"] += 1
            touched.add(twin.pk)
            for mark in lesson.marks.all().order_by("created_at"):
                enrollment = enrollments.get(mark.enrollment_id)
                if enrollment is None:
                    self.counts["marks_without_target"] += 1
                    continue
                if (twin.pk, enrollment.pk) in filled:
                    self.counts["marks_target_kept"] += 1
                    continue
                created = copy_mark(mark, lesson=twin, enrollment=enrollment)
                filled.add((twin.pk, enrollment.pk))
                manifest["marks_created"].append(str(created.pk))
                self.counts["marks_copied"] += 1
        return touched

    def _tag_seminars(self, target, touched, manifest, *, every_kind=False) -> None:
        """Bütün xanaları BİR seminar alt qrupunun tələbələrində olan seminar dərsi həmin alt qrupa bağlanır.

        ``every_kind`` (ailədə ``split_all``) — alt qrupları mühazirəni də AYRI saatda keçən ailə (Mülki müdafiə 135
        TSPX, 336 F): tək alt qrupun mühazirəsi də ona bağlanır ki, o biri alt qrupun xanası boş görünməsin."""
        Lesson = _model("Lesson")
        kinds = ("seminar", "lecture") if every_kind else ("seminar",)
        lessons = Lesson.objects.filter(pk__in=touched, kind__in=kinds, seminar_group__isnull=True)
        corrected = corrected_lesson_ids([lesson.pk for lesson in lessons])
        for lesson in lessons.prefetch_related("marks__enrollment"):
            numbers = {mark.enrollment.seminar_group for mark in lesson.marks.all()}
            if str(lesson.pk) in corrected or len(numbers) != 1 or None in numbers:
                continue
            Lesson.objects.filter(pk=lesson.pk).update(seminar_group=numbers.pop(), updated_at=timezone.now())
            manifest["seminar_lessons_tagged"].append(str(lesson.pk))
            self.counts["seminar_lessons_tagged" if lesson.kind == "seminar" else "lectures_tagged"] += 1

    def _slots(self, target, sources, manifest) -> None:
        ScheduleSlot = _model("ScheduleSlot")
        own = list(ScheduleSlot.objects.select_for_update().filter(offering__in=sources))
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

    def _load_rows(self, target, sources, manifest) -> None:
        Row = _model("TeachingTaskRow", "workload")
        rows = (
            Row.objects.filter(
                organization=self.organization,
                subject_id=target.subject_id,
                period_id=target.period_id,
                groups__in=[source.group_id for source in sources],
            )
            .exclude(groups=target.group_id)
            .distinct()
        )
        for row in rows:
            row.groups.add(target.group_id)
            manifest["load_rows_group_added"].append(str(row.pk))
            self.counts["load_rows_group_added"] += 1

    def _retire(self, sources, manifest) -> None:
        Enrollment = _model("Enrollment")
        ids = list(Enrollment.objects.filter(offering__in=sources, status="enrolled").values_list("pk", flat=True))
        Enrollment.objects.filter(pk__in=ids).update(status="dropped", updated_at=timezone.now())
        manifest["source_enrollments_dropped"].extend(str(pk) for pk in ids)
        self.counts["source_enrollments_dropped"] += len(ids)
        for source in sources:
            source.is_active = False
            source.save(update_fields=["is_active", "updated_at"])
            manifest["sources_retired"].append(str(source.pk))
            self.counts["sources_retired"] += 1


def undo(*, organization, actor, counts) -> None:
    """Manifestdəkini geri qaytar (sonradan dəyişmiş xana / dərs SAXLANILIR, sayılır)."""
    AuditLog = _model("AuditLog", "audit")
    rows = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON).order_by(
        "-created_at"
    )
    for row in rows:
        manifest = (row.changes or {}).get("manifest") or {}
        target_id = (row.changes or {}).get("target")
        if not manifest.get("sources_retired"):
            continue
        if _model("CourseOffering").objects.filter(pk__in=manifest["sources_retired"], is_active=True).exists():
            counts["undo_already_done"] += 1
            continue
        with transaction.atomic():
            _undo_family(organization, actor, counts, manifest, target_id)


def _undo_family(organization, actor, counts, manifest, target_id) -> None:
    Enrollment, Lesson, LessonMark = _model("Enrollment"), _model("Lesson"), _model("LessonMark")
    CourseOffering, SeminarGroup = _model("CourseOffering"), _model("SeminarGroup")
    ScheduleSlot, Row = _model("ScheduleSlot"), _model("TeachingTaskRow", "workload")
    counts["undo_marks_deleted"] += LessonMark.objects.filter(pk__in=manifest.get("marks_created", [])).delete()[0]
    Lesson.objects.filter(pk__in=manifest.get("seminar_lessons_tagged", [])).update(seminar_group=None)
    doomed = Lesson.objects.filter(pk__in=manifest.get("lessons_created", []), marks__isnull=True)
    counts["undo_lessons_deleted"] += doomed.delete()[0]
    Enrollment.objects.filter(pk__in=manifest.get("seminar_group_set", [])).update(seminar_group=None)
    created = Enrollment.objects.filter(pk__in=manifest.get("enrollments_created", []), lesson_marks__isnull=True)
    counts["undo_enrollments_deleted"] += created.delete()[0]
    SeminarGroup.objects.filter(pk__in=manifest.get("seminar_groups_created", [])).delete()
    ScheduleSlot.objects.filter(pk__in=manifest.get("slots_created", [])).delete()
    ScheduleSlot.all_objects.filter(pk__in=manifest.get("slots_soft_deleted", [])).update(
        is_deleted=False, deleted_at=None
    )
    for row in Row.objects.filter(pk__in=manifest.get("load_rows_group_added", [])):
        row.groups.remove(target_id)
    Enrollment.objects.filter(pk__in=manifest.get("source_enrollments_dropped", []), status="dropped").update(
        status="enrolled", updated_at=timezone.now()
    )
    CourseOffering.objects.filter(pk__in=manifest.get("sources_retired", [])).update(is_active=True)
    CourseOffering.objects.filter(pk__in=manifest.get("target_created", []), enrollments__isnull=True).update(
        is_active=False
    )
    recompute_absences(
        list(Enrollment.objects.filter(pk__in=manifest.get("source_enrollments_dropped", [])))
        + list(Enrollment.objects.filter(offering_id=target_id, status="enrolled"))
    )
    counts["undo_families"] += 1
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={"target": target_id, "sources": manifest.get("sources_retired", [])},
        reason=UNDO_REASON,
        resource_type=RESOURCE,
        resource_id=str(target_id),
    )


__all__ = ["PLAN", "Merger", "undo"]
