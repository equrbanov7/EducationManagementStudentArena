"""``clear_stale_off_schedule_flags`` — artıq cədvələ uyğun gələn dərslərin «cədvəldən kənar» işarəsini təmizləyir
(2026-11-03).

İşarə (``Lesson.off_schedule_reason``) yalnız dərs yaradılanda yazılırdı və sonra heç vaxt yenidən yoxlanmırdı:
dərs «Data bərpası» ilə slotsuz açılıb, cədvəl SONRA düzəlibsə işarə qalırdı. Kod artıq dərs düzəliləndə və slot
yazılanda işarəni yenidən qiymətləndirir (:mod:`apps.registrar.off_schedule_flags`); bu əmr MÖVCUD data üçündür.

Qayda yaradılma ilə EYNİDİR: dərsin tarixində (həftə günü + üst/alt + dövr) açılışın cədvəldə DURAN slotunun
başlanğıc saatı dərsin saatıdır. Yalnız təmizlənir; dərs, xana, tələbə toxunulmur. Hər açılışın «Dəyişiklik
tarixçəsi»nə köhnə səbəblə sətir + bir yekun audit sətri. DEFOLT DRY-RUN; idempotent (ikinci qaçışda 0).
Stdout-a YALNIZ saylar (``off_schedule_flags: açar=say …``).
"""

from __future__ import annotations

import re
from collections import Counter

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ... import off_schedule_flags
from ...models import CourseOffering, Lesson
from .import_timetable_docx import resolve_period
from .relocate_twin_enrollment import superadmin

PREFIX = "off_schedule_flags:"
REASON = "Cədvəl sonradan düzəlib — cədvələ uyğun dərsin «cədvəldən kənar» işarəsi təmizləndi (2026-11-03)"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class Command(BaseCommand):
    help = "Cədvələ uyğun gələn dərslərin köhnəlmiş «cədvəldən kənar» işarəsini təmizləyir (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--period", default="", help="Semestr: «Payız 2026/2027» və ya UUID (boş = hamısı)")
        parser.add_argument("--offering", default="", help="Yalnız bu jurnal (açılışın UUID-i)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        actor = superadmin(options["actor"])
        offering_id = str(options["offering"] or "").strip().lower()
        if offering_id and not _UUID.match(offering_id):
            raise CommandError("off_schedule_offering_invalid")
        Organization = django_apps.get_model("organizations", "Organization")
        counts = Counter()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("off_schedule_organization_unknown")
            period = None
            if str(options["period"] or "").strip():
                period = resolve_period(organization, options["period"])
                if period is None:
                    raise CommandError("off_schedule_period_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                cleared = self._run(organization, period, offering_id, actor, counts)
                if cleared:
                    log_action(
                        action=AuditAction.UPDATE,
                        user=actor,
                        organization=organization,
                        new_values={
                            "period_id": str(getattr(period, "pk", "") or ""),
                            "offering_id": offering_id,
                            "lesson_ids": cleared,
                        },
                        reason=REASON,
                        resource_type="registrar.Lesson",
                        resource_id=off_schedule_flags.SOURCE_COMMAND,
                        resource_repr="Cədvəldən kənar işarəsi (köhnəlmiş)",
                    )
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        keys = ("offerings", "flagged", "still_off_schedule", "stale", "cleared")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={counts[key]}" for key in keys))

    def _run(self, organization, period, offering_id, actor, counts) -> list:
        flagged = Lesson.objects.filter(organization=organization).exclude(off_schedule_reason="")
        if period is not None:
            flagged = flagged.filter(offering__period=period)
        if offering_id:
            flagged = flagged.filter(offering_id=offering_id)
        by_offering: dict = {}
        for lesson in flagged.order_by("offering_id", "date", "start_time"):
            by_offering.setdefault(lesson.offering_id, []).append(lesson)
        offerings = CourseOffering.objects.filter(pk__in=list(by_offering)).select_related(
            "period", "organization", "subject"
        )
        cleared = []
        for offering in offerings.order_by("pk"):
            lessons = by_offering[offering.pk]
            counts["offerings"] += 1
            counts["flagged"] += len(lessons)
            stale = off_schedule_flags.stale_lessons(offering, lessons)
            counts["stale"] += len(stale)
            counts["still_off_schedule"] += len(lessons) - len(stale)
            if not stale:
                continue
            done = off_schedule_flags.clear(offering, stale, by_user=actor, source=off_schedule_flags.SOURCE_COMMAND)
            counts["cleared"] += done
            cleared += [str(lesson.pk) for lesson in stale if not lesson.off_schedule_reason]
        return cleared
