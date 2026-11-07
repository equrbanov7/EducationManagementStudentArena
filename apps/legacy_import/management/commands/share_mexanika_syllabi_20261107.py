"""Sahib 2026-11-07 (Mexanika və riyaziyyat): sillabussuz jurnallar müəllimin ÖZ təsdiqli sillabusuna (sabit id-lər).

Qaydalar: :mod:`apps.legacy_import.services.mexanika_syllabi_20261107`. Defolt dry-run; ``--apply`` yazır,
``--undo mxsyl-…`` audit qəbzi üzrə qaytarır. Stdout-a YALNIZ ``mexanika_syllabi: açar=say`` sətirləri, hər hədəf
üçün ``entry=<açar> result=<kod>`` və yazılıbsa ``batch=``.
"""

import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from apps.legacy_import.services import mexanika_syllabi_20261107 as service
from apps.legacy_import.services.repair_support import RepairContext, establish_rls_scope, resolve_organization
from core.rls_pooling import rls_worker_atomic

PREFIX = "mexanika_syllabi"
UNDO_PATTERN = r"mxsyl-\d{8}-\d{6}-[a-f0-9]{4}"


class Command(BaseCommand):
    help = "Mexanika 2026-11-07: sillabussuz jurnalları müəllimin öz təsdiqli sillabusuna bağlayır (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_superuser=True, is_active=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        batch = options["undo"]
        if batch and not re.fullmatch(UNDO_PATTERN, batch):
            raise CommandError("undo_arguments")
        org = resolve_organization(options["org"])
        results = []
        try:
            with transaction.atomic():
                establish_rls_scope(RepairContext(org, actor, options["apply"], 0))
                if batch:
                    counts = service.undo(org, actor, batch)
                else:
                    counts, results, batch = service.apply(org, actor)
                if not options["apply"]:
                    transaction.set_rollback(True)
        except service.RestoreError as exc:
            raise CommandError(str(exc)) from None
        except DatabaseError:
            raise CommandError("share_database_conflict") from None
        mode = ("undo" if options["undo"] else "apply") if options["apply"] else "dry_run"
        self.stdout.write(f"{PREFIX}: mode={mode} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        for key, result in results:
            self.stdout.write(f"{PREFIX}: entry={key} result={result}")
        if options["apply"] and not options["undo"] and batch:
            self.stdout.write(f"{PREFIX}: batch={batch}")
