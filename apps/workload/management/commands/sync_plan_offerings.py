"""``sync_plan_offerings`` — plan → qrup açılışları BACKFILL-i (2026-09-25; dry-run DEFOLTDUR).

Sahibin tələbi: «tədris planı kafedralara göndəriləndə fənn avtomatik qruplara
düşsün». Yeni axında bu, dekanlıq təsdiqi anında baş verir; bu əmr KEÇMİŞ
sənədlər üçün eyni işi görür (idempotent, heç nə silmir):

1. seçilmiş sənədlərin sətirlərində boş ``period``-u tədris ili + fəsildən bağlayır
   (``plan_calendar`` — ləğv edilmiş sənədlər xaric, hər statusda);
2. planı kafedraya ÇATMIŞ sənədlər (təsdiqlənib / bölgü təsdiqlənib / düzəlişdə) üçün
   hər sətrin qrup açılışını yaradır-yeniləyir və yeni/boş açılışa qrupun aktiv
   tələbələrini yazır — təsdiqdə işləyən EYNİ yol (``offering_sync``); fərqli
   müəllim (təhvil / cədvəl redaktoru) əzilmir, seçmə blok açılmır;
3. ``--include-drafts`` — kafedranın göndərilməmiş köhnə qaralama/bölüşdürülən
   sənədləri də (təsdiq hadisəsi olmayan yol; məs. TAPŞIRIQ kitabçasından idxal).

Bütün iş BİR tranzaksiyadadır: dry-run sonda geri alınır (rəqəmlər dəqiqdir),
``--apply``-də istənilən xəta hər şeyi geri qaytarır.

    manage.py sync_plan_offerings --org qku --year 2026/2027 [--include-drafts] \\
        [--task <uuid> ...] [--actor <istifadəçi>]
    ... --apply
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from apps.workload.constants import TaskStatus
from apps.workload.models import TeachingTask
from apps.workload.services.offering_rules import plan_reached_chair
from apps.workload.services.offering_sync import COUNTER_KEYS, rows_queryset, sync_task_offerings
from apps.workload.services.plan_calendar import ensure_row_periods
from apps.workload.services.scoping import resolve_actor
from apps.workload.services.tasks import normalize_academic_year
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "Plan → qrup açılışları: boş semestr + açılış + tələbə qeydiyyatı (dry-run defolt, --apply yazır)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--year", default="", help="Tədris ili, məs. 2026/2027 (boş — hamısı)")
        parser.add_argument("--task", action="append", default=[], help="Yalnız bu tapşırıq(lar) (UUID)")
        parser.add_argument("--include-drafts", action="store_true", help="Göndərilməmiş kafedra qaralamaları da")
        parser.add_argument("--actor", default="", help="Audit + alt qrup əlavəsi üçün aktiv istifadəçi adı")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        self.totals = dict.fromkeys(COUNTER_KEYS, 0)
        self.missing: dict = {}
        self.tasks_seen = 0
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                self._run(options)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        self._summary(options)

    def _run(self, options):
        organization = Organization.objects.filter(slug=options["org"]).first()
        if organization is None:
            raise CommandError(f"organization_not_found: {options['org']}")
        actor = None
        if options["actor"]:
            user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
            if user is None:
                raise CommandError(f"actor_not_found: {options['actor']}")
            actor = resolve_actor(user, organization)
        tasks = TeachingTask.objects.filter(organization=organization).exclude(status=TaskStatus.CANCELLED)
        if options["year"]:
            year = normalize_academic_year(options["year"])
            if not year:
                raise CommandError(f"bad_year: {options['year']}")
            tasks = tasks.filter(academic_year=year)
        if options["task"]:
            tasks = tasks.filter(pk__in=options["task"])
        self.stdout.write(f"Təşkilat: {organization.name} · il: {options['year'] or 'hamısı'}")
        for task in tasks.select_related("chair").order_by("academic_year", "chair__name"):
            self._task(task, actor=actor, include_drafts=options["include_drafts"])

    def _task(self, task, *, actor, include_drafts):
        self.tasks_seen += 1
        rows = list(rows_queryset(task))
        legacy_draft = task.status in (TaskStatus.DRAFT, TaskStatus.DISTRIBUTING) and task.submitted_at is None
        if plan_reached_chair(task) or (include_drafts and legacy_draft):
            report = sync_task_offerings(task, actor=actor, create=True, rows=rows)
            mode = "açılış"
        else:
            report = ensure_row_periods(rows, task=task)
            mode = "yalnız semestr"
        for key in COUNTER_KEYS:
            self.totals[key] += int(report.get(key) or 0)
        for season, count in (report.get("missing_seasons") or {}).items():
            key = f"{task.academic_year} {season}"
            self.missing[key] = self.missing.get(key, 0) + count
        shown = ("period_set", "period_missing", "created", "updated", "enrolled", "elective_pending")
        detail = " · ".join(f"{key}={report.get(key, 0)}" for key in shown if report.get(key))
        self.stdout.write(
            f"  · {task.chair.name} · {task.academic_year} · {task.status} → {mode}: {len(rows)} sətir"
            + (f" · {detail}" if detail else "")
        )

    def _summary(self, options):
        self.stdout.write(f"Sənəd: {self.tasks_seen}")
        self.stdout.write(
            " · ".join(f"{key}={value}" for key, value in self.totals.items() if value) or "dəyişiklik yoxdur"
        )
        if self.missing:
            self.stdout.write(
                "Semestri tapılmayan sətirlər (əvvəlcə «Semestr açılışı»nda dövr yaradın): "
                + ", ".join(f"{key}: {count}" for key, count in sorted(self.missing.items()))
            )
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY-RUN — heç nə yazılmadı (--apply ilə yazılır)."))
