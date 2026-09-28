"""Audit 2026-09-28 SV-3 — köhnə anonim cavabları təsadüfi sıra ilə YENİDƏN yazır.

Bufer (``services/pending``) tətbiq olunmazdan əvvəl yazılmış cavablar qəbzlərlə eyni
tranzaksiyada, eyni sırada yaranıb: ``ORDER BY ctid`` / ``xmin`` onları tələbəyə bağlayır.
Bu əmr hər kampaniyanın cavablarını (cavab mətnləri və ballar dəyişmədən) yeni təsadüfi
UUID-lərlə, təsadüfi sırada, tək tranzaksiyada yenidən yazır; nəticə rəqəmləri dəyişmir.
Əmrdən ƏVVƏL alınmış ehtiyat nüsxələr isə bağı saxlayır — onlar həssas sayılmalıdır::

    python manage.py surveys_shuffle_responses                # quru icra: kampaniyalar və saylar
    python manage.py surveys_shuffle_responses --apply        # yaz
    python manage.py surveys_shuffle_responses --org qku --apply
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Count

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Anonim sorğu cavablarını təsadüfi sıra ilə yenidən yazır (defolt quru icra)."

    def add_arguments(self, parser):
        parser.add_argument("--org", dest="org_slug", default="", help="Yalnız bu təşkilat (slug)")
        parser.add_argument("--apply", action="store_true", help="Dəyişiklikləri yaz")

    def handle(self, *args, **options):
        from apps.surveys.models import SurveyCampaign
        from apps.surveys.services.pending import reshuffle_campaign

        with rls_worker_atomic(), bypass_rls():
            campaigns = SurveyCampaign.objects.select_related("organization", "period").annotate(n=Count("responses"))
            if options["org_slug"]:
                campaigns = campaigns.filter(organization__slug=options["org_slug"])
            for campaign in campaigns.order_by("organization__slug", "period__start_date"):
                written = reshuffle_campaign(campaign.pk) if options["apply"] and campaign.n else 0
                state = f"yenidən yazıldı: {written}" if options["apply"] else f"cavab: {campaign.n}"
                self.stdout.write(f"{campaign.organization.slug} · {campaign.period.name}: {state}")
            if not options["apply"]:
                self.stdout.write(self.style.WARNING("Quru icra — heç nə yazılmadı (--apply ilə təkrarlayın)."))
