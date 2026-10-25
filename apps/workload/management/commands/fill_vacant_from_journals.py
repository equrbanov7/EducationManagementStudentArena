"""``fill_vacant_from_journals`` — semestrin VAKANT saatını jurnalda dərsi keçən müəllimə yazır (sahib 2026-10-25).

Sahib: «payızda vakantda olanlar olmamalıdır — köhnə sistemdən dəqiqləşdirməyə çalış, datadan ki bunu kim
keçir. Boş olmasın.» Sübut və qərar qaydaları :mod:`apps.workload.services.vacant_fill`, yazı və geri qaytarma
:mod:`apps.workload.services.vacant_fill_apply`.

* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir, sonda geri alınır (bildiriş getmir); hesabat yazılır.
* ``--apply`` — rəsmi düzəliş axını (səbəb + paket id-li qeyd + bölgü snapshot-u), paylanmış sənəd yenidən
  təsdiqlənir: «Dərs yükü təyin edildi» yalnız yükü dəyişən müəllimə, bir dəfə (``--no-notify`` — heç kimə).
* ``--undo <paket>`` — paketin yazdıqlarını «Vakant»a qaytarır (``--apply`` ilə yazır).
* İdempotent: ikinci ``--apply`` → ``pairs_filled=0``.
* Stdout-a YALNIZ saylar; adlı hesabat ``--report`` faylına (0600).

    manage.py fill_vacant_from_journals --org qku --year 2026/2027 --season fall --actor <superadmin> \\
        --legacy-journals legacy_journals.json --report ~/EMSArena-backups/…/vacant_fill_dryrun.md \\
        [--apply] [--no-notify] [--undo vacantfill-…]
"""

from __future__ import annotations

import os
import secrets
from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.organizations.models import Organization
from apps.workload.constants import Season
from apps.workload.services.scoping import resolve_actor
from apps.workload.services.tasks import normalize_academic_year
from apps.workload.services.vacant_fill import DECISIONS, LegacyFileError, collect, load_legacy, summary_by_chair
from apps.workload.services.vacant_fill_apply import VacantFiller, undo_batch
from apps.workload.services.vacant_fill_report import build_report
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

SHOWN = (
    "legacy_journals_loaded",
    "vacant_rows_before",
    "vacant_hours_before",
    "vacant_pairs",
    *(f"pairs_{decision}" for decision in DECISIONS),
    "pairs_fill_legacy",
    "pairs_fill_lessons",
    "pairs_filled",
    "hours_filled",
    "pairs_filled_outside_chair",
    "pairs_blocked",
    "pairs_changed_meanwhile",
    "memberships_added",
    "tasks_reconfirmed",
    "tasks_left_amended",
    "vacant_rows_after",
    "vacant_hours_after",
)


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "Semestrin vakant saatını jurnalda dərsi keçən müəllimə yazır (sübutla) — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--year", required=True, help="Tədris ili (YYYY/YYYY)")
        parser.add_argument("--season", default=Season.FALL, choices=list(Season.values), help="Fəsil (defolt: fall)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--report", default="", help="Adlı Markdown hesabatın yolu (0600)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--no-notify", action="store_true", help="Yenidən təsdiqdə bildiriş göndərmə")
        parser.add_argument("--undo", default="", help="Bu paketin yazdıqlarını vakanta qaytar (vacantfill-…)")
        parser.add_argument(
            "--legacy-journals",
            default="",
            help="Köhnə sistemin jurnal sübutu (legacy_journal_teachers_extract çıxışı, JSON)",
        )

    def handle(self, *args, **options):
        organization = Organization.objects.filter(slug=options["org"]).first()
        if organization is None:
            raise CommandError(f"organization_not_found: {options['org']}")
        user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if user is None or not user.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        year = normalize_academic_year(options["year"])
        if not year:
            raise CommandError("bad_year")
        mode = "apply" if options["apply"] else "dry_run"
        try:
            legacy = load_legacy(options["legacy_journals"])
        except LegacyFileError as exc:
            raise CommandError(str(exc)) from None
        # Dry-run-da bildiriş HEÇ VAXT getmir (tranzaksiya geri alınır, amma xarici kanal ola bilər).
        notify = bool(options["apply"]) and not options["no_notify"]
        counts: Counter = Counter()
        report = ""
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                actor = resolve_actor(user, organization)
                if options["undo"]:
                    counts = undo_batch(organization=organization, batch=options["undo"], actor=actor, notify=notify)
                else:
                    counts, report = self._fill(organization, year, options["season"], actor, mode, notify, legacy)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        if report and options["report"]:
            _write_private(options["report"], report)
        keys = sorted(counts) if options["undo"] else SHOWN
        self.stdout.write(f"vacantfill: mode={mode} " + " ".join(f"{key}={counts.get(key, 0)}" for key in keys))

    def _fill(self, organization, year, season, actor, mode, notify, legacy):
        batch = f"vacantfill-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        items = collect(organization, year, season, legacy)
        before = summary_by_chair(items)
        filler = VacantFiller(organization=organization, actor=actor, batch=batch, notify=notify)
        filler.run(items)
        after = summary_by_chair(collect(organization, year, season, legacy))
        counts = Counter(filler.counts)
        counts["vacant_pairs"] = len(items)
        for item in items:
            counts[f"pairs_{item.decision}"] += 1
            if item.decision == "fill":
                counts["pairs_fill_legacy" if item.source == "legacy_journal" else "pairs_fill_lessons"] += 1
        counts["legacy_journals_loaded"] = sum(len(value) for value in legacy.values())
        counts["vacant_rows_before"] = sum(value["rows"] for value in before.values())
        counts["vacant_hours_before"] = sum(value["hours"] for value in before.values())
        counts["vacant_rows_after"] = sum(value["rows"] for value in after.values())
        counts["vacant_hours_after"] = sum(value["hours"] for value in after.values())
        if mode == "apply" and counts["pairs_filled"]:
            self.stdout.write(f"vacantfill: batch={batch}")
        report = build_report(
            mode=mode, batch=batch, year=year, season=season, before=before, after=after, items=items, counts=counts
        )
        return counts, report


def _write_private(path: str, text: str) -> None:
    path = os.path.expanduser(path)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o600)
