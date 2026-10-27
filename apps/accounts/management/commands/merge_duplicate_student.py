"""``merge_duplicate_student`` — köhnə sistem deltasının yaratdığı ikinci tələbə hesabını əsas hesaba birləşdirir.

RİM MR-000030.2 (2026-10-27): «real hesab (ATİS) + delta hesabı; i/e-lər ikinci hesabın sətrindədir». Qaydalar
:mod:`apps.accounts.services.student_merge` (plan qapıları + birləşdirmə). YALNIZ sahibin təsdiqlədiyi plan faylındakı
cütlər (``student-merge/1``: ``{"duplicate": id, "keep": id}``) — namizəd siyahısı lokal qurulur, avtomatik
birləşdirmə YOXDUR.

* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir, sonda geri alınır (saylar dəqiqdir).
* ``--apply`` — yazır; paket ``stmerge-YYYYMMDD-HHMMSS-xxxx`` (stdout-da ``batch=``), manifest audit sətrindədir.
* ``--undo <paket> --apply`` — paketi geri qaytarır. İdempotent: ikinci ``--apply`` → ``pairs_merged=0``.
* Stdout-a YALNIZ saylar: ``student_merge: açar=dəyər …``.

    manage.py merge_duplicate_student --org qku --actor <superadmin> --file plan.json [--apply]
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services.student_merge import apply as merge_apply
from apps.accounts.services.student_merge import plan as merge_plan
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

BATCH_RE = re.compile(r"^stmerge-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "Delta-nın yaratdığı tələbə dublikatını əsas hesaba birləşdirir (plan faylı) — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", default="", help="student-merge/1 plan faylı (sahibin təsdiqlədiyi cütlər)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", default="", help="Bu paketi geri qaytar (stmerge-…)")

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
        pairs = []
        if not undo:
            if not options["file"]:
                raise CommandError("file_required")
            try:
                pairs = merge_plan.load(options["file"])
            except merge_plan.MergePlanError as exc:
                raise CommandError(str(exc)) from None
        mode = "apply" if options["apply"] else "dry_run"
        batch = merge_apply.new_batch()
        counts = {}
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk, bypass=True)
                if undo:
                    counts = merge_apply.undo(organization, undo, actor=actor)
                else:
                    counts = merge_apply.execute(organization, pairs, actor=actor, batch=batch)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        except merge_plan.MergePlanError as exc:
            raise CommandError(str(exc)) from None
        skips = sorted(key for key in counts if key.startswith("skip_"))
        keys = sorted(counts) if undo else [*merge_apply.SHOWN, *skips]
        self.stdout.write(f"student_merge: mode={mode} " + " ".join(f"{key}={counts.get(key, 0)}" for key in keys))
        if mode == "apply" and not undo and counts.get("pairs_merged"):
            self.stdout.write(f"student_merge: batch={batch}")
