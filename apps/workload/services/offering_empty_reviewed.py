"""Only explicitly reviewed empty courses may open without inventing a plan choice."""

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db.models import Q


def ensure_empty(sync, key):
    Record = apps.get_model("registrar.StudentAcademicRecord")
    Enrollment = apps.get_model("registrar.Enrollment")
    Choice = apps.get_model("registrar.GroupElectiveChoice")
    Offering = apps.get_model("registrar.CourseOffering")
    subject, period, group = key
    if (
        Record.objects.filter(organization_id=sync.org_id, group_id=group)
        .filter(Q(status="enrolled") | (Q(is_active=True) & ~Q(status__in=("graduated", "expelled"))))
        .exists()
        or Enrollment.objects.filter(organization_id=sync.org_id, offering__group_id=group).exists()
        or Choice.objects.filter(organization_id=sync.org_id, group_id=group, period_id=period).exists()
        or Offering.objects.filter(
            organization_id=sync.org_id, subject_id=subject, group_id=group, period_id=period
        ).exists()
    ):
        raise ValidationError("Reviewed empty group has academic records, enrollment, choice or journal.")
