"""«Həll olunub» statusunda ilişib qalmış müraciətləri avtomatik bağlayır.

Repo-da Celery beat cədvəli yoxdur (bax `apps/applications/services/maintenance.py`),
ona görə giriş nöqtəsi bu əmrdir — cron/systemd timer ilə gündəlik çağırılır.
"""

from django.core.management.base import BaseCommand

from apps.applications.services.maintenance import close_stale_resolved
from apps.organizations.models import Organization
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Cavabdan sonra təsdiqlənməmiş müraciətləri avtomatik bağlayır."

    def add_arguments(self, parser):
        parser.add_argument("--org", dest="org_slug", default="")

    def handle(self, *args, **options):
        # RLS transaction-pooling təhlükəsizliyi (FAZA 4/Task 1).
        with rls_worker_atomic():
            slug = (options.get("org_slug") or "").strip()
            organization = Organization.objects.filter(slug=slug).first() if slug else None
            closed = close_stale_resolved(organization=organization)
            self.stdout.write(self.style.SUCCESS(f"{closed} müraciət avtomatik bağlandı."))
