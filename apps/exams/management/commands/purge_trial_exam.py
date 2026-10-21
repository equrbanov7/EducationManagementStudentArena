"""``purge_trial_exam`` — real olmayan (sınaq) imtahanı hamıdan, nəticələrdən və jurnaldan silir (sahib 2026-10-21).

Sahib: «233IT ing üçün Cloud-dan sınaq midterm etdik, real deyildi — onu silmək lazımdır. Hamıdan, nəticədə,
examdə silinsin gərək». Nə silindiyi və rədd halları: ``apps/exams/services/trial_exam_purge.py``.

Təhlükəsizlik:

* ``--slug`` DƏQİQ uyğunluq (təşkilat daxilində) + ``--expect-title`` imtahanın adına BƏRABƏR olmalıdır;
* defolt DRY-RUN (heç nə yazılmır); ``--apply`` → ``--reason`` (≥20 simvol) və real bazada
  ``--i-know-this-is-production``; rədd halında heç nə yazılmır;
* stdout-a YALNIZ bir sayların sətri düşür (şəxs adı / istifadəçi adı yox) — ``prod-data-ops.yml`` onu süzür;
* idempotent: ikinci qaçış heç nə tapmır və audit sətri yazmır.

İstifadə::

    manage.py purge_trial_exam --org qku --slug cloud-computing-51K75E --expect-title "Cloud Computing"
    manage.py purge_trial_exam --org qku --slug cloud-computing-51K75E --expect-title "Cloud Computing" \\
        --apply --reason "Sınaq midterm-in silinməsi — sahibin 2026-10-21 tapşırığı" --i-know-this-is-production
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.exams.services import trial_exam_purge as purge
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

_REHEARSAL_GUC = "emsarena.rehearsal_target"
_REASON_MIN = 20


def _disposable_database() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [_REHEARSAL_GUC])
        row = cursor.fetchone()
    return bool(row and row[0] == "disposable")


class Command(BaseCommand):
    help = (
        "Sınaq imtahanını (cəhdlər, apellyasiyalar, jurnal xanaları, biletlər, bildirişlər) tam silir; defolt dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı")
        parser.add_argument("--slug", required=True, help="İmtahanın slug-ı (dəqiq uyğunluq)")
        parser.add_argument("--expect-title", required=True, help="İmtahanın adı — təhlükəsizlik yoxlaması (bərabər)")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--reason", default="", help="--apply üçün səbəb (≥20 simvol)")
        parser.add_argument(
            "--allow-retake-links",
            action="store_true",
            help="«İmtahan şansı» / 25% izləri (append-only) qalsın, qalan hər şey silinsin",
        )
        parser.add_argument("--i-know-this-is-production", action="store_true")

    def handle(self, *args, **opts):
        slug = opts["slug"].strip()
        if not slug:
            raise CommandError("trial_exam_slug_required")
        if opts["apply"] and len(opts["reason"].strip()) < _REASON_MIN:
            raise CommandError(f"trial_exam_reason_too_short: --reason ən azı {_REASON_MIN} simvol olmalıdır.")
        with rls_worker_atomic(), bypass_rls():
            if opts["apply"] and not (_disposable_database() or opts["i_know_this_is_production"]):
                raise CommandError("trial_exam_not_disposable: real bazada --i-know-this-is-production verin.")
            self._run(slug, opts)

    def _run(self, slug, opts):
        Organization = django_apps.get_model("organizations", "Organization")
        organization = Organization.objects.filter(slug=opts["org"].strip()).first()
        if organization is None:
            raise CommandError("trial_exam_org_not_found")
        exam = purge.find_exam(organization=organization, slug=slug)
        if exam is None:
            self._report({"exam_found": 0}, "DRY-RUN")
            raise CommandError("trial_exam_not_found: bu slug ilə imtahan yoxdur.")
        if str(exam.title or "").strip() != opts["expect_title"].strip():
            raise CommandError("trial_exam_title_mismatch: --expect-title imtahanın adına bərabər deyil.")
        allow = opts["allow_retake_links"]
        if not opts["apply"]:
            plan = purge.build_plan(exam, allow_retake_links=allow)
            self._report(plan.counts, "DRY-RUN", plan.blockers)
            return
        try:
            plan = purge.apply_purge(exam, reason=opts["reason"].strip(), allow_retake_links=allow)
        except purge.PurgeRefused as refused:
            self._report(refused.plan.counts, "REFUSED", refused.plan.blockers)
            raise CommandError(f"trial_exam_refused: {','.join(refused.plan.blockers)}") from None
        self._report(plan.counts, "APPLY" if plan.has_data or not plan.counts.get("exam_deleted_before") else "NOOP")

    def _report(self, counts, mode, blockers=()):
        parts = [f"{key}={int(counts.get(key, 0))}" for key in purge.COUNT_KEYS]
        parts.append(f"blocked={len(blockers)}")
        for blocker in sorted(blockers):
            parts.append(f"blocked_{blocker}=1")
        parts.append(f"mode={mode}")
        self.stdout.write("trial_exam_purge: " + " ".join(parts))
