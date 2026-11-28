"""Şəxsi və struktur əhatəli cədvəl ixracı üçün oxu sorğuları."""

from django.apps import apps
from django.core.exceptions import PermissionDenied

from core.constants import OrgUnitType
from core.roles import ProfileRole, user_has_any_role

from . import schedule, schedule_manage
from .models import ScheduleSlot, StudentAcademicRecord
from .offering_chairs import official_offering_chairs
from .schedule_workbook import workbook_bytes  # noqa: F401


def has_personal_teaching(user, slots):
    return bool(slots) or user_has_any_role(user, (ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER))


def can_access_personal_export(user, organization):
    """At least one permitted period, using the same effective slots as the download."""
    from .schedule_stale_teachers import personal_teacher_slot_q

    if has_student_schedule(organization, user):
        return False
    if has_personal_teaching(user, ()):
        return True
    return ScheduleSlot.objects.filter(organization=organization).filter(personal_teacher_slot_q(user)).exists()


def has_student_schedule(organization, user):
    from .page_contexts import is_student_family_user

    return (
        is_student_family_user(organization, user)
        or StudentAcademicRecord.objects.filter(organization=organization, student=user, group__isnull=False).exists()
    )


def structure_choices(organization, offerings, *, chairs_by_offering=None):
    """Siyahıya yalnız əhatədəki qrupların fakültələri və fənləri aparan kafedralar çıxır."""
    if chairs_by_offering is None:
        chairs_by_offering = official_offering_chairs(offerings, organization.pk)
    units = apps.get_model("organizations", "OrgUnit").objects.filter(organization=organization)
    group_ancestors = {
        ancestor
        for path in offerings.order_by().values_list("group__path", flat=True).distinct()
        if path
        for ancestor in path.split("/")
    }
    chair_ids = {key for keys in chairs_by_offering.values() for key in keys}
    chair_ancestors = {
        ancestor
        for path in units.filter(pk__in=chair_ids).values_list("path", flat=True)
        for ancestor in path.split("/")
    }
    return {
        "faculties": list(
            units.filter(pk__in=group_ancestors, unit_type=OrgUnitType.FACULTY)
            .order_by("name")
            .values("id", "name", "path")
        ),
        "chairs": list(
            units.filter(pk__in=chair_ancestors, unit_type__in=(OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT))
            .order_by("name")
            .values("id", "name", "path")
        ),
    }


def _chosen(raw, choices):
    if not raw:
        return None
    for choice in choices:
        if str(choice["id"]) == raw:
            return choice
    raise PermissionDenied


def management_slots(user, organization, period, params):
    if not schedule_manage.can_view(user, organization):
        raise PermissionDenied
    permission = schedule_manage.read_permission(user, organization)
    offerings = schedule_manage.scoped_offerings(user, organization, period=period, permission=permission, widened=True)
    labels = []
    if params.get("faculty") or params.get("chair"):
        chair_map = official_offering_chairs(offerings, organization.pk)
        choices = structure_choices(organization, offerings, chairs_by_offering=chair_map)
        faculty = _chosen(params.get("faculty"), choices["faculties"])
        if faculty:
            offerings = offerings.filter(group__path__startswith=faculty["path"] + "/")
            labels.append(faculty["name"])
        chair = _chosen(params.get("chair"), choices["chairs"])
        if chair:
            related_chairs = {
                str(row["id"])
                for row in choices["chairs"]
                if row["id"] == chair["id"] or row["path"].startswith(chair["path"] + "/")
            }
            offerings = offerings.filter(pk__in=[key for key, ids in chair_map.items() if related_chairs & ids])
            labels.append(chair["name"])
    if params.get("group"):
        groups = schedule_manage.scoped_groups(user, organization, permission=permission, widened=True)
        group = _chosen(params["group"], groups.values("id", "name"))
        offerings = offerings.filter(group_id=group["id"])
        labels.append(group["name"])
    if params.get("teacher"):
        # Seçici və icazə paneldəki müəllim siyahısının eynisidir. Əlavə struktur filtrləri
        # kombinə ediləndə başqa fakültədə dərs keçirən müəllimin həmin dərsi ixraca düşmür.
        all_scoped = schedule_manage.scoped_offerings(
            user, organization, period=period, permission=permission, widened=True
        )
        assignments = schedule_manage.scoped_assignments(
            user, organization, period=period, permission=permission, widened=True
        )
        teachers = schedule_manage.scoped_teacher_rows(
            all_scoped, organization=organization, period=period, assignments=assignments
        )
        teacher = _chosen(params["teacher"], teachers)
        slots = schedule.get_teacher_schedule(
            organization=organization, teacher=teacher["id"], period=period, offerings=offerings
        )
        labels.append(teacher["name"])
        return slots, labels, teacher["name"]
    slots = schedule._slots_for(ScheduleSlot.objects.filter(organization=organization, offering__in=offerings))
    return slots, labels, ""
