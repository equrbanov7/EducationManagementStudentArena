"""``fix_task_row_hours`` — tapşırıq sətrində BİR fəaliyyətin saatını düzəldir (rəsmi düzəliş axını ilə).

Səbəb (sahib 2026-10-15): rəsmi TAPŞIRIQ kitabçasında («Proqramlaşdırma» vərəqi) «631/5K» və «631/5K ing»
«Müasir proqramlaşdırma dilləri» sətirlərinin Laboratoriya «Cəmi» xanasına səhvən sətrin CƏMİ (mühazirə 30 +
seminar 15 = 45) yazılıb → idxal sətrə ``lab_total=45`` və 45 saatlıq laboratoriya bölgüsü yaradıb.

Yol UI ilə EYNİDİR (``services.row_edit.set_activity_hours``): sənəd təsdiqlənibsə sətir üçün düzəliş
(``--reason`` qeyd kimi, səbəb «Texniki səhvin düzəlişi») → fəaliyyətin bölgüsü yeni cəmə sığdırılır
(0 → silinir) → sətrin fəaliyyət cəmi (0-da plan da) yazılır, ``total_hours`` yenidən hesablanır →
sənəd əvvəl ``distributed`` idisə yenidən təsdiqlənir (TƏKRAR bildiriş yalnız saatı dəyişən müəllimə). Jurnal sahibi
(``CourseOffering.instructor``) mövcud sinxronla izləyir — mühazirəçi dəyişmirsə toxunulmur.

* DEFOLT DRY-RUN — bir tranzaksiya, ``--apply`` verilməsə sonda geri alınır (heç nə yazılmır).
* Hər ``--group`` işarəsi (vergüllə bir neçə: «631/5K,631/5K ing») kafedranın tapşırığında fənn + qrup üzrə
  DƏQİQ BİR sətrə uyğun gəlməlidir — 0 və ya 2+ olsa heç nə yazılmır (``CommandError``).
* İdempotent: saat artıq istənilən qədərdirsə ``unchanged``.
* Stdout-a YALNIZ saylar düşür (şəxs adı yoxdur).

İstifadə::

    manage.py fix_task_row_hours --org qku --year 2026/2027 --chair "Proqramlaşdırma kafedrası" \\
        --group "631/5K,631/5K ing" --subject "Müasir proqramlaşdırma dilləri" --activity lab --hours 0 \\
        --reason "TAPŞIRIQ kitabçasında laboratoriya xanasına sətrin cəmi yazılıb" --actor superadmin [--apply]
"""

from __future__ import annotations

from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.workload.constants import ACTIVITY_TOTAL_FIELD, AmendmentReason, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTask, WorkloadAmendment
from apps.workload.services.distribution import confirm_distribution, distribution_readiness, teacher_loads
from apps.workload.services.row_edit import set_activity_hours
from apps.workload.services.scoping import WorkloadDenied, resolve_actor
from apps.workload.services.task_form1_import import find_chair, subject_slug
from apps.workload.services.task_form1_parsing import group_key, group_tokens
from apps.workload.services.tasks import normalize_academic_year
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


def row_group_keys(row) -> set[str]:
    keys = {group_key(unit.name) for unit in row.groups.all()}
    keys |= {group_key(token) for token in group_tokens(row.groups_text)}
    keys.discard("")
    return keys


def match_rows(task, *, subject: str, tokens) -> dict:
    """Qrup işarəsi → uyğun sətirlər (fənn slug-ı + qrup açarı ilə; DƏQİQ bərabərlik)."""
    wanted_subject = subject_slug(subject)
    rows = [
        row
        for row in task.rows.select_related("subject").prefetch_related("groups")
        if wanted_subject in {subject_slug(row.subject_text), subject_slug(row.subject.name) if row.subject_id else ""}
    ]
    return {token: [row for row in rows if group_key(token) in row_group_keys(row)] for token in tokens}


