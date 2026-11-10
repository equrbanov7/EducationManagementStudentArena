"""Dərs yükü axınının qrup qeydiyyatı üçün «başqa jurnalda aktivdir» qapısı (2026-11-10).

Kök səbəb (boş xanalar hesabatı, ``docs/audits/2026-11-10-empty-cells``): ``Importer._confirm_and_enroll`` qrupun
HƏR aktiv tələbəsini qrupun öz açılışına ``enroll_student_in_subject`` ilə yazırdı. Tələbə həmin fənni artıq başqa
jurnalda (alt qrup / birləşik qrup / legacy «alt qrupdan əlavə») keçirsə, ikinci — BOŞ — qeydiyyat yaranırdı:
öz qrup jurnalında keçmiş bütün dərslər «—» görünür, xanalar isə o biri jurnaldadır. 2026-10-24 ``dedupe`` fazası
238 belə sətri təmizləmişdi, amma axın düzəlmədiyi üçün hər yükləmədə yenidən yaranırdı (2026-10-31, 2026-11-09).

Qayda :func:`apps.registrar.services._enroll_own_students`-dəki ilə eynidir: eyni fənn + dövr üzrə BAŞQA açılışda
``enrolled`` sətri olan tələbə bu açılışa yazılmır.
"""

from __future__ import annotations

from django.apps import apps as django_apps


def active_elsewhere(offering, student_ids) -> set:
    """``student_ids``-dən eyni fənn + dövr üzrə başqa açılışda AKTİV qeydiyyatı olanlar."""

    Enrollment = django_apps.get_model("registrar", "Enrollment")
    ids = [pk for pk in student_ids if pk]
    if not ids:
        return set()
    return set(
        Enrollment.objects.filter(
            organization_id=offering.organization_id,
            student_id__in=ids,
            status="enrolled",
            offering__subject_id=offering.subject_id,
            offering__period_id=offering.period_id,
        )
        .exclude(offering_id=offering.pk)
        .values_list("student_id", flat=True)
    )


__all__ = ["active_elsewhere"]
