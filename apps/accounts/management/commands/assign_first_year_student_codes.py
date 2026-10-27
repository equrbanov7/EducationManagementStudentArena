"""``assign_first_year_student_codes`` — «Tələbə kodu» olmayan 1-ci kurs tələbələrinə kod (sahib 2026-10-27).

Sahibin qərarı («qalanını tövsiyə olunan kimi et, qrup nömrəsi»): ATİS idxalı (2026-09-19) tələbələrinin kodu yoxdur.

1. Köhnə sistemdə FİN ilə tapılan, heç bir hesabda istifadə olunmamış legacy tələbə id-si kod olur
   (legacy delta paketi — ``--legacy-bundle``, ``legacy_delta_extract`` çıxışı, ``.json`` və ya ``.json.gz``);
2. qalanlara QRUP NÖMRƏSİNDƏN kod: ``<N><GG><SS>`` — ``N`` qrup adındakı ədəd («236 İT» → 236), ``GG`` eyni
   ``N``-li qruplar arasında qrupun sıra nömrəsi (01–99), ``SS`` qrup daxilində tələbənin sıra nömrəsi (01–99,
   soyad + ad sırası). Məs. «236 İT» qrupunun ``GG=07``-dirsə: 2360701, 2360702 … Tam qayda:
   :mod:`apps.accounts.services.first_year_data.codes`.

* FILL-ONLY: kodu olan hesaba toxunulmur; qrup / status / istifadəçi adı dəyişmir.
* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir, sonda geri alınır (saylar dəqiqdir).
* ``--apply`` — yazır; paket ``stcodes-YYYYMMDD-HHMMSS-xxxx``, id → kod siyahısı BİR audit sətrindədir.
* İdempotent: ikinci ``--apply`` → ``targets=0``.
* Stdout-a YALNIZ saylar və 3 nümunə kod: ``student_codes: açar=dəyər …``.

    manage.py assign_first_year_student_codes --org qku --actor <superadmin> --legacy-bundle delta.json.gz [--apply]
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services.first_year_data import codes as code_service
from apps.accounts.services.first_year_data.scope import first_year_records, new_batch
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "1-ci kurs tələbələrinə «Tələbə kodu»: legacy id (FİN ilə), yoxdursa qrup nömrəsi — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--legacy-bundle", required=True, help="Legacy delta paketi (.json / .json.gz)")
        parser.add_argument("--admission-year", type=int, default=2026, help="Qəbul ili (defolt 2026)")
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
        try:
            legacy = code_service.LegacyIndex.load(options["legacy_bundle"])
        except code_service.CodesError as exc:
            raise CommandError(str(exc)) from None
        mode = "apply" if options["apply"] else "dry_run"
        batch = new_batch("stcodes")
        counts: Counter = Counter()
        examples: list = []
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk, bypass=True)
                records = first_year_records(organization, options["admission_year"], counts)
                planner = code_service.CodePlanner(organization, records, legacy, counts)
                planned = planner.plan()
                examples = planner.examples
                code_service.write_codes(organization, planned, actor=actor, batch=batch, counts=counts)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        skips = sorted(key for key in counts if key.startswith("skip_"))
        line = " ".join(f"{key}={counts.get(key, 0)}" for key in (*code_service.SHOWN, *skips))
        self.stdout.write(f"student_codes: mode={mode} {line}")
        self.stdout.write(f"student_codes: examples={','.join(examples) or '-'}")
        if mode == "apply" and counts.get("written"):
            self.stdout.write(f"student_codes: batch={batch}")
