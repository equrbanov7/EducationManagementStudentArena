"""«Fənnimə aid apellyasiyalar» — kim nəyi görür (sahib 2026-10-21, kabinet bölməsi 2026-10-27).

YALNIZ-OXU görünüş; qərar hüququ heç kimə buradan verilmir (qərar imtahan mərkəzinin ``appeal.respond`` +
``appeal.decide`` açarı ilədir, ``services.permissions``).

**Müəllim əhatəsi** — müəllim öz tədris etdiyi açılışların tələbələrinin HƏMİN FƏNN üzrə apellyasiyalarını görür.
«Tədris edir» = açılışın jurnal sahibi (``CourseOffering.instructor``), cədvəl slotunu aparan müəllim
(``ScheduleSlot.instructor``, silinməmiş) və ya bölünmüş jurnalın AKTİV payı (``JournalShare`` — payda tələbələr
göstərilibsə yalnız onlar, boşdursa açılışın bütün tələbələri). Əlavə inzibati rol (dekan, kafedra müdiri, RİM
əməkdaşı …) əhatəni NƏ daraldır, NƏ genişləndirir.

**Nəzarət əhatəsi** (sahib 2026-10-27) — superadmin və aktiv təşkilatda ``ikt_rehber`` (RİM rəhbəri) üzvlüyü:
təşkilatın BÜTÜN apellyasiyaları (yenə yalnız-oxu).

Menyu görünürlüyü (:func:`teaching_section_visible`) eyni qaydadandır: nəzarət rolu, müəllim rolu və ya faktiki
tədris (tək ``EXISTS``). Tələbə (müəllim rolu olmayan) üçün sorğu getmir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q

from core.roles import ProfileRole, is_superadmin_user, user_has_any_role

_DROPPED = "dropped"
_TEACHER_ROLES = frozenset({ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER})
_STUDENT_ROLES = frozenset({ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT})


def _authenticated(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False))


def _model(app_label, name):
    try:
        return django_apps.get_model(app_label, name)
    except LookupError:  # pragma: no cover — modul quraşdırılmayıb
        return None


def is_rim_head(user, organization) -> bool:
    """Aktiv təşkilatda AKTİV ``ikt_rehber`` üzvlüyü varmı (rol adı normallaşdırılır)."""
    if not _authenticated(user) or organization is None:
        return False
    membership_model = _model("organizations", "Membership")
    if membership_model is None:
        return False
    names = membership_model.objects.filter(user=user, organization=organization, is_active=True).values_list(
        "role__name", flat=True
    )
    return any(ProfileRole.normalize_membership_role_name(name or "") == ProfileRole.IKT_REHBER for name in names)


def has_oversight(user, organization) -> bool:
    """Təşkilat üzrə BÜTÜN apellyasiyaları görən nəzarət rolu (superadmin / RİM rəhbəri)."""
    return is_superadmin_user(user) or is_rim_head(user, organization)


def _slot_offering_ids(user, organization):
    slot_model = _model("registrar", "ScheduleSlot")
    if slot_model is None:
        return None
    rows = slot_model.objects.filter(instructor_id=user.pk, organization_id=organization.pk)
    if hasattr(slot_model, "deleted_at"):
        rows = rows.filter(deleted_at__isnull=True)
    return rows.values("offering_id")


def _share_queryset(user, organization):
    share_model = _model("registrar", "JournalShare")
    if share_model is None:
        return None
    return share_model.objects.filter(teacher_id=user.pk, organization_id=organization.pk, is_active=True)


def taught_offering_ids(user, organization) -> list:
    """Jurnal sahibi və ya cədvəl slotunun müəllimi olduğu açılışlar (bölünmüş jurnal payı DAXİL DEYİL)."""
    if organization is None or not _authenticated(user):
        return []
    offering_model = _model("registrar", "CourseOffering")
    if offering_model is None:
        return []
    condition = Q(instructor_id=user.pk)
    slots = _slot_offering_ids(user, organization)
    if slots is not None:
        condition |= Q(pk__in=slots)
    return list(
        offering_model.objects.filter(organization_id=organization.pk).filter(condition).values_list("pk", flat=True)
    )


def teaches_any(user, organization) -> bool:
    """Bu təşkilatda heç olmasa bir açılışı tədris edirmi (sahib / slot / aktiv pay) — tək ``EXISTS``."""
    if organization is None or not _authenticated(user):
        return False
    offering_model = _model("registrar", "CourseOffering")
    if offering_model is None:
        return False
    condition = Q(instructor_id=user.pk)
    slots = _slot_offering_ids(user, organization)
    if slots is not None:
        condition |= Q(pk__in=slots)
    shares = _share_queryset(user, organization)
    if shares is not None:
        condition |= Q(pk__in=shares.values("offering_id"))
    return offering_model.objects.filter(organization_id=organization.pk).filter(condition).exists()


def teaching_section_visible(user, organization) -> bool:
    """Kabinet menyusu: nəzarət rolu, müəllim rolu və ya faktiki tədris (inzibati rol mane olmur)."""
    if not _authenticated(user):
        return False
    if is_superadmin_user(user):
        return True
    if organization is None:
        return False
    # Rol yoxlaması üzvlük keşindəndir (kabinet qabığı sorğu büdcəlidir); RİM rəhbəri ``ikt_rehber`` aliası ilə.
    if user_has_any_role(user, _TEACHER_ROLES | {ProfileRole.IKT_REHBER}):
        return True
    from .subject_scope import scope_for

    if scope_for(user, organization) is not None:
        return True
    if user_has_any_role(user, _STUDENT_ROLES):
        return False  # tələbə (müəllim rolu yoxdur) — sorğusuz
    if teaches_any(user, organization):
        return True
    from .subject_scope import exam_teacher_queryset

    return exam_teacher_queryset(user, organization).exists()


def allowed_pairs(user, organization) -> set:
    """Müəllimin görə bildiyi ``(tələbə_id, fənn_id)`` cütləri (bütöv açılışlar + bölünmüş jurnal payları)."""
    enrollment_model = _model("registrar", "Enrollment")
    if enrollment_model is None or organization is None or not _authenticated(user):
        return set()
    pairs = set()
    offering_ids = set(taught_offering_ids(user, organization))
    shares = _share_queryset(user, organization)
    share_enrollment_ids = set()
    if shares is not None:
        for share in shares.prefetch_related("enrollments"):
            picked = [row.pk for row in share.enrollments.all()]
            if picked:
                share_enrollment_ids.update(picked)
            else:
                offering_ids.add(share.offering_id)
    condition = Q(offering_id__in=offering_ids) if offering_ids else Q(pk__in=[])
    if share_enrollment_ids:
        condition |= Q(pk__in=share_enrollment_ids)
    if not offering_ids and not share_enrollment_ids:
        return pairs
    rows = enrollment_model.objects.filter(condition).exclude(status=_DROPPED)
    pairs.update(rows.values_list("student_id", "offering__subject_id"))
    return {(student_id, subject_id) for student_id, subject_id in pairs if student_id and subject_id}


def teaching_appeals_queryset(user, organization):
    """Müəllimin tədris etdiyi açılışların tələbələrinin həmin fənn üzrə apellyasiyaları (yalnız-oxu)."""
    from apps.appeals.models import Appeal

    pairs = allowed_pairs(user, organization)
    if not pairs:
        return Appeal.objects.none()
    student_ids = {student_id for student_id, _subject in pairs}
    subject_ids = {subject_id for _student, subject_id in pairs}
    candidates = Appeal.objects.filter(
        organization_id=organization.pk, exam__subject_id__in=subject_ids, student_id__in=student_ids
    )
    keep = [
        pk
        for pk, student_id, subject_id in candidates.values_list("pk", "student_id", "exam__subject_id")
        if (student_id, subject_id) in pairs
    ]
    return Appeal.objects.filter(pk__in=keep)


def scoped_appeals(user, organization):
    """``(queryset, org_wide)`` — bölmənin baza dəsti (nəzarət → bütün təşkilat, əks halda müəllim əhatəsi)."""
    from apps.appeals.models import Appeal

    if organization is None or not _authenticated(user):
        return Appeal.objects.none(), False
    if has_oversight(user, organization):
        return Appeal.objects.filter(organization_id=organization.pk), True
    from .subject_scope import exam_teacher_queryset, scoped_queryset

    return (
        teaching_appeals_queryset(user, organization)
        | scoped_queryset(user, organization)
        | exam_teacher_queryset(user, organization)
    ).distinct(), False


__all__ = [
    "allowed_pairs",
    "has_oversight",
    "is_rim_head",
    "scoped_appeals",
    "taught_offering_ids",
    "teaches_any",
    "teaching_appeals_queryset",
    "teaching_section_visible",
]
