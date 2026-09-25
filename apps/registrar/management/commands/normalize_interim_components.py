"""Midterm dövrlərinin (2026/2027-dən) jurnallarını TƏK «Midterm» komponentinə gətirir.

Nə üçün var (sahibin qərarı 2026-09-25): «3 kollokvium olmayacaq, 1 midterm olacaq — 20
ballıq». Köhnə kod cari dövrdə jurnal açılanda boş «Kollokvium 1–3» komponentləri yaradırdı.
Jurnal indi özü (``interim_components.ensure_kollokviums``) açılanda bunu düzəldir; bu komanda
isə deploydan sonra BÜTÜN midterm-dövr açılışlarını bir dəfəyə eyni vəziyyətə gətirir ki,
tələbə kabineti və hesabatlar müəllimin jurnalı açmasını gözləmədən «Midterm …/20» göstərsin.

Nə edir (hər açılış üçün, yalnız midterm rejimli dövrlərdə):
* «Midterm» (kind=kollokvium, max 20) yoxdursa yaradır;
* BALI/SÜBUTU OLMAYAN köhnə «Kollokvium N» komponentlərini silir;
* balı olan komponentə TOXUNMUR (hesabatda «saxlanıldı» kimi göstərilir).

Keçmiş (kollokvium rejimli) dövrlər heç vaxt dəyişmir.

Təhlükəsizlik: DEFOLT DRY-RUN (``--apply`` olmadan heç nə yazılmır); idempotent (ikinci
icra 0 dəyişiklik); bütün DB işi ``rls_worker_atomic()`` + ``bypass_rls()`` içindədir; hər
dəyişən açılış ``core.audit.log_action`` ilə audit izinə düşür.

İstifadə::

    python manage.py normalize_interim_components                     # dry-run
    python manage.py normalize_interim_components --apply             # yazır
    python manage.py normalize_interim_components --organization qku  # yalnız bu təşkilat (slug)
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ... import interim_assessment, interim_components
from ...models import AssessmentComponent, ComponentKind, CourseOffering

AUDIT_REASON = "aralıq qiymətləndirmə normallaşdırıldı: 3 kollokvium → tək Midterm (0–20), 2026/2027-dən"


class _DryRun(Exception):
    """Dry-run tranzaksiyasını geri qaytarmaq üçün."""


class Command(BaseCommand):
    help = "Midterm dövrlərində (2026/2027-dən) jurnalları tək «Midterm» (0–20) komponentinə gətirir."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")
        parser.add_argument("--organization", default=None, help="yalnız bu təşkilatın slug-ı")

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        totals = {"offerings": 0, "changed": 0, "created": 0, "removed": 0, "kept": 0}
        with rls_worker_atomic(), bypass_rls():
            # Açıq tranzaksiya: dry-run-da HƏR ŞEY geri qaytarılır (``rls_worker_atomic``
            # defolt konfiqurasiyada no-op-dur, ``ensure_kollokviums`` isə öz atomic-i ilə commit edərdi).
            try:
                with transaction.atomic():
                    offerings = CourseOffering.objects.select_related("period", "organization")
                    if options["organization"]:
                        offerings = offerings.filter(organization__slug=options["organization"])
                    for offering in offerings.iterator(chunk_size=500):
                        if not interim_assessment.is_midterm_offering(offering):
                            continue
                        totals["offerings"] += 1
                        self._normalize(offering, totals, apply=apply)
                    if not apply:
                        raise _DryRun
            except _DryRun:
                pass
        mode = "YAZILDI" if apply else "DRY-RUN (heç nə yazılmadı — yazmaq üçün --apply)"
        self.stdout.write(
            f"{mode}: midterm-dövr açılışı {totals['offerings']}, dəyişən {totals['changed']}, "
            f"yaradılan Midterm {totals['created']}, silinən boş kollokvium {totals['removed']}, "
            f"balı olduğu üçün saxlanılan {totals['kept']}"
        )

    def _normalize(self, offering, totals, *, apply):
        before = list(
            AssessmentComponent.objects.filter(offering=offering, kind=ComponentKind.KOLLOKVIUM).values_list(
                "id", "name"
            )
        )
        had_midterm = any(name.strip().lower() == "midterm" for _, name in before)
        after = interim_components.ensure_kollokviums(offering)
        after_ids = {component.id for component in after}
        removed = [name for cid, name in before if cid not in after_ids]
        kept = [component.name for component in after[1:]]
        created = not had_midterm
        if not (created or removed):
            totals["kept"] += len(kept)
            return
        totals["changed"] += 1
        totals["created"] += int(created)
        totals["removed"] += len(removed)
        totals["kept"] += len(kept)
        if apply:
            log_action(
                AuditAction.UPDATE,
                organization=offering.organization,
                obj=offering,
                changes={"midterm_created": created, "removed_components": removed, "kept_components": kept},
                reason=AUDIT_REASON,
            )
