"""``apply_journal_shares`` — köhnə sistemin jurnal bölgüsünü bölünmüş jurnal paylarına yazır (sahib 2026-10-26).

Sahib: «Fənn 2 müəllim arasında bölünübsə mühazirəçi mühazirəni, seminarçı yalnız öz ballarını görsün»; səviyyə
jurnalında «müəllim yalnız öz tələbələrini görsün … müəllimin jurnalı itməsin — köhnə sistemin jurnal datasından
götür». Qaydalar :mod:`apps.registrar.journal_share_import`, əhatə :mod:`apps.registrar.journal_shares`.

* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir, sonda geri alınır (saylar dəqiqdir).
* ``--apply`` — yazır; paket ``shares-YYYYMMDD-HHMMSS-xxxx`` (stdout-da ``batch=``).
* ``--undo <paket>`` — paketin paylarını söndürür (qeydiyyat çıxarışları «Jurnal təmizliyi» tarixçəsindən qayıdır).
* İdempotent: ikinci ``--apply`` → ``shares_created=0``.
* Stdout-a YALNIZ saylar: ``journal_shares: açar=dəyər …``.

    manage.py apply_journal_shares --org qku --actor <superadmin> --file shares.json [--apply]
    manage.py apply_journal_shares --org qku --actor <superadmin> --undo shares-… --apply
"""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from apps.registrar.journal_share_import import SHOWN, ShareFileError, apply_shares, load, new_batch, undo_batch
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

BATCH_RE = re.compile(r"^shares-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "Köhnə sistemin jurnal bölgüsünü bölünmüş jurnal paylarına yazır — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", default="", help="journal-shares/1 JSON faylı")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", default="", help="Bu paketin paylarını söndür (shares-…)")

    def handle(self, *args, **options):
        organization = Organization.objects.filter(slug=options["org"]).first()
        if organization is None:
            raise CommandError("organization_not_found")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if actor is None or not actor.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        undo = (options["undo"] or "").strip()
        if undo and not BATCH_RE.match(undo):
            raise CommandError("bad_batch")
        data = None
        if not undo:
            if not options["file"]:
                raise CommandError("file_required")
            try:
                data = load(options["file"])
            except ShareFileError as exc:
                raise CommandError(str(exc)) from None
        mode = "apply" if options["apply"] else "dry_run"
        batch = new_batch()
        counts = {}
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                if undo:
                    counts = undo_batch(organization, undo)
                else:
                    counts = apply_shares(organization, data, actor=actor, batch=batch)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        except ShareFileError as exc:
            raise CommandError(str(exc)) from None
        keys = sorted(counts) if undo else SHOWN
        self.stdout.write(f"journal_shares: mode={mode} " + " ".join(f"{key}={counts.get(key, 0)}" for key in keys))
        if mode == "apply" and not undo and (counts.get("shares_created") or counts.get("shares_updated")):
            self.stdout.write(f"journal_shares: batch={batch}")
