"""«Öz əhatə» resolver-i — tələbə + heyət rolu qapısının registrar tərəfi (sahib qaydası 2026-11-08).

Qapının özü :mod:`apps.organizations.self_conflict`-dədir (organizations registrar-ı import edə bilmir);
bu resolver ``RegistrarConfig.ready()``-də qoşulur və YALNIZ qarışıq (tələbə + heyət) istifadəçi üçün çağırılır.

Əhatə (fail-closed — şübhəli halda daha çox gizlədir):

* aktiv akademik qeydi (``enrolled`` / ``academic_leave``) olan qruplar;
* həmin qrupların alt qrupları, ana qrupu və ana qrupun digər alt qrupları (:func:`apps.registrar.subgroup_rollup.group_family` — reyestr izi
  ``settings.parent_group`` və ya ad şablonu);
* bu qrup ailəsindəki bütün aktiv qeydlər (qrup yoldaşları);
* qrup ailəsinin bütün açılışları + özünün yazıldığı (hər statusda) açılışlar.

Ən çoxu 6 sorğu, nəticə request ömrü ərzində ``user``-də saxlanılır (bax ``organizations.self_conflict.own_scope``).
"""

from __future__ import annotations

from django.db.models import Q

from apps.organizations.public import build_own_scope

from .models import AcademicStatus, CourseOffering, Enrollment, StudentAcademicRecord

#: «Təhsil alan» statuslar — xaric/məzun qeydi qapını AÇMIR.
STUDYING_STATUSES = (AcademicStatus.ENROLLED, AcademicStatus.ACADEMIC_LEAVE)


def resolve_own_scope(user, organization, student=None):
    """``student`` — tələbə kimi baxılan hesab (defolt ``user``); sahib 2026-11-09: eyni FİN-li bağlı tələbə hesabı."""
    from django.apps import apps as django_apps

    from .subgroup_rollup import group_family

    student = student or user
    own_group_ids = set(
        StudentAcademicRecord.objects.filter(
            organization=organization, student=student, is_active=True, status__in=STUDYING_STATUSES
        )
        .exclude(group_id=None)
        .values_list("group_id", flat=True)
    )
    if not own_group_ids:
        # Akademik qeydi yoxdursa yenə də özünün yazıldığı jurnallar qorunur.
        return build_own_scope(
            user_id=user.pk, student_ids=[student.pk], offering_ids=_offering_ids(student, organization, set())
        )
    org_unit = django_apps.get_model("organizations", "OrgUnit")
    groups = list(
        org_unit.objects.filter(organization=organization, pk__in=own_group_ids).only(
            "id", "name", "parent_id", "settings"
        )
    )
    family = set(own_group_ids)
    parents = {}
    for subs, ancestors in group_family(organization, groups).values():
        family.update(unit.pk for unit in subs)
        parents.update((unit.pk, unit) for unit in ancestors)
    family.update(parents)
    # Alt qrupdakı tələbə üçün ana qrupun DİGƏR alt qrupları da (632/6 İ-1 → 632/6 İ → 632/6 İ-2) «öz» sayılır.
    for subs, _ancestors in group_family(organization, list(parents.values())).values():
        family.update(unit.pk for unit in subs)
    mates = list(
        StudentAcademicRecord.objects.filter(
            organization=organization, group_id__in=family, is_active=True
        ).values_list("pk", "student_id")
    )
    own_records = StudentAcademicRecord.objects.filter(organization=organization, student=student).values_list(
        "pk", flat=True
    )
    return build_own_scope(
        user_id=user.pk,
        student_ids=[student.pk, *(student_id for _pk, student_id in mates)],
        record_ids=[pk for pk, _student_id in mates] + list(own_records),
        group_ids=family,
        offering_ids=_offering_ids(student, organization, family),
    )


def _offering_ids(user, organization, family):
    enrolled = Enrollment.objects.filter(organization=organization, student=user).values("offering_id")
    condition = Q(pk__in=enrolled)
    if family:
        condition |= Q(group_id__in=family)
    return CourseOffering.objects.filter(organization=organization).filter(condition).values_list("pk", flat=True)


__all__ = ["STUDYING_STATUSES", "resolve_own_scope"]
