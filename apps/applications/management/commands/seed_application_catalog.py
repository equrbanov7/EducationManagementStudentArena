"""Müraciət kataloqunu (şöbələr + növlər) doldurur — İDEMPOTENT.

Mövcud sətirlərə TOXUNMUR: tenant kataloqu redaktə edibsə təkrar icra onu
geri qaytarmır. Miqrasiya `0003_seed_permissions_and_catalog` eyni servisi
çağırır; bu əmr yeni təşkilat üçün əl ilə doldurma yoludur.
"""

from django.core.management.base import BaseCommand

from apps.applications.services.catalog import seed_catalog
from apps.organizations.models import Organization
from core.constants import OrganizationType


class Command(BaseCommand):
    help = "Müraciət kataloqunu (ApplicationUnit + ApplicationKind) doldurur."

    def add_arguments(self, parser):
        parser.add_argument("--org", dest="org_slug", default="", help="Yalnız bu slug-lı təşkilat.")

    def handle(self, *args, **options):
        queryset = Organization.objects.filter(is_active=True)
        slug = (options.get("org_slug") or "").strip()
        if slug:
            queryset = queryset.filter(slug=slug)
        else:
            queryset = queryset.filter(org_type=OrganizationType.UNIVERSITY)

        for organization in queryset:
            units, kinds = seed_catalog(organization)
            self.stdout.write(self.style.SUCCESS(f"{organization.slug}: {len(units)} şöbə, {len(kinds)} növ hazırdır."))
