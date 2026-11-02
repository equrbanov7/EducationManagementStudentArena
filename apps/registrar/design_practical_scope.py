"""Design subject ownership limits a legacy practical label; never infer from student group."""

from django.db.models import F, Q

# Structural unit names, not role names or user-controlled subject-title substrings.
DESIGN_CHAIR_NAMES = ("Dizayn kafedrası", "Design department", "Department of Design")
MEMO = "_design_practical_label_memo"


def scope_q():
    names = Q()
    for name in DESIGN_CHAIR_NAMES:
        names |= Q(subject__chair_unit__name__iexact=name)
    return names & Q(
        subject__chair_unit__organization_id=F("organization_id"),
        subject__organization_id=F("organization_id"),
        subject__chair_unit__unit_type="chair",
    )


def is_design_offering(offering):
    if offering is None or not getattr(offering, "pk", None):
        return False
    if MEMO in offering.__dict__:
        return offering.__dict__[MEMO]
    from .models import CourseOffering

    if type(offering).subject.is_cached(offering) and type(offering.subject).chair_unit.is_cached(offering.subject):
        subject, chair = offering.subject, offering.subject.chair_unit
        value = bool(
            chair
            and chair.organization_id == offering.organization_id == subject.organization_id
            and chair.unit_type == "chair"
            and chair.name.casefold() in {name.casefold() for name in DESIGN_CHAIR_NAMES}
        )
    else:
        value = CourseOffering.objects.filter(
            scope_q(), pk=offering.pk, organization_id=offering.organization_id
        ).exists()
    offering.__dict__[MEMO] = value
    return value
