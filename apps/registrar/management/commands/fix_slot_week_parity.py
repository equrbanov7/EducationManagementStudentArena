"""``fix_slot_week_parity`` — çıxarılmış «üst/alt həftə» slotunu dərs tarixçəsi ardıcıl həftə göstərirsə hər həftəyə
qaytarır (RİM 2026-10-27, MR-8).

``infer_timetable_from_lessons``-in köhnə paritet qaydası 4 tarixdən 1-i buraxılan hər həftə dərsini «alt/üst həftə»
edirdi. Qayda indi :func:`apps.registrar.timetable_inference.decide_week_type` — ≥ 2 cüt ardıcıl həftə → hər həftə.

YALNIZ bu əmrin yaratdığı slotlar (audit ``resource_id="infer_timetable_from_lessons"`` → ``created_ids``) — rəsmi
docx idxalı və redaktorda yaradılan slotlara toxunulmur; sonradan redaktorda dəyişdirilmiş slot (slotun öz audit
sətri var) da qalır. Slotun tarixçəsi: həmin açılışın eyni həftə günü + (zəngə çəkilmiş) saat + növdə, cədvəldən
kənar işarəsi olmayan dərsləri. Hər həftəyə keçid toqquşma yaradırsa (qrup / müəllim / otaq — məs. qarşı həftədə
başqa dərs) slot qalır və sayılır. Cədvəl kilidi altında; bir audit sətri (dəyişən slot id-ləri). DEFOLT DRY-RUN.
Stdout-a YALNIZ saylar (``slot_parity: açar=say …``). İdempotent: ikinci qaçışda slot artıq ``all``-dur.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ... import schedule_conflicts
from ...models import Lesson, ScheduleSlot, WeekType
from ...schedule import effective_instructor_id
from ...schedule_lock import lock_schedule
from ...timetable_inference import consecutive_week_pairs, decide_week_type, parity_counts, snap_to_bell
from ...timetable_inference_plan import inferred_slot_ids
from .import_timetable_docx import resolve_period
from .relocate_twin_enrollment import superadmin

PREFIX = "slot_parity:"
SOURCE = "infer_timetable_from_lessons"
RESOURCE_ID = "fix_slot_week_parity"
REASON = "Cədvəl: ardıcıl həftələrdə keçirilən dərsin slotu «üst/alt həftə» deyil, hər həftədir — RİM 2026-10-27 (MR-8)"


class Command(BaseCommand):
    help = "Çıxarılmış üst/alt həftə slotlarını ardıcıl həftə sübutu ilə hər həftəyə qaytarır (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--period", required=True, help="Semestr: «Payız 2026/2027» və ya dövrün UUID-i")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        actor = superadmin(options["actor"])
        Organization = django_apps.get_model("organizations", "Organization")
        counts = Counter()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("slot_parity_organization_unknown")
            period = resolve_period(organization, options["period"])
            if period is None:
                raise CommandError("slot_parity_period_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                lock_schedule(organization.pk, period.pk)
                changed = self._fix(organization, period, counts)
                if changed:
                    log_action(
                        action=AuditAction.UPDATE,
                        user=actor,
                        organization=organization,
                        new_values={"period_id": str(period.pk), "week_type": WeekType.ALL, "slot_ids": changed},
                        reason=REASON,
                        resource_type="registrar.ScheduleSlot",
                        resource_id=RESOURCE_ID,
                        resource_repr="Dərs cədvəli (həftə pariteti düzəlişi)",
                    )
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))

    def _fix(self, organization, period, counts) -> list:
        AuditLog = django_apps.get_model("audit", "AuditLog")
        inferred = inferred_slot_ids(organization, SOURCE)
        live = list(schedule_conflicts.live_slots(organization, period_id=period.pk))
        by_day = defaultdict(list)
        for slot in live:
            by_day[slot.weekday].append(slot)
        candidates = [
            slot for slot in live if slot.week_type in (WeekType.ODD, WeekType.EVEN) and str(slot.pk) in inferred
        ]
        counts["alternate_slots"] = sum(1 for slot in live if slot.week_type in (WeekType.ODD, WeekType.EVEN))
        counts["inferred_alternate_slots"] = len(candidates)
        edited = set(
            AuditLog.objects.filter(
                organization=organization, resource_id__in=[str(slot.pk) for slot in candidates]
            ).values_list("resource_id", flat=True)
        )
        history = self._history(organization, period, candidates)
        changed = []
        for slot in sorted(candidates, key=lambda row: (row.weekday, row.start_time, str(row.pk))):
            if str(slot.pk) in edited:
                counts["edited_kept"] += 1
                continue
            days = history.get(slot.pk, set())
            odd, even = parity_counts(period, days)
            if decide_week_type(odd, even, consecutive_pairs=consecutive_week_pairs(days)) != WeekType.ALL:
                counts["alternate_confirmed"] += 1
                continue
            conflicts = schedule_conflicts.detect(
                organization=organization,
                weekday=slot.weekday,
                start_time=slot.start_time,
                end_time=slot.end_time,
                week_type=WeekType.ALL,
                room=slot.room,
                group_id=slot.offering.group_id,
                instructor_id=effective_instructor_id(slot),
                exclude_ids=[slot.pk],
                candidates=by_day[slot.weekday],
                period_id=period.pk,
                subject_id=slot.offering.subject_id,
                kind=slot.kind,
                offering_id=slot.offering_id,
            )
            if conflicts:
                counts["conflict_kept"] += 1
                continue
            slot.week_type = WeekType.ALL  # yaddaşda da — növbəti slotların toqquşma yoxlaması bunu görür
            ScheduleSlot.objects.filter(pk=slot.pk).update(week_type=WeekType.ALL, updated_at=timezone.now())
            changed.append(str(slot.pk))
        counts["slots_set_weekly"] = len(changed)
        return changed

    @staticmethod
    def _history(organization, period, slots) -> dict:
        """``slot pk → {tarix}`` — açılışın eyni gün + (zəngə çəkilmiş) saat + növdə keçirilmiş dərsləri."""

        wanted = defaultdict(list)
        for slot in slots:
            wanted[slot.offering_id].append(slot)
        out: dict = defaultdict(set)
        rows = (
            Lesson.objects.filter(organization=organization, offering_id__in=list(wanted), offering__period=period)
            .exclude(start_time__isnull=True)
            .filter(off_schedule_reason="")
            .values_list("offering_id", "date", "start_time", "kind")
        )
        for offering_id, day, start, kind in rows.iterator(chunk_size=5000):
            snapped, _end = snap_to_bell(start, None, 25)
            for slot in wanted[offering_id]:
                if slot.kind == kind and slot.weekday == day.isoweekday() and slot.start_time == snapped:
                    out[slot.pk].add(day)
        return out
