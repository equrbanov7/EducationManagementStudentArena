"""student_organization_management flow — əsas sinif (__init__ + run) + mixin-lər."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from apps.notifications.models import (
    MembershipRequestRoleType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)

from ....models import ProfileRole, UserProfile
from ..._helpers import (
    STUDENT_ORG_MANAGEMENT_MIN_LEVEL,
    _close_other_pending_student_requests,
    _collect_actor_permissions,
    _csv_to_int_set,
    _ensure_profile_admin_membership,
    _get_active_organization,
    _is_superadmin_user,
    _membership_request_role_label,
    _render_profile_section,
    _resolve_membership_role,
    _resolve_next_url,
    _set_student_org_request_status,
    _sync_profile_pending_request_snapshot,
)
from ._invites import _InvitesMixin
from ._members import _MembersMixin
from ._requests import _RequestsMixin

User = get_user_model()


class _StudentOrgManagementFlow(_RequestsMixin, _InvitesMixin, _MembersMixin):
    """student_organization_management view-nin request-scoped məntiqi (god-file refaktoru).

    Davranış köhnə tək-funksiyalı implementasiya ilə eynidir."""

    def __init__(self, request):
        self.request = request
        self.is_superadmin = None
        self.org = None
        self.remove_reason = None
        self.student_role = None
        self.user_level = None

    def run(self):
        from apps.organizations.models import Membership
        from apps.organizations.permissions import has_permission as _has_org_permission
        from apps.organizations.services import create_audit_log, get_user_org_role_level

        self.org = _get_active_organization(self.request)
        self.is_superadmin = _is_superadmin_user(self.request.user)
        if not self.org and (not self.is_superadmin):
            messages.error(self.request, "Aktiv təşkilat tapılmadı.")
            return redirect("accounts:profile")
        if self.org is not None:
            _ensure_profile_admin_membership(self.request.user, self.org)
        self.user_level = 999 if self.is_superadmin else get_user_org_role_level(self.request.user, self.org)
        teacher_student_only = False
        teacher_can_manage_students = False
        teacher_can_invite_members = False
        if not self.is_superadmin and self.user_level < STUDENT_ORG_MANAGEMENT_MIN_LEVEL:
            if self.org is not None:
                actor_perms, _ = _collect_actor_permissions(self.request.user, self.org)
                teacher_can_manage_students = _has_org_permission(list(actor_perms), "member.student_manage")
                teacher_can_invite_members = _has_org_permission(list(actor_perms), "member.invite")
                if teacher_can_manage_students or teacher_can_invite_members:
                    teacher_student_only = True
                else:
                    messages.error(
                        self.request,
                        "Bu bölmədən istifadə üçün minimum HR, təşkilat admini və ya daha yüksək səlahiyyət tələb olunur.",
                    )
                    return redirect("accounts:profile")
            else:
                messages.error(
                    self.request,
                    "Bu bölmədən istifadə üçün minimum HR, təşkilat admini və ya daha yüksək səlahiyyət tələb olunur.",
                )
                return redirect("accounts:profile")
        self.student_role = _resolve_membership_role(self.org, ProfileRole.STUDENT)
        if self.request.method == "POST":
            action = (self.request.POST.get("action") or "").strip().lower()
            next_url = _resolve_next_url(self.request, reverse("accounts:student_organization_management"))
            teacher_allowed_actions = set()
            if teacher_can_manage_students:
                teacher_allowed_actions.update(
                    {
                        "approve_requested_student",
                        "add_student",
                        "bulk_approve_requested_students",
                        "remove_student",
                        "remove_org_member",
                    }
                )
            if teacher_can_invite_members:
                teacher_allowed_actions.update({"invite_student", "bulk_invite_students", "revoke_sent_invites"})
            if teacher_student_only and action not in teacher_allowed_actions:
                messages.error(self.request, "Bu əməliyyat üçün icazəniz yoxdur.")
                return redirect(next_url)
            if teacher_student_only and action in {"invite_student", "bulk_invite_students"}:
                self.request.POST = self.request.POST.copy()
                self.request.POST["invite_role_type"] = MembershipRequestRoleType.STUDENT
            if teacher_student_only and action == "revoke_sent_invites":
                self.request.POST = self.request.POST.copy()
                self.request.POST["revoke_role_type"] = MembershipRequestRoleType.STUDENT
            if action in {"approve_requested_student", "add_student"}:
                target_user_id = self.request.POST.get("user_id")
                target_profile = get_object_or_404(UserProfile.objects.select_related("user"), user_id=target_user_id)
                is_ok, error_message = self._approve_requested_profile(target_profile)
                if not is_ok:
                    messages.error(self.request, error_message)
                    return redirect(next_url)
                messages.success(self.request, f"Uğurla əlavə edildi: {target_profile.user.username}.")
                return redirect(next_url)
            if action == "bulk_approve_requested_students":
                single_user_id = (self.request.POST.get("single_user_id") or "").strip()
                reject_user_id = (self.request.POST.get("reject_user_id") or "").strip()
                bulk_reject_mode = (self.request.POST.get("bulk_reject") or "").strip() == "1"
                selected_user_ids = _csv_to_int_set(self.request.POST.get("selected_user_ids"))
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
                        int(user_id)
                        for user_id in self.request.POST.getlist("selected_pending_user_ids")
                        if user_id.isdigit()
                    }
                if not selected_user_ids:
                    if bulk_reject_mode:
                        messages.error(self.request, "Silmək üçün ən azı bir tələbə seçin.")
                    else:
                        messages.error(self.request, "Təsdiq üçün ən azı bir tələbə seçin.")
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
                        is_ok, _ = self._reject_requested_profile(pending_profile)
                    else:
                        is_ok, _ = self._approve_requested_profile(pending_profile)
                    if is_ok:
                        processed_count += 1
                    else:
                        failed_usernames.append(pending_profile.user.username)
                if processed_count:
                    if bulk_reject_mode or is_single_reject:
                        if is_single_reject and processed_count == 1:
                            messages.success(self.request, "Uğurla yeniləndi: tələbə müraciəti silindi.")
                        else:
                            messages.success(
                                self.request, f"Uğurla yeniləndi: {processed_count} tələbənin müraciəti silindi."
                            )
                    elif is_single_approve and processed_count == 1:
                        messages.success(self.request, "Uğurla əlavə edildi: 1 tələbə əlavə edildi.")
                    else:
                        messages.success(self.request, f"Uğurla əlavə edildi: {processed_count} tələbə əlavə edildi.")
                if failed_usernames:
                    messages.warning(
                        self.request, "Bu istifadəçilər üçün əməliyyat tamamlanmadı: " + ", ".join(failed_usernames[:8])
                    )
                return redirect(next_url)
            if action in {
                "invite_student",
                "bulk_invite_students",
                "invite_teacher_staff",
                "bulk_invite_teacher_staff",
            }:
                invite_role_type = (
                    (self.request.POST.get("invite_role_type") or MembershipRequestRoleType.STUDENT).strip().lower()
                )
                if invite_role_type not in {
                    MembershipRequestRoleType.STUDENT,
                    MembershipRequestRoleType.TEACHER,
                    MembershipRequestRoleType.STAFF,
                }:
                    invite_role_type = MembershipRequestRoleType.STUDENT
                invite_role_label = _membership_request_role_label(invite_role_type).lower()
                if action in {"invite_student", "invite_teacher_staff"}:
                    single_user_id = (self.request.POST.get("user_id") or "").strip()
                else:
                    single_user_id = (self.request.POST.get("single_invite_user_id") or "").strip()
                selected_user_ids = _csv_to_int_set(self.request.POST.get("selected_user_ids"))
                is_single_invite = False
                if single_user_id.isdigit():
                    selected_user_ids = {int(single_user_id)}
                    is_single_invite = True
                if not selected_user_ids:
                    field_name = "selected_unassigned_user_ids"
                    if invite_role_type == MembershipRequestRoleType.TEACHER:
                        field_name = "selected_unassigned_teacher_user_ids"
                    elif invite_role_type == MembershipRequestRoleType.STAFF:
                        field_name = "selected_unassigned_staff_user_ids"
                    selected_user_ids = {
                        int(user_id) for user_id in self.request.POST.getlist(field_name) if user_id.isdigit()
                    }
                if not selected_user_ids:
                    messages.error(self.request, f"Dəvət göndərmək üçün ən azı bir {invite_role_label} seçin.")
                    return redirect(next_url)
                processed_count = 0
                failed_usernames = []
                target_users = User.objects.filter(id__in=selected_user_ids, is_active=True).order_by("username")
                for target_user in target_users:
                    if invite_role_type == MembershipRequestRoleType.STUDENT:
                        is_ok, _ = self._invite_student_user(target_user)
                    else:
                        is_ok, _ = self._invite_user_for_role(target_user, invite_role_type)
                    if is_ok:
                        processed_count += 1
                    else:
                        failed_usernames.append(target_user.username)
                if processed_count:
                    if is_single_invite and processed_count == 1:
                        messages.success(
                            self.request, f"Uğurla əlavə edildi: {target_users.first().username} üçün dəvət göndərildi."
                        )
                    else:
                        messages.success(
                            self.request,
                            f"Uğurla əlavə edildi: {processed_count} {invite_role_label} istifadəçiyə dəvət göndərildi.",
                        )
                if failed_usernames:
                    messages.warning(
                        self.request, "Bu istifadəçilər üçün dəvət göndərilmədi: " + ", ".join(failed_usernames[:8])
                    )
                return redirect(next_url)
            if action in {"revoke_sent_invites", "revoke_teacher_staff_invites"}:
                revoke_role_type = (
                    (self.request.POST.get("revoke_role_type") or MembershipRequestRoleType.STUDENT).strip().lower()
                )
                if revoke_role_type not in {
                    MembershipRequestRoleType.STUDENT,
                    MembershipRequestRoleType.TEACHER,
                    MembershipRequestRoleType.STAFF,
                }:
                    revoke_role_type = MembershipRequestRoleType.STUDENT
                single_revoke_user_id = (self.request.POST.get("single_revoke_user_id") or "").strip()
                selected_user_ids = _csv_to_int_set(self.request.POST.get("selected_user_ids"))
                is_single_revoke = False
                if single_revoke_user_id.isdigit():
                    selected_user_ids = {int(single_revoke_user_id)}
                    is_single_revoke = True
                if not selected_user_ids:
                    field_name = "selected_sent_invite_user_ids"
                    if revoke_role_type == MembershipRequestRoleType.TEACHER:
                        field_name = "selected_sent_teacher_invite_user_ids"
                    elif revoke_role_type == MembershipRequestRoleType.STAFF:
                        field_name = "selected_sent_staff_invite_user_ids"
                    selected_user_ids = {
                        int(user_id) for user_id in self.request.POST.getlist(field_name) if user_id.isdigit()
                    }
                if not selected_user_ids:
                    messages.error(self.request, "Geri çəkmək üçün ən azı bir dəvət seçin.")
                    return redirect(next_url)
                processed_count = 0
                failed_usernames = []
                target_users = User.objects.filter(id__in=selected_user_ids, is_active=True).order_by("username")
                for target_user in target_users:
                    is_ok, _ = self._revoke_sent_invite_for_user(target_user, revoke_role_type)
                    if is_ok:
                        processed_count += 1
                    else:
                        failed_usernames.append(target_user.username)
                if processed_count:
                    if is_single_revoke and processed_count == 1:
                        messages.success(self.request, "Dəvət geri çəkildi.")
                    else:
                        messages.success(self.request, f"{processed_count} dəvət geri çəkildi.")
                if failed_usernames:
                    messages.warning(
                        self.request,
                        "Bu istifadəçilər üçün geri çəkmə tamamlanmadı: " + ", ".join(failed_usernames[:8]),
                    )
                return redirect(next_url)
            if action in {"remove_student", "remove_org_member"}:
                target_user_id = self.request.POST.get("user_id")
                self.remove_reason = (self.request.POST.get("remove_reason") or "").strip()
                if not self.remove_reason:
                    messages.warning(
                        self.request,
                        "Uzaqlaşdırma üçün səbəb qeyd etmək məcburidir. Zəhmət olmasa səbəb yazın və yenidən cəhd edin.",
                    )
                    return redirect(next_url)
                target_user = get_object_or_404(User, id=target_user_id, is_active=True)
                is_ok, error_message = self._remove_org_member(target_user, remove_reason=self.remove_reason)
                if not is_ok:
                    messages.error(self.request, error_message)
                    return redirect(next_url)
                messages.success(self.request, f"Uğurla uzaqlaşdırıldı: {target_user.username}.")
                return redirect(next_url)
            if action in {"approve_teacher_staff_request", "reject_teacher_staff_request"}:
                from apps.notifications.models import MembershipRequestRoleType as MRR
                from core.rls import bypass_rls as _bypass_rls_ts

                request_id = (
                    self.request.POST.get("request_id") or self.request.POST.get("ts_request_id") or ""
                ).strip()
                if not request_id.isdigit():
                    messages.error(self.request, "Keçərsiz müraciət ID-si.")
                    return redirect(next_url)
                with _bypass_rls_ts():
                    ts_request = StudentOrganizationRequest.objects.filter(
                        id=int(request_id),
                        organization=self.org,
                        status=StudentOrganizationRequestStatus.PENDING,
                        role_type__in=[MRR.TEACHER, MRR.STAFF],
                    ).first()
                if ts_request is None:
                    messages.error(self.request, "Müraciət tapılmadı və ya artıq cavablandırılıb.")
                    return redirect(next_url)
                if action == "approve_teacher_staff_request":
                    with _bypass_rls_ts():
                        with transaction.atomic():
                            target_profile, _ = UserProfile.objects.get_or_create(user=ts_request.user)
                            _set_student_org_request_status(
                                request_obj=ts_request,
                                status=StudentOrganizationRequestStatus.APPROVED,
                                note="Qəbul edildi.",
                                responded_by=self.request.user,
                            )
                            from apps.organizations.models import Membership  # noqa: F811

                            role_name = "teacher" if ts_request.role_type == MRR.TEACHER else "member"
                            role_obj = self.org.roles.filter(name=role_name, is_active=True).first()
                            if role_obj is None:
                                if ts_request.role_type == MRR.STAFF:
                                    for fallback_name in ["staff", "hr", "member"]:
                                        role_obj = self.org.roles.filter(name=fallback_name, is_active=True).first()
                                        if role_obj:
                                            break
                                if role_obj is None:
                                    role_obj = self.org.roles.filter(is_active=True).order_by("level").first()
                            if role_obj:
                                existing_membership = (
                                    Membership.objects.filter(user=ts_request.user, organization=self.org)
                                    .order_by("-is_active", "-is_primary", "-role__level")
                                    .first()
                                )
                                has_other_primary = (
                                    Membership.objects.filter(user=ts_request.user, is_active=True, is_primary=True)
                                    .exclude(organization=self.org)
                                    .exists()
                                )
                                if existing_membership:
                                    existing_membership.role = role_obj
                                    existing_membership.is_active = True
                                    existing_membership.is_primary = not has_other_primary
                                    existing_membership.title = ""
                                    existing_membership.save(
                                        update_fields=["role", "is_active", "is_primary", "title", "updated_at"]
                                    )
                                else:
                                    Membership.objects.create(
                                        user=ts_request.user,
                                        organization=self.org,
                                        role=role_obj,
                                        assigned_by=self.request.user,
                                        is_active=True,
                                        is_primary=not has_other_primary,
                                    )
                                target_profile.organization = self.org
                                target_profile.organization_type = self.org.org_type
                                if ts_request.role_type == MRR.TEACHER:
                                    target_profile.role = ProfileRole.TEACHER
                                elif ts_request.role_type == MRR.STAFF:
                                    target_profile.role = ProfileRole.MEMBER
                                else:
                                    target_profile.role = ProfileRole.MEMBER
                                target_profile.requested_organization = None
                                target_profile.requested_organization_name = ""
                                target_profile.requested_organization_message = ""
                                target_profile.save(
                                    update_fields=[
                                        "organization",
                                        "organization_type",
                                        "role",
                                        "requested_organization",
                                        "requested_organization_name",
                                        "requested_organization_message",
                                        "updated_at",
                                    ]
                                )
                            _close_other_pending_student_requests(
                                user=ts_request.user, accepted_organization=self.org, responded_by=self.request.user
                            )
                        create_audit_log(
                            user=self.request.user,
                            organization=self.org,
                            action="update",
                            resource_type="membership",
                            resource_id=ts_request.user.id,
                            resource_repr=f"{ts_request.user.username} approved as {role_name}",
                            old_values={"status": "pending"},
                            new_values={
                                "status": "approved",
                                "role": role_name,
                                "action": "approve_teacher_staff_request",
                            },
                            request=self.request,
                        )
                    messages.success(
                        self.request, f"{ts_request.user.get_full_name() or ts_request.user.username} qəbul edildi."
                    )
                else:
                    with _bypass_rls_ts():
                        target_profile, _ = UserProfile.objects.get_or_create(user=ts_request.user)
                        _set_student_org_request_status(
                            request_obj=ts_request,
                            status=StudentOrganizationRequestStatus.REJECTED,
                            note="Müraciət rədd edildi.",
                            responded_by=self.request.user,
                        )
                        _sync_profile_pending_request_snapshot(target_profile)
                    messages.success(
                        self.request,
                        f"{ts_request.user.get_full_name() or ts_request.user.username} müraciəti rədd edildi.",
                    )
                return redirect(next_url)
            messages.error(self.request, "Naməlum əməliyyat.")
            return redirect(next_url)
        return _render_profile_section(self.request, "student-organization-management")
