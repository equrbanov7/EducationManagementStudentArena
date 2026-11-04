"""Teacher filters stay within the caller's already authorized journal queryset."""

from django.contrib.auth import get_user_model
from django.db.models import F, Q

from .models import JournalShare, Lesson


def active_shares(queryset):
    return JournalShare.objects.filter(
        offering_id__in=queryset.order_by().values("pk"),
        organization_id=F("offering__organization_id"),
        is_active=True,
    )


def teachers_for(queryset):
    owners = queryset.exclude(instructor_id=None).order_by().values("instructor_id")
    return get_user_model().objects.filter(Q(pk__in=owners) | Q(pk__in=active_shares(queryset).values("teacher_id")))


def taught_offering_ids(teacher_id):
    """Journals with lessons conducted in the teacher's name — their history after the load moved away.

    Owner 2026-11-04: a load moved to another teacher by mistake took the journal out of the admin «MÜƏLLİM»
    filter (owner/share only), so «Bu müəllimə bərpa et» had no row to sit on. The caller still filters its own
    authorized queryset; this only widens WHICH of those rows match the teacher, never what the actor may see.
    """
    return Lesson.objects.filter(instructor_id=teacher_id, organization_id=F("offering__organization_id")).values(
        "offering_id"
    )


def filter_teacher(queryset, teacher_id):
    shares = active_shares(queryset).filter(teacher_id=teacher_id)
    return queryset.filter(
        Q(instructor_id=teacher_id) | Q(pk__in=shares.values("offering_id")) | Q(pk__in=taught_offering_ids(teacher_id))
    )
