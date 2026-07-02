"""student-org management section — sorğu qurma (part 1)."""

from django.core.paginator import Paginator
from django.db.models import Q

from apps.notifications.models import (
    MembershipRequestRoleType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from apps.organizations.models import Membership
from core.rls import bypass_rls

from ....models import ProfileRole, UserProfile
from ..constants import PROFILE_ROLE_LABELS, STUDENT_PENDING_INVITE_TITLE
from ..membership import _pending_student_request_queryset
from ..roles_map import _map_org_role_to_profile_role, _membership_request_role_type_for_profile_role


def _mgmt_section_queries(
    *,
    section,
    request,
    organization,
    is_superadmin,
    superadmin_user_ids,
    student_search,
    pending_search,
    unassigned_search,
    sent_invite_search,
    teacher_staff_search,
):
    from apps.organizations.public import get_unit_scope

    unit_scope = get_unit_scope(request.user, organization, request=request)
    scoped_unit_ids = None
    if not is_superadmin and unit_scope.is_unit_scoped:
        from apps.organizations.models import OrgUnit

        scoped_unit_ids = list(
            OrgUnit.objects.filter(organization=organization)
            .filter(unit_scope.unit_subtree_q())
            .values_list("pk", flat=True)
        )
    section["unit_scope_active"] = scoped_unit_ids is not None

    # Bypass RLS for all management queries.  The Membership and
    # StudentOrganizationRequest tables are RLS-protected in PostgreSQL.
    # Although the admin's current_org_id is set, cross-org subqueries
    # (e.g. pending_request_user_ids_any without org filter) and Django
    # JOIN-based .exclude() clauses return incomplete results without the
    # bypass, causing the unassigned-users list to appear empty and
    # invites to fail on production.  The middleware resets RLS context at
    # end-of-request, so enabling bypass here is safe.
    from core.rls import set_rls_bypass

    set_rls_bypass(True)

    sent_pending_invites_qs = (
        Membership.objects.filter(
            organization=organization,
            is_active=False,
            title=STUDENT_PENDING_INVITE_TITLE,
            user__is_active=True,
        )
        .exclude(user_id__in=superadmin_user_ids)
        .select_related("user", "assigned_by", "role", "user__profile")
        .order_by("-updated_at", "user__username")
    )
    if scoped_unit_ids is not None:
        # Unit-scoped idarəçi yalnız öz alt-ağacına ünvanlanmış dəvətləri görür.
        sent_pending_invites_qs = sent_pending_invites_qs.filter(scope_unit_id__in=scoped_unit_ids)
    sent_pending_invites = list(sent_pending_invites_qs)
    pending_invite_user_ids = {invite.user_id for invite in sent_pending_invites}
    sent_student_invites = []
    sent_teacher_invites = []
    sent_staff_invites = []
    for invite_membership in sent_pending_invites:
        mapped_role = _map_org_role_to_profile_role(invite_membership.role)
        invite_membership.management_role_key = mapped_role
        invite_membership.management_role_label = getattr(
            invite_membership.role, "display_name", ""
        ) or PROFILE_ROLE_LABELS.get(mapped_role, getattr(invite_membership.role, "name", "Üzv"))
        invite_membership.management_position = (
            getattr(getattr(invite_membership.user, "profile", None), "staff_position", "") or ""
        ).strip()
        if mapped_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
            sent_student_invites.append(invite_membership)
        elif mapped_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}:
            sent_teacher_invites.append(invite_membership)
        else:
            sent_staff_invites.append(invite_membership)

    section["sent_student_invites_total_count"] = len(sent_student_invites)
    section["sent_teacher_invites_total_count"] = len(sent_teacher_invites)
    section["sent_staff_invites_total_count"] = len(sent_staff_invites)

    if sent_invite_search:
        search_lower = sent_invite_search.lower()

        def _match_invite(invite_membership):
            return any(
                search_lower in (value or "").lower()
                for value in [
                    invite_membership.user.username,
                    invite_membership.user.email,
                    invite_membership.user.first_name,
                    invite_membership.user.last_name,
                    invite_membership.management_role_label,
                    invite_membership.management_position,
                ]
            )

        sent_student_invites = [invite for invite in sent_student_invites if _match_invite(invite)]
        sent_teacher_invites = [invite for invite in sent_teacher_invites if _match_invite(invite)]
        sent_staff_invites = [invite for invite in sent_staff_invites if _match_invite(invite)]

    legacy_requested_profiles = (
        UserProfile.objects.filter(
            user__is_active=True,
            organization__isnull=True,
            role__in=[
                ProfileRole.STUDENT,
                ProfileRole.LEAD_STUDENT,
                ProfileRole.TEACHER,
                ProfileRole.ASSISTANT_TEACHER,
                ProfileRole.MEMBER,
                ProfileRole.HR,
            ],
        )
        .exclude(user__id__in=superadmin_user_ids)
        .filter(
            Q(requested_organization=organization)
            | Q(
                requested_organization__isnull=True,
                requested_organization_name__iexact=organization.name,
            )
        )
        .exclude(user_id__in=pending_invite_user_ids)
    )
    legacy_user_ids = set(legacy_requested_profiles.values_list("user_id", flat=True))
    if legacy_user_ids:
        with bypass_rls():
            existing_pending_request_keys = set(
                _pending_student_request_queryset(
                    organization=organization,
                    statuses=[StudentOrganizationRequestStatus.PENDING],
                )
                .filter(user_id__in=legacy_user_ids)
                .values_list("user_id", "role_type")
            )
            missing_pending_requests = []
            for legacy_profile in legacy_requested_profiles.select_related("user"):
                legacy_role_type = _membership_request_role_type_for_profile_role(legacy_profile.role)
                if (legacy_profile.user_id, legacy_role_type) in existing_pending_request_keys:
                    continue
                missing_pending_requests.append(
                    StudentOrganizationRequest(
                        user=legacy_profile.user,
                        organization=organization,
                        role_type=legacy_role_type,
                        message=(legacy_profile.requested_organization_message or "").strip(),
                        status=StudentOrganizationRequestStatus.PENDING,
                    )
                )
            if missing_pending_requests:
                StudentOrganizationRequest.objects.bulk_create(missing_pending_requests)

    students = (
        UserProfile.objects.filter(user__is_active=True)
        .exclude(user__id__in=superadmin_user_ids)
        .filter(
            Q(
                organization=organization,
                role__in=[ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT],
            )
            | Q(
                user__memberships__organization=organization,
                user__memberships__is_active=True,
                user__memberships__role__name="student",
            )
        )
        .select_related("user")
        .distinct()
        .order_by("user__username")
    )
    if scoped_unit_ids is not None:
        # Dekan/kafedra müdürü yalnız öz alt-ağacına bağlı tələbələri görür.
        students = students.filter(
            user__memberships__organization=organization,
            user__memberships__is_active=True,
            user__memberships__scope_unit_id__in=scoped_unit_ids,
        )
    section["students_total_count"] = students.count()
    if student_search:
        students = students.filter(
            Q(user__username__icontains=student_search)
            | Q(user__email__icontains=student_search)
            | Q(user__first_name__icontains=student_search)
            | Q(user__last_name__icontains=student_search)
        )

    pending_requested_students = (
        _pending_student_request_queryset(
            organization=organization,
            statuses=[
                StudentOrganizationRequestStatus.PENDING,
                StudentOrganizationRequestStatus.AUTO_CLOSED,
            ],
        )
        .filter(role_type=MembershipRequestRoleType.STUDENT)
        .filter(user__is_active=True)
        .exclude(user_id__in=superadmin_user_ids)
        .exclude(user_id__in=pending_invite_user_ids)
        .select_related("user", "organization", "user__profile", "user__profile__organization")
        .order_by("-created_at", "user__username")
    )
    if scoped_unit_ids is not None:
        # Təşkilata qoşulma müraciətləri org-səviyyəli intake axınıdır —
        # unit-scoped idarəçi (dekan/kafedra müdürü) bunları idarə etmir.
        pending_requested_students = pending_requested_students.none()
    section["pending_requested_students_total_count"] = pending_requested_students.count()
    if pending_search:
        pending_requested_students = pending_requested_students.filter(
            Q(user__username__icontains=pending_search)
            | Q(user__email__icontains=pending_search)
            | Q(user__first_name__icontains=pending_search)
            | Q(user__last_name__icontains=pending_search)
            | Q(message__icontains=pending_search)
            | Q(resolution_note__icontains=pending_search)
        )

    with bypass_rls():
        pending_request_user_ids_any = list(
            _pending_student_request_queryset(statuses=[StudentOrganizationRequestStatus.PENDING]).values_list(
                "user_id", flat=True
            )
        )

    unassigned_students = (
        UserProfile.objects.filter(
            user__is_active=True,
            organization__isnull=True,
            role__in=[ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT],
        )
        .exclude(user__id__in=superadmin_user_ids)
        .exclude(user_id__in=pending_request_user_ids_any)
        .exclude(user_id__in=pending_invite_user_ids)
        .exclude(
            user__memberships__organization=organization,
            user__memberships__is_active=True,
        )
        .filter(
            requested_organization__isnull=True,
        )
        .select_related("user", "requested_organization")
        .distinct()
        .order_by("user__username")
    )
    if scoped_unit_ids is not None:
        # Sərbəst (heç bir təşkilata bağlı olmayan) istifadəçilər org-səviyyəli
        # intake siyahısıdır — unit-scoped idarəçiyə göstərilmir.
        unassigned_students = unassigned_students.none()
    section["unassigned_students_total_count"] = unassigned_students.count()
    if unassigned_search:
        unassigned_students = unassigned_students.filter(
            Q(user__username__icontains=unassigned_search)
            | Q(user__email__icontains=unassigned_search)
            | Q(user__first_name__icontains=unassigned_search)
            | Q(user__last_name__icontains=unassigned_search)
        )

    unassigned_teachers = (
        UserProfile.objects.filter(
            user__is_active=True,
            organization__isnull=True,
            role__in=[ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER],
        )
        .exclude(user__id__in=superadmin_user_ids)
        .exclude(user_id__in=pending_request_user_ids_any)
        .exclude(user_id__in=pending_invite_user_ids)
        .exclude(
            user__memberships__organization=organization,
            user__memberships__is_active=True,
        )
        .filter(
            requested_organization__isnull=True,
        )
        .select_related("user", "requested_organization")
        .distinct()
        .order_by("user__username")
    )
    if scoped_unit_ids is not None:
        unassigned_teachers = unassigned_teachers.none()
    section["unassigned_teachers_total_count"] = unassigned_teachers.count()
    if teacher_staff_search:
        unassigned_teachers = unassigned_teachers.filter(
            Q(user__username__icontains=teacher_staff_search)
            | Q(user__email__icontains=teacher_staff_search)
            | Q(user__first_name__icontains=teacher_staff_search)
            | Q(user__last_name__icontains=teacher_staff_search)
            | Q(department__icontains=teacher_staff_search)
        )

    unassigned_staff = (
        UserProfile.objects.filter(
            user__is_active=True,
            organization__isnull=True,
            role__in=[ProfileRole.MEMBER, ProfileRole.HR],
        )
        .exclude(user__id__in=superadmin_user_ids)
        .exclude(user_id__in=pending_request_user_ids_any)
        .exclude(user_id__in=pending_invite_user_ids)
        .exclude(
            user__memberships__organization=organization,
            user__memberships__is_active=True,
        )
        .filter(
            requested_organization__isnull=True,
        )
        .select_related("user", "requested_organization")
        .distinct()
        .order_by("user__username")
    )
    if scoped_unit_ids is not None:
        unassigned_staff = unassigned_staff.none()
    section["unassigned_staff_total_count"] = unassigned_staff.count()
    if teacher_staff_search:
        unassigned_staff = unassigned_staff.filter(
            Q(user__username__icontains=teacher_staff_search)
            | Q(user__email__icontains=teacher_staff_search)
            | Q(user__first_name__icontains=teacher_staff_search)
            | Q(user__last_name__icontains=teacher_staff_search)
            | Q(department__icontains=teacher_staff_search)
            | Q(staff_position__icontains=teacher_staff_search)
        )

    students_page = request.GET.get(section["students_page_param"])
    pending_page = request.GET.get(section["pending_page_param"])
    unassigned_page = request.GET.get(section["unassigned_page_param"])
    sent_invites_page = request.GET.get(section["sent_invites_page_param"])
    teacher_unassigned_page = request.GET.get(section["teacher_unassigned_page_param"])
    teacher_invites_page = request.GET.get(section["teacher_invites_page_param"])
    staff_unassigned_page = request.GET.get(section["staff_unassigned_page_param"])
    staff_invites_page = request.GET.get(section["staff_invites_page_param"])
    teacher_staff_page = request.GET.get(section["teacher_staff_page_param"])
    section["students"] = Paginator(students, 12).get_page(students_page)
    section["pending_requested_students"] = Paginator(pending_requested_students, 12).get_page(pending_page)
    section["unassigned_students"] = Paginator(unassigned_students, 12).get_page(unassigned_page)
    section["sent_student_invites"] = Paginator(sent_student_invites, 12).get_page(sent_invites_page)
    section["unassigned_teachers"] = Paginator(unassigned_teachers, 12).get_page(teacher_unassigned_page)
    section["sent_teacher_invites"] = Paginator(sent_teacher_invites, 12).get_page(teacher_invites_page)
    section["unassigned_staff"] = Paginator(unassigned_staff, 12).get_page(staff_unassigned_page)
    section["sent_staff_invites"] = Paginator(sent_staff_invites, 12).get_page(staff_invites_page)

    teacher_staff_pending_qs = (
        StudentOrganizationRequest.objects.filter(
            organization=organization,
            status=StudentOrganizationRequestStatus.PENDING,
            role_type__in=[MembershipRequestRoleType.TEACHER, MembershipRequestRoleType.STAFF],
            user__is_active=True,
        )
        .exclude(user_id__in=superadmin_user_ids)
        .exclude(user_id__in=pending_invite_user_ids)
        .select_related("user", "user__profile")
        .order_by("-created_at", "user__username")
    )
    if scoped_unit_ids is not None:
        # Müəllim/əməkdaş qoşulma müraciətləri də org-səviyyəli intake-dir.
        teacher_staff_pending_qs = teacher_staff_pending_qs.none()
    section["pending_teacher_requests_total_count"] = teacher_staff_pending_qs.filter(
        role_type=MembershipRequestRoleType.TEACHER
    ).count()
    section["pending_staff_requests_total_count"] = teacher_staff_pending_qs.filter(
        role_type=MembershipRequestRoleType.STAFF
    ).count()
    if teacher_staff_search:
        teacher_staff_pending_qs = teacher_staff_pending_qs.filter(
            Q(user__username__icontains=teacher_staff_search)
            | Q(user__email__icontains=teacher_staff_search)
            | Q(user__first_name__icontains=teacher_staff_search)
            | Q(user__last_name__icontains=teacher_staff_search)
            | Q(message__icontains=teacher_staff_search)
        )
    section["pending_teacher_staff_requests"] = Paginator(teacher_staff_pending_qs, 12).get_page(teacher_staff_page)

    teacher_requests_qs = teacher_staff_pending_qs.filter(role_type=MembershipRequestRoleType.TEACHER)
    staff_requests_qs = teacher_staff_pending_qs.filter(role_type=MembershipRequestRoleType.STAFF)
    section["pending_teacher_requests"] = Paginator(
        teacher_requests_qs,
        12,
    ).get_page(request.GET.get(section["teacher_requests_page_param"]))
    section["pending_staff_requests"] = Paginator(
        staff_requests_qs,
        12,
    ).get_page(request.GET.get(section["staff_requests_page_param"]))

    active_member_qs = (
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            user__is_active=True,
        )
        .exclude(user_id__in=superadmin_user_ids)
        .select_related("user", "role", "user__profile")
        .order_by("user_id", "-is_primary", "-role__level", "role__display_name")
    )
    if scoped_unit_ids is not None:
        # Dekan/kafedra müdürü yalnız öz alt-ağacına bağlı müəllim/əməkdaşları görür.
        active_member_qs = active_member_qs.filter(scope_unit_id__in=scoped_unit_ids)

    def _split_non_student_members(memberships):
        teacher_member_list = []
        staff_member_list = []
        seen_member_user_ids = set()
        removable_member_roles = {
            ProfileRole.STUDENT,
            ProfileRole.LEAD_STUDENT,
            ProfileRole.TEACHER,
            ProfileRole.ASSISTANT_TEACHER,
            ProfileRole.MEMBER,
            ProfileRole.HR,
        }
        for membership in memberships:
            if membership.user_id in seen_member_user_ids:
                continue
            seen_member_user_ids.add(membership.user_id)
            mapped_role = _map_org_role_to_profile_role(membership.role)
            membership.management_role_key = mapped_role
            membership.management_role_label = getattr(
                membership.role,
                "display_name",
                "",
            ) or PROFILE_ROLE_LABELS.get(mapped_role, membership.role.name)
            membership.management_position = (getattr(membership.user.profile, "staff_position", "") or "").strip()
            membership.management_can_remove = mapped_role in removable_member_roles and membership.user_id != getattr(
                organization, "owner_id", None
            )

            if mapped_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
                continue
            if mapped_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}:
                teacher_member_list.append(membership)
                continue
            staff_member_list.append(membership)

        return teacher_member_list, staff_member_list

    all_teacher_members, all_staff_members = _split_non_student_members(active_member_qs)
    section["teacher_members_total_count"] = len(all_teacher_members)
    section["staff_members_total_count"] = len(all_staff_members)

    if teacher_staff_search:
        active_member_qs = active_member_qs.filter(
            Q(user__username__icontains=teacher_staff_search)
            | Q(user__email__icontains=teacher_staff_search)
            | Q(user__first_name__icontains=teacher_staff_search)
            | Q(user__last_name__icontains=teacher_staff_search)
            | Q(role__display_name__icontains=teacher_staff_search)
            | Q(role__name__icontains=teacher_staff_search)
        )

    teacher_members, staff_members = _split_non_student_members(active_member_qs)
    return teacher_members, staff_members
