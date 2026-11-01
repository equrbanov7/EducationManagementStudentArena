"""Fixed AppliedMath source14316 continuity repair; fresh baseline required for mutations."""

from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from apps.legacy_import.services import applied_math_recovery as recovery
from apps.legacy_import.services.repair_support import RepairContext, establish_rls_scope, resolve_organization
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Mənbə14316 tətbiqi riyaziyyat jurnalını ID-lərini saxlayaraq öz6690 sillabusu ilə düzəlt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--file", required=True)
        parser.add_argument("--sha256", required=True)
        parser.add_argument("--baseline", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", action="store_true")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_superuser=True, is_active=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        org = resolve_organization(options["org"])
        try:
            loaded = recovery.load(options["file"], options["sha256"])
            with transaction.atomic():
                establish_rls_scope(RepairContext(org, actor, options["apply"], 0))
                counts = recovery.repair(
                    org,
                    actor,
                    loaded,
                    apply=options["apply"],
                    expected_baseline=options["baseline"],
                    undo=options["undo"],
                )
                if not options["apply"]:
                    transaction.set_rollback(True)
        except (recovery.RestoreError, recovery.domain.Error) as exc:
            raise CommandError(str(exc)) from None
        except (ObjectDoesNotExist, MultipleObjectsReturned):
            raise CommandError("live_scope_conflict") from None
        except OSError:
            raise CommandError("plan_file_unavailable") from None
        except DatabaseError:
            raise CommandError("repair_database_conflict") from None
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(
            "applied_math_journal: mode=" + mode + " " + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        )
