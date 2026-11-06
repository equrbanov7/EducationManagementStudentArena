"""Sahib 2026-11-07: köhnə sillabuslar (repo planı, şəxsi bölmələrsiz) → jurnala bağlı TƏSDİQLİ versiya / plan saatı.

Defolt dry-run; ``--apply`` yazır, ``--undo lgsyl-…`` audit qəbzi üzrə geri qaytarır. Stdout-a YALNIZ
``legacy_syllabi: açar=say`` sətirləri, hər hədəf üçün ``entry=<açar> result=<kod>`` və yazılıbsa ``batch=``.
"""

import re

from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from apps.legacy_import.services import legacy_syllabi_20261107_plan as plan_module
from apps.legacy_import.services import legacy_syllabi_20261107_recovery as recovery
from apps.legacy_import.services.repair_support import RepairContext, establish_rls_scope, resolve_organization
from core.rls_pooling import rls_worker_atomic

PREFIX = "legacy_syllabi"
UNDO_PATTERN = r"lgsyl-\d{8}-\d{6}-[a-f0-9]{4}"


class Command(BaseCommand):
    help = (
        "Köhnə sillabuslar repo planından (şəxsi bölmələr çıxarılıb): jurnala bağlı təsdiqli versiya və ya plan "
        "saatının rəsmi yükə uyğunlaşdırılması; köhnə versiyalar arxivdə qalır, müəllimin işi toxunulmur."
    )

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
            plan = plan_module.load()
            with transaction.atomic():
                establish_rls_scope(RepairContext(org, actor, options["apply"], 0))
                if batch:
                    counts = recovery.undo(org, actor, batch, plan)
                else:
                    counts, results, batch = recovery.apply(org, actor, plan)
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
        for key, result in results:
            self.stdout.write(f"{PREFIX}: entry={key} result={result}")
        if options["apply"] and not options["undo"] and batch:
            self.stdout.write(f"{PREFIX}: batch={batch}")
