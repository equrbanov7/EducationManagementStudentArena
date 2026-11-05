"""``release_stale_slot_teachers`` — jurnalı və dərs yükü olmayan müəllimin cədvəlində qalan dərslər (2026-11-05).

Sahib (2026-11-05): «bəzi müəllimlərdə elektron jurnalında və dərs yükündə o fənn olmasa da dərs cədvəlində
qalıb». Kod artıq bunu oxuda gizlədir və bölgü / təhvil zamanı slotu düzəldir
(:mod:`apps.registrar.schedule_stale_teachers`); bu əmr MÖVCUD data üçündür:

* aktiv jurnalın slotuna YAZILMIŞ müəllim jurnalın sahibi/pay sahibi deyil, jurnalda dərs aparmayıb və bu fənn +
  semestr + qrup üzrə dərs yükü yoxdursa → slotun müəllimi BOŞALDILIR (NULL: dərs qrupun cədvəlində qalır, jurnal
  sahibini izləyir). Slot silinmir; hər boşaltma audit jurnalına köhnə müəllimlə düşür;
* qeyri-aktiv jurnalın HƏLƏ cədvəldə duran (parklanmamış) slotu → PARKLANIR (yumşaq: yeri və müəllimi saxlanılır,
  redaktorun «yenidən yerləşdirilməli» siyahısındadır). Artıq parklanmışlara toxunulmur — təmir paketlərinin
  geri qaytarma sübutudur.

DEFOLT DRY-RUN; idempotent (ikinci qaçışda 0). Stdout-a YALNIZ saylar (``slot_teachers: açar=say …``).
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.audit import log_actions
from core.constants import AuditAction
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ... import schedule_stale_teachers
from ...models import ScheduleSlot
from .import_timetable_docx import resolve_period
from .relocate_twin_enrollment import superadmin

PREFIX = "slot_teachers:"
PARK_REASON = "Jurnal deaktiv edilib — onun cədvəldə qalan dərsi parklandı (release_stale_slot_teachers, 2026-11-05)"
KEYS = ("checked", "current", "released", "inactive_live", "inactive_parked")


class Command(BaseCommand):
    help = "Jurnalı/dərs yükü qalmayan slot müəllimini boşaldır, deaktiv jurnalın slotunu parklayır (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--period", default="", help="Semestr: «Payız 2026/2027» və ya UUID (boş = hamısı)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        actor = superadmin(options["actor"])
        Organization = django_apps.get_model("organizations", "Organization")
        counts = Counter()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("slot_teachers_organization_unknown")
            period = None
            if str(options["period"] or "").strip():
                period = resolve_period(organization, options["period"])
                if period is None:
                    raise CommandError("slot_teachers_period_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                self._release(organization, period, actor, counts)
                self._park_inactive(organization, period, actor, counts)
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={counts[key]}" for key in KEYS))

    @staticmethod
    def _slots(organization, period):
        slots = ScheduleSlot.objects.filter(organization=organization)
        return slots.filter(offering__period=period) if period is not None else slots

    def _release(self, organization, period, actor, counts) -> None:
        overrides = list(
            self._slots(organization, period)
            .filter(offering__is_active=True, instructor__isnull=False)
            .select_related("offering")
        )
        overrides = [slot for slot in overrides if slot.instructor_id != slot.offering.instructor_id]
        counts["checked"] = len(overrides)
        offering_ids = sorted({slot.offering_id for slot in overrides}, key=str)
        counts["released"] = schedule_stale_teachers.release(offering_ids=offering_ids, by_user=actor)
        counts["current"] = counts["checked"] - counts["released"]

    def _park_inactive(self, organization, period, actor, counts) -> None:
        live = list(
            self._slots(organization, period)
            .select_for_update(of=("self",))
            .filter(offering__is_active=False, is_parked=False)
            .order_by("pk")
        )
        counts["inactive_live"] = len(live)
        if not live:
            return
        now = timezone.now()
        ScheduleSlot.objects.filter(pk__in=[slot.pk for slot in live]).update(
            is_parked=True, parked_at=now, parked_by=actor, park_reason=PARK_REASON, updated_at=now
        )
        log_actions(
            {
                "action": AuditAction.UPDATE,
                "user": actor,
                "organization": organization,
                "old_values": {"is_parked": False},
                "new_values": {"is_parked": True, "offering": str(slot.offering_id)},
                "reason": PARK_REASON,
                "resource_type": "registrar.ScheduleSlot",
                "resource_id": str(slot.pk),
                "resource_repr": f"{slot.offering_id} · {slot.weekday} {slot.start_time:%H:%M}",
            }
            for slot in live
        )
        counts["inactive_parked"] = len(live)
