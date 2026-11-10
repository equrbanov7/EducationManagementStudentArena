"""``subject_folder_auto_assign`` — mövcud qovluqları sahibin tədris etdiyi qruplara avtomatik təyin edir (sahib 2026-11-10).

Qayda: :mod:`apps.subject_folder.services.auto_assign`. Defolt DRY-RUN (tranzaksiya geri qaytarılır, yalnız saylar).
Təkrar qaçış idempotentdir (sətri olan açılışa toxunulmur). ``--undo --batch <id>`` partiyanın təyinatlarını passiv
edir (sətir qalır — avtomatik qayda onu yenidən açmır). Stdout-a YALNIZ saylar düşür (``sf_auto_assign: açar=say``)::

    python manage.py subject_folder_auto_assign --org qku                       # dry-run
    python manage.py subject_folder_auto_assign --org qku --apply               # yaz (batch id çap olunur)
    python manage.py subject_folder_auto_assign --org qku --apply --undo --batch sfauto-20261110-…
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "sf_auto_assign:"


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"sf_auto_assign_failed_{slug}"[:120]


class Command(BaseCommand):
    help = (
        "Fənn qovluqlarını sahibin həmin fənn + semestrdə tədris etdiyi qruplara avtomatik təyin edir (defolt dry-run)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", default="", help="Təşkilatın slug-ı (boş = hamısı)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--include-ended", action="store_true", help="Semestri bitmiş qovluqları da daxil et")
        parser.add_argument(
            "--no-notify", action="store_true", help="Tələbələrə «Yeni fənn qovluğu» bildirişi getməsin"
        )
        parser.add_argument("--batch", default="", help="Partiya id-si (--undo üçün məcburi)")
        parser.add_argument("--undo", action="store_true", help="--batch partiyasının təyinatlarını passiv et")

    def handle(self, *args, **options):
        try:
            summary = self._run(options)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(f"{PREFIX} mode={mode} undo={int(bool(options['undo']))} batch={summary['batch']}")
        counts = summary.get("counts") or {}
        self.stdout.write(
            PREFIX + " " + (" ".join(f"{key}={value}" for key, value in sorted(counts.items())) or "noop")
        )

    def _run(self, options) -> dict:
        from apps.subject_folder.services import auto_assign

        if options["undo"] and not options["batch"].strip():
            raise CommandError("sf_auto_assign_batch_required")
        with rls_worker_atomic(), bypass_rls():
            organization = None
            if options["org"].strip():
                Organization = django_apps.get_model("organizations", "Organization")
                organization = Organization.objects.filter(slug=options["org"].strip()).first()
                if organization is None:
                    raise CommandError("sf_auto_assign_organization_unknown")
            with transaction.atomic():
                if options["undo"]:
                    summary = auto_assign.undo(options["batch"].strip(), organization=organization)
                else:
                    folders = auto_assign.candidate_folders(
                        organization=organization, include_ended=options["include_ended"]
                    ).select_related("organization", "owner")
                    summary = auto_assign.auto_assign(
                        folders,
                        batch=options["batch"].strip() or auto_assign.new_batch_id(),
                        notify_students=not options["no_notify"] and options["apply"],
                    )
                if not options["apply"]:
                    transaction.set_rollback(True)
        return summary
