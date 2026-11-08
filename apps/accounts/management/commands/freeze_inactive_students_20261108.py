"""``freeze_inactive_students_20261108`` — heç bir fəndə i/e / bal / midterm olmayan tələbələri dondur (defolt dry-run).

Qaydalar: :mod:`apps.accounts.services.inactive_students_2026_11_08`. Stdout-a YALNIZ saylar və hesab id-ləri
(``inactive_students: açar=say …``) — ad / FİN çıxmır.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...services.inactive_students_2026_11_08 import run, skipped_report

PREFIX = "inactive_students:"


class Command(BaseCommand):
    help = "Sahib 2026-11-08: aktivliyi olmayan tələbələri dondur — yazılış suspended + hesab bloku (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin dondurduğunu geri qaytar")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument(
            "--show-skipped", action="store_true", help="Yalnız oxu: heç kimə yazılmamış jurnallı tələbələr + qrup id"
        )

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        Organization = django_apps.get_model("organizations", "Organization")
        counts = Counter()
        report = []
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("inactive_students_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            if options["show_skipped"]:
                rows = skipped_report(organization)
                self.stdout.write(f"{PREFIX} mode=show_skipped")
                for student_id, group_id in rows:
                    self.stdout.write(f"{PREFIX} no_evidence={student_id}_{group_id or 'none'}")
                return
            with transaction.atomic():
                run(organization=organization, actor=actor, counts=counts, undo=options["undo"], report=report)
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
        for start in range(0, len(report), 40):
            self.stdout.write(f"{PREFIX} user_ids=" + "-".join(str(pk) for pk in report[start : start + 40]))
