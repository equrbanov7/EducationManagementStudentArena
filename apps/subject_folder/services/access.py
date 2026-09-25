"""Kim nəyi görür / edir — fənn qovluğunun icazə qaydaları (fail-closed).

Rollar:
  * **sahib** — qovluğu yaradan müəllim (``folder.owner``): məzmunu idarə edir,
    öz tədris etdiyi açılışlara təyin edir;
  * **qrupun müəllimi** — təyin olunmuş açılışın CANLI müəllimi
    (:func:`lookups.teaches_offering`): həmin qrupun göndərişlərini yoxlayır,
    qovluğun materiallarını görür;
  * **tələbə** — təyin olunmuş açılışda ``enrolled`` qeydiyyatlı: dərc edilmiş
    məzmunu görür, YALNIZ öz göndərişlərini görür;
  * **əhatəli əməkdaş** — ``journal.view`` əhatəsi açılışın qrupunu örtən və ya
    ``journal.correct`` org-wide daşıyıcısı: YALNIZ OXU;
  * **inzibatçı** — superuser / təşkilat sahibi / İKT (RİM) rəhbəri.

Tək-obyekt yoxlamaları ``can_*`` (bool), toplu siyahılar üçün ``*_q`` (Q)
funksiyaları var — siyahı sətir-sətir ``can_*`` çağırmır (N+1 yoxdur).
"""

from __future__ import annotations

from django.db.models import Q

from ..constants import ORG_VIEW_PERMISSIONS, STAFF_VIEW_PERMISSIONS, FolderStatus
from ..errors import FolderError
from . import lookups


def _scope(user, organization, permission):
    from apps.organizations.public import get_permission_scope

    return get_permission_scope(user, organization, permission)


# ── Əməkdaş əhatəsi ─────────────────────────────────────────────────────────


def staff_scope_covers_offering(user, offering) -> bool:
    """``journal.view`` əhatəsi qrupu örtür və ya ``journal.correct`` org-wide-dır."""
    if not lookups.is_authenticated(user) or offering is None:
        return False
    organization = offering.organization
    for permission in ORG_VIEW_PERMISSIONS:
        if _scope(user, organization, permission).is_org_wide:
            return True
    for permission in STAFF_VIEW_PERMISSIONS:
        if lookups.group_in_scope(_scope(user, organization, permission), organization, offering.group_id):
            return True
    return False


def staff_offerings_q(user, organization, *, field: str = "offering") -> Q | None:
    """Əhatəli əməkdaşın gördüyü açılışların Q-su (``field`` = açılış FK yolu); əhatə yoxdursa ``None``.

    ⚠️ Org-wide hal üçün BOŞ ``Q()`` qaytarılmır: ``x | Q()`` Django-da ``x``-ə
    bərabərdir (boş şərt OR-da düşür), yəni «hamısı» itərdi. Açıq şərt verilir.
    """
    everything = Q(**{f"{field}__organization": organization})
    for permission in ORG_VIEW_PERMISSIONS:
        if _scope(user, organization, permission).is_org_wide:
            return everything
    combined = None
    for permission in STAFF_VIEW_PERMISSIONS:
        scope = _scope(user, organization, permission)
        if not scope.has_structure_access:
            continue
        if scope.is_org_wide:
            return everything
        clause = lookups.scope_group_ids_q(scope, organization, field=f"{field}__group")
        combined = clause if combined is None else combined | clause
    return combined


# ── Qovluq ──────────────────────────────────────────────────────────────────


def can_manage_folder(user, folder) -> bool:
    """Məzmunu dəyişmək: sahib müəllim (aktiv ``grade.input``) və ya inzibatçı."""
    if not lookups.is_authenticated(user) or folder is None:
        return False
    if lookups.is_org_admin(user, folder.organization):
        return True
    return folder.owner_id == user.pk and lookups.has_instructor_authority(user, folder.organization)


def ensure_can_manage(user, folder) -> None:
    if not can_manage_folder(user, folder):
        raise FolderError.of("permission.not_owner")
    if folder.status == FolderStatus.ARCHIVED:
        raise FolderError.of("folder.archived")


def _active_assignments(folder):
    return list(folder.assignments.filter(is_active=True).select_related("offering", "offering__organization"))


def teaches_any_assignment(user, folder, assignments=None) -> bool:
    rows = _active_assignments(folder) if assignments is None else assignments
    return any(lookups.teaches_offering(user, row.offering) for row in rows)


