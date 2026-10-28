"""MR46 exact source syllabus restoration — dry-run default, no overwrite."""

import re

from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from apps.legacy_import.services import mr46_syllabus as restore
from apps.legacy_import.services.repair_support import RepairContext, establish_rls_scope, resolve_organization
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    output_prefix = "mr46_syllabus"
    recovery = restore
    undo_pattern = r"mr46-\d{8}-\d{6}-[a-f0-9]{4}"

    help = "MR46: legacy8891 sillabusunu yalnız müəllimin QKU1500 jurnalına bərpa et."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--file", default="")
        parser.add_argument("--sha256", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        restore = self.recovery
        actor = get_user_model().objects.filter(username=options["actor"], is_superuser=True, is_active=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        org = resolve_organization(options["org"])
        batch = options["undo"]
        if batch and (not re.fullmatch(self.undo_pattern, batch) or options["file"]):
            raise CommandError("undo_arguments")
        try:
            data = restore.load(options["file"], options["sha256"]) if not batch else None
            with transaction.atomic():
                establish_rls_scope(RepairContext(org, actor, options["apply"], 0))
                if batch:
                    counts = restore.undo(org, actor, batch)
                else:
                    counts, batch = restore.apply(org, actor, data)
                if not options["apply"]:
                    transaction.set_rollback(True)
        except restore.RestoreError as exc:
            raise CommandError(str(exc)) from None
        except (ObjectDoesNotExist, MultipleObjectsReturned):
            raise CommandError("live_scope_conflict") from None
        except OSError:
            raise CommandError("plan_file_unavailable") from None
        except DatabaseError:
            raise CommandError("restore_database_conflict") from None
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(
            f"{self.output_prefix}: mode={mode} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        )
        if options["apply"] and not options["undo"] and counts.get("syllabi_created"):
            self.stdout.write(f"{self.output_prefix}: batch={batch}")
