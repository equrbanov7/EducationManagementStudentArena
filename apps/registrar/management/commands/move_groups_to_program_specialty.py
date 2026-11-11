"""``move_groups_to_program_specialty`` — qrup tələbələrinin proqram ixtisasının altına (sahib 2026-11-12; defolt dry-run).

Qaydalar: :mod:`apps.registrar.group_specialty_move_2026_11_12`. ``--group <ad>`` yalnız bir qrup (dəqiq ad, böyük-kiçik
hərf fərqsiz). ``--apply`` yazır və ``batch`` id-si (``groupmove-…``) çap edir; ``--undo --batch <id>`` yalnız HƏLƏ
hədəfdə olan qrupları geri qaytarır (``--apply`` olmadan — önizləmə). Bütün DB işi ``rls_worker_atomic()`` +
``bypass_rls()`` + RLS konteksti içindədir; dry-run tranzaksiyası geri qaytarılır. Stdout-a YALNIZ
``group_move: açar=dəyər …`` sətirləri (adlar ascii-qatlanmış); gözlənilməz xəta ``CommandError: group_move_failed_…``.
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ... import group_specialty_move_2026_11_12 as move
from .relocate_twin_enrollment import superadmin


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"group_move_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "Sahib 2026-11-12: qrupu tələbələrinin proqram ixtisasının altına köçür (müraciət marşrutu); defolt dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--group", default="", help="Yalnız bu qrup (dəqiq ad, böyük-kiçik hərf fərqsiz)")
        parser.add_argument("--batch", default="", help="Qaçış id-si (groupmove-…); --undo üçün məcburi")
        parser.add_argument("--undo", action="store_true", help="--batch qaçışını geri qaytar")

    def handle(self, *args, **options):
        batch = str(options["batch"] or "").strip()
        if batch and not move.BATCH_RE.match(batch):
            raise CommandError("group_move_batch_invalid")
        if options["undo"] and not batch:
            raise CommandError("group_move_undo_needs_batch")
        if batch and not options["undo"]:
            raise CommandError("group_move_batch_needs_undo")
        try:
            counts = self._run(options, batch)
        except CommandError:
            raise
        except LookupError as exc:
            raise CommandError(str(exc)) from None
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        mode = ("undo_" if options["undo"] else "") + ("apply" if options["apply"] else "dry_run")
        tail = " ".join(f"{key}={counts[key]}" for key in sorted(counts) if key != "batch")
        self.stdout.write(f"{move.PREFIX} mode={mode} {tail} batch={counts.get('batch', '')}")

    def _run(self, options, batch):
        actor = superadmin(options["actor"])
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("group_move_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                if options["undo"]:
                    counts = move.undo(
                        self, organization=organization, actor=actor, apply=options["apply"], batch=batch
                    )
                else:
                    counts = move.run(
                        self,
                        organization=organization,
                        actor=actor,
                        apply=options["apply"],
                        group_name=str(options["group"] or ""),
                    )
                if not options["apply"]:
                    transaction.set_rollback(True)
        return counts
