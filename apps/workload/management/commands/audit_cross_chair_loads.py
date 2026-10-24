"""``audit_cross_chair_loads`` — kafedralar arası dərs yükünün yoxlanışı (sahib 2026-10-25; dry-run DEFOLT).

Sahib: «Bəzi müəllim ştat olaraq bir kafedradadır, amma saat hesabı olaraq başqa kafedrada fənn götürüb —
onu da nizamla tənzimlə.» Model: müəllimin ŞTAT kafedrası (``people.home_chair_rank``) bir yerdir, yük sətri isə
FƏNNİN kafedrasının tapşırığındadır; müəllim orada ƏLAVƏ (``is_primary=False``) müəllim üzvlüyü ilə durur.

Əmr YALNIZ təhlükəsiz düzəlişi edir — ``--apply`` ilə: başqa kafedranın tapşırığında bölgüsü olan, amma həmin
kafedrada aktiv üzvlüyü olmayan müəllimə ``join_chair_as_teacher`` (2026-10-12 idxal qaydası; ştatı dəyişmir,
audit jurnalına yazılır). Qərar tələb edən hallar YALNIZ sayılır, dəyişdirilmir:

* ``duplicate_row_keys`` — eyni fənn + semestr + qrup iki kafedranın tapşırığındadır (saat iki dəfə sayılır);
* ``rows_subject_other_chair`` — sətrin fənni kataloqda başqa kafedranındır (``Subject.chair_unit``);
* ``home_from_extra_membership`` — ştat kafedrası yalnız əlavə üzvlükdən gəlir (əsas üzvlüyü kafedrasız rol:
  dekan müavini, tədris şöbəsi əməkdaşı …) — ştatın harada olduğunu sahib/HR təsdiqləməlidir.

Çıxış YALNIZ saylardır (ad yoxdur). İdempotent: ikinci ``--apply`` → ``membership_added=0``.

    manage.py audit_cross_chair_loads --org qku --year 2026/2027 --actor <superadmin> [--apply]
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services.people import home_chairs, is_assignable_teacher, join_chair_as_teacher
from apps.workload.services.tasks import normalize_academic_year
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

SHOWN = (
    "assignment_teachers",
    "cross_teachers",
    "cross_assignments",
    "cross_hours",
    "teachers_without_home_chair",
    "home_from_extra_membership",
    "missing_membership",
    "membership_added",
    "duplicate_row_keys",
    "rows_subject_other_chair",
)
REASON = "audit_cross_chair_loads: başqa kafedranın tapşırığında bölgüsü olan müəllim — kafedrada ƏLAVƏ üzvlük"


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "Kafedralar arası dərs yükü: saylar + çatışmayan kənar üzvlük (dry-run defolt)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--year", required=True, help="Tədris ili (YYYY/YYYY)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        self.counts = dict.fromkeys(SHOWN, 0)
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                self._run(options)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(f"cross_chair: mode={mode} " + " ".join(f"{key}={self.counts[key]}" for key in SHOWN))

    def _run(self, options) -> None:
        organization = Organization.objects.filter(slug=options["org"]).first()
        if organization is None:
            raise CommandError(f"organization_not_found: {options['org']}")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if actor is None or not actor.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        year = normalize_academic_year(options["year"])
        if not year:
            raise CommandError("bad_year")
        assignments = list(
            TeacherAssignment.objects.filter(
                organization=organization, row__task__academic_year=year, teacher__isnull=False
            )
            .select_related("teacher", "row__task__chair")
            .order_by("row__task__chair__name", "teacher_id")
        )
        teacher_ids = {item.teacher_id for item in assignments}
        homes = home_chairs(organization, teacher_ids)
        self.counts["assignment_teachers"] = len(teacher_ids)
        self.counts["teachers_without_home_chair"] = len(teacher_ids - set(homes))
        self.counts["home_from_extra_membership"] = self._home_from_extra(organization, homes)
        cross_teachers, pairs = set(), {}
        for item in assignments:
            chair = item.row.task.chair
            home = homes.get(item.teacher_id)
            if home is not None and home["id"] != str(chair.pk):
                cross_teachers.add(item.teacher_id)
                self.counts["cross_assignments"] += 1
                self.counts["cross_hours"] += int(item.hours or 0)
            pairs.setdefault((chair.pk, item.teacher_id), (chair, item.teacher))
        self.counts["cross_teachers"] = len(cross_teachers)
        for chair, teacher in pairs.values():
            if is_assignable_teacher(organization, chair, teacher):
                continue
            self.counts["missing_membership"] += 1
            if options["apply"] and join_chair_as_teacher(
                organization=organization, user=teacher, chair=chair, actor_user=actor, reason=REASON
            ):
                self.counts["membership_added"] += 1
        self._rows(organization, year)

    def _home_from_extra(self, organization, homes) -> int:
        """Ştat kafedrası əsas olmayan üzvlükdən gəlir, əsas üzvlük isə kafedrasız roldadır (qərar siyahısı)."""
        Membership = django_apps.get_model("organizations", "Membership")
        primary_elsewhere = set(
            Membership.objects.filter(
                organization=organization, user_id__in=list(homes), is_active=True, is_primary=True
            )
            .exclude(scope_unit__unit_type__in=("chair", "department"))
            .values_list("user_id", flat=True)
        )
        primary_in_chair = set(
            Membership.objects.filter(
                organization=organization,
                user_id__in=list(homes),
                is_active=True,
                is_primary=True,
                scope_unit__unit_type__in=("chair", "department"),
            ).values_list("user_id", flat=True)
        )
        return len(primary_elsewhere - primary_in_chair)

    def _rows(self, organization, year) -> None:
        """Qərar siyahısı: eyni fənn + semestr + qrup iki kafedrada; fənni kataloqda başqa kafedranın olan sətir."""
        keys = defaultdict(set)
        other_subject_rows = set()
        rows = (
            TeachingTaskRow.objects.filter(organization=organization, task__academic_year=year, subject__isnull=False)
            .values_list("pk", "task__chair_id", "subject_id", "period_id", "groups", "subject__chair_unit_id")
            .order_by()
        )
        for row_id, chair_id, subject_id, period_id, group_id, subject_chair_id in rows:
            if group_id is not None:
                keys[(subject_id, period_id, group_id)].add(chair_id)
            if subject_chair_id and subject_chair_id != chair_id:
                other_subject_rows.add(row_id)
        self.counts["duplicate_row_keys"] = sum(1 for chairs in keys.values() if len(chairs) > 1)
        self.counts["rows_subject_other_chair"] = len(other_subject_rows)