class Command(BaseCommand):
    help = "Tapşırıq sətrində bir fəaliyyətin saatını rəsmi düzəliş axını ilə düzəldir — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--year", default="2026/2027", help="Tədris ili (YYYY/YYYY)")
        parser.add_argument("--chair", required=True, help="Kafedra adı («… kafedrası» şəkilçisi ilə və ya onsuz)")
        parser.add_argument("--group", required=True, help="Qrup işarəsi; vergüllə bir neçə («631/5K,631/5K ing»)")
        parser.add_argument("--subject", required=True, help="Fənn adı (sətrin fənni)")
        parser.add_argument("--activity", required=True, choices=sorted(ACTIVITY_TOTAL_FIELD), help="Fəaliyyət")
        parser.add_argument("--hours", required=True, type=int, help="Yeni cəm saat (0 = fəaliyyəti çıxar)")
        parser.add_argument("--reason", required=True, help="Düzəlişin qeydi (tarixçəyə yazılır)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        if options["hours"] < 0:
            raise CommandError("hours_negative")
        if not options["reason"].strip():
            raise CommandError("reason_required")
        tokens = [token.strip() for token in options["group"].split(",") if token.strip()]
        if not tokens:
            raise CommandError("group_required")
        counters: Counter = Counter()
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                self._run(options, tokens, counters)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        mode = "APPLY" if options["apply"] else "DRY-RUN (heç nə yazılmadı)"
        self.stdout.write(f"{mode}: " + " · ".join(f"{key}={counters[key]}" for key in sorted(counters)))

    def _run(self, options, tokens, counters) -> None:
        from django.apps import apps as django_apps

        Organization = django_apps.get_model("organizations", "Organization")
        organization = Organization.objects.filter(slug=options["org"]).first()
        if organization is None:
            raise CommandError(f"organization_not_found: {options['org']}")
        user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if user is None or not user.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        chair = find_chair(organization, options["chair"])
        if chair is None:
            raise CommandError("chair_not_found_or_ambiguous")
        year = normalize_academic_year(options["year"])
        task = TeachingTask.objects.filter(organization=organization, chair=chair, academic_year=year).first()
        if task is None:
            raise CommandError("task_not_found")

        matches = match_rows(task, subject=options["subject"], tokens=tokens)
        for token, rows in matches.items():
            if len(rows) != 1:
                raise CommandError(
                    f"group_token_match_count={len(rows)} (gözlənən 1) — token #{tokens.index(token) + 1}"
                )
        counters["rows_matched"] = len(matches)

        actor = resolve_actor(user, organization)
        was_distributed = task.status == TaskStatus.DISTRIBUTED
        loads_before = teacher_loads(task)
        activity, hours = options["activity"], options["hours"]
        field = ACTIVITY_TOTAL_FIELD[activity]
        amend = {"reason": AmendmentReason.CORRECTION, "note": options["reason"].strip()}
        for rows in matches.values():
            row = rows[0]
            before = int(getattr(row, field) or 0)
            assigned_before = TeacherAssignment.objects.filter(row=row, activity=activity).count()
            if before == hours:
                counters["unchanged"] += 1
                continue
            task.refresh_from_db()
            try:
                saved = set_activity_hours(task=task, row=row, activity=activity, hours=hours, actor=actor, amend=amend)
            except WorkloadDenied as exc:
                raise CommandError(f"blocked: {exc.code}") from exc
            counters["rows_changed"] += 1
            counters["hours_removed" if hours < before else "hours_added"] += abs(before - hours)
            assigned_after = TeacherAssignment.objects.filter(row=saved, activity=activity).count()
            counters["assignments_removed"] += max(assigned_before - assigned_after, 0)
        task.refresh_from_db()
        if counters["rows_changed"]:
            counters["amendments_opened"] = WorkloadAmendment.objects.filter(task=task, note=amend["note"]).count()
        if was_distributed and task.status == TaskStatus.AMENDED:
            readiness = distribution_readiness(task)
            if not readiness["is_ready"]:
                raise CommandError(f"reconfirm_blocked: incomplete_rows={len(readiness['incomplete_rows'])}")
            # Kafedranın bütün müəllimlərinə təkrar bildiriş yox — yalnız saatı dəyişən müəllimə (sahib 2026-10-17).
            confirm_distribution(task=task, actor=actor, allow_vacant=True, loads_before=loads_before)
            counters["reconfirmed"] += 1
        elif task.status == TaskStatus.AMENDED:
            counters["left_amended"] += 1  # düzəliş əmrdən ƏVVƏL açıq idi — təsdiq kafedranın qərarıdır
