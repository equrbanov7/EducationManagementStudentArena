"""Fənn ↔ Kurs (LMS) körpüsü (W1) — ``services``-dən köçürülüb (modul-ölçü büdcəsi, sxem/davranış eyni).

Köhnə ``services.ensure_offering_course`` / ``services.sync_offering_course_members`` adları
``apps.registrar.services``-də re-eksport olunur.
"""

from __future__ import annotations

from .models import Enrollment

# ── Fənn ↔ Kurs (LMS) körpüsü (W1) ───────────────────────────────────────────
#
# Registrar akademik planı ilə `courses` (məzmun) arasında bağ: offering üçün
# real Course yaradılır/bağlanır ki, tələbə "Fənlərim"də fənnə klik edəndə fənn
# içinə (mövzu/resurs) çatsın. `courses` modeli STATİK import olunmur (modul-
# sərhəd qrafı asiklik qalsın) — app registry ilə həll olunur.


def ensure_offering_course(*, offering, owner=None):
    """Idempotently link/create the LMS ``Course`` for *offering*.

    Owner precedence: explicit *owner* → the offering instructor → the org
    owner (Course.owner is required). Returns the linked Course."""
    from django.apps import apps as django_apps

    if offering.course_id:
        return offering.course

    Course = django_apps.get_model("courses", "Course")
    course_owner = owner or offering.instructor or offering.organization.owner
    course = Course.objects.create(
        owner=course_owner,
        title=offering.subject.name,
        organization=offering.organization,
        unit=offering.group,
        period=offering.period,
        status="published",
    )
    offering.course = course
    offering.save(update_fields=["course", "updated_at"])
    return course


def sync_offering_course_members(*, offering):
    """Grant the instructor + enrolled students access to the linked Course.

    So the "fənn içi" (course dashboard) is reachable by the section's students.
    Returns the number of student memberships created."""
    from django.apps import apps as django_apps

    if not offering.course_id:
        return 0
    CourseMembership = django_apps.get_model("courses", "CourseMembership")

    if offering.instructor_id:
        CourseMembership.objects.get_or_create(
            course_id=offering.course_id, user_id=offering.instructor_id, defaults={"role": "teacher"}
        )
    created = 0
    enrolled = offering.enrollments.filter(status=Enrollment.Status.ENROLLED).select_related("student")
    for enrollment in enrolled:
        _, was_created = CourseMembership.objects.get_or_create(
            course_id=offering.course_id, user=enrollment.student, defaults={"role": "student"}
        )
        created += int(was_created)
    return created


__all__ = ["ensure_offering_course", "sync_offering_course_members"]
