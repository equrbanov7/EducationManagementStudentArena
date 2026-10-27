"""``relocate_twin_enrollment`` — «əkiz jurnal» xanalarını tələbənin düzgün açılışına köçür (RİM 2026-10-27, MR-11/15).

Qaydalar: :mod:`apps.registrar.twin_relocate`. Plan faylı (``twin-relocate/1``, YALNIZ id-lər) lokal qurulur:
``python manage.py build_twin_repair_plans`` (köhnə sistemin MariaDB-si + prod nüsxəsi). DEFOLT DRY-RUN (eyni kod,
geri qaytarılır). Stdout-a YALNIZ saylar (``twin_relocate: açar=say …``).
"""

from __future__ import annotations

import json
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...twin_relocate import FORMAT, Relocator

PREFIX = "twin_relocate:"


def load_plan(path: str, fmt: str, prefix: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise CommandError(f"{prefix}_file_unreadable") from None
    if not isinstance(data, dict) or data.get("format") != fmt:
        raise CommandError(f"{prefix}_format_unknown")
    return data


def superadmin(username: str):
    actor = get_user_model().objects.filter(username=username, is_active=True, is_superuser=True).first()
    if actor is None:
        raise CommandError("actor_must_be_active_superuser")
    return actor


def run_plan(command, *, options, prefix: str, runner) -> None:
    """Ortaq gövdə: təşkilat + RLS konteksti + tranzaksiya (dry-run geri qaytarılır) + saylar."""

    actor = superadmin(options["actor"])
    Organization = django_apps.get_model("organizations", "Organization")
    counts = Counter()
    label = prefix.rstrip(":")
    with rls_worker_atomic(), bypass_rls():
        organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
        if organization is None:
            raise CommandError(f"{label}_organization_unknown")
        apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
        with transaction.atomic():
            runner(organization, actor, counts)
            if not options["apply"]:
                transaction.set_rollback(True)
    command.stdout.write(f"{prefix} mode={'apply' if options['apply'] else 'dry_run'}")
    command.stdout.write(prefix + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))


def add_plan_arguments(parser, fmt: str) -> None:
    parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
    parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
    parser.add_argument("--file", required=True, help=f"{fmt} JSON faylı")
    parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")


class Command(BaseCommand):
    help = "Əkiz jurnalın xanalarını tələbənin düzgün açılışına köçürür (plan faylı ilə; defolt dry-run)."

    def add_arguments(self, parser):
        add_plan_arguments(parser, FORMAT)

    def handle(self, *args, **options):
        data = load_plan(options["file"], FORMAT, "twin_relocate")

        def runner(organization, actor, counts):
            Relocator(organization=organization, actor=actor, counts=counts).run(data.get("items") or [])

        run_plan(self, options=options, prefix=PREFIX, runner=runner)
