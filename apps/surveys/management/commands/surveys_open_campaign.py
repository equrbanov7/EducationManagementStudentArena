"""Dövrün anonim sorğu kampaniyasını əl ilə açır (backfill / jurnal bağlanması siqnalı qaçıbsa).

Defolt QURU icra (heç nə yazılmır, yalnız hesabat); ``--apply`` ilə yazır::

    python manage.py surveys_open_campaign --period <uuid>            # önizləmə
    python manage.py surveys_open_campaign --period <uuid> --apply    # aç + bildiriş
    python manage.py surveys_open_campaign --period <uuid> --apply --no-notify

İdempotentdir: kampaniya varsa yenisi yaranmır; qaralama açılır; bağlı kampaniyaya
toxunulmur (yenidən açılış yalnız kabinetdən, səbəbli qərarla).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Akademik dövr üçün anonim müəllim qiymətləndirmə sorğusunu açır (defolt quru icra)."

    def add_arguments(self, parser):
        parser.add_argument("--period", required=True, help="AcademicPeriod UUID")
        parser.add_argument("--apply", action="store_true", help="Dəyişiklikləri yaz (əks halda quru icra)")
        parser.add_argument("--no-notify", action="store_true", help="Tələbələrə bildiriş göndərmə")

    def handle(self, *args, **options):
        from apps.surveys.constants import CampaignStatus, OpenedVia
        from apps.surveys.models import SurveyCampaign
        from apps.surveys.services import notify
        from apps.surveys.services.campaigns import ensure_campaign
        from apps.surveys.services.templates import ensure_default_template

        AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
        with rls_worker_atomic(), bypass_rls():
            period = AcademicPeriod.objects.select_related("organization").filter(pk=options["period"]).first()
            if period is None:
                raise CommandError("Dövr tapılmadı.")
            organization = period.organization
            campaign = SurveyCampaign.objects.filter(organization=organization, period=period).first()
            students = notify.eligible_student_ids(organization, period.pk)
            self.stdout.write(
                f"Təşkilat: {organization.slug} · dövr: {period.name} ({period.academic_year})\n"
                f"Kampaniya: {campaign.status if campaign else 'yoxdur'} · bağlı jurnallı tələbə: {len(students)}"
            )
            if not options["apply"]:
                self.stdout.write(self.style.WARNING("Quru icra — heç nə yazılmadı (--apply ilə təkrarlayın)."))
                return
            if campaign is not None and campaign.status == CampaignStatus.CLOSED:
                self.stdout.write(self.style.WARNING("Kampaniya bağlıdır — toxunulmadı."))
                return
            with transaction.atomic():
                ensure_default_template(organization)
                campaign, created, opened = ensure_campaign(organization, period, via=OpenedVia.MANUAL)
                if opened and not options["no_notify"] and campaign.is_active_on(timezone.localdate()):
                    notify.notify_campaign_opened(organization, campaign, students)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Hazırdır: status={campaign.status} yaradıldı={created} açıldı={opened} "
                    f"bağlanma={campaign.closes_on} möhlət={campaign.grace_until}"
                )
            )
