"""
Organization-request queries for accounts.
"""

from apps.notifications.models import StudentOrganizationRequest


def pending_student_request_queryset(*, user=None, organization=None, statuses=None):
    """Return student organization requests filtered by the provided criteria."""
    query = StudentOrganizationRequest.objects.all()

    if statuses:
        query = query.filter(status__in=list(statuses))
    if user is not None:
        query = query.filter(user=user)
    if organization is not None:
        query = query.filter(organization=organization)

    return query


__all__ = ["pending_student_request_queryset"]
