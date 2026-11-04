"""Teacher filters stay within the caller's already authorized journal queryset.

Broad list «MÜƏLLİM» filter = the selected teacher's OWN list (owner 2026-11-04). Before, the
filter was a bare ownership match (``instructor`` or an active share) over the whole broad set,
while the teacher's own list (and view-as) is the workload projection of
:mod:`apps.registrar.teacher_journal_list`: current load = positive workload (alias families,
canonical handovers) AND ownership/kind-share; history = recorded lessons/marks, handed-over
observer journals, master and owned-past history; split into «cari» / «tarixçə». The admin saw
owned journals outside the teacher's load and missed the history/observer ones. :func:`mirror`
runs that same authority with the teacher as subject, inside the viewer's own broad scope.
"""

from django.contrib.auth import get_user_model
from django.db.models import F, Q

from .models import JournalShare, Lesson, TeachingHandover


def active_shares(queryset):
    return JournalShare.objects.filter(
        offering_id__in=queryset.order_by().values("pk"),
        organization_id=F("offering__organization_id"),
        is_active=True,
    )


def teachers_for(queryset):
    """Picker candidates: owners, share holders, handed-over observers and real lesson authors."""
    offerings = queryset.order_by().values("pk")
    owners = queryset.exclude(instructor_id=None).order_by().values("instructor_id")
    observers = TeachingHandover.objects.filter(offering_id__in=offerings, reverted_at__isnull=True).values(
        "from_instructor_id"
    )
    authors = Lesson.objects.filter(offering_id__in=offerings).exclude(instructor_id=None).values("instructor_id")
    return get_user_model().objects.filter(
        Q(pk__in=owners)
        | Q(pk__in=active_shares(queryset).values("teacher_id"))
        | Q(pk__in=observers)
        | Q(pk__in=authors)
    )


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
    """Legacy ownership match — only when the teacher has no own-list authority (see :func:`mirror`)."""
    shares = active_shares(queryset).filter(teacher_id=teacher_id)
    return queryset.filter(
        Q(instructor_id=teacher_id) | Q(pk__in=shares.values("offering_id")) | Q(pk__in=taught_offering_ids(teacher_id))
    )


def mirror(queryset, teacher_id, organization):
    """``(teacher, queryset)`` — the teacher's own visible list inside the viewer's ``queryset``.

    ``teacher`` is ``None`` (queryset unchanged) when the id is not an active user holding
    same-tenant ``grade.input`` — such a teacher has no own list to mirror, and the caller keeps
    the legacy ownership filter so the admin can still find those journals.
    """
    from .journal_own_history import eligible
    from .teacher_journal_list import own_visible_queryset

    try:
        pk = int(teacher_id)
    except (TypeError, ValueError):
        return None, queryset
    teacher = get_user_model().objects.filter(pk=pk, is_active=True).first() if pk > 0 else None
    if teacher is None or organization is None or not eligible(teacher, organization):
        return None, queryset
    return teacher, own_visible_queryset(queryset, teacher, organization)
