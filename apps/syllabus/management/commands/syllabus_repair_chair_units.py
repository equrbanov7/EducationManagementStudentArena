"""R-2 bərpası — `Syllabus.chair_unit` ixtisasdan KAFEDRAYA çəkilir.

Niyə lazımdır
-------------
Müəllim səthi `chair_unit`-i `offering.group.parent`-dən götürürdü; köçürülmüş
strukturda qrupun valideyni **ixtisasdır**, ona görə kafedra müdirinin əhatəsi
sillabusa çatmırdı (bax `apps/syllabus/services/units.py`).  Kod düzəlişi yalnız
YENİ sətirlərə təsir edir — bu əmr MÖVCUD sətirləri bir dəfə düzəldir.

Xüsusiyyətlər
-------------
* **Quru icra defoltdur** — dəyişiklik yalnız ``--apply`` ilə yazılır.
* **İdempotent** — ikinci icra 0 sətir toxunur (kafedraya bağlı sətir seçilmir).
* **Auditlidir** — hər dəyişiklik ``audit_auditlog``-a köhnə/yeni dəyərlə düşür.
* Bölmə ağacında kafedra əcdadı OLMAYAN sətrə TOXUNMUR (uydurma bağ yaradılmır).
* **`chair_unit` BOŞ olan sətirlər də həll edilir** (2026-09-11). Köçürülmüş
  4 926 sillabusun HAMISI boş idi — nə ixtisasa, nə kafedraya bağlı — ona görə
  «Sillabuslar» və «Sillabus təsdiqi» ekranlarında kafedra süzgəci boş qalır,
  kafedra müdirinin növbəsinə isə heç nə düşmürdü. Müəllifin aktiv kafedra
  üzvlüyü (``author_chair_unit``) burada yeganə real bağdır: klonda 4 885 /
  4 926 sətir bu yolla həll olunur; qalan 41-in müəllifi kafedrasız
  işçidir (``myedu.worker.*``) və boş qalır — uydurma bağ yaradılmır.

İstifadə::

    python manage.py syllabus_repair_chair_units                 # quru
    python manage.py syllabus_repair_chair_units --apply
    python manage.py syllabus_repair_chair_units --org myedu-univ --apply
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ...models import Syllabus
from ...services.units import CHAIR_UNIT_TYPES, resolve_syllabus_chair_unit


class Command(BaseCommand):
    help = "Sillabusların `chair_unit` sahəsini ixtisasdan kafedraya çəkir (idempotent, auditli)."

    def add_arguments(self, parser):
        parser.add_argument("--org", dest="org_slug", help="Yalnız bu təşkilatın slug-ı üzrə işlə")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Dəyişikliyi YAZ (defolt: quru icra — heç nə yazılmır)",
        )

    def handle(self, *args, **options):
        from core.rls import bypass_rls
        from core.rls_pooling import rls_worker_atomic

        with rls_worker_atomic(), bypass_rls():
            self._repair(**options)

    def _repair(self, *, org_slug=None, apply=False, **_options):
        # Kafedraya ARTIQ bağlı olanlar seçilmir (idempotentlik); ixtisasa bağlı
        # və ya BOŞ olanlar həll edilir.
        queryset = Syllabus.objects.exclude(chair_unit__unit_type__in=CHAIR_UNIT_TYPES).select_related(
            "chair_unit", "organization", "author"
        )
        if org_slug:
            queryset = queryset.filter(organization__slug=org_slug)

        planned = []
        unresolved = 0
        for syllabus in queryset.iterator(chunk_size=500):
            current = syllabus.chair_unit
            target = resolve_syllabus_chair_unit(
                unit=current, author=syllabus.author, organization=syllabus.organization
            )
            if target is None or (current is not None and target.pk == current.pk):
                unresolved += 1
                continue
            planned.append((syllabus, current, target))

        for syllabus, current, target in planned[:20]:
            before = f"«{current.name}» ({current.unit_type})" if current is not None else "— boş —"
            self.stdout.write(f"  → {syllabus.pk}: {before} ⇒ «{target.name}»")
        if unresolved:
            self.stdout.write(f"  kafedrası tapılmayan (toxunulmur): {unresolved}")
        if len(planned) > 20:
            self.stdout.write(f"  … və daha {len(planned) - 20} sətir")

        if not apply:
            self.stdout.write(self.style.WARNING(f"QURU İCRA: {len(planned)} sillabus düzəldiləcəkdi (--apply verin)."))
            return

        with transaction.atomic():
            for syllabus, current, target in planned:
                Syllabus.objects.filter(pk=syllabus.pk).update(chair_unit=target)
                log_action(
                    AuditAction.UPDATE,
                    organization=syllabus.organization,
                    obj=syllabus,
                    old_values={
                        "chair_unit": str(current.pk) if current is not None else None,
                        "chair_unit_name": current.name if current is not None else None,
                    },
                    new_values={"chair_unit": str(target.pk), "chair_unit_name": target.name},
                    reason="syllabus_repair_chair_units (R-2)",
                    resource_type="syllabus.syllabus",
                    resource_id=str(syllabus.pk),
                    resource_repr=str(syllabus),
                )

        self.stdout.write(self.style.SUCCESS(f"✅ {len(planned)} sillabusun kafedra bağı düzəldildi."))
