"""Exact source-evidenced IT235 sector repair."""

from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from core.rls import apply_rls_request_context

from ...it235_sector_repair import RepairError, run


class Command(BaseCommand):
    help = "235 İT üzrə iki mənbə-təsdiqli sektor keçidi (default dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--expected-baseline", default="")
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        # This exact dossier is WCU-scoped; never enable a tenant bypass.
        from django.apps import apps

        org_id = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
        try:
            user = get_user_model().objects.get(username=options["actor"], is_active=True, is_superuser=True)
            apply_rls_request_context(user_id=user.pk, org_id=org_id, bypass=False, local=True)
            org = apps.get_model("organizations.Organization").objects.get(pk=org_id)
            result = run(
                organization=org, user=user, apply=options["apply"], expected_baseline=options["expected_baseline"]
            )
        except RepairError as exc:
            raise CommandError(str(exc)) from exc
        except ObjectDoesNotExist as exc:
            model_name = type(exc).__qualname__.split(".")[0].lower()
            raise CommandError("it_sector_missing_" + model_name) from None
        except (MultipleObjectsReturned, ValidationError, DatabaseError) as exc:
            raise CommandError("it_sector_" + type(exc).__name__.lower()) from None
        mode = "apply" if options["apply"] else "dry_run"
        fields = [f"mode={mode}"]
        for key in ("baseline", "pending", "already_present", "applied"):
            if key in result:
                fields.append(f"{key}={result[key]}")
        self.stdout.write("it235_sector: " + " ".join(fields))
