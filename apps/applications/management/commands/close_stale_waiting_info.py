"""Üç iş günü cavabsız qalmış əlavə məlumat sorğularını bağla."""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...services.waiting_info import close_stale_waiting_info


class Command(BaseCommand):
    help = "Üç iş günü əlavə məlumat gəlməyən müraciətləri həll olunmuş saymadan bağlayır."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="")

    def handle(self, *args, **options):
        with rls_worker_atomic(), bypass_rls():
            organization = None
            if options["org"]:
                organization = (
                    apps.get_model("organizations", "Organization").objects.filter(slug=options["org"]).first()
                )
                if organization is None:
                    raise CommandError("Təşkilat tapılmadı.")
            closed = close_stale_waiting_info(organization=organization)
            self.stdout.write(f"{closed} cavabsız müraciət bağlandı.")
