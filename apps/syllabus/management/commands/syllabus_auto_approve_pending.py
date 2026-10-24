"""Kafedra təsdiqini gözləyən sillabusları AVTOMATİK təsdiqləyir (sahib 2026-10-25).

Sahib: «sillabus approve hissəsini hələlik söndür, avtomatik qəbul olsun».  «Sillabus təsdiqi tələb
olunur» açarı (RİM «Sistem tənzimləmələri» → «Sillabus») SÖNÜLÜ olanda yeni göndərilənlər onsuz da dərhal
təsdiqlənir; bu əmr açar söndürülməzdən ƏVVƏL göndərilmiş, kafedra növbəsində qalmış versiyaları EYNİ
servislə (:func:`apps.syllabus.services.workflow.auto_approve`) təsdiqləyir.

GÖZLƏYƏN = YALNIZ ``submitted`` (göndərilib) və ``review`` (kafedra baxışda).  ``draft``, ``revision``
(geri qaytarılıb) və ``rejected`` (rədd) TOXUNULMUR — onlar müəllimin növbəsindədir, kafedranın yox.

* **Quru icra defoltdur**; yazı yalnız ``--apply`` ilə.
* **İdempotentdir** — təsdiqləndikdən sonra versiya ``approved`` olur, ikinci icra 0 sətir tapır.
* Açar YANDIRILIBSA (kafedra təsdiqi tələb olunur) ``--apply`` rədd edilir (``CommandError: approval_required``):
  kafedra müdirinin növbəsini onun xəbəri olmadan boşaltmaq olmaz.  Quru icra yenə də sayı göstərir.
* stdout-a YALNIZ saylar yazılır (ad/FİN yoxdur): ``syllabus_auto_approve: açar=say …``.

İstifadə::

    python manage.py syllabus_auto_approve_pending                 # quru icra
    python manage.py syllabus_auto_approve_pending --org qku --apply
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

from core import runtime_settings_syllabus

from ...constants import SyllabusStatus
from ...models import SyllabusVersion
from ...services import workflow

logger = logging.getLogger(__name__)

PENDING_STATUSES = (SyllabusStatus.SUBMITTED.value, SyllabusStatus.REVIEW.value)
#: Toxunulmayan, lakin məlumat üçün sayılan «müəllimdə qalan» statuslar.
UNTOUCHED_STATUSES = (SyllabusStatus.REVISION.value, SyllabusStatus.REJECTED.value)


class Command(BaseCommand):
    help = "Gözləyən (submitted/review) sillabusları avtomatik təsdiqləyir (idempotent, defolt quru icra)."

    def add_arguments(self, parser):
        parser.add_argument("--org", dest="org_slug", help="Yalnız bu təşkilatın slug-ı üzrə işlə")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Faktiki təsdiqlə (defolt: quru icra — heç nə yazılmır)",
        )

    def handle(self, *args, **options):
        from core.rls import bypass_rls
        from core.rls_pooling import rls_worker_atomic

        with rls_worker_atomic(), bypass_rls():
            self._run(org_slug=options.get("org_slug"), apply=bool(options.get("apply")))

    def _queryset(self, statuses, org_slug):
        queryset = SyllabusVersion.objects.filter(status__in=statuses)
        if org_slug:
            queryset = queryset.filter(organization__slug=org_slug)
        return queryset

    def _run(self, *, org_slug=None, apply=False):
        required = runtime_settings_syllabus.approval_required()
        pending = self._queryset(PENDING_STATUSES, org_slug)
        by_status = {status: pending.filter(status=status).count() for status in PENDING_STATUSES}
        untouched = {status: self._queryset([status], org_slug).count() for status in UNTOUCHED_STATUSES}
        total = sum(by_status.values())
        self.stdout.write(
            "syllabus_auto_approve: pending=%d submitted=%d review=%d revision_untouched=%d rejected_untouched=%d "
            "approval_required=%d"
            % (
                total,
                by_status[SyllabusStatus.SUBMITTED.value],
                by_status[SyllabusStatus.REVIEW.value],
                untouched[SyllabusStatus.REVISION.value],
                untouched[SyllabusStatus.REJECTED.value],
                int(required),
            )
        )

        if not apply:
            self.stdout.write("syllabus_auto_approve: dry_run=1 would_approve=%d" % total)
            return
        if required:
            raise CommandError("approval_required")

        approved = failed = 0
        # Siyahı əvvəlcədən yığılır — təsdiq statusu dəyişir, canlı kursorla üst-üstə düşməsin.
        for version in list(pending.select_related("syllabus", "organization").order_by("pk")):
            try:
                workflow.auto_approve(version=version)
            except Exception:  # noqa: BLE001 — bir versiya qalanını dayandırmasın; ad/id loga yazılmır
                failed += 1
                logger.exception("syllabus_auto_approve_pending: version failed")
                continue
            approved += 1
        self.stdout.write("syllabus_auto_approve: applied=1 approved=%d failed=%d" % (approved, failed))
        if failed:
            raise CommandError("some_failed")
