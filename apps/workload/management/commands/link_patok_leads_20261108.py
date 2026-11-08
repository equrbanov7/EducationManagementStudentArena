"""``link_patok_leads_20261108`` — patok tərəfdaşı sətirləri aparıcı sətrə AÇIQ bağla (sahib 2026-11-08).

Qaydalar: :mod:`apps.workload.services.patok_links`. DEFOLT DRY-RUN (eyni kod, tranzaksiya geri qaytarılır),
``--apply`` yazır. ``--pairs tərəfdaş_uuid:aparıcı_uuid,…`` — birmənalı olmayan sətirlər üçün əl ilə cütlər.
Stdout-a YALNIZ saylar və sətir id-ləri (``patok_links: açar=dəyər …``; ad çap olunmur).

    manage.py link_patok_leads_20261108 --org qku --actor <superadmin> [--year 2026/2027] [--pairs …] [--apply]
"""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from apps.workload.center_registry import current_academic_year
from apps.workload.services.patok_links import link_patok_leads
from apps.workload.services.scoping import WorkloadDenied
from apps.workload.services.tasks import normalize_academic_year
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "patok_links:"
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_PAIRS = re.compile(rf"^{_UUID}:{_UUID}(,{_UUID}:{_UUID})*$")


def parse_pairs(value: str) -> list[tuple[str, str]]:
    value = (value or "").strip().lower()
    if not value:
        return []
    if not _PAIRS.match(value):
        raise CommandError("patok_links_pairs_format")
    pairs = [tuple(item.split(":")) for item in value.split(",")]
    if len({partner for partner, _lead in pairs}) != len(pairs):
        raise CommandError("patok_links_pairs_duplicate")
    return pairs


class Command(BaseCommand):
    help = "Sahib 2026-11-08: patok tərəfdaşı → aparıcı sətir açıq bağı (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--year", default="", help="Tədris ili (YYYY/YYYY; boş — cari il)")
        parser.add_argument("--pairs", default="", help="tərəfdaş_uuid:aparıcı_uuid,… (əl ilə cütlər)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        pairs = parse_pairs(options["pairs"])
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("patok_links_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            year = normalize_academic_year(options["year"]) if options["year"] else current_academic_year(organization)
            if not year:
                raise CommandError("patok_links_bad_year")
            with transaction.atomic():
                try:
                    counts, ambiguous = link_patok_leads(organization=organization, year=year, actor=actor, pairs=pairs)
                except WorkloadDenied as exc:
                    raise CommandError("patok_links_" + str(exc.code).removeprefix("workload.")) from None
                if not options["apply"]:
                    transaction.set_rollback(True)
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(f"{PREFIX} mode={mode} year={year.replace('/', '-')}")
        keys = ("partners", "linked", "ambiguous", "no_lead", "pair_linked", "pair_unchanged")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={counts.get(key, 0)}" for key in keys))
        for row_id in ambiguous:
            self.stdout.write(f"{PREFIX} ambiguous_row={row_id}")
