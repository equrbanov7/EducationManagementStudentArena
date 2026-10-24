"""Eyni fənn + semestrdə İKİ aktiv qeydiyyat — rəsmi «alt qrup birləşməsi» ilə tamamlanır.

Necə yaranır: legacy jurnalında tələbə başqa qrupun/alt qrupun jurnalına yazılıb (delta onu ``source_group``
ilə «alt qrupdan əlavə» kimi qeyd edir, xanaları oradadır); dərs yükü axını (``_confirm_and_enroll``) isə
qrupun bütün tələbələrini ÖZ qrup jurnalına da yazır. Nəticə: tələbə fənni iki jurnalda görür, biri boşdur.

Həll yeni məntiq deyil — «Alt qrupa yerləşdir»in öz qaydası (``guest_merge.release_source``): ÖZ qrup
qeydiyyatı tarixçəyə keçir (``dropped`` + ``superseded_by`` → alt qrup sətri), heç nə silinmir, geri qaytarmaq
olar (``restore_source``). Yalnız bu hal: dəqiq BİR öz-qrup qeydiyyatı, onda HEÇ BİR xana yoxdur və ən azı bir
alt-qrup qeydiyyatı var. Xanası olan öz-qrup qeydiyyatına, yekunu/bağlı jurnalı olana toxunulmur (sayılır).
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count

REASON = "Köhnə sistemdən köçürmə: tələbə bu fənni alt qrup jurnalında keçir (legacy jurnal siyahısı)"


def dedupe_enrollments(run, period_ids) -> None:
    from apps.registrar.public import guest_merge

    Enrollment = django_apps.get_model("registrar", "Enrollment")
    LessonMark = django_apps.get_model("registrar", "LessonMark")
    period_ids = [pk for pk in period_ids if pk]
    if not period_ids:
        return
    rows = list(
        Enrollment.objects.filter(
            organization=run.organization, status="enrolled", offering__period_id__in=period_ids
        ).values_list(
            "pk", "student_id", "offering__subject_id", "offering__period_id", "source_group_id", "created_at"
        )
    )
    groups: dict = defaultdict(list)
    for pk, student, subject, period, source_group, created in rows:
        groups[(student, subject, period)].append((pk, source_group, created))
    duplicates = {key: items for key, items in groups.items() if len(items) > 1}
    if not duplicates:
        return
    ids = [pk for items in duplicates.values() for pk, _sg, _c in items]
    marks = dict(
        LessonMark.objects.filter(enrollment_id__in=ids)
        .values("enrollment_id")
        .annotate(n=Count("id"))
        .values_list("enrollment_id", "n")
    )
    objects = Enrollment.objects.select_related("offering").in_bulk(ids)
    for key in sorted(duplicates, key=lambda k: (k[0], str(k[1]), str(k[2]))):
        items = duplicates[key]
        own = [item for item in items if item[1] is None]
        guests = [item for item in items if item[1] is not None]
        if len(own) != 1 or not guests:
            run.count("dedupe.shape_kept")
            continue
        source = own[0][0]
        if marks.get(source, 0):
            run.count("dedupe.own_has_marks_kept")
            continue
        target = sorted(guests, key=lambda item: (-marks.get(item[0], 0), item[2], str(item[0])))[0][0]
        try:
            with transaction.atomic():
                guest_merge.release_source(
                    source=objects[source], target=objects[target], by_user=run.actor, reason=REASON
                )
        except ValidationError:
            run.count("dedupe.release_blocked")
            continue
        run.count("dedupe.released")
        run.touched("enrollments", source, ["status", "superseded_by"])


__all__ = ["dedupe_enrollments"]