def student_audience_offering_ids(folder) -> list:
    """Tələbə görünüşünün açıldığı açılışlar: qovluq AKTİV + aktiv təyinatlar."""
    if folder.status != FolderStatus.ACTIVE:
        return []
    return list(folder.assignments.filter(is_active=True).values_list("offering_id", flat=True))


def is_folder_student(user, folder) -> bool:
    offering_ids = student_audience_offering_ids(folder)
    if not offering_ids or not lookups.is_authenticated(user):
        return False
    return lookups.audience_enrollments(offering_ids).filter(student_id=user.pk).exists()


def can_view_folder(user, folder) -> bool:
    """Qovluğu açmaq (tələbə yalnız dərc edilmiş məzmunu görür — bax ``can_view_material``)."""
    if can_manage_folder(user, folder):
        return True
    assignments = _active_assignments(folder)
    if teaches_any_assignment(user, folder, assignments):
        return True
    if is_folder_student(user, folder):
        return True
    return any(staff_scope_covers_offering(user, row.offering) for row in assignments)


def is_staff_viewer(user, folder) -> bool:
    """Qovluğu idarə etməyən, amma tələbə görünüşündən artıq görən (müəllim/əməkdaş)."""
    if can_manage_folder(user, folder):
        return True
    assignments = _active_assignments(folder)
    if teaches_any_assignment(user, folder, assignments):
        return True
    return any(staff_scope_covers_offering(user, row.offering) for row in assignments)


def _student_can_see_item(item) -> bool:
    topic = getattr(item, "topic", None)
    if topic is not None and topic.is_archived:
        return False
    return bool(item.is_published) and not item.is_archived


def can_view_material(user, material) -> bool:
    folder = material.folder
    if is_staff_viewer(user, folder):
        return True
    return _student_can_see_item(material) and is_folder_student(user, folder)


def can_view_task(user, task) -> bool:
    folder = task.folder
    if is_staff_viewer(user, folder):
        return True
    return _student_can_see_item(task) and is_folder_student(user, folder)


# ── Təyinat / göndəriş ──────────────────────────────────────────────────────


def can_review_assignment(user, assignment) -> bool:
    """Göndərişi yoxlamaq: təyin olunmuş açılışın CANLI müəllimi (və ya inzibatçı)."""
    return lookups.teaches_offering(user, assignment.offering)


def ensure_can_review(user, assignment) -> None:
    if not can_review_assignment(user, assignment):
        raise FolderError.of("permission.not_reviewer")


def can_view_submission(user, submission) -> bool:
    if not lookups.is_authenticated(user):
        return False
    if submission.student_id == user.pk:
        return True
    assignment = submission.assignment
    if can_review_assignment(user, assignment):
        return True
    if can_manage_folder(user, assignment.folder):
        return True
    return staff_scope_covers_offering(user, assignment.offering)


def reviewable_assignments_q(user, organization, *, prefix: str = "") -> Q:
    """``FolderAssignment`` (və ya ``<prefix>`` yolu) Q — aktorun yoxlaya bildiyi təyinatlar."""
    if lookups.is_org_admin(user, organization):
        return Q(**{f"{prefix}organization": organization})
    if not lookups.has_instructor_authority(user, organization):
        return Q(pk__in=[])
    return Q(**{f"{prefix}organization": organization}) & lookups.taught_offerings_q(user, prefix=f"{prefix}offering__")


def visible_submissions_q(user, organization) -> Q:
    """``Submission`` Q — aktorun görə bildiyi bütün cəhdlər (öz + yoxladığı + sahibi + əhatə)."""
    if not lookups.is_authenticated(user):
        return Q(pk__in=[])
    if lookups.is_org_admin(user, organization):
        return Q(organization=organization)
    clause = Q(student_id=user.pk) | reviewable_assignments_q(user, organization, prefix="assignment__")
    if lookups.has_instructor_authority(user, organization):
        clause |= Q(task__folder__owner_id=user.pk)
    staff = staff_offerings_q(user, organization, field="assignment__offering")
    if staff is not None:
        clause |= staff
    return Q(organization=organization) & clause


__all__ = [
    "can_manage_folder",
    "can_review_assignment",
    "can_view_folder",
    "can_view_material",
    "can_view_submission",
    "can_view_task",
    "ensure_can_manage",
    "ensure_can_review",
    "is_folder_student",
    "is_staff_viewer",
    "reviewable_assignments_q",
    "staff_offerings_q",
    "staff_scope_covers_offering",
    "student_audience_offering_ids",
    "teaches_any_assignment",
    "visible_submissions_q",
]
