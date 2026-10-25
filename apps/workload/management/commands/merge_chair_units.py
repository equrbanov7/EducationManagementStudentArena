"""``merge_chair_units`` — kafedranı başqa kafedraya qovuşdurur (sahib 2026-10-25; dry-run DEFOLT).

Sahib: «Xarici dillər kafedrası olub, ora rəsmi olaraq elə dəyişib — ona birləşdir.» Defolt cüt
:data:`MERGES`-dədir (vahid ADLARI — şəxs yox); başqa cüt üçün ``--source`` + ``--target``.

Bir tranzaksiyada (dry-run = eyni yol + geri qaytarma, saylar dəqiqdir):

1. ``workload.services.chair_merge.merge_chair_load`` — ``--year`` və sonrakı illərin dərs yükü (sətirlər
   bölgüləri ilə; eyni sətir birləşir, saat ikiqat olmur), fənn kataloqu, cari sillabuslar;
2. ``organizations.chair_merge.merge_chair_unit`` — aktiv üzvlüklər (əsas üzvlük əsas qalır, müdir rolu),
   alt vahidlər, hədəfə köhnə ad (``aliases`` — axtarış/siyahı idxalı), mənbə ARXİVLƏNİR (``merged_into``
   tarixçəsi; heç nə silinmir).

Eyni sətrin hər iki kafedrada bölgüsü varsa (``duplicate_rows_conflict``) apply RƏDD edilir. Çıxış YALNIZ
saylardır. İdempotent: ikinci qaçış → ``already_merged=1``, köçürmə sayları 0.

    manage.py merge_chair_units --org qku --year 2026/2027 --actor <superadmin> [--apply]
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.organizations.models import Organization
from apps.organizations.public import merge_chair_unit, resolve_chair_merge_units
from apps.workload.services.chair_merge import merge_chair_load
from apps.workload.services.tasks import normalize_academic_year
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

#: (mənbə, hədəf) — sahibin 2026-10-25 qərarı.
MERGES = (("İngilis dili mərkəzi (Kafedra)", "Xarici dillər kafedrası"),)

SHOWN = (
    "source_found",
    "already_merged",
    "tasks_rechaired",
    "rows_moved",
    "assignments_moved",
    "hours_moved",
    "duplicate_rows_merged",
    "duplicate_rows_conflict",
    "tasks_closed",
    "tasks_history_kept",
    "subjects_moved",
    "plan_rows_moved",
    "syllabi_moved",
    "syllabi_history_kept",
    "memberships_moved",
    "memberships_deduplicated",
    "memberships_reactivated",
    "memberships_inactive_kept",
    "head_moved",
    "head_conflict",
    "children_moved",
    "target_aliases_added",
    "source_archived",
)


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "Kafedra qovuşması: cari dərs yükü, üzvlüklər, kataloq, sillabus → hədəf; mənbə arxivlənir (dry-run defolt)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--year", required=True, help="Cari tədris ili (YYYY/YYYY) — əvvəlki illər tarixdir")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--source", default="", help="Mənbə kafedranın adı (defolt: MERGES)")
        parser.add_argument("--target", default="", help="Hədəf kafedranın adı (defolt: MERGES)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        if bool(options["source"]) != bool(options["target"]):
            raise CommandError("source_and_target_together")
        pairs = ((options["source"], options["target"]),) if options["source"] else MERGES
        self.counts = dict.fromkeys(SHOWN, 0)
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                for source_name, target_name in pairs:
                    self._merge(options, source_name, target_name)
                if self.counts["duplicate_rows_conflict"]:
                    raise _DryRunRollback()
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        mode = "apply" if options["apply"] and not self.counts["duplicate_rows_conflict"] else "dry_run"
        self.stdout.write(f"chair_merge: mode={mode} " + " ".join(f"{key}={self.counts[key]}" for key in SHOWN))
        if options["apply"] and self.counts["duplicate_rows_conflict"]:
            raise CommandError("duplicate_rows_conflict")

    def _merge(self, options, source_name, target_name) -> None:
        organization = Organization.objects.filter(slug=options["org"]).first()
        if organization is None:
            raise CommandError("organization_not_found")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if actor is None or not actor.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        year = normalize_academic_year(options["year"])
        if not year:
            raise CommandError("bad_year")
        try:
            source, target, already = resolve_chair_merge_units(organization, source_name, target_name)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if target is None:
            raise CommandError("target_not_found")
        if source is None:
            raise CommandError("source_not_found")
        self.counts["source_found"] += 1
        today = timezone.localdate().isoformat()
        reason = f"merge_chair_units: «{source.name}» → «{target.name}» (sahibin {today} qərarı, rəsmi ad dəyişikliyi)"
        note = f"Birləşdi → {target.name} ({today})."
        for key, value in merge_chair_load(
            organization, source, target, year=year, actor=actor, reason=reason, note=note
        ).items():
            self.counts[key] = self.counts.get(key, 0) + value
        for key, value in merge_chair_unit(
            organization, source, target, actor=actor, date=today, reason=reason
        ).items():
            self.counts[key] = self.counts.get(key, 0) + value
        if already:
            self.counts["already_merged"] = max(self.counts["already_merged"], 1)
