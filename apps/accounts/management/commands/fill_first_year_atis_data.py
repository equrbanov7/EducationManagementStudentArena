"""``fill_first_year_atis_data`` — ATİS datası olmayan 1-ci kurs hesablarının BOŞ sahələrini ATİS ixracından doldurur.

Sahib 2026-10-27: köhnə sistem deltasının yaratdığı 2026 qəbulu hesablarında FİN, doğum tarixi, telefon, real
e-poçt, vəsiqə, qəbul sahələri, ATİS id-si və tədris dili yoxdur. ``import_students_atis``-i təkrar işlətmək OLMAZ
(tanınan FİN-ləri ötürür, qalanlara ikinci hesab yaradır). Bu əmr hesab YARATMIR, qrupa toxunmur:

* tutuşdurma — əvvəl FİN, FİN-siz hesab üçün soyad + ad + ata adının DƏQİQ açarı (proqram / qrup ziddiyyətsiz);
  qeyri-müəyyən hal ötürülür və sayılır (qayda: :mod:`apps.accounts.services.first_year_data.atis_fill`);
* doldurma — yalnız BOŞ sahə; e-poçt yalnız placeholder-dirsə;
* heç bir hesaba düşməyən ATİS sətirləri yalnız SAYILIR (təhsil forması və ixtisas şifri üzrə).

* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir, sonda geri alınır (saylar dəqiqdir).
* ``--apply`` — yazır; paket ``atisfill-YYYYMMDD-HHMMSS-xxxx``, id → doldurulan sahə ADLARI BİR audit sətrindədir.
* İdempotent: ikinci ``--apply`` → ``students_filled=0``.
* Stdout-a YALNIZ saylar: ``atis_fill: açar=dəyər …``.

    manage.py fill_first_year_atis_data --org qku --actor <superadmin> --file bakalavr.xlsx [--apply]
"""

from __future__ import annotations

import re
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services.first_year_data import atis_fill
from apps.accounts.services.first_year_data.atis_rows import AtisFileError, load_rows
from apps.accounts.services.first_year_data.scope import first_year_records, new_batch
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

_KEY_SAFE = re.compile(r"[^a-z0-9_]+")


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


def _key(value: str) -> str:
    return _KEY_SAFE.sub("_", str(value).lower()).strip("_") or "unknown"


class Command(BaseCommand):
    help = "1-ci kurs: ATİS datası olmayan hesabların BOŞ sahələrini ATİS ixracından doldurur — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", required=True, help="ATİS «Bakalavr» ixracı (.xlsx)")
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
            rows = load_rows(options["file"])
        except AtisFileError as exc:
            raise CommandError(str(exc)) from None
        mode = "apply" if options["apply"] else "dry_run"
        batch = new_batch("atisfill")
        counts: Counter = Counter()
        filler = None
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk, bypass=True)
                records = first_year_records(organization, options["admission_year"], counts)
                filler = atis_fill.AtisFiller(organization, records, rows, counts)
                filler.match()
                filler.write(actor=actor, batch=batch)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        skips = sorted(key for key in counts if key.startswith("skip_"))
        fields = sorted(key for key in counts if key.startswith("field_"))
        self.stdout.write(
            f"atis_fill: mode={mode} " + " ".join(f"{key}={counts.get(key, 0)}" for key in (*atis_fill.SHOWN, *skips))
        )
        if fields:
            self.stdout.write("atis_fill: " + " ".join(f"{key}={counts[key]}" for key in fields))
        if filler is not None and filler.missing_by_form:
            missing = {f"missing_form_{_key(k)}": v for k, v in filler.missing_by_form.items()}
            missing.update({f"missing_program_{_key(k)}": v for k, v in filler.missing_by_program.items()})
            self.stdout.write("atis_fill: " + " ".join(f"{key}={missing[key]}" for key in sorted(missing)))
        if mode == "apply" and counts.get("students_filled"):
            self.stdout.write(f"atis_fill: batch={batch}")
