"""
Organization views: student organization management, requests, invitations.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.notifications.models import StudentOrganizationRequest, StudentOrganizationRequestStatus
from core.constants import OrganizationType

from ..models import ProfileRole, UserProfile
from ._helpers import (
    STUDENT_ORG_MANAGEMENT_MIN_LEVEL,
    STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
    STUDENT_PENDING_INVITE_TITLE,
    _build_student_org_management_section,
    _build_student_org_request_section,
    _close_other_pending_student_requests,
    _csv_to_int_set,
    _ensure_profile_admin_membership,
    _get_active_organization,
    _is_superadmin_user,
    _map_org_role_to_profile_role,
    _normalized_org_name,
    _pending_student_request_queryset,
    _resolve_membership_role,
    _resolve_next_url,
    _role_capabilities,
    _set_student_org_request_status,
    _sync_profile_pending_request_snapshot,
)

User = get_user_model()


@login_required
def student_organization_management(request):
    """Manage student membership add/remove operations for high-level organization roles."""
    from apps.organizations.models import Membership
    from apps.organizations.services import create_audit_log, get_user_org_role_level

    org = _get_active_organization(request)
    if not org:
        messages.error(request, "Aktiv təşkilat tapılmadı.")
        return redirect("accounts:profile")

    _ensure_profile_admin_membership(request.user, org)

    is_superadmin = _is_superadmin_user(request.user)
    user_level = 999 if is_superadmin else get_user_org_role_level(request.user, org)
    if not is_superadmin and user_level < STUDENT_ORG_MANAGEMENT_MIN_LEVEL:
        messages.error(
            request,
            "Bu bölmədən istifadə üçün minimum HR, təşkilat admini və ya daha yüksək səlahiyyət tələb olunur.",
        )
        return redirect("accounts:profile")

    student_role = _resolve_membership_role(org, ProfileRole.STUDENT)

    def _load_pending_request_for_user(target_user, *, include_auto_closed=False):
        statuses = [StudentOrganizationRequestStatus.PENDING]
        if include_auto_closed:
            statuses.append(StudentOrganizationRequestStatus.AUTO_CLOSED)
        return (
            _pending_student_request_queryset(
                user=target_user,
                organization=org,
                statuses=statuses,
            )
            .order_by("-created_at")
            .first()
        )

    def _approve_requested_profile(target_profile):
        target_user = target_profile.user
        target_request = _load_pending_request_for_user(target_user)

        if target_request is None:
            requested_org = target_profile.requested_organization
            requested_name = _normalized_org_name(target_profile.requested_organization_name)
            is_requested_for_org = (requested_org is not None and requested_org == org) or (
                requested_org is None and requested_name and requested_name == _normalized_org_name(org.name)
            )
            if not is_requested_for_org:
                return False, "İstifadəçi bu təşkilatı seçməyib."
            target_request = StudentOrganizationRequest.objects.create(
                user=target_user,
                organization=org,
                message=(target_profile.requested_organization_message or "").strip(),
                status=StudentOrganizationRequestStatus.PENDING,
            )

        if target_profile.organization and target_profile.organization != org:
            _set_student_org_request_status(
                request_obj=target_request,
                status=StudentOrganizationRequestStatus.AUTO_CLOSED,
                note=f"İstifadəçi artıq {target_profile.organization.name} təşkilatının üzvüdür.",
                responded_by=request.user,
            )
            _sync_profile_pending_request_snapshot(target_profile)
            return False, "İstifadəçi başqa təşkilata bağlıdır."

        if Membership.objects.filter(
            user=target_user,
            organization=org,
            is_active=False,
            title=STUDENT_PENDING_INVITE_TITLE,
        ).exists():
            return False, "Bu istifadəçi üçün dəvət göndərilib, əvvəlcə istifadəçi qəbul etməlidir."

        if student_role is None:
            return False, "Bu təşkilat üçün tələbə rolu tapılmadı."

        target_membership = (
            Membership.objects.filter(user=target_user, organization=org)
            .select_related("role")
            .order_by("-is_active", "-is_primary", "-role__level")
            .first()
        )
        if target_membership and not is_superadmin and target_membership.role.level >= user_level:
            return False, "Yalnız öz səviyyənizdən aşağı istifadəçiləri idarə edə bilərsiniz."

        with transaction.atomic():
            if target_membership:
                old_role = target_membership.role.name
                target_membership.role = student_role
                target_membership.assigned_by = request.user
                target_membership.is_active = True
                target_membership.is_primary = True
                target_membership.title = ""
                target_membership.save(
                    update_fields=[
                        "role",
                        "assigned_by",
                        "is_active",
                        "is_primary",
                        "title",
                        "updated_at",
                    ]
                )
            else:
                old_role = ""
                target_membership = Membership.objects.create(
                    user=target_user,
                    organization=org,
                    role=student_role,
                    assigned_by=request.user,
                    is_primary=True,
                    is_active=True,
                    title="",
                )

            target_profile.organization = org
            target_profile.organization_type = org.org_type
            target_profile.role = ProfileRole.STUDENT
            target_profile.requested_organization = org
            target_profile.requested_organization_name = org.name
            target_profile.requested_organization_message = ""
            target_profile.student_university_name = org.name
            target_profile.student_school_identifier = (
                org.organization_identifier or org.license_identifier or ""
                if org.org_type == OrganizationType.SCHOOL
                else ""
            )
            target_profile.save(
                update_fields=[
                    "organization",
                    "organization_type",
                    "role",
                    "requested_organization",
                    "requested_organization_name",
                    "requested_organization_message",
                    "student_university_name",
                    "student_school_identifier",
                    "updated_at",
                ]
            )

            _set_student_org_request_status(
                request_obj=target_request,
                status=StudentOrganizationRequestStatus.APPROVED,
                note="Təşkilat tərəfindən qəbul edildi.",
                responded_by=request.user,
            )
            now = timezone.now()
            _pending_student_request_queryset(
                user=target_user,
                organization=org,
                statuses=[StudentOrganizationRequestStatus.PENDING],
            ).exclude(id=target_request.id).update(
                status=StudentOrganizationRequestStatus.AUTO_CLOSED,
                resolution_note="Eyni təşkilat üzrə əvvəlki müraciət avtomatik bağlandı.",
                responded_by=request.user,
                responded_at=now,
                updated_at=now,
            )
            _close_other_pending_student_requests(
                user=target_user,
                accepted_organization=org,
                responded_by=request.user,
            )

        create_audit_log(
            user=request.user,
            organization=org,
            action="update",
            resource_type="membership",
            resource_id=target_membership.id,
            resource_repr=str(target_membership),
            old_values={"role": old_role} if old_role else None,
            new_values={
                "role": student_role.name,
                "attached_user": target_user.username,
                "action": "approve_requested_student",
            },
            request=request,
        )

        return True, ""

    def _reject_requested_profile(target_profile):
        target_request = _load_pending_request_for_user(
            target_profile.user,
            include_auto_closed=True,
        )
        if target_request is None:
            requested_org = target_profile.requested_organization
            requested_name = _normalized_org_name(target_profile.requested_organization_name)
            is_requested_for_org = (requested_org is not None and requested_org == org) or (
                requested_org is None and requested_name and requested_name == _normalized_org_name(org.name)
            )
            if not is_requested_for_org:
                return False, "İstifadəçi bu təşkilata müraciət etməyib."

            target_profile.requested_organization = None
            target_profile.requested_organization_name = ""
            target_profile.requested_organization_message = ""
            target_profile.save(
                update_fields=[
                    "requested_organization",
                    "requested_organization_name",
                    "requested_organization_message",
                    "updated_at",
                ]
            )
            return True, ""

        _set_student_org_request_status(
            request_obj=target_request,
            status=StudentOrganizationRequestStatus.REJECTED,
            note="Müraciət təşkilat tərəfindən silindi.",
            responded_by=request.user,
        )
        _sync_profile_pending_request_snapshot(target_profile)
        return True, ""

    def _invite_student_user(target_user):
        target_profile, _ = UserProfile.objects.get_or_create(user=target_user)

        if student_role is None:
            return False, "Bu təşkilat üçün tələbə rolu tapılmadı."

        if target_profile.organization and target_profile.organization != org:
            return False, "İstifadəçi başqa təşkilata bağlıdır."
        if target_profile.organization == org:
            return False, "İstifadəçi artıq bu təşkilatdadır."

        existing_invite = Membership.objects.filter(
            user=target_user,
            organization=org,
            is_active=False,
            title=STUDENT_PENDING_INVITE_TITLE,
        ).first()
        if existing_invite:
            return False, "Bu istifadəçi üçün artıq dəvət göndərilib."

        with transaction.atomic():
            invite_membership, _ = Membership.objects.update_or_create(
                user=target_user,
                organization=org,
                role=student_role,
                scope_unit=None,
                defaults={
                    "assigned_by": request.user,
                    "is_primary": False,
                    "is_active": False,
                    "title": STUDENT_PENDING_INVITE_TITLE,
                },
            )

            target_profile.requested_organization = org
            target_profile.requested_organization_name = org.name
            target_profile.requested_organization_message = ""
            target_profile.save(
                update_fields=[
                    "requested_organization",
                    "requested_organization_name",
                    "requested_organization_message",
                    "updated_at",
                ]
            )

            now = timezone.now()
            _pending_student_request_queryset(
                user=target_user,
                organization=org,
                statuses=[StudentOrganizationRequestStatus.PENDING],
            ).update(
                status=StudentOrganizationRequestStatus.AUTO_CLOSED,
                resolution_note="Təşkilat dəvəti göndərildiyi üçün müraciət bağlandı.",
                responded_by=request.user,
                responded_at=now,
                updated_at=now,
            )

        create_audit_log(
            user=request.user,
            organization=org,
            action="create",
            resource_type="membership_invite",
            resource_id=invite_membership.id,
            resource_repr=f"{target_user.username} pending invite",
            old_values=None,
            new_values={
                "action": "invite_student",
                "invited_user": target_user.username,
                "role": student_role.name,
            },
            request=request,
        )
        return True, ""

    def _revoke_sent_invite_for_user(target_user):
        target_profile, _ = UserProfile.objects.get_or_create(user=target_user)
        invite_membership = (
            Membership.objects.filter(
                user=target_user,
                organization=org,
                is_active=False,
                title=STUDENT_PENDING_INVITE_TITLE,
            )
            .select_related("role")
            .first()
        )
        if invite_membership is None:
            return False, "Geri çəkiləcək aktiv dəvət tapılmadı."

        invite_id = str(invite_membership.id)
        with transaction.atomic():
            invite_membership.delete()
            now = timezone.now()
            _pending_student_request_queryset(
                user=target_user,
                organization=org,
                statuses=[StudentOrganizationRequestStatus.PENDING],
            ).update(
                status=StudentOrganizationRequestStatus.CANCELLED,
                resolution_note="Təşkilat dəvəti geri çəkildiyi üçün müraciət ləğv edildi.",
                responded_by=request.user,
                responded_at=now,
                updated_at=now,
            )
            _sync_profile_pending_request_snapshot(target_profile)

        create_audit_log(
            user=request.user,
            organization=org,
            action="delete",
            resource_type="membership_invite",
            resource_id=invite_id,
            resource_repr=f"{target_user.username} invite revoked",
            old_values={"status": "pending"},
            new_values={"status": "revoked_by_org"},
            request=request,
        )
        return True, ""

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        next_url = _resolve_next_url(request, reverse("accounts:student_organization_management"))

        if action in {"approve_requested_student", "add_student"}:
            target_user_id = request.POST.get("user_id")
            target_profile = get_object_or_404(UserProfile.objects.select_related("user"), user_id=target_user_id)
            is_ok, error_message = _approve_requested_profile(target_profile)
            if not is_ok:
                messages.error(request, error_message)
                return redirect(next_url)
            messages.success(request, f"Uğurla əlavə edildi: {target_profile.user.username}.")
            return redirect(next_url)

        if action == "bulk_approve_requested_students":
            single_user_id = (request.POST.get("single_user_id") or "").strip()
            reject_user_id = (request.POST.get("reject_user_id") or "").strip()
            bulk_reject_mode = (request.POST.get("bulk_reject") or "").strip() == "1"
            selected_user_ids = _csv_to_int_set(request.POST.get("selected_user_ids"))
            is_single_approve = False
            is_single_reject = False
            if single_user_id.isdigit():
                selected_user_ids = {int(single_user_id)}
                is_single_approve = True
            elif reject_user_id.isdigit():
                selected_user_ids = {int(reject_user_id)}
                is_single_reject = True
            if not selected_user_ids:
                selected_user_ids = {
                    int(user_id) for user_id in request.POST.getlist("selected_pending_user_ids") if user_id.isdigit()
                }
            if not selected_user_ids:
                if bulk_reject_mode:
                    messages.error(request, "Silmək üçün ən azı bir tələbə seçin.")
                else:
                    messages.error(request, "Təsdiq üçün ən azı bir tələbə seçin.")
                return redirect(next_url)

            processed_count = 0
            failed_usernames = []
            pending_profiles = (
                UserProfile.objects.filter(user_id__in=selected_user_ids)
                .select_related("user", "requested_organization")
                .order_by("user__username")
            )
            for pending_profile in pending_profiles:
                if bulk_reject_mode or is_single_reject:
                    is_ok, _ = _reject_requested_profile(pending_profile)
                else:
                    is_ok, _ = _approve_requested_profile(pending_profile)
                if is_ok:
                    processed_count += 1
                else:
                    failed_usernames.append(pending_profile.user.username)

            if processed_count:
                if bulk_reject_mode or is_single_reject:
                    if is_single_reject and processed_count == 1:
                        messages.success(request, "Uğurla yeniləndi: tələbə müraciəti silindi.")
                    else:
                        messages.success(request, f"Uğurla yeniləndi: {processed_count} tələbənin müraciəti silindi.")
                else:
                    if is_single_approve and processed_count == 1:
                        messages.success(request, "Uğurla əlavə edildi: 1 tələbə əlavə edildi.")
                    else:
                        messages.success(request, f"Uğurla əlavə edildi: {processed_count} tələbə əlavə edildi.")
            if failed_usernames:
                messages.warning(
                    request,
                    "Bu istifadəçilər üçün əməliyyat tamamlanmadı: " + ", ".join(failed_usernames[:8]),
                )
            return redirect(next_url)

        if action in {"invite_student", "bulk_invite_students"}:
            if action == "invite_student":
                single_user_id = (request.POST.get("user_id") or "").strip()
            else:
                single_user_id = (request.POST.get("single_invite_user_id") or "").strip()

            selected_user_ids = _csv_to_int_set(request.POST.get("selected_user_ids"))
            is_single_invite = False
            if single_user_id.isdigit():
                selected_user_ids = {int(single_user_id)}
                is_single_invite = True
            if not selected_user_ids:
                selected_user_ids = {
                    int(user_id)
                    for user_id in request.POST.getlist("selected_unassigned_user_ids")
                    if user_id.isdigit()
                }
            if not selected_user_ids:
                messages.error(request, "Dəvət göndərmək üçün ən azı bir tələbə seçin.")
                return redirect(next_url)

            processed_count = 0
            failed_usernames = []
            target_users = User.objects.filter(id__in=selected_user_ids, is_active=True).order_by("username")
            for target_user in target_users:
                is_ok, _ = _invite_student_user(target_user)
                if is_ok:
                    processed_count += 1
                else:
                    failed_usernames.append(target_user.username)

            if processed_count:
                if is_single_invite and processed_count == 1:
                    messages.success(
                        request,
                        f"Uğurla əlavə edildi: {target_users.first().username} üçün dəvət göndərildi.",
                    )
                else:
                    messages.success(request, f"Uğurla əlavə edildi: {processed_count} tələbəyə dəvət göndərildi.")
            if failed_usernames:
                messages.warning(
                    request,
                    "Bu istifadəçilər üçün dəvət göndərilmədi: " + ", ".join(failed_usernames[:8]),
                )
            return redirect(next_url)

        if action == "revoke_sent_invites":
            single_revoke_user_id = (request.POST.get("single_revoke_user_id") or "").strip()
            selected_user_ids = _csv_to_int_set(request.POST.get("selected_user_ids"))
            is_single_revoke = False
            if single_revoke_user_id.isdigit():
                selected_user_ids = {int(single_revoke_user_id)}
                is_single_revoke = True
            if not selected_user_ids:
                selected_user_ids = {
                    int(user_id)
                    for user_id in request.POST.getlist("selected_sent_invite_user_ids")
                    if user_id.isdigit()
                }
            if not selected_user_ids:
                messages.error(request, "Geri çəkmək üçün ən azı bir dəvət seçin.")
                return redirect(next_url)

            processed_count = 0
            failed_usernames = []
            target_users = User.objects.filter(id__in=selected_user_ids, is_active=True).order_by("username")
            for target_user in target_users:
                is_ok, _ = _revoke_sent_invite_for_user(target_user)
                if is_ok:
                    processed_count += 1
                else:
                    failed_usernames.append(target_user.username)

            if processed_count:
                if is_single_revoke and processed_count == 1:
                    messages.success(request, "Dəvət geri çəkildi.")
                else:
                    messages.success(request, f"{processed_count} dəvət geri çəkildi.")
            if failed_usernames:
                messages.warning(
                    request,
                    "Bu istifadəçilər üçün geri çəkmə tamamlanmadı: " + ", ".join(failed_usernames[:8]),
                )
            return redirect(next_url)

        if action == "remove_student":
            target_user_id = request.POST.get("user_id")
            remove_reason = (request.POST.get("remove_reason") or "").strip()
            target_user = get_object_or_404(User, id=target_user_id, is_active=True)
            target_profile, _ = UserProfile.objects.get_or_create(user=target_user)
            active_memberships = list(
                Membership.objects.filter(user=target_user, organization=org, is_active=True).select_related("role")
            )
            if not active_memberships and target_profile.organization != org:
                messages.error(request, "İstifadəçi bu təşkilata bağlı deyil.")
                return redirect(next_url)

            is_student_target = target_profile.role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT} or any(
                membership.role.name == "student" for membership in active_memberships
            )
            if not is_student_target:
                messages.error(request, "Yalnız tələbə istifadəçilər bu bölmədən uzaqlaşdırıla bilər.")
                return redirect(next_url)

            highest_target_level = max([membership.role.level for membership in active_memberships], default=0)
            if not is_superadmin and highest_target_level >= user_level:
                messages.error(request, "Yalnız öz səviyyənizdən aşağı istifadəçiləri idarə edə bilərsiniz.")
                return redirect(next_url)

            with transaction.atomic():
                if active_memberships:
                    membership_ids = [membership.id for membership in active_memberships]
                    Membership.objects.filter(id__in=membership_ids).update(
                        is_active=False,
                        is_primary=False,
                    )

                fallback_membership = (
                    Membership.objects.filter(user=target_user, is_active=True)
                    .exclude(organization=org)
                    .select_related("organization", "role")
                    .order_by("-is_primary", "-role__level")
                    .first()
                )
                if fallback_membership:
                    target_profile.organization = fallback_membership.organization
                    target_profile.organization_type = fallback_membership.organization.org_type
                    target_profile.role = _map_org_role_to_profile_role(fallback_membership.role)
                else:
                    target_profile.organization = None
                    target_profile.organization_type = OrganizationType.INDIVIDUAL
                    if target_profile.role not in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
                        target_profile.role = ProfileRole.STUDENT

                # Do not auto-create a new pending request after removal.
                target_profile.requested_organization = None
                target_profile.requested_organization_name = ""
                target_profile.requested_organization_message = ""
                target_profile.student_university_name = ""
                target_profile.student_school_identifier = ""
                target_profile.save(
                    update_fields=[
                        "organization",
                        "organization_type",
                        "role",
                        "requested_organization",
                        "requested_organization_name",
                        "requested_organization_message",
                        "student_university_name",
                        "student_school_identifier",
                        "updated_at",
                    ]
                )

            create_audit_log(
                user=request.user,
                organization=org,
                action="update",
                resource_type="membership",
                resource_id=target_user.id,
                resource_repr=f"{target_user.username} removed from {org.name}",
                old_values={"organization": org.name},
                new_values={"organization": "", "action": "remove_student"},
                reason=remove_reason or None,
                request=request,
            )

            messages.success(request, f"Uğurla uzaqlaşdırıldı: {target_user.username}.")
            return redirect(next_url)

        if action in {"approve_teacher_staff_request", "reject_teacher_staff_request"}:
            from apps.notifications.models import MembershipRequestRoleType as MRR

            request_id = (request.POST.get("request_id") or request.POST.get("ts_request_id") or "").strip()
            if not request_id.isdigit():
                messages.error(request, "Keçərsiz müraciət ID-si.")
                return redirect(next_url)

            ts_request = StudentOrganizationRequest.objects.filter(
                id=int(request_id),
                organization=org,
                status=StudentOrganizationRequestStatus.PENDING,
                role_type__in=[MRR.TEACHER, MRR.STAFF],
            ).first()
            if ts_request is None:
                messages.error(request, "Müraciət tapılmadı və ya artıq cavablandırılıb.")
                return redirect(next_url)

            if action == "approve_teacher_staff_request":
                with transaction.atomic():
                    target_profile, _ = UserProfile.objects.get_or_create(user=ts_request.user)
                    _set_student_org_request_status(
                        request_obj=ts_request,
                        status=StudentOrganizationRequestStatus.APPROVED,
                        note="Qəbul edildi.",
                        responded_by=request.user,
                    )
                    # Assign teacher/staff membership role
                    from apps.organizations.models import Membership

                    role_name = "teacher" if ts_request.role_type == MRR.TEACHER else "member"
                    role_obj = org.roles.filter(name=role_name, is_active=True).first()
                    if role_obj is None:
                        role_obj = org.roles.filter(is_active=True).order_by("level").first()
                    if role_obj:
                        Membership.objects.update_or_create(
                            user=ts_request.user,
                            organization=org,
                            defaults={
                                "role": role_obj,
                                "is_active": True,
                                "is_primary": not Membership.objects.filter(
                                    user=ts_request.user, is_active=True, is_primary=True
                                )
                                .exclude(organization=org)
                                .exists(),
                            },
                        )
                        target_profile.organization = org
                        target_profile.organization_type = org.org_type
                        target_profile.role = (
                            ProfileRole.TEACHER if ts_request.role_type == MRR.TEACHER else ProfileRole.MEMBER
                        )
                        target_profile.requested_organization = None
                        target_profile.requested_organization_name = ""
                        target_profile.save(
                            update_fields=[
                                "organization",
                                "organization_type",
                                "role",
                                "requested_organization",
                                "requested_organization_name",
                                "updated_at",
                            ]
                        )
                messages.success(
                    request,
                    f"{ts_request.user.get_full_name() or ts_request.user.username} qəbul edildi.",
                )
            else:
                _set_student_org_request_status(
                    request_obj=ts_request,
                    status=StudentOrganizationRequestStatus.REJECTED,
                    note="Müraciət rədd edildi.",
                    responded_by=request.user,
                )
                messages.success(
                    request,
                    f"{ts_request.user.get_full_name() or ts_request.user.username} müraciəti rədd edildi.",
                )
            return redirect(next_url)

        messages.error(request, "Naməlum əməliyyat.")
        return redirect(next_url)

    context = _build_student_org_management_section(
        request=request,
        organization=org,
        is_superadmin=is_superadmin,
        user_level=user_level,
    )
    return render(request, "accounts/student_organization_management.html", context)


@login_required
def student_organization_request(request):
    """Allow students to browse organizations and send join requests with a short message."""
    from apps.organizations.models import Membership, Organization

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    capabilities = _role_capabilities(request.user, profile)
    if "student-organization-request" not in capabilities["allowed_sections"]:
        messages.error(request, "Bu bölmə yalnız tələbələr üçün aktivdir.")
        return redirect("accounts:profile")

    default_next = f"{reverse('accounts:profile')}?section=student-organization-request"
    if request.method == "POST":
        action = (request.POST.get("action") or "submit_request").strip().lower()
        next_url = _resolve_next_url(request, default_next)

        if action == "submit_request":
            if profile.organization_id:
                messages.error(request, "Hazırda təşkilata bağlısınız. Yeni müraciət üçün əvvəlcə çıxış edin.")
                return redirect(next_url)

            organization_id = (request.POST.get("organization_id") or "").strip()
            if not organization_id:
                messages.error(request, "Müraciət üçün bir təşkilat seçin.")
                return redirect(next_url)

            target_org = (
                Organization.objects.filter(
                    id=organization_id,
                    is_active=True,
                    status="active",
                )
                .exclude(org_type=OrganizationType.INDIVIDUAL)
                .first()
            )
            if target_org is None:
                messages.error(request, "Seçilən təşkilat tapılmadı və ya aktiv deyil.")
                return redirect(next_url)

            existing_pending_invite = Membership.objects.filter(
                user=request.user,
                organization=target_org,
                is_active=False,
                title=STUDENT_PENDING_INVITE_TITLE,
            ).exists()
            if existing_pending_invite:
                messages.info(request, "Bu təşkilatdan sizə artıq dəvət göndərilib. Profildə qəbul edə bilərsiniz.")
                return redirect(next_url)

            request_message = (request.POST.get("request_message") or "").strip()
            if len(request_message) > STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH:
                messages.error(
                    request,
                    f"Müraciət mesajı maksimum {STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH} simvol ola bilər.",
                )
                return redirect(next_url)

            existing_pending = (
                _pending_student_request_queryset(
                    user=request.user,
                    organization=target_org,
                    statuses=[StudentOrganizationRequestStatus.PENDING],
                )
                .order_by("-created_at")
                .first()
            )
            if existing_pending:
                existing_pending.message = request_message
                existing_pending.resolution_note = ""
                existing_pending.responded_by = None
                existing_pending.responded_at = None
                existing_pending.save(
                    update_fields=[
                        "message",
                        "resolution_note",
                        "responded_by",
                        "responded_at",
                        "updated_at",
                    ]
                )
                target_request = existing_pending
            else:
                target_request = StudentOrganizationRequest.objects.create(
                    user=request.user,
                    organization=target_org,
                    message=request_message,
                    status=StudentOrganizationRequestStatus.PENDING,
                )

            # Keep one pending row per user+organization for cleaner history and UI.
            duplicate_pending = _pending_student_request_queryset(
                user=request.user,
                organization=target_org,
                statuses=[StudentOrganizationRequestStatus.PENDING],
            ).exclude(id=target_request.id)
            if duplicate_pending.exists():
                now = timezone.now()
                duplicate_pending.update(
                    status=StudentOrganizationRequestStatus.CANCELLED,
                    resolution_note="Yeni müraciət göndərildiyi üçün əvvəlki pending bağlandı.",
                    responded_by=request.user,
                    responded_at=now,
                    updated_at=now,
                )

            profile.requested_organization = target_org
            profile.requested_organization_name = target_org.name
            profile.requested_organization_message = request_message
            profile.organization_type = target_org.org_type
            if profile.role not in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
                profile.role = ProfileRole.STUDENT
            profile.save(
                update_fields=[
                    "requested_organization",
                    "requested_organization_name",
                    "requested_organization_message",
                    "organization_type",
                    "role",
                    "updated_at",
                ]
            )
            _sync_profile_pending_request_snapshot(profile)

            messages.success(request, f"{target_org.name} üçün müraciətiniz göndərildi və təsdiq gözləyir.")
            return redirect(next_url)

        if action == "clear_request":
            request_id = (request.POST.get("request_id") or "").strip()
            target_request = None
            if request_id:
                target_request = (
                    _pending_student_request_queryset(
                        user=request.user,
                        statuses=[StudentOrganizationRequestStatus.PENDING],
                    )
                    .filter(id=request_id)
                    .select_related("organization")
                    .first()
                )
            else:
                organization_id = (request.POST.get("organization_id") or "").strip()
                if organization_id:
                    target_request = (
                        _pending_student_request_queryset(
                            user=request.user,
                            statuses=[StudentOrganizationRequestStatus.PENDING],
                        )
                        .filter(organization_id=organization_id)
                        .select_related("organization")
                        .first()
                    )

            if target_request is None:
                messages.error(request, "Ləğv ediləcək aktiv müraciət tapılmadı.")
                return redirect(next_url)

            _set_student_org_request_status(
                request_obj=target_request,
                status=StudentOrganizationRequestStatus.CANCELLED,
                note="Müraciət tələbə tərəfindən ləğv edildi.",
                responded_by=request.user,
            )
            _sync_profile_pending_request_snapshot(profile)
            messages.success(request, f"{target_request.organization.name} üçün müraciət ləğv edildi.")
            return redirect(next_url)

        messages.error(request, "Naməlum əməliyyat.")
        return redirect(next_url)

    context = _build_student_org_request_section(request=request, profile=profile)
    return render(request, "accounts/student_organization_request.html", context)


@login_required
def student_org_invitation_action(request):
    """Allow students to accept or reject pending organization invitations."""
    from apps.organizations.models import Membership
    from apps.organizations.services import create_audit_log

    if request.method != "POST":
        return redirect(f"{reverse('accounts:profile')}?section=profile-info")

    invite_id = request.POST.get("invite_id")
    action = (request.POST.get("action") or "").strip().lower()
    back_url = _resolve_next_url(request, f"{reverse('accounts:profile')}?section=profile-info")

    invite_membership = get_object_or_404(
        Membership.objects.select_related("organization", "role", "assigned_by"),
        id=invite_id,
        user=request.user,
        is_active=False,
        title=STUDENT_PENDING_INVITE_TITLE,
    )

    if action == "accept":
        organization = invite_membership.organization
        if organization.is_suspended:
            messages.error(request, "Təşkilat hazırda aktiv deyil.")
            return redirect(back_url)

        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        if profile.organization and profile.organization != organization:
            messages.error(request, "Əvvəlcə mövcud təşkilatdan çıxın, sonra yeni dəvəti qəbul edin.")
            return redirect(back_url)

        student_role = _resolve_membership_role(organization, ProfileRole.STUDENT)
        if student_role is None:
            messages.error(request, "Təşkilatda tələbə rolu tapılmadı.")
            return redirect(back_url)

        with transaction.atomic():
            invite_membership.role = student_role
            invite_membership.is_active = True
            invite_membership.is_primary = True
            invite_membership.title = ""
            invite_membership.save(
                update_fields=[
                    "role",
                    "is_active",
                    "is_primary",
                    "title",
                    "updated_at",
                ]
            )

            profile.organization = organization
            profile.organization_type = organization.org_type
            profile.role = ProfileRole.STUDENT
            profile.requested_organization = organization
            profile.requested_organization_name = organization.name
            profile.requested_organization_message = ""
            profile.student_university_name = organization.name
            profile.student_school_identifier = (
                organization.organization_identifier or organization.license_identifier or ""
                if organization.org_type == OrganizationType.SCHOOL
                else ""
            )
            profile.save(
                update_fields=[
                    "organization",
                    "organization_type",
                    "role",
                    "requested_organization",
                    "requested_organization_name",
                    "requested_organization_message",
                    "student_university_name",
                    "student_school_identifier",
                    "updated_at",
                ]
            )

            now = timezone.now()
            _pending_student_request_queryset(
                user=request.user,
                organization=organization,
                statuses=[StudentOrganizationRequestStatus.PENDING],
            ).update(
                status=StudentOrganizationRequestStatus.APPROVED,
                resolution_note="Dəvət qəbul edildiyi üçün üzvlük aktivləşdi.",
                responded_by=request.user,
                responded_at=now,
                updated_at=now,
            )
            _close_other_pending_student_requests(
                user=request.user,
                accepted_organization=organization,
                responded_by=request.user,
            )

        request.session["active_organization"] = organization.slug
        create_audit_log(
            user=request.user,
            organization=organization,
            action="update",
            resource_type="membership_invite",
            resource_id=invite_membership.id,
            resource_repr=f"{request.user.username} accepted invite",
            old_values={"status": "pending"},
            new_values={"status": "accepted"},
            request=request,
        )
        messages.success(request, f"{organization.name} təşkilatına qoşuldunuz.")
        return redirect(back_url)

    if action == "reject":
        organization = invite_membership.organization
        invite_membership.delete()
        create_audit_log(
            user=request.user,
            organization=organization,
            action="delete",
            resource_type="membership_invite",
            resource_id=invite_id,
            resource_repr=f"{request.user.username} rejected invite",
            old_values={"status": "pending"},
            new_values={"status": "rejected"},
            request=request,
        )
        messages.info(request, f"{organization.name} dəvəti rədd edildi.")
        return redirect(back_url)

    messages.error(request, "Naməlum əməliyyat.")
    return redirect(back_url)


@login_required
def student_leave_organization(request):
    """Allow students to leave their current organization with mandatory reason."""
    from apps.organizations.models import Membership
    from apps.organizations.services import create_audit_log

    if request.method != "POST":
        return redirect(f"{reverse('accounts:profile')}?section=profile-info")

    reason = (request.POST.get("leave_reason") or "").strip()
    back_url = _resolve_next_url(request, f"{reverse('accounts:profile')}?section=profile-info")
    if not reason:
        messages.error(request, "Təşkilatdan çıxmaq üçün səbəb qeyd etmək məcburidir.")
        return redirect(back_url)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    organization = profile.organization
    if organization is None:
        messages.error(request, "Hazırda bağlı olduğunuz təşkilat yoxdur.")
        return redirect(back_url)

    is_student_user = (
        profile.role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}
        or Membership.objects.filter(
            user=request.user,
            organization=organization,
            is_active=True,
            role__name="student",
        ).exists()
    )
    if not is_student_user:
        messages.error(request, "Bu əməliyyat yalnız tələbələr üçün aktivdir.")
        return redirect(back_url)

    with transaction.atomic():
        Membership.objects.filter(user=request.user, organization=organization, is_active=True).update(
            is_active=False,
            is_primary=False,
        )
        profile.organization = None
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.requested_organization = None
        profile.requested_organization_name = ""
        profile.requested_organization_message = ""
        profile.student_university_name = ""
        profile.student_school_identifier = ""
        profile.save(
            update_fields=[
                "organization",
                "organization_type",
                "requested_organization",
                "requested_organization_name",
                "requested_organization_message",
                "student_university_name",
                "student_school_identifier",
                "updated_at",
            ]
        )

    request.session.pop("active_organization", None)
    create_audit_log(
        user=request.user,
        organization=organization,
        action="update",
        resource_type="membership",
        resource_id=request.user.id,
        resource_repr=f"{request.user.username} left organization",
        old_values={"organization": organization.name},
        new_values={"organization": ""},
        reason=reason,
        request=request,
    )
    messages.success(request, f"{organization.name} təşkilatından ayrıldınız.")
    return redirect(back_url)
