"""Qəbul edilmiş sərbəst iş ballarını jurnala yenidən ötürür (``pending`` / istəyə görə ``blocked``).

İstifadə::

    python manage.py subject_folder_sync_journal                    # dry-run: yalnız say
    python manage.py subject_folder_sync_journal --apply            # pending-ləri ötür
    python manage.py subject_folder_sync_journal --apply --include-blocked --org qku
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Fənn qovluğu: jurnala düşməmiş sərbəst iş ballarını yenidən ötürür."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Həqiqətən ötür (default: dry-run).")
        parser.add_argument(
            "--include-blocked", action="store_true", help="Jurnalın rədd etdiklərini də yenidən yoxla."
        )
        parser.add_argument("--org", default="", help="Təşkilat slug-ı (boş = hamısı).")
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        from apps.subject_folder.services.journal import resolve_journal_hook, retry_pending

        with rls_worker_atomic(), bypass_rls():
            organization_id = None
            if options["org"]:
                organization = (
                    django_apps.get_model("organizations", "Organization").objects.filter(slug=options["org"]).first()
                )
                if organization is None:
                    raise CommandError(f"Təşkilat tapılmadı: {options['org']}")
                organization_id = organization.pk
            summary = retry_pending(
                organization_id=organization_id,
                include_blocked=options["include_blocked"],
                limit=options["limit"],
                apply=options["apply"],
            )
        hook = "var" if resolve_journal_hook() else "YOXDUR (registrar tərəfi hələ qoşulmayıb)"
        mode = "APPLY" if options["apply"] else "DRY-RUN"
        self.stdout.write(f"[{mode}] jurnal hook-u: {hook}; nəticə: {summary}")
