"""MR-000250 / MR-000251: Gövhər Aydəmirovanın iki jurnalına öz köhnə sillabusu — defolt dry-run, auditli undo."""

import re

from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from apps.legacy_import.services import govher_syllabi_recovery as recovery
from apps.legacy_import.services.repair_support import RepairContext, establish_rls_scope, resolve_organization
from core.rls_pooling import rls_worker_atomic

PREFIX = "govher_syllabi"
UNDO_PATTERN = r"govsyl-\d{8}-\d{6}-[a-f0-9]{4}"


class Command(BaseCommand):
    help = (
        "MR-250 (234 EKO az: ingilis dilli səhv məzmun → müəllimin Azərbaycan dilli sillabusu) və MR-251 "
        "(235 QM: boş qaralama → müəllimin köhnə sillabusu) təsdiqli versiya kimi; köhnə versiyalar arxivdə qalır."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--file", default="")
        parser.add_argument("--sha256", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_superuser=True, is_active=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        org = resolve_organization(options["org"])
        batch = options["undo"]
        if batch and (not re.fullmatch(UNDO_PATTERN, batch) or options["file"] or options["sha256"]):
            raise CommandError("undo_arguments")
        try:
            loaded = None if batch else recovery.load(options["file"], options["sha256"])
            with transaction.atomic():
                establish_rls_scope(RepairContext(org, actor, options["apply"], 0))
                if batch:
                    counts = recovery.undo(org, actor, batch)
                else:
                    counts, batch = recovery.apply(org, actor, loaded)
                if not options["apply"]:
                    transaction.set_rollback(True)
        except recovery.RestoreError as exc:
            raise CommandError(str(exc)) from None
        except (ObjectDoesNotExist, MultipleObjectsReturned):
            raise CommandError("live_scope_conflict") from None
        except OSError:
            raise CommandError("plan_file_unavailable") from None
        except DatabaseError:
            raise CommandError("restore_database_conflict") from None
        mode = ("undo" if options["undo"] else "apply") if options["apply"] else "dry_run"
        self.stdout.write(f"{PREFIX}: mode={mode} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        if options["apply"] and not options["undo"] and counts.get("versions_created"):
            self.stdout.write(f"{PREFIX}: batch={batch}")
