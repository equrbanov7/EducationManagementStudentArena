"""``merge_duplicate_teacher`` — müəllimin ikinci (dublikat) hesabını əsas hesaba birləşdirir (sahib 2026-11-08).

Hal: Fatma — əsas hesab 8170 (dərs yükündə, aktiv), dublikat 7794 (bloklanıb, amma köhnə sistemdən köçən çox
jurnalın müəllimi; bəzi jurnallarda hər iki hesab var). Birləşmədən sonra hər şey əsas hesabdadır, müəllimin
yazdığı heç nə silinmir və gizlənmir. Qaydalar :mod:`apps.accounts.services.teacher_merge` (siyasət cədvəli,
qapılar, paylar, geri qaytarma).

* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir, sonda geri alınır (saylar dəqiqdir).
* ``--apply`` — yazır; paket ``tmerge-YYYYMMDD-HHMMSS-xxxx`` (stdout-da ``batch=``), manifest audit sətrindədir.
* ``--undo <paket> --apply`` — paketi geri qaytarır. İdempotent: ikinci ``--apply`` → ``merged=0``.
* Stdout-a YALNIZ saylar: ``teacher_merge: açar=dəyər …`` (ad / FİN / istifadəçi adı yoxdur).

    manage.py merge_duplicate_teacher --org qku --actor <superadmin> --source 7794 --target 8170 [--apply]
    manage.py merge_duplicate_teacher --org qku --actor <superadmin> --undo tmerge-… --apply
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services.teacher_merge import apply as merge_apply
from apps.accounts.services.teacher_merge import guards
from apps.accounts.services.teacher_merge import undo as merge_undo
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

BATCH_RE = re.compile(r"^tmerge-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")
PREFIX = "teacher_merge:"


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "Müəllim dublikatı hesabını əsas hesaba birləşdirir — dry-run defolt, --undo geri qaytarır."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--source", type=int, default=0, help="Dublikat (bağlanacaq) hesabın id-si")
        parser.add_argument("--target", type=int, default=0, help="Əsas (saxlanılan) hesabın id-si")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", default="", help="Bu paketi geri qaytar (tmerge-…)")

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
        if not undo and (options["source"] <= 0 or options["target"] <= 0):
            raise CommandError("source_and_target_required")
        mode = "apply" if options["apply"] else "dry_run"
        batch = merge_apply.new_batch()
        counts = {}
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk, bypass=True)
                if undo:
                    counts = merge_undo.undo(organization, undo, actor=actor)
                else:
                    counts = merge_apply.execute(
                        organization, options["source"], options["target"], actor=actor, batch=batch
                    )
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        except guards.MergeError as exc:
            raise CommandError(str(exc)) from None
        if undo:
            keys = sorted(counts)
        else:
            detail = sorted(key for key in counts if key not in merge_apply.SHOWN)
            keys = [*merge_apply.SHOWN, *detail]
        self.stdout.write(f"{PREFIX} mode={mode} " + " ".join(f"{key}={counts.get(key, 0)}" for key in keys))
        if mode == "apply" and not undo and counts.get("merged"):
            self.stdout.write(f"{PREFIX} batch={batch}")
