"""``merge_level_journals`` — köhnə sistemin qruplara bölünmüş səviyyə jurnalının tələbələrini müəllimin ev jurnalına
qonaq kimi yığır (sahib 2026-10-27). Qaydalar: :mod:`apps.registrar.level_merge`, geri qaytarma:
:mod:`apps.registrar.level_merge_undo`.

* Plan (``level-merge/1``, YALNIZ id-lər) lokal qurulur: ``build_journal_share_plans`` → ``levelmerge.json``.
* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir, sonda geri alınır (saylar dəqiqdir).
* ``--apply`` — yazır; paket ``lvlmerge-YYYYMMDD-HHMMSS-xxxx`` (stdout-da ``batch=``).
* ``--undo <paket> --apply`` — paketi audit manifestinə görə geri qaytarır.
* Stdout-a YALNIZ saylar: ``level_merge: açar=dəyər …``.

    manage.py merge_level_journals --org qku --actor <superadmin> --file levelmerge.json [--apply]
    manage.py merge_level_journals --org qku --actor <superadmin> --undo lvlmerge-… --apply
"""

from __future__ import annotations

import json
import re
from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...level_merge import FORMAT, LevelMergeError, Merger, new_batch
from ...level_merge_undo import undo_batch

PREFIX = "level_merge:"
BATCH_RE = re.compile(r"^lvlmerge-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise CommandError("level_merge_file_unreadable") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("journals"), list):
        raise CommandError("level_merge_format_unknown")
    return data


class Command(BaseCommand):
    help = "Bölünmüş səviyyə jurnalının tələbələrini ev jurnalına qonaq kimi yığır (plan faylı; defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", default="", help="level-merge/1 JSON faylı")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", default="", help="Bu paketi geri qaytar (lvlmerge-…)")

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        undo = (options["undo"] or "").strip()
        if undo and not BATCH_RE.match(undo):
            raise CommandError("bad_batch")
        if not undo and not options["file"]:
            raise CommandError("file_required")
        plan = None if undo else _load(options["file"])
        mode = "apply" if options["apply"] else "dry_run"
        batch = new_batch()
        counts: Counter = Counter()
        try:
            with rls_worker_atomic(), bypass_rls():
                organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
                if organization is None:
                    raise CommandError("organization_not_found")
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
                with transaction.atomic():
                    if undo:
                        counts = undo_batch(organization, undo, actor=actor)
                    else:
                        Merger(organization=organization, actor=actor, batch=batch, counts=counts).run(plan)
                    if not options["apply"]:
                        raise _DryRunRollback()
        except _DryRunRollback:
            pass
        except LevelMergeError as exc:
            raise CommandError(str(exc)) from None
        counts.setdefault("journals_in_file" if not undo else "journals_in_batch", 0)
        self.stdout.write(f"{PREFIX} mode={mode}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
        if mode == "apply" and not undo and counts.get("journals_merged"):
            self.stdout.write(f"{PREFIX} batch={batch}")
