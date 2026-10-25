"""``fix_workload_overcount`` — dərs yükündə ARTIQ sayılan saatlar: audit + təhlükəsiz düzəliş (sahib 2026-10-25).

Sahib: «lazımından artıq çıxmasın ortaya. Patok dərsi olanda 30 saat 2-yə vurulmur, mühazirə tək formada
hesablanır» + «seminarda da patok ola bilər — 60 saatlıq fənn bir qrup kimi 60 saat». Qaydalar:
:mod:`apps.workload.services.overcount_detect` (aşkarlama) və :mod:`apps.workload.services.overcount_fix`
(nə avtomatik düzəlir, nə qərar siyahısına düşür).

* DEFOLT DRY-RUN — eyni kod bir tranzaksiyada işləyir, sonda geri alınır; hesabat yenə yazılır.
* ``--apply`` — rəsmi düzəliş axını (səbəb + paket id-li qeyd + tam snapshot), paylanmış sənəd yenidən
  təsdiqlənir (bildiriş yalnız yükü dəyişən müəllimə; ``--no-notify`` — heç kimə).
* ``--undo <paket>`` — paketin düzəlişlərini snapshot-dan geri qaytarır (``--apply`` ilə yazır).
* İdempotent: ikinci ``--apply`` → ``rows_deleted_*=0``, ``rows_zeroed_*=0``.
* Stdout-a YALNIZ saylar; adlı hesabat ``--report`` faylına (0600).

    manage.py fix_workload_overcount --org qku --year 2026/2027 --actor <superadmin> \\
        --report /path/overload_audit.md [--apply] [--no-notify] [--undo overcount-…]
"""

from __future__ import annotations

import os
import secrets
from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.organizations.models import Organization
from apps.workload.services.overcount_fix import OvercountFixer, teacher_totals
from apps.workload.services.overcount_report import build_report
from apps.workload.services.overcount_undo import undo_batch
from apps.workload.services.scoping import resolve_actor
from apps.workload.services.tasks import normalize_academic_year
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

SHOWN = (
    "dup_clusters_fixed",
    "dup_decision_clusters",
    "rows_deleted_vacant_repeat",
    "rows_deleted_same_teacher_repeat",
    "rows_deleted_covered_by_group_rows",
    "rows_deleted_repeat_of_stream_row",
    "joint_lecture_streams",
    "joint_seminar_streams",
    "joint_lab_streams",
    "joint_decision_streams",
    "rows_zeroed_lecture",
    "rows_zeroed_seminar",
    "rows_zeroed_lab",
    "hours_removed_named",
    "hours_removed_vacant",
    "tasks_reconfirmed",
    "tasks_left_amended",
    "teachers_over_norm_before",
    "teachers_over_norm_after",
)


class _DryRunRollback(Exception):
    """Dry-run: tranzaksiyanı geri almaq üçün daxili siqnal."""


class Command(BaseCommand):
    help = "Dərs yükündə artıq sayılan saatlar (dublikat + birgə dərs): audit + düzəliş — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku", help="Təşkilatın slug-ı")
        parser.add_argument("--year", required=True, help="Tədris ili (YYYY/YYYY)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--report", default="", help="Adlı Markdown hesabatın yolu (0600)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--no-notify", action="store_true", help="Yenidən təsdiqdə bildiriş göndərmə")
        parser.add_argument("--undo", default="", help="Bu paketin düzəlişlərini geri qaytar (overcount-…)")
        parser.add_argument("--focus", default="", help="Hesabatda mütləq göstəriləcək istifadəçi adları (vergüllə)")

    def handle(self, *args, **options):
        organization = Organization.objects.filter(slug=options["org"]).first()
        if organization is None:
            raise CommandError(f"organization_not_found: {options['org']}")
        user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if user is None or not user.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        year = normalize_academic_year(options["year"])
        if not year:
            raise CommandError("bad_year")
        mode = "apply" if options["apply"] else "dry_run"
        counts: Counter = Counter()
        report = ""
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                actor = resolve_actor(user, organization)
                if options["undo"]:
                    counts = undo_batch(
                        organization=organization, batch=options["undo"], actor=actor, notify=not options["no_notify"]
                    )
                else:
                    counts, report = self._fix(organization, year, actor, mode, options)
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        if report and options["report"]:
            self._write(options["report"], report)
        keys = sorted(counts) if options["undo"] else SHOWN
        self.stdout.write(f"overcount: mode={mode} " + " ".join(f"{key}={counts.get(key, 0)}" for key in keys))

    def _fix(self, organization, year, actor, mode, options):
        batch = f"overcount-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        before = teacher_totals(organization, year)
        fixer = OvercountFixer(
            organization=organization, year=year, actor=actor, batch=batch, notify=not options["no_notify"]
        )
        first, last = fixer.run()
        after = teacher_totals(organization, year)
        focus_names = [name.strip() for name in options["focus"].split(",") if name.strip()]
        focus = set(get_user_model().objects.filter(username__in=focus_names).values_list("pk", flat=True))
        report = build_report(
            organization=organization,
            year=year,
            mode=mode,
            batch=batch,
            first=first,
            last=last,
            fixer=fixer,
            before=before,
            after=after,
            focus=focus,
        )
        counts = Counter(fixer.counts)
        counts["teachers_over_norm_before"], counts["teachers_over_norm_after"] = _over_norm(
            organization, year, before, after
        )
        if options["apply"] and any(key.startswith("rows_") and value for key, value in fixer.counts.items()):
            self.stdout.write(f"overcount: batch={batch}")
        return counts, report

    @staticmethod
    def _write(path: str, text: str) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, mode=0o700, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(path, 0o600)


def _over_norm(organization, year, before, after) -> tuple[int, int]:
    from apps.workload.models import TeacherWorkloadProfile
    from apps.workload.services.norms import norms_for

    ids = list(set(before) | set(after))
    profiles = {
        p.teacher_id: p
        for p in TeacherWorkloadProfile.objects.filter(
            organization=organization, teacher_id__in=ids, academic_year=year
        )
    }
    norms = norms_for(organization, ids, profiles)

    def over(totals) -> int:
        return sum(1 for pk, value in totals.items() if norms.get(pk) and value["total"] > norms[pk])

    return over(before), over(after)
