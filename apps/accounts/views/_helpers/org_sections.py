"""
Student-organization management/request section builders.

These functions assemble the template context for the
"student-organization-management" and "student-organization-request" profile
sections. They are large because each section drives many paginated tabs;
keeping them isolated here keeps the rest of the helpers package readable.
"""

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q

from django.urls import reverse

from apps.notifications.models import (
    MembershipRequestRoleType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from core.constants import OrganizationType
from core.rls import bypass_rls

from ...models import ProfileRole
from .constants import (
    PROFILE_ROLE_LABELS,
    STUDENT_ORG_MANAGEMENT_MIN_LEVEL,
    STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
    STUDENT_PENDING_INVITE_TITLE,
)
from .formatting import _append_query_params, _query_string
from .membership import _pending_student_request_queryset
from .roles_map import (
    _map_org_role_to_profile_role,
    _membership_request_role_label,
    _membership_request_role_type_for_profile_role,
)

User = get_user_model()


def _build_student_org_management_section(
    *,
    request,
    organization,
    is_superadmin,
    user_level,
    default_view=None,
    teacher_student_only=False,
    can_manage_students=True,
    can_invite_members=True,
):
    from apps.organizations.models import Membership
    from apps.organizations.models import Organization as OrganizationModel

    from ...models import UserProfile

    student_search = request.GET.get("student_org_search", "")
    pending_search = request.GET.get("student_org_pending_search", "")
    unassigned_search = request.GET.get("student_org_unassigned_search", "")
    sent_invite_search = request.GET.get("student_org_sent_invite_search", "")
    teacher_staff_search = request.GET.get("student_org_ts_search", "")
    organization_search = request.GET.get("organization_search", "")
    organization_status_filter = (request.GET.get("organization_status", "") or "").strip().lower()
    organization_type_filter = (request.GET.get("organization_type", "") or "").strip().lower()
    superadmin_user_ids = list(
        User.objects.filter(Q(is_superuser=True) | Q(profile__role=ProfileRole.SUPERADMIN)).values_list("id", flat=True)
    )

    allowed_management_views = {"students", "teachers", "staff"}
    if teacher_student_only:
        allowed_management_views = {"students"}
    if is_superadmin:
        allowed_management_views.add("organizations")

    fallback_management_view = default_view or (
        "organizations" if is_superadmin and organization is None else "students"
    )
    management_view = (request.GET.get("management_view") or fallback_management_view).strip().lower()
    if management_view not in allowed_management_views:
        management_view = (
            fallback_management_view if fallback_management_view in allowed_management_views else "students"
        )

    student_tab = (request.GET.get("student_tab") or "members").strip().lower()
    if student_tab not in {"members", "pending", "unassigned", "invites"}:
        student_tab = "members"

    teacher_tab = (request.GET.get("teacher_tab") or "members").strip().lower()
    if teacher_tab not in {"members", "requests", "unassigned", "invites"}:
        teacher_tab = "members"

    staff_tab = (request.GET.get("staff_tab") or "members").strip().lower()
    if staff_tab not in {"members", "requests", "unassigned", "invites"}:
        staff_tab = "members"

    section = {
        "organization": organization,
        "is_superadmin": is_superadmin,
        "teacher_student_only": teacher_student_only,
        "active_management_view": management_view,
        "active_student_tab": student_tab,
        "active_teacher_tab": teacher_tab,
        "active_staff_tab": staff_tab,
        "management_view_options": [],
        "student_tab_options": [],
        "teacher_tab_options": [],
        "staff_tab_options": [],
        "students": [],
        "pending_requested_students": [],
        "unassigned_students": [],
        "sent_student_invites": [],
        "teacher_members": [],
        "staff_members": [],
        "unassigned_teachers": [],
        "sent_teacher_invites": [],
        "unassigned_staff": [],
        "sent_staff_invites": [],
        "pending_teacher_requests": [],
        "pending_staff_requests": [],
        "pending_teacher_staff_requests": [],
        "students_total_count": 0,
        "pending_requested_students_total_count": 0,
        "unassigned_students_total_count": 0,
        "sent_student_invites_total_count": 0,
        "teacher_members_total_count": 0,
        "pending_teacher_requests_total_count": 0,
        "unassigned_teachers_total_count": 0,
        "sent_teacher_invites_total_count": 0,
        "staff_members_total_count": 0,
        "pending_staff_requests_total_count": 0,
        "unassigned_staff_total_count": 0,
        "sent_staff_invites_total_count": 0,
        "organization_records": [],
        "student_search_query": student_search,
        "pending_search_query": pending_search,
        "unassigned_search_query": unassigned_search,
        "sent_invite_search_query": sent_invite_search,
        "teacher_staff_search_query": teacher_staff_search,
        "organization_search_query": organization_search,
        "organization_status_filter": organization_status_filter,
        "organization_type_filter": organization_type_filter,
        "post_next_url": "",
        "access_denied_message": "",
        "can_manage_students": False,
        "can_invite_members": False,
        "pending_org_count": 0,
        "students_page_param": "student_org_members_page",
        "students_pagination_query": "",
        "pending_page_param": "student_org_pending_page",
        "pending_pagination_query": "",
        "unassigned_page_param": "student_org_unassigned_page",
        "unassigned_pagination_query": "",
        "sent_invites_page_param": "student_org_sent_invites_page",
        "sent_invites_pagination_query": "",
        "teacher_staff_page_param": "student_org_ts_page",
        "teacher_staff_pagination_query": "",
        "teacher_members_page_param": "teacher_members_page",
        "teacher_members_pagination_query": "",
        "staff_members_page_param": "staff_members_page",
        "staff_members_pagination_query": "",
        "teacher_requests_page_param": "teacher_requests_page",
        "teacher_requests_pagination_query": "",
        "teacher_unassigned_page_param": "teacher_unassigned_page",
        "teacher_unassigned_pagination_query": "",
        "teacher_invites_page_param": "teacher_invites_page",
        "teacher_invites_pagination_query": "",
        "staff_requests_page_param": "staff_requests_page",
        "staff_requests_pagination_query": "",
        "staff_unassigned_page_param": "staff_unassigned_page",
        "staff_unassigned_pagination_query": "",
        "staff_invites_page_param": "staff_invites_page",
        "staff_invites_pagination_query": "",
        "organizations_page_param": "organization_page",
        "organizations_pagination_query": "",
    }

    if organization is None:
        if is_superadmin and management_view == "organizations":
            # Superadmin "organizations" view — extracted to a dedicated,
            # unit-testable service (FAZA 9). Lazy import keeps the
            # _helpers <-> services dependency one-directional.
            from ...services.org_management import build_superadmin_organizations_view

            return build_superadmin_organizations_view(
                request=request,
                section=section,
                organization_search=organization_search,
                organization_status_filter=organization_status_filter,
                organization_type_filter=organization_type_filter,
            )

        section["access_denied_message"] = "Aktiv təşkilat tapılmadı."
        return section

    if not is_superadmin and not teacher_student_only and user_level < STUDENT_ORG_MANAGEMENT_MIN_LEVEL:
        section["access_denied_message"] = (
            "Bu bölmə üçün minimum HR, təşkilat admini və ya daha yüksək səviyyə tələb olunur."
        )
        return section

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

    sent_pending_invites = list(
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

    section["teacher_members"] = Paginator(
        teacher_members,
        12,
    ).get_page(request.GET.get(section["teacher_members_page_param"]))
    section["staff_members"] = Paginator(
        staff_members,
        12,
    ).get_page(request.GET.get(section["staff_members_page_param"]))

    for pending_request in section["pending_requested_students"].object_list:
        pending_request.request_display_status = (
            "Gözləyir" if pending_request.status == StudentOrganizationRequestStatus.PENDING else "Bağlanıb"
        )
        pending_request.request_display_class = (
            "warning" if pending_request.status == StudentOrganizationRequestStatus.PENDING else "secondary"
        )

        profile = getattr(pending_request.user, "profile", None)
        if (
            profile
            and profile.organization == organization
            and pending_request.status == StudentOrganizationRequestStatus.PENDING
        ):
            pending_request.request_note = "İstifadəçi artıq bu təşkilatın üzvüdür."
            pending_request.request_is_actionable = False
            continue

        active_other_org_name = ""
        if profile and profile.organization and profile.organization != organization:
            active_other_org_name = profile.organization.name

        if not active_other_org_name and pending_request.status == StudentOrganizationRequestStatus.PENDING:
            active_other_membership = (
                Membership.objects.filter(user=pending_request.user, is_active=True)
                .exclude(organization=organization)
                .select_related("organization", "role")
                .order_by("-is_primary", "-role__level")
                .first()
            )
            if active_other_membership:
                active_other_org_name = active_other_membership.organization.name

        if active_other_org_name and pending_request.status == StudentOrganizationRequestStatus.PENDING:
            pending_request.request_note = f"İstifadəçi artıq {active_other_org_name} təşkilatının üzvüdür."
            pending_request.request_is_actionable = False
        elif pending_request.status == StudentOrganizationRequestStatus.AUTO_CLOSED:
            pending_request.request_note = (
                pending_request.resolution_note or ""
            ).strip() or "Bu müraciət avtomatik bağlanıb."
            pending_request.request_is_actionable = False
        else:
            pending_request.request_note = (pending_request.resolution_note or "").strip()
            pending_request.request_is_actionable = True

    organization_records = OrganizationModel.objects.none()
    if is_superadmin:
        organization_records = (
            OrganizationModel.objects.select_related("owner")
            .annotate(active_member_count=Count("memberships", filter=Q(memberships__is_active=True)))
            .order_by("name")
        )
        if organization_search:
            organization_records = organization_records.filter(
                Q(name__icontains=organization_search)
                | Q(slug__icontains=organization_search)
                | Q(organization_identifier__icontains=organization_search)
                | Q(license_identifier__icontains=organization_search)
                | Q(owner__username__icontains=organization_search)
                | Q(owner__email__icontains=organization_search)
            )
        if organization_type_filter:
            organization_records = organization_records.filter(org_type=organization_type_filter)
        if organization_status_filter == "active":
            organization_records = organization_records.filter(is_active=True, status="active")
        elif organization_status_filter == "pending":
            organization_records = organization_records.filter(status="pending")
        elif organization_status_filter == "suspended":
            organization_records = organization_records.filter(status="suspended")
        elif organization_status_filter == "inactive":
            organization_records = organization_records.filter(is_active=False)

        section["organization_records"] = Paginator(
            organization_records,
            12,
        ).get_page(request.GET.get(section["organizations_page_param"]))
        section["pending_org_count"] = OrganizationModel.objects.filter(status="pending").count()

    base_query_kwargs = {
        "section": "student-organization-management",
        "management_view": management_view,
        "student_tab": student_tab,
        "teacher_tab": teacher_tab,
        "staff_tab": staff_tab,
        "student_org_search": student_search,
        "student_org_pending_search": pending_search,
        "student_org_unassigned_search": unassigned_search,
        "student_org_sent_invite_search": sent_invite_search,
        "student_org_ts_search": teacher_staff_search,
        "organization_search": organization_search,
        "organization_status": organization_status_filter,
        "organization_type": organization_type_filter,
    }
    section["students_pagination_query"] = _query_string(**base_query_kwargs)
    section["pending_pagination_query"] = _query_string(**base_query_kwargs)
    section["unassigned_pagination_query"] = _query_string(**base_query_kwargs)
    section["sent_invites_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_staff_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_members_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_members_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_requests_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_unassigned_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_invites_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_requests_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_unassigned_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_invites_pagination_query"] = _query_string(**base_query_kwargs)
    section["organizations_pagination_query"] = _query_string(**base_query_kwargs)
    section["post_next_url"] = _append_query_params(
        reverse("accounts:student_organization_management"),
        **{key: value for key, value in base_query_kwargs.items() if key != "section"},
    )

    section["student_tab_options"] = [
        {
            "value": "members",
            "label": "Tələbələr",
            "count": section["students_total_count"],
        },
        {
            "value": "pending",
            "label": "Müraciətlər",
            "count": section["pending_requested_students_total_count"],
        },
        {
            "value": "unassigned",
            "label": "Dəvətsizlər",
            "count": section["unassigned_students_total_count"],
        },
        {
            "value": "invites",
            "label": "Dəvətlər",
            "count": section["sent_student_invites_total_count"],
        },
    ]
    section["teacher_tab_options"] = [
        {
            "value": "members",
            "label": "Müəllimlər",
            "count": section["teacher_members_total_count"],
        },
        {
            "value": "requests",
            "label": "Müraciətlər",
            "count": section["pending_teacher_requests_total_count"],
        },
        {
            "value": "unassigned",
            "label": "Dəvətsizlər",
            "count": section["unassigned_teachers_total_count"],
        },
        {
            "value": "invites",
            "label": "Dəvətlər",
            "count": section["sent_teacher_invites_total_count"],
        },
    ]
    section["staff_tab_options"] = [
        {
            "value": "members",
            "label": "Staff",
            "count": section["staff_members_total_count"],
        },
        {
            "value": "requests",
            "label": "Müraciətlər",
            "count": section["pending_staff_requests_total_count"],
        },
        {
            "value": "unassigned",
            "label": "Dəvətsizlər",
            "count": section["unassigned_staff_total_count"],
        },
        {
            "value": "invites",
            "label": "Dəvətlər",
            "count": section["sent_staff_invites_total_count"],
        },
    ]
    section["management_view_options"] = [
        {
            "value": "students",
            "label": "Tələbələr",
            "count": section["students_total_count"],
        },
        {
            "value": "teachers",
            "label": "Müəllimlər",
            "count": (
                section["teacher_members_total_count"]
                + section["pending_teacher_requests_total_count"]
                + section["unassigned_teachers_total_count"]
                + section["sent_teacher_invites_total_count"]
            ),
        },
        {
            "value": "staff",
            "label": "Staff",
            "count": (
                section["staff_members_total_count"]
                + section["pending_staff_requests_total_count"]
                + section["unassigned_staff_total_count"]
                + section["sent_staff_invites_total_count"]
            ),
        },
    ]
    if is_superadmin:
        section["management_view_options"].append(
            {
                "value": "organizations",
                "label": "Təşkilatlar",
                "count": section["organization_records"].paginator.count,
            }
        )

    section["can_manage_students"] = bool(can_manage_students)
    section["can_invite_members"] = bool(can_invite_members)
    return section


def _build_student_org_request_section(*, request, profile):
    from apps.organizations.models import Membership, Organization

    search_query = request.GET.get("student_org_request_search", "")
    org_type_filter = (request.GET.get("student_org_request_type", "") or "").strip().lower()
    request_role_type = _membership_request_role_type_for_profile_role(getattr(profile, "role", ProfileRole.MEMBER))
    request_role_label = _membership_request_role_label(request_role_type)
    request_role_label_lower = str(request_role_label).lower()
    allowed_types = {
        OrganizationType.SCHOOL,
        OrganizationType.UNIVERSITY,
        OrganizationType.COURSE_CENTER,
    }
    if org_type_filter not in allowed_types:
        org_type_filter = ""

    with bypass_rls():
        pending_invites = list(
            Membership.objects.filter(
                user=request.user,
                is_active=False,
                title=STUDENT_PENDING_INVITE_TITLE,
                organization__is_active=True,
                organization__status="active",
            )
            .select_related("organization", "role", "assigned_by")
            .order_by("organization__name")
        )
    pending_invite_org_ids = {inv.organization_id for inv in pending_invites}
    for pending_invite in pending_invites:
        invite_profile_role = _map_org_role_to_profile_role(getattr(pending_invite, "role", None))
        invite_role_type = _membership_request_role_type_for_profile_role(invite_profile_role)
        pending_invite.role_label = _membership_request_role_label(invite_role_type)
        pending_invite.role_label_lower = str(pending_invite.role_label).lower()

    legacy_requested_org = getattr(profile, "requested_organization", None)
    has_matching_pending_request = False
    # If the admin already sent an invite for this org, the pending request
    # was auto-closed. Do not recreate it — the invite section handles this.
    has_invite_for_legacy_org = legacy_requested_org is not None and legacy_requested_org.pk in pending_invite_org_ids
    if legacy_requested_org is not None and not has_invite_for_legacy_org:
        with bypass_rls():
            has_matching_pending_request = StudentOrganizationRequest.objects.filter(
                user=request.user,
                organization=legacy_requested_org,
                status=StudentOrganizationRequestStatus.PENDING,
                role_type=request_role_type,
            ).exists()
    if (
        profile.organization is None
        and legacy_requested_org is not None
        and legacy_requested_org.is_active
        and not legacy_requested_org.is_suspended
        and profile.role
        in {
            ProfileRole.STUDENT,
            ProfileRole.LEAD_STUDENT,
            ProfileRole.TEACHER,
            ProfileRole.ASSISTANT_TEACHER,
            ProfileRole.MEMBER,
            ProfileRole.HR,
        }
        and not has_matching_pending_request
        and not has_invite_for_legacy_org
    ):
        with bypass_rls():
            StudentOrganizationRequest.objects.create(
                user=request.user,
                organization=legacy_requested_org,
                role_type=request_role_type,
                message=(profile.requested_organization_message or "").strip(),
                status=StudentOrganizationRequestStatus.PENDING,
            )

    with bypass_rls():
        pending_student_requests = list(
            StudentOrganizationRequest.objects.filter(
                user=request.user,
                status=StudentOrganizationRequestStatus.PENDING,
                role_type=request_role_type,
                organization__is_active=True,
                organization__status="active",
            )
            .select_related("organization")
            .order_by("-created_at")
        )
    # If there's a pending invite for an org, suppress the pending request
    # for the same org so the user sees only the invite accept/reject UI.
    if pending_invite_org_ids:
        pending_student_requests = [
            r for r in pending_student_requests if r.organization_id not in pending_invite_org_ids
        ]

    for pending_request in pending_student_requests:
        pending_request.role_label = request_role_label
        pending_request.role_label_lower = request_role_label_lower

    pending_requested_org = pending_student_requests[0].organization if pending_student_requests else None
    pending_requested_org_name = pending_requested_org.name if pending_requested_org else ""
    pending_request_message = (pending_student_requests[0].message or "").strip() if pending_student_requests else ""
    selected_org_id = (
        str(pending_requested_org.id) if pending_requested_org else str(profile.requested_organization_id or "")
    )
    pending_request_org_ids = {item.organization_id for item in pending_student_requests}

    organizations = Organization.objects.filter(is_active=True, status="active").exclude(
        org_type=OrganizationType.INDIVIDUAL
    )
    if org_type_filter:
        organizations = organizations.filter(org_type=org_type_filter)
    if search_query:
        organizations = organizations.filter(
            Q(name__icontains=search_query)
            | Q(country__icontains=search_query)
            | Q(slug__icontains=search_query)
            | Q(organization_identifier__icontains=search_query)
            | Q(license_identifier__icontains=search_query)
        )
    organizations = organizations.order_by("name")

    page_param = "student_org_request_page"
    page_number = request.GET.get(page_param)
    organizations_page = Paginator(organizations, 12).get_page(page_number)

    return {
        "organizations": organizations_page,
        "search_query": search_query,
        "org_type_filter": org_type_filter,
        "pending_invites": pending_invites,
        "pending_invites_count": len(pending_invites),
        "has_pending_invites": bool(pending_invites),
        "pending_invite_org_ids": pending_invite_org_ids,
        "pending_student_requests": pending_student_requests,
        "pending_student_requests_count": len(pending_student_requests),
        "has_pending_student_requests": bool(pending_student_requests),
        "pending_request_org_ids": pending_request_org_ids,
        "current_organization": profile.organization,
        "pending_requested_organization": pending_requested_org,
        "pending_requested_org_name": pending_requested_org_name,
        "pending_request_message": pending_request_message,
        "selected_org_id": selected_org_id,
        "page_param": page_param,
        "pagination_query": _query_string(
            section="student-organization-request",
            student_org_request_search=search_query,
            student_org_request_type=org_type_filter,
        ),
        "post_next_url": _append_query_params(
            reverse("accounts:student_organization_request"),
            student_org_request_search=search_query,
            student_org_request_type=org_type_filter,
        ),
        "request_message_max_length": STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
        "request_role_type": request_role_type,
        "request_role_label": request_role_label,
        "request_role_label_lower": request_role_label_lower,
    }
