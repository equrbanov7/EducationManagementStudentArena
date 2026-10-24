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

İstifadə::

    python manage.py fix_syllabus_plan_hours                     # quru icra
    python manage.py fix_syllabus_plan_hours --org qku --apply
    python manage.py fix_syllabus_plan_hours --org qku --fill-empty --apply
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.syllabus.models import SyllabusVersion
from apps.syllabus.public import SyllabusStatus, services
from core.audit import log_action
from core.constants import AuditAction

from ...plan_hours import plan_hours_for_offering

_EDITABLE = {SyllabusStatus.DRAFT.value, SyllabusStatus.REVISION.value}


def _norm(hours) -> dict:
    return services.clean_override_hours(hours)


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

    def _expected(self, syllabus, memo) -> dict:
        override = _norm(syllabus.plan_hours_override)
        if override:
            return override
        offering = syllabus.offering if syllabus.offering_id else None
        if offering is None:
            return {}
        if offering.pk not in memo:
            memo[offering.pk] = _norm(plan_hours_for_offering(offering))
        return memo[offering.pk]

    def _run(self, *, org_slug=None, fill_empty=False, apply=False, **_options):
        queryset = (
            SyllabusVersion.objects.exclude(status=SyllabusStatus.ARCHIVED.value)
            .select_related("organization", "syllabus", "syllabus__offering", "syllabus__offering__group")
            .order_by("organization_id", "syllabus_id", "created_at")
        )
        if org_slug:
            queryset = queryset.filter(organization__slug=org_slug)

        counts: Counter = Counter()
        planned = []
        memo: dict = {}
        for version in queryset.iterator(chunk_size=200):
            counts["scanned"] += 1
            expected = self._expected(version.syllabus, memo)
            stored = _norm(version.plan_hours)
            if not expected:
                counts["no_source"] += 1
                continue
            if stored == expected:
                counts["ok"] += 1
                continue
            if not stored and version.status not in _EDITABLE and not fill_empty:
                counts[f"empty_locked_skipped:{version.status}"] += 1
                continue
            kind = "fill" if not stored else ("lower" if sum(expected.values()) < sum(stored.values()) else "other")
            counts[f"fix:{version.status}:{kind}"] += 1
            if _norm(version.syllabus.plan_hours_override):
                counts["fix_from_override"] += 1
            planned.append((version, stored, expected))

        for key in sorted(counts):
            self.stdout.write(f"  {key}: {counts[key]}")
        if not apply:
            self.stdout.write(
                self.style.WARNING(f"QURU İCRA: {counts['scanned']} versiyadan {len(planned)}-i düzələcəkdi (--apply).")
            )
            return

        written = 0
        for version, stored, expected in planned:
            with transaction.atomic():
                fresh = SyllabusVersion.objects.select_related("organization", "syllabus").get(pk=version.pk)
                if _norm(fresh.plan_hours) != stored or not services.write_version_plan_hours(fresh, expected):
                    continue
                written += 1
                log_action(
                    AuditAction.UPDATE,
                    organization=fresh.organization,
                    obj=fresh,
                    old_values={"plan_hours": stored},
                    new_values={"plan_hours": expected},
                    reason="fix_syllabus_plan_hours: sillabus BİR qrupun saatıdır, müəllimin yükü deyil (sahib 2026-10-25)",
                    resource_type="syllabus.version",
                    resource_id=str(fresh.pk),
                    resource_repr=f"{fresh.syllabus_id} {fresh.label}",
                )
        self.stdout.write(
            self.style.SUCCESS(f"✅ {written} versiyanın plan saatı düzəldildi ({counts['scanned']} yoxlanıldı).")
        )
