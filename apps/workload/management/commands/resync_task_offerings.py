"""``resync_task_offerings`` — kafedra tapşırıqlarının açılış + qeydiyyat təkrar keçidi (2026-10-15; dry-run DEFOLT).

Səbəb: TAPŞIRIQ kitabçasından rəsmi seçmə blok seçimi (``row.subject``) sonradan
doldurulmuş sətirlər üçün açılış yox idi (sinxron seçmə cütü «gözləyir» sayırdı) —
jurnal yox, cədvəl idxalı ``subject_not_in_group``. Qayda indi :mod:`.offering_electives`
-dədir; bu əmr planı kafedraya ÇATMIŞ sənədlər üçün təsdiqdəki EYNİ yolu təkrarlayır:

1. ``offering_sync.sync_task_offerings`` — açılış yarat/yenilə (müəllim/saat qaydaları
   eyni), rəsmi blok seçimi → qrupun qərarı (``choose_group_elective``);
2. qrupun «öz» açılışlarına aktiv tələbələr (``enroll_group_students`` — idempotent,
   tarixçə/birləşmə qaydaları registrar-dadır), ``_confirm_and_enroll`` kimi.

TƏYİNATLARA toxunmur, «Vakant» yazmır, bildiriş göndərmir. Bütün iş BİR tranzaksiyadadır:
dry-run sonda geri alınır; çıxış YALNIZ saylardır.

    manage.py resync_task_offerings --org qku --year 2026/2027 (--chair "<ad>" | --all-chairs) \\
        --actor <superadmin> [--apply]
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from apps.workload.constants import TaskStatus
from apps.workload.models import TeachingTask
from apps.workload.services.offering_rules import plan_reached_chair
from apps.workload.services.offering_sync import sync_task_offerings
from apps.workload.services.scoping import resolve_actor
from apps.workload.services.task_form1_import import find_chair
from apps.workload.services.tasks import normalize_academic_year
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

#: Çıxışdakı saylar (sıra sabitdir).
SHOWN = (
    "created",
    "updated",
    "elective_from_task",
    "elective_choice_recorded",
    "elective_choice_conflict",
    "elective_choice_failed",
    "elective_pending",
    "inactive_skipped",
    "rows_skipped",
    "period_missing",
    "enrollments_created",
)


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "Kafedra tapşırıqları → açılış + rəsmi seçmə blok seçimi + qrup qeydiyyatı (dry-run defolt)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--year", required=True, help="Tədris ili (YYYY/YYYY)")
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--chair", default="", help="Kafedra adı («… kafedrası» şəkilçisi ilə və ya onsuz)")
        scope.add_argument("--all-chairs", action="store_true", help="Bütün kafedraların tapşırıqları")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit + qərar müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        self.totals = dict.fromkeys(SHOWN, 0)
        self.tasks_seen = self.tasks_skipped = 0
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                self._run(options)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        mode = "APPLY" if options["apply"] else "DRY-RUN (heç nə yazılmadı)"
        self.stdout.write(f"tasks={self.tasks_seen} · tasks_not_reached_chair={self.tasks_skipped}")
        self.stdout.write(f"{mode}: " + " · ".join(f"{key}={self.totals[key]}" for key in SHOWN))

    def _run(self, options) -> None:
        organization = Organization.objects.filter(slug=options["org"]).first()
        if organization is None:
            raise CommandError(f"organization_not_found: {options['org']}")
        user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if user is None or not user.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        year = normalize_academic_year(options["year"])
        if not year:
            raise CommandError("bad_year")
        tasks = TeachingTask.objects.filter(organization=organization, academic_year=year).exclude(
            status=TaskStatus.CANCELLED
        )
        if not options["all_chairs"]:
            chair = find_chair(organization, options["chair"])
            if chair is None:
                raise CommandError("chair_not_found_or_ambiguous")
            tasks = tasks.filter(chair=chair)
        actor = resolve_actor(user, organization)
        for task in tasks.select_related("organization", "chair").order_by("chair__name", "created_at"):
            self._task(task, actor=actor)

    def _task(self, task, *, actor) -> None:
        if not plan_reached_chair(task):
            self.tasks_skipped += 1
            return
        self.tasks_seen += 1
        report = sync_task_offerings(task, actor=actor, create=True)
        for key in SHOWN:
            self.totals[key] += int(report.get(key) or 0)
        self.totals["enrollments_created"] += int(report.get("enrolled") or 0) + int(report.get("guest_added") or 0)
        self.totals["enrollments_created"] += self._enroll_all(report.get("group_offering_ids") or {}, actor)

    @staticmethod
    def _enroll_all(group_offering_ids, actor) -> int:
        """``_confirm_and_enroll`` kimi: qrupun HƏR öz açılışına aktiv tələbələr (sinxron yalnız boşları yazır)."""
        from django.apps import apps as django_apps

        from apps.registrar.public import services as registrar_services

        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        created = 0
        for kind, ids in group_offering_ids.items():
            offerings = list(CourseOffering.objects.filter(pk__in=set(ids), is_active=True).select_related("period"))
            if not offerings:
                continue
            report = registrar_services.enroll_group_students(
                offerings=offerings,
                kind=kind,
                by_user=actor.user,
                reason="Tədris tapşırığı: açılışların təkrar keçidi (resync_task_offerings)",
            )
            created += int(report.get("created") or 0) + int(report.get("guest_added") or 0)
        return created
