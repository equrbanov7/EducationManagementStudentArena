"""Mövcud sillabusların PLAN SAATINI bir qrupun saatına gətirir (sahib 2026-10-25).

Problem
-------
«Fənn 75 saatdır … müəllimin dərs yükü 105 saat olsa da, sillabus olaraq 75 saat yazmalıdır.»  Birləşmə (patok)
fənnində sillabusun ``plan_hours``-u müəllimin yük sətrinin CƏMİNDƏN (birgə mühazirə + bütün qrupların seminarı)
yazılmışdı.  İndi mənbə ``registrar.plan_hours_for_offering``-dir: qrupun ixtisas planı → yükdə BİR qrupa düşən
pay (birgə mühazirə bir dəfə, seminar/lab bir qrupun payı) → istənilən plan; dosyedə kafedranın əl ilə düzəlişi
(``Syllabus.plan_hours_override``) varsa o üstündür.

Nə edir
-------
* Arxivdən başqa BÜTÜN versiyalar (təsdiqlənmiş DAXİL) — yalnız ``plan_hours`` sahəsi.  Redaktəyə açıq
  versiyada ``set_plan_hours`` (tamamlanma yenidən hesablanır); təqdim/baxış/təsdiqlənmiş versiyada yalnız sütun.
  Bölmələrə — müəllimin həftəlik bölgüsünə — TOXUNULMUR; cədvəlin sətir sayı ``week_plan.expected_week_rows``
  qaydası ilə plandan özü çıxır.
* Plan saatı BOŞ olan kilidli (təqdim/baxış/təsdiqlənmiş) versiyalar defolt olaraq yalnız SAYILIR — onları
  doldurmaq ``--fill-empty`` ilə (köçürülmüş/bağlı nüsxələr; boş = «bilinmir», səhv deyil).
* Mənbə tapılmayan versiyaya toxunulmur.  Quru icra defoltdur (``--apply`` ilə yazılır), idempotentdir, hər yazı
  ``audit_auditlog``-a düşür.  Stdout-a YALNIZ saylar çıxır (ad/qrup yoxdur).
* Qayda 2026-11-26-dan ``apps/registrar/syllabus_plan_hours_sync.py``-dadır: yük sətri / tapşırıq sinxronu
  (``workload.offering_sync``) açılışın saatını dəyişəndə eyni düzəliş DƏRHAL edilir; əmr hesabat və köhnə
  qalıqlar üçündür (quru icrada «fix:*» sayı 0 olmalıdır).

İstifadə::

    python manage.py fix_syllabus_plan_hours                     # quru icra
    python manage.py fix_syllabus_plan_hours --org qku --apply
    python manage.py fix_syllabus_plan_hours --org qku --fill-empty --apply
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand

from ... import syllabus_plan_hours_sync as shared
from ...plan_hours import plan_hours_for_offering


class Command(BaseCommand):
    help = "Sillabus plan saatını bir qrupun saatına gətirir (təsdiqlənmiş daxil; idempotent, auditli, quru icra)."

    def add_arguments(self, parser):
        parser.add_argument("--org", dest="org_slug", help="Yalnız bu təşkilatın slug-ı üzrə işlə")
        parser.add_argument(
            "--fill-empty",
            action="store_true",
            help="Plan saatı BOŞ olan kilidli (təqdim/baxış/təsdiqlənmiş) versiyaları da doldur",
        )
        parser.add_argument("--apply", action="store_true", help="Dəyişikliyi YAZ (defolt: quru icra)")

    def handle(self, *args, **options):
        from core.rls import bypass_rls
        from core.rls_pooling import rls_worker_atomic

        with rls_worker_atomic(), bypass_rls():
            self._run(**options)

    def _run(self, *, org_slug=None, fill_empty=False, apply=False, **_options):
        # Qayda ``syllabus_plan_hours_sync``-dədir — açılış sinxronu (2026-11-26) eyni qərarı dərhal verir.
        queryset = shared.versions_queryset()
        if org_slug:
            queryset = queryset.filter(organization__slug=org_slug)

        counts: Counter = Counter()
        planned = []
        memo: dict = {}
        for version in queryset.iterator(chunk_size=200):
            counts["scanned"] += 1
            expected = shared.expected_plan_hours(version.syllabus, memo, resolve=plan_hours_for_offering)
            stored = shared.norm(version.plan_hours)
            key, fix = shared.classify(version, stored, expected, fill_empty=fill_empty)
            counts[key] += 1
            if not fix:
                continue
            if shared.norm(version.syllabus.plan_hours_override):
                counts["fix_from_override"] += 1
            planned.append((version, stored, expected))

        for key in sorted(counts):
            self.stdout.write(f"  {key}: {counts[key]}")
        if not apply:
            self.stdout.write(
                self.style.WARNING(f"QURU İCRA: {counts['scanned']} versiyadan {len(planned)}-i düzələcəkdi (--apply).")
            )
            return

        written = sum(
            1
            for version, stored, expected in planned
            if shared.write_fix(version, stored, expected, reason=shared.REASON_COMMAND)
        )
        self.stdout.write(
            self.style.SUCCESS(f"✅ {written} versiyanın plan saatı düzəldildi ({counts['scanned']} yoxlanıldı).")
        )
