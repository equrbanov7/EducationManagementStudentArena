"""Read-only list attribution and published-version presentation."""

from django.db.models import Case, CharField, Count, F, Q, Value, When
from django.db.models.functions import Coalesce
from django.utils.translation import pgettext_lazy

from apps.syllabus.public import STATUS_SORT_INDEX, SyllabusStatus
from core.person_names import clean_name_part

_CTX = "accounts.syllabus"


def full_name(user):
    if user is None:
        return ""
    profile = getattr(user, "profile", None)
    return getattr(profile, "full_name_with_patronymic", "") or user.get_full_name().strip() or user.username


def attribution(syllabus=None, offering=None):
    author = syllabus.author if syllabus is not None else None
    offering = syllabus.offering if syllabus is not None and syllabus.offering_id else offering
    teacher = offering.instructor if offering is not None and offering.instructor_id else None
    return {"author_name": full_name(author), "teacher_name": full_name(teacher)}


def published_version(syllabus):
    approved = syllabus.approved_version
    if approved is not None and approved.status == SyllabusStatus.APPROVED:
        return approved
    return syllabus.current_version


def published_queryset(queryset):
    return queryset.annotate(
        _published_status=Case(
            When(approved_version__status=SyllabusStatus.APPROVED, then=Value(SyllabusStatus.APPROVED)),
            default=Coalesce(F("current_version__status"), Value(SyllabusStatus.DRAFT)),
            output_field=CharField(),
        )
    )


def published_counts(queryset):
    counts = {status.value: 0 for status in SyllabusStatus}
    for item in queryset.order_by().values("_published_status").annotate(n=Count("pk")):
        counts[item["_published_status"]] = item["n"]
    counts["total"] = sum(counts.values())
    return counts


def published_sort(queryset, sort):
    if sort == "completion":
        return queryset.annotate(
            _published_percent=Case(
                When(approved_version__status=SyllabusStatus.APPROVED, then=F("approved_version__completion_percent")),
                default=F("current_version__completion_percent"),
            )
        ).order_by("-_published_percent", "subject__name", "pk")
    if sort != "status":
        return queryset
    return queryset.annotate(
        _published_rank=Case(
            *(When(_published_status=status, then=Value(rank)) for status, rank in STATUS_SORT_INDEX.items()),
            default=Value(99),
        )
    ).order_by("_published_rank", "subject__name", "pk")


def teacher_options(queryset, user):
    people = {str(user.pk): full_name(user)}
    fields = ("id", "first_name", "last_name", "profile__patronymic", "username")
    values = (
        queryset.order_by()
        .values_list(*(f"{prefix}__{field}" for prefix in ("author", "offering__instructor") for field in fields))
        .distinct()
    )
    for row in values:
        for person in (row[:5], row[5:]):
            pk, first, last, patronymic, username = person
            if pk is not None:
                people[str(pk)] = (
                    " ".join(value for value in (first, last, clean_name_part(patronymic)) if value).strip() or username
                )
    return [{"key": pk, "label": label} for pk, label in sorted(people.items(), key=lambda pair: pair[1])]


def teacher_filter(queryset, key):
    if not key:
        return queryset
    if not key.isascii() or not key.isdecimal() or len(key) > 19 or int(key) > 2**63 - 1:
        return queryset.none()
    return queryset.filter(Q(author_id=key) | Q(offering__instructor_id=key))


DRAFT_PRESERVED = pgettext_lazy(_CTX, "Yeni qaralama saxlanılır")
