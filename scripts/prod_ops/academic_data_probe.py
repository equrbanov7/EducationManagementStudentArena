"""Tədris məlumatlarının sağlamlığı (YALNIZ-OXU, yalnız saylar və dövr/qrup adları — şəxs məlumatı yoxdur).

`manage.py shell`-ə STDIN ilə ötürülür (bax prod-exam-ops.yml). 2026-10-19 dalğasından sonra:
* eyni növ dövrlərin tarixləri üst-üstə düşürmü (kabinet indi bunu `full_clean` ilə rədd edir — köhnə
  belə dövrlər redaktədə ilişəcək);
* «Kurs» (`course_year`) göstərilməmiş aktiv qruplar (semestr açılışında jurnal yaranmır);
* qəbul ili müəyyən edilə bilməyən qruplar (qəbul ili üzrə plan seçimi ən son plana düşəcək);
* bayram təqvimi doldurulubmu.
"""

from collections import Counter

from django.apps import apps as django_apps

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
OrgUnit = django_apps.get_model("organizations", "OrgUnit")
AcademicHoliday = django_apps.get_model("organizations", "AcademicHoliday")
StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")

with rls_worker_atomic(), bypass_rls():
    from apps.organizations.public import group_cohort_year

    periods = list(
        AcademicPeriod.objects.order_by("organization_id", "period_type", "start_date").values(
            "id", "organization_id", "period_type", "name", "academic_year", "start_date", "end_date", "is_current"
        )
    )
    overlaps = []
    for i, a in enumerate(periods):
        for b in periods[i + 1 :]:
            if (b["organization_id"], b["period_type"]) != (a["organization_id"], a["period_type"]):
                continue
            if b["start_date"] <= a["end_date"] and a["start_date"] <= b["end_date"]:
                overlaps.append((a, b))
    print(f"periods_total: {len(periods)}")
    print(f"periods_current: {sum(1 for p in periods if p['is_current'])}")
    print(f"period_overlaps: {len(overlaps)}")
    for a, b in overlaps[:20]:
        print(
            f"  overlap: {a['academic_year']} {a['name']} ({a['start_date']}..{a['end_date']})"
            f" <-> {b['academic_year']} {b['name']} ({b['start_date']}..{b['end_date']})"
        )

    groups = list(OrgUnit.objects.filter(unit_type="group", is_active=True, is_service_unit=False))
    with_students = set(
        StudentAcademicRecord.objects.filter(is_active=True, status="enrolled", group__isnull=False)
        .values_list("group_id", flat=True)
        .distinct()
    )
    no_course = [g for g in groups if not (g.settings or {}).get("course_year")]
    no_course_with_students = [g for g in no_course if g.pk in with_students]
    no_cohort = []
    for g in groups:
        try:
            year = group_cohort_year(g)
        except Exception:  # noqa: BLE001 — probe heç vaxt yıxılmasın
            year = None
        if not year:
            no_cohort.append(g)
    print(f"groups_active: {len(groups)} (tələbəsi olan: {len(with_students)})")
    print(f"groups_without_course_year: {len(no_course)} (tələbəsi olan: {len(no_course_with_students)})")
    for g in no_course_with_students[:25]:
        print(f"  no_course_year: {g.name}")
    print(f"groups_without_cohort_year: {len(no_cohort)}")
    for g in no_cohort[:25]:
        print(f"  no_cohort_year: {g.name}")

    holidays = Counter(AcademicHoliday.objects.values_list("kind", flat=True))
    print(f"holidays_total: {sum(holidays.values())} {dict(holidays)}")
