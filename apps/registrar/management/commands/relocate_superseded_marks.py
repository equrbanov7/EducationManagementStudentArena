"""``relocate_superseded_marks`` — köçürülmüş tələbənin fantom sütunlardakı xanalarını varis jurnala daşıyır (RİM 2026-10-27).

Qaydalar :mod:`apps.registrar.superseded_marks`-dadır (MR-000010, MR-000030.1). Hədəf xana doludursa HEÇ VAXT üzərinə
yazılmır (``conflict_kept``). Boşalan fantom sütun (köçürmə dərsi, düzəlişsiz) eyni paketdə silinir,
``--undo`` onu eyni id ilə bərpa edir.

* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir, sonda geri alınır (saylar dəqiqdir).
* ``--plan-out FAYL`` — (yalnız oxu) daşınacaq xanaların id planı (``superseded-marks/1``, 0600) — lokal qurulur.
* ``--file FAYL`` — yalnız plandakı xanalar; hər sətir canlı hesablama ilə yoxlanılır (fərq → ``plan_mismatch``).
* ``--apply`` — yazır; paket ``supmarks-YYYYMMDD-HHMMSS-xxxx`` (stdout-da ``batch=``), manifest audit sətrindədir.
* ``--undo <paket> --apply`` — daşınmış xanaları (və silinmiş fantom dərsi) geri qaytarır.
* İdempotent: ikinci ``--apply`` → ``moved=0``. Stdout-a YALNIZ saylar: ``superseded_marks: açar=dəyər …``.

    manage.py relocate_superseded_marks --org qku --actor <superadmin> [--file plan.json] [--apply]
"""

from __future__ import annotations

import json
import os
import re

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.registrar import superseded_marks as service
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

BATCH_RE = re.compile(r"^supmarks-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


def _write_private(path: str, payload: dict) -> None:
    fd = os.open(os.path.expanduser(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


class Command(BaseCommand):
    help = "Köçürülmüş tələbənin fantom sütunlardakı xanalarını varis jurnala daşıyır — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", default="", help="superseded-marks/1 plan faylı (yalnız id-lər)")
        parser.add_argument("--plan-out", default="", help="Planı bu fayla yaz (yalnız oxu, 0600)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", default="", help="Bu paketi geri qaytar (supmarks-…)")

    def handle(self, *args, **options):
        organization = (
            django_apps.get_model("organizations", "Organization").objects.filter(slug=options["org"]).first()
        )
        if organization is None:
            raise CommandError("organization_not_found")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if actor is None or not actor.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        undo = (options["undo"] or "").strip()
        if undo and not BATCH_RE.match(undo):
            raise CommandError("bad_batch")
        if undo and (options["file"] or options["plan_out"]):
            raise CommandError("undo_takes_no_file")
        plan, plan_period = None, ""
        if options["file"]:
            try:
                plan_period, plan = service.load_plan(options["file"])
            except service.PlanError as exc:
                raise CommandError(str(exc)) from None
        mode = "apply" if options["apply"] and not options["plan_out"] else "dry_run"
        batch = service.new_batch()
        counts = {}
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk, bypass=True)
                if undo:
                    counts = service.undo_batch(organization, undo)
                else:
                    period = self._period(organization)
                    if plan is not None and plan_period != str(period.pk):
                        raise CommandError("plan_period_mismatch")
                    if options["plan_out"]:
                        moves, counts = service.build_moves(organization, period)
                        rows = service.plan_rows(moves)
                        _write_private(
                            options["plan_out"], {"format": service.FORMAT, "period": str(period.pk), "moves": rows}
                        )
                        counts["plan_rows"] = len(rows)
                    else:
                        counts = service.apply_moves(
                            organization, period, actor=actor, batch=batch, plan=plan, write=True
                        )
                if mode != "apply":
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        except service.PlanError as exc:
            raise CommandError(str(exc)) from None
        keys = sorted(counts) if undo else service.SHOWN
        self.stdout.write(f"superseded_marks: mode={mode} " + " ".join(f"{key}={counts.get(key, 0)}" for key in keys))
        if mode == "apply" and not undo and (counts.get("moved") or counts.get("target_same")):
            self.stdout.write(f"superseded_marks: batch={batch}")

    @staticmethod
    def _period(organization):
        periods = list(
            django_apps.get_model("organizations", "AcademicPeriod").objects.filter(
                organization=organization, is_current=True
            )
        )
        if len(periods) != 1:
            raise CommandError("current_period_not_unique")
        return periods[0]
