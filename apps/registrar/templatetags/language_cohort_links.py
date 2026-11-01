"""Journal entry point follows the cohort registry's central permission scope."""

from django import template
from django.db.models import Q

from apps.registrar.integrity import is_authorized_instructor
from apps.registrar.language_cohorts import can_manage, department_choices
from apps.registrar.language_levels import LEVEL_RE
from apps.registrar.models import CourseOffering, LanguageLevelCohort

register = template.Library()


@register.inclusion_tag("registrar/partials/_language_cohort_entry.html", takes_context=True)
def language_cohort_entry(context):
    request = context.get("request")
    organization = getattr(request, "organization", None)
    user = getattr(request, "user", None)
    visible = False
    if organization and user and user.is_authenticated and user.is_active:
        visible = department_choices(user, organization).exists()
        if not visible and is_authorized_instructor(organization=organization, instructor=user):
            visible = (
                CourseOffering.objects.filter(
                    organization=organization, is_active=True, subject__name__iregex=LEVEL_RE.pattern
                )
                .filter(Q(instructor=user) | Q(shares__teacher=user, shares__is_active=True))
                .exists()
            )
    return {"visible": visible}


@register.inclusion_tag("registrar/partials/_language_cohort_manage_entry.html")
def language_cohort_manage_entry(offering, user):
    if not getattr(offering, "pk", None):
        return {"cohort": None}
    group = offering._state.fields_cache.get("group")
    if group is not None and not (group.settings or {}).get("language_level_cohort"):
        return {"cohort": None}
    cohort = (
        LanguageLevelCohort.objects.filter(organization_id=offering.organization_id, offering_id=offering.pk)
        .select_related("organization", "offering")
        .first()
    )
    return {"cohort": cohort if cohort is not None and can_manage(user, cohort) else None}
