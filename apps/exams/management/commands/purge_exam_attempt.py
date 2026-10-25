"""``purge_exam_attempt`` — bir tələbənin SƏHV imtahan cəhdini hər yerdən silir (sahib 2026-10-25).

Sahib: «Şirməmməd üçün olan son imtahan nəticəsini də sil, onunla bağlı olanı, o səhvən olub. Onu əsas götürmə».
Nə silindiyi, jurnal izinin geri alınması və rədd halları: ``apps/exams/services/exam_attempt_purge.py``.

Təhlükəsizlik:

* ``--username`` DƏQİQ uyğunluq; cəhd ``--latest`` (tələbənin təşkilatdakı ən son cəhdi) və ya ``--attempt <id>``;
* ``--apply`` → ``--expect-exam-slug`` cəhdin imtahanının slug-ına BƏRABƏR olmalıdır, ``--reason`` (≥20 simvol) və
  real bazada ``--i-know-this-is-production``; defolt DRY-RUN (heç nə yazılmır); rədd halında heç nə yazılmır;
* stdout-a YALNIZ bir ``attempt_purge:`` sətri düşür (id-lər, slug, saylar — ad / istifadəçi adı / bal yox);
* idempotent: ikinci qaçış heç nə tapmır (``--latest`` üçün audit işarəsi: ən son cəhd artıq silinibsə NOOP).

İstifadə::

    manage.py purge_exam_attempt --org qku --username ad.soyad --latest
    manage.py purge_exam_attempt --org qku --username ad.soyad --attempt 12345 --expect-exam-slug final-XXXXXX \\
        --apply --reason "Səhv imtahan cəhdinin silinməsi — sahibin 2026-10-25 tapşırığı" --i-know-this-is-production
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.exams.services import exam_attempt_purge as purge
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

_REHEARSAL_GUC = "emsarena.rehearsal_target"
_REASON_MIN = 20
_UNSAFE = re.compile(r"[^0-9A-Za-z_.:-]")


def _disposable_database() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [_REHEARSAL_GUC])
        row = cursor.fetchone()
    return bool(row and row[0] == "disposable")


def _safe(value) -> str:
    return _UNSAFE.sub("_", str(value or "")) or "-"


class Command(BaseCommand):
    help = (
        "Bir tələbənin səhv imtahan cəhdini (cavablar, apellyasiyalar, jurnal izi, bildirişlər) silir; defolt dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı")
        parser.add_argument("--username", required=True, help="Tələbənin istifadəçi adı (dəqiq uyğunluq)")
        which = parser.add_mutually_exclusive_group(required=True)
        which.add_argument("--latest", action="store_true", help="Tələbənin ən son cəhdi")
        which.add_argument("--attempt", default="", help="Cəhdin id-si")
        parser.add_argument("--expect-exam-slug", default="", help="--apply üçün: cəhdin imtahanının slug-ı (bərabər)")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--reason", default="", help="--apply üçün səbəb (≥20 simvol)")
        parser.add_argument(
            "--allow-retake-links",
            action="store_true",
            help="25% müraciətinin izləri (append-only) qalsın, qalan hər şey silinsin",
        )
        parser.add_argument("--i-know-this-is-production", action="store_true")

    def handle(self, *args, **opts):
        attempt_ref = str(opts["attempt"] or "").strip()
        if not opts["latest"] and not attempt_ref.isdigit():
            raise CommandError("attempt_purge_bad_attempt_id: --attempt rəqəm olmalıdır.")
        if opts["apply"]:
            if len(opts["reason"].strip()) < _REASON_MIN:
                raise CommandError(f"attempt_purge_reason_too_short: --reason ən azı {_REASON_MIN} simvol olmalıdır.")
            if not opts["expect_exam_slug"].strip():
                raise CommandError("attempt_purge_expect_slug_required: --apply üçün --expect-exam-slug verin.")
        with rls_worker_atomic(), bypass_rls():
            if opts["apply"] and not (_disposable_database() or opts["i_know_this_is_production"]):
                raise CommandError("attempt_purge_not_disposable: real bazada --i-know-this-is-production verin.")
            self._run(int(attempt_ref) if attempt_ref else None, opts)

    def _run(self, attempt_id, opts):
        Organization = django_apps.get_model("organizations", "Organization")
        organization = Organization.objects.filter(slug=opts["org"].strip()).first()
        if organization is None:
            raise CommandError("attempt_purge_org_not_found")
        user = get_user_model().objects.filter(username=opts["username"].strip()).first()
        if user is None:
            raise CommandError("attempt_purge_student_not_found")
        attempt, already = purge.find_attempt(
            organization=organization, user=user, attempt_id=attempt_id, latest=opts["latest"]
        )
        if attempt is None:
            if already:
                self._report({}, {"attempt_found": 0, "already_purged": 1}, "NOOP")
                return
            self._report({}, {"attempt_found": 0}, "DRY-RUN")
            raise CommandError("attempt_purge_not_found: tələbənin bu təşkilatda belə cəhdi yoxdur.")
        expected = opts["expect_exam_slug"].strip()
        if expected and expected != str(attempt.exam.slug or ""):
            raise CommandError("attempt_purge_exam_slug_mismatch: --expect-exam-slug cəhdin imtahanına bərabər deyil.")
        allow = opts["allow_retake_links"]
        if not opts["apply"]:
            plan = purge.build_plan(attempt, allow_retake_links=allow)
            self._report(plan.info, plan.counts, "DRY-RUN", plan.blockers)
            return
        try:
            plan = purge.apply_purge(attempt, reason=opts["reason"].strip(), allow_retake_links=allow)
        except purge.PurgeRefused as refused:
            self._report(refused.plan.info, refused.plan.counts, "REFUSED", refused.plan.blockers)
            raise CommandError(f"attempt_purge_refused: {','.join(refused.plan.blockers)}") from None
        if plan is None:
            self._report({}, {"attempt_found": 0, "already_purged": 1}, "NOOP")
            return
        self._report(plan.info, plan.counts, "APPLY")

    def _report(self, info, counts, mode, blockers=()):
        parts = [f"{key}={_safe(info.get(key, '-'))}" for key in purge.INFO_KEYS]
        parts += [f"{key}={int(counts.get(key, 0))}" for key in purge.COUNT_KEYS]
        parts.append(f"blocked={len(blockers)}")
        parts += [f"blocked_{blocker}=1" for blocker in sorted(blockers)]
        parts.append(f"mode={mode}")
        self.stdout.write("attempt_purge: " + " ".join(parts))
