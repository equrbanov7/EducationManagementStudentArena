"""Fixed current syllabus audit repair; no writer runs during default dry-run."""

import json
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from apps.legacy_import.services import reaudit_syllabi
from apps.legacy_import.services.repair_support import RepairContext, establish_rls_scope, resolve_organization
from apps.syllabus.public import TransitionDenied
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Audit edilmiş cari sillabusları mənbə və plan əsasında bərpa/təsdiq et; default yalnız oxu."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--offering", action="append", default=[])
        parser.add_argument("--source-file", default="")
        parser.add_argument("--source-sha256", default="")
        parser.add_argument("--baseline", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", default="")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        try:
            actor = (
                get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
            )
            if actor is None:
                raise CommandError("active_operator_required")
            if options["undo"] and (not re.fullmatch(r"[a-f0-9-]{36}", options["undo"]) or options["source_file"]):
                raise CommandError("undo_arguments_invalid")
            org = resolve_organization(options["org"])
            establish_rls_scope(RepairContext(org, actor, options["apply"], 0))
            packet = reaudit_syllabi.source_packet(options["source_file"], options["source_sha256"])
            result = reaudit_syllabi.run(
                org,
                actor,
                packet=packet,
                offering_ids=options["offering"],
                apply=options["apply"],
                expected_baseline=options["baseline"],
                undo=options["undo"],
            )
        except reaudit_syllabi.RestoreError as error:
            raise CommandError(str(error)) from None
        except TransitionDenied as error:
            raise CommandError(error.code) from None
        except (ObjectDoesNotExist, DatabaseError):
            raise CommandError("reviewed_live_state_conflict") from None
        except OSError:
            raise CommandError("reviewed_private_packet_unavailable") from None
        self.stdout.write("audit_syllabi: " + json.dumps(result, sort_keys=True))
