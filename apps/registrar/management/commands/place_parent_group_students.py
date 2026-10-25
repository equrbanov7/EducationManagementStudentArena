"""``place_parent_group_students`` — ana qrupda qalmış tələbəni jurnal sübutu ilə alt qrupa köçürür (sahib 2026-10-26).

Bax :mod:`apps.registrar.subgroup_member_placement`. DEFOLT DRY-RUN (eyni kod, tranzaksiya geri qaytarılır —
saylar dəqiqdir); ``--apply`` ilə yazır. ``--group`` (təkrarlana bilər) — yalnız həmin ana qrup(lar); verilməsə
bütün ana qruplar. Stdout-a YALNIZ saylar; ``--list`` (yalnız lokal) qrup adları ilə sətirlər çap edir.

İstifadə::

    manage.py place_parent_group_students --org qku --actor <superadmin> [--group "3/336 F"] [--apply] [--list]
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...dashboard_data import current_period
from ...subgroup_member_placement import run

PREFIX = "subgroup_placement:"
REASON = "Jurnal datasına görə alt qrupa yerləşdirmə (ana qrupda qalmış tələbə) — sahibin 2026-10-26 tapşırığı"


class Command(BaseCommand):
    help = "Ana qrupda qalmış tələbələri cari dövrün jurnal xanalarına görə alt qrupa köçürür."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--group", action="append", default=[], help="Ana qrupun adı (təkrarlana bilər)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--list", action="store_true", help="Sətirləri adlarla çap et (yalnız lokal)")

    def handle(self, *args, **options):
        organization = (
            django_apps.get_model("organizations", "Organization")
            .objects.filter(slug=str(options["org"]).strip())
            .first()
        )
        if organization is None:
            raise CommandError("subgroup_placement_organization_unknown")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        names = [name.strip() for name in options["group"] if name.strip()]
        with rls_worker_atomic(), bypass_rls():
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            period = current_period(organization)
            if period is None:
                raise CommandError("subgroup_placement_no_current_period")
            counts, items = run(
                organization, period, actor=actor, reason=REASON, names=names, apply=bool(options["apply"])
            )
            parents = len({item.parent_id for item in items})
            if options["list"]:
                lines = self._lines(items)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'} parents={parents}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
        if options["list"]:
            for line in lines:
                self.stdout.write(line)

    def _lines(self, items):
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        User = get_user_model()
        unit_ids = {item.parent_id for item in items} | {gid for item in items for gid in item.marks}
        names = dict(OrgUnit.objects.filter(pk__in=unit_ids).values_list("pk", "name"))
        people = {
            row[0]: f"{row[1]} {row[2]}".strip()
            for row in User.objects.filter(pk__in=[item.student_id for item in items]).values_list(
                "pk", "last_name", "first_name"
            )
        }
        out = []
        for item in sorted(items, key=lambda i: (names.get(i.parent_id, ""), i.status, people.get(i.student_id, ""))):
            marks = ", ".join(f"{names.get(gid, gid)}:{n}" for gid, n in sorted(item.marks.items(), key=str))
            out.append(
                f"{names.get(item.parent_id, '')} | {item.status} | {names.get(item.target_id, '') if item.target_id else '—'}"
                f" | {people.get(item.student_id, item.student_id)} | {marks}"
            )
        return out
