"""Defolt sorğu şablonunu (kod dəsti) təşkilat(lar)a əkir — idempotent.

Kampaniya açılanda şablon onsuz da «tənbəl» əkilir; bu əmr əvvəlcədən hazırlamaq
və ya yeni sual versiyasını yaymaq üçündür::

    python manage.py surveys_ensure_template              # quru icra: bütün universitetlər
    python manage.py surveys_ensure_template --apply      # yaz
    python manage.py surveys_ensure_template --org qku --apply
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Defolt anonim sorğu şablonunu təşkilatlara əkir (defolt quru icra)."

    def add_arguments(self, parser):
        parser.add_argument("--org", dest="org_slug", default="", help="Yalnız bu təşkilat (slug)")
        parser.add_argument("--apply", action="store_true", help="Dəyişiklikləri yaz")

    def handle(self, *args, **options):
        from apps.surveys.defaults import DEFAULT_TEMPLATE_NAME, DEFAULT_TEMPLATE_VERSION
        from apps.surveys.models import SurveyTemplate
        from apps.surveys.services.templates import ensure_default_template

        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organizations = Organization.objects.filter(org_type="university", is_active=True)
            if options["org_slug"]:
                organizations = organizations.filter(slug=options["org_slug"])
            for organization in organizations.order_by("slug"):
                exists = SurveyTemplate.objects.filter(
                    organization=organization, name=DEFAULT_TEMPLATE_NAME, version=DEFAULT_TEMPLATE_VERSION
                ).exists()
                if options["apply"]:
                    ensure_default_template(organization)
                state = "var" if exists else ("yaradıldı" if options["apply"] else "yaradılacaq")
                self.stdout.write(f"{organization.slug}: şablon v{DEFAULT_TEMPLATE_VERSION} — {state}")
            if not options["apply"]:
                self.stdout.write(self.style.WARNING("Quru icra — heç nə yazılmadı (--apply ilə təkrarlayın)."))
