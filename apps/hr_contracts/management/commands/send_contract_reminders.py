"""Əmək müqaviləsi bitmə xatırlatmaları — Celery beat-in əl ilə / ehtiyat (cron) işə salınması.

İstifadə::

    python manage.py send_contract_reminders --dry-run            # nə göndəriləcəyini göstər, heç nə yazma
    python manage.py send_contract_reminders                      # göndər (idempotent — təkrar işə salmaq olar)
    python manage.py send_contract_reminders --org qku --date 2026-11-01 --dry-run
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand, CommandError

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Əmək müqavilələri: bitmə xatırlatmaları (HR + işçi), idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Heç nə yazma və göndərmə — yalnız plan.")
        parser.add_argument("--org", default="", help="Yalnız bu təşkilat (slug).")
        parser.add_argument("--date", default="", help="Hesablama tarixi (YYYY-MM-DD; defolt — bu gün).")

    def handle(self, *args, **options):
        from django.apps import apps as django_apps

        from apps.hr_contracts.services.reminders import run

        on = None
        if options["date"]:
            try:
                on = dt.date.fromisoformat(options["date"])
            except ValueError as exc:
                raise CommandError("--date YYYY-MM-DD formatında olmalıdır.") from exc
        with rls_worker_atomic(), bypass_rls():
            organization = None
            if options["org"]:
                Organization = django_apps.get_model("organizations", "Organization")
                organization = Organization.objects.filter(slug=options["org"]).first()
                if organization is None:
                    raise CommandError(f"Təşkilat tapılmadı: {options['org']}")
            summary = run(on=on, organization=organization, dry_run=options["dry_run"])
        mode = "DRY-RUN" if summary["dry_run"] else "APPLY"
        for item in summary["items"]:
            self.stdout.write(
                f"  {item['kind']:<15} № {item['number']:<20} hədd {item['threshold']:>3} · qalıb {item['days_left']} gün"
            )
        self.stdout.write(
            f"[{mode}] {summary['date']} · hədlər {summary['thresholds']}: xatırlatma {summary['reminders']}, "
            f"müddəti bitdi {summary['expired']}, artıq göndərilmiş {summary['skipped']}"
        )
