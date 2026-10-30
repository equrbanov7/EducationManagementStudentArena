"""Teacher filters stay within the caller's already authorized journal queryset."""

from django.contrib.auth import get_user_model
from django.db.models import F, Q

from .models import JournalShare


def active_shares(queryset):
    return JournalShare.objects.filter(
        offering_id__in=queryset.order_by().values("pk"),
        organization_id=F("offering__organization_id"),
        is_active=True,
    )


def teachers_for(queryset):
    owners = queryset.exclude(instructor_id=None).order_by().values("instructor_id")
    return get_user_model().objects.filter(Q(pk__in=owners) | Q(pk__in=active_shares(queryset).values("teacher_id")))


def filter_teacher(queryset, teacher_id):
    shares = active_shares(queryset).filter(teacher_id=teacher_id)
    return queryset.filter(Q(instructor_id=teacher_id) | Q(pk__in=shares.values("offering_id")))
