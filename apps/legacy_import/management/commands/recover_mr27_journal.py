"""MR27 source-backed bərpa; dry-run default, immutable ledger-i saxlayan compensating undo."""

import re

from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from apps.legacy_import.services.mr27_plan import RecoveryError, load
from apps.legacy_import.services.mr27_recovery import Recovery
from apps.legacy_import.services.mr27_undo import undo
from apps.legacy_import.services.repair_support import RepairContext, establish_rls_scope, resolve_organization


class Command(BaseCommand):
    help = "MR-000027: yalnız 2 source tələbəsi və 21 source xanasının boşluqları; default dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--file", default="")
        parser.add_argument("--sha256", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--include-teacher-assertion", action="store_true")
        parser.add_argument("--undo", default="")

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        org = resolve_organization(options["org"])
        batch = options["undo"]
        if batch and (not re.fullmatch(r"mr27-\d{8}-\d{6}-[a-f0-9]{4}", batch) or options["file"]):
            raise CommandError("undo_arguments")
        try:
            data = load(options["file"], options["sha256"]) if not batch else None
            with transaction.atomic():
                establish_rls_scope(RepairContext(org, actor, options["apply"], 0))
                if batch:
                    counts = undo(org, actor, batch)
                else:
                    plan, sha, size = data
                    counts, batch = Recovery(
                        org, actor, plan, sha, size, teacher_assertion=options["include_teacher_assertion"]
                    ).execute()
                if not options["apply"]:
                    transaction.set_rollback(True)
        except (ObjectDoesNotExist, MultipleObjectsReturned):
            raise CommandError("live_scope_conflict") from None
        except DatabaseError:
            raise CommandError("recovery_database_conflict") from None
        except (RecoveryError, OSError) as exc:
            raise CommandError(str(exc) if isinstance(exc, RecoveryError) else "plan_file_unavailable") from None
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(f"mr27_recovery: mode={mode} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        if (
            options["apply"]
            and not options["undo"]
            and any(v for k, v in counts.items() if k.startswith(("created_", "updated_")))
        ):
            self.stdout.write(f"mr27_recovery: batch={batch}")
