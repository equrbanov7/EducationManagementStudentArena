"""``merge_duplicate_staff`` — eyni müəllimin dublikat İŞÇİ hesabını əsas hesaba birləşdirir (sahib 2026-11-03).

Hal: köhnə sistemdəki ikinci işçi qeydindən gəlmiş dublikat hesab (bloklu) dərslərin müəllifi və sillabusların
sahibi olaraq qalıb — jurnal ``handover`` ilə əsas hesaba keçsə də kabinetdə «Adınıza keçirilmiş» 0 görünür
(``Lesson.instructor`` dublikatdır) və sillabuslar onun deyil. Köçən/köçməyən sahələrin inventarı və səbəbləri:
:mod:`apps.accounts.services.staff_merge.fields`; qapılar: :mod:`apps.accounts.services.staff_merge.plan`.

* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir və sonda geri alınır (saylar və DB trigger-ləri dəqiqdir).
* ``--apply`` — yazır; paket ``stfmerge-YYYYMMDD-HHMMSS-xxxx`` (stdout-da ``batch=``), hər qrup audit sətrindədir.
* Geri qaytarma əmri YOXDUR (bloklu hesaba dərs müəllimi yazmağı DB trigger-i qadağan edir) — apply-dan əvvəl
  workflow DB ehtiyat nüsxəsi alır, audit sətirlərində hər qrupun dəqiq id-ləri var.
* İdempotent: ikinci ``--apply`` → ``moved=0``.  Stdout-a YALNIZ saylar (şəxs adı yoxdur).

    manage.py merge_duplicate_staff --org qku --actor <superadmin> --source-user 8388 --target-user 7730 \\
        --reason "…" [--force-name-mismatch] [--apply]
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from apps.accounts.services.staff_merge import apply as merge_apply
from apps.accounts.services.staff_merge import plan as merge_plan
from apps.accounts.services.staff_merge.fields import MOVES
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "staff_merge"


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "Eyni müəllimin dublikat işçi hesabını əsas hesaba birləşdirir (yalnız id-lər) — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--source-user", type=int, default=None, help="Dublikat (bloklu / heç daxil olmamış) id")
        parser.add_argument("--target-user", type=int, default=None, help="Əsas (aktiv) hesabın id-si")
        parser.add_argument("--reason", default="", help="Səbəb (audit; ən azı 10 simvol)")
        parser.add_argument(
            "--force-name-mismatch",
            action="store_true",
            help="Ad/soyad/ata adı fərqlidir, amma sahib eyni şəxs olduğunu təsdiqləyib",
        )
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        organization = (
            django_apps.get_model("organizations", "Organization").objects.filter(slug=options["org"]).first()
        )
        if organization is None:
            raise CommandError("organization_not_found")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if actor is None or not actor.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        if options["source_user"] is None or options["target_user"] is None:
            raise CommandError("source_and_target_required")
        mode = "apply" if options["apply"] else "dry_run"
        batch = merge_apply.new_batch()
        counts, left = {}, {}
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk, bypass=True)
                source, target = merge_plan.check(
                    organization,
                    options["source_user"],
                    options["target_user"],
                    reason=options["reason"],
                    force_name_mismatch=options["force_name_mismatch"],
                )
                counts = merge_apply.execute(
                    organization, source, target, actor=actor, reason=options["reason"].strip(), batch=batch
                )
                left = merge_apply.remaining(organization, source)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        except merge_plan.StaffMergeError as exc:
            raise CommandError(str(exc)) from None
        except DatabaseError:
            # Açılış/dərs müəllimi trigger-i (aktiv üzv + grade.input) və s. — mətn şəxs məlumatı daşıya bilər.
            raise CommandError("db_guard_rejected") from None
        self._report(mode, counts, left, batch=batch)

    def _report(self, mode, counts, left, *, batch):
        keys = ["moved", "conflicts"]
        for move in MOVES:
            keys.append(f"{move.key}_moved")
            if counts.get(f"{move.key}_conflict"):
                keys.append(f"{move.key}_conflict")
        keys += ["source_blocked_now", "source_blocked"]
        self.stdout.write(f"{PREFIX}: mode={mode} " + " ".join(f"{key}={counts.get(key, 0)}" for key in keys))
        if left:
            self.stdout.write(f"{PREFIX}_left: " + " ".join(f"{key}={value}" for key, value in left.items()))
        if mode == "apply" and counts.get("moved"):
            self.stdout.write(f"{PREFIX}: batch={batch}")
