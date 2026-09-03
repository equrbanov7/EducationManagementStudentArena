"""
POST-form handling for the profile page.

``user_profile`` is a GET-oriented context builder; this module isolates the
``request.method == "POST"`` branch. ``handle_profile_post`` returns either:

* an ``HttpResponse`` — the caller must return it immediately (redirect/JSON),
* or a ``dict`` of state overrides the caller merges before building the GET
  context (``active_section`` and the ``category_management_*`` forms).

Behavior is identical to the original inline block — this is a pure extraction.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import pgettext_lazy

from apps.audit.public import log_action
from core.upload_security import randomize_uploaded_filename

from ... import profile_hooks
from ...models import ProfileRole
from ...services.profile_actions import publish_system_notification
from .._helpers import _user_has_any_role

User = get_user_model()


def _log_password_change(request, *, method):
    """Şifrə dəyişməsini audit jurnalına yazır (təhlükəsizlik izi)."""
    from core.constants import AuditAction

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        reason=f"Password changed via {method}",
        request=request,
        resource_type="UserPassword",
        resource_id=str(request.user.pk),
        resource_repr=request.user.username,
    )


def handle_profile_post(
    request,
    *,
    profile,
    capabilities,
    allowed_sections,
    active_section,
    password_change_form,
    validate_avatar_upload,
):
    """
    Process the POST branch of ``user_profile``.

    Returns a dict with keys:
      * ``response``: an HttpResponse to return immediately, or ``None``.
      * ``active_section``: the (possibly updated) active section.
      * ``password_change_form``: the (possibly rebound) password form.
      * ``category_management_create_form``: bound create form or ``None``.
      * ``category_management_edit_form``: bound edit form or ``None``.
      * ``category_management_edit_item``: the category being edited or ``None``.
    """
    from ...forms import CustomPasswordChangeForm, OTPPasswordResetConfirmForm

    category_management_create_form = None
    category_management_edit_form = None
    category_management_edit_item = None
    password_otp_form = None

    def _result(response=None):
        return {
            "response": response,
            "active_section": active_section,
            "password_change_form": password_change_form,
            "password_otp_form": password_otp_form,
            "category_management_create_form": category_management_create_form,
            "category_management_edit_form": category_management_edit_form,
            "category_management_edit_item": category_management_edit_item,
        }

    submitted_form = (request.POST.get("profile_form") or "").strip()

    if submitted_form == "update-avatar":
        uploaded_avatar = request.FILES.get("avatar")
        avatar_error = validate_avatar_upload(uploaded_avatar)
        if avatar_error:
            messages.error(request, avatar_error)
            return _result(redirect(f"{reverse('accounts:profile')}?section=profile-info"))

        randomize_uploaded_filename(uploaded_avatar)
        profile.avatar = uploaded_avatar
        profile.save(update_fields=["avatar", "updated_at"])
        messages.success(request, _("Profil şəkli uğurla yeniləndi."))
        return _result(redirect(f"{reverse('accounts:profile')}?section=profile-info"))

    if submitted_form == "change-password":
        password_change_form = CustomPasswordChangeForm(request.user, request.POST)
        if password_change_form.is_valid():
            user = password_change_form.save()
            update_session_auth_hash(request, user)
            _log_password_change(request, method="current-password")
            messages.success(request, _("Şifrə uğurla yeniləndi."))
            return _result(redirect(f"{reverse('accounts:profile')}?section=change-password"))

        messages.error(request, _("Şifrə yenilənmədi. Zəhmət olmasa formadakı xətaları düzəldin."))
        active_section = "change-password"
    elif submitted_form == "change-password-otp":
        # «Mövcud şifrəni unutdum» axını: emailə göndərilən OTP + yeni şifrə.
        # Kod PASSWORD_RESET məqsədli EmailOTP ilə yoxlanılır (bax password_otp.py).
        password_otp_form = OTPPasswordResetConfirmForm(request.user, request.POST)
        if password_otp_form.is_valid():
            user = password_otp_form.save()
            update_session_auth_hash(request, user)
            _log_password_change(request, method="email-otp")
            messages.success(request, _("Şifrə uğurla yeniləndi."))
            return _result(redirect(f"{reverse('accounts:profile')}?section=change-password"))

        messages.error(request, _("Şifrə yenilənmədi. Zəhmət olmasa formadakı xətaları düzəldin."))
        active_section = "change-password"
    elif submitted_form == "publish-notification":
        if "publish-notification" not in allowed_sections:
            messages.error(request, _("Bu əməliyyatı yerinə yetirmək üçün icazəniz yoxdur."))
            return _result(redirect(f"{reverse('accounts:profile')}?section=profile-info"))
        # Validation + fan-out lives in services.profile_actions (FAZA 8).
        ok, message_key = publish_system_notification(request=request, capabilities=capabilities)
        if ok:
            messages.success(request, _(message_key))
        else:
            messages.error(request, _(message_key))
        return _result(redirect(f"{reverse('accounts:profile')}?section=publish-notification"))
    else:
        # M2 (2026-07-02): kateqoriya CRUD budağı blog-a köçüb —
        # profile_hooks.category_post_actions (apps/blog/profile_sections.py).
        # None = bu POST kateqoriyalara aid deyil → köhnə generic fallback.
        _category_result = profile_hooks.category_post_actions(
            request, submitted_form=submitted_form, allowed_sections=allowed_sections
        )
        if _category_result is not None:
            if _category_result["response"] is not None:
                return _result(_category_result["response"])
            active_section = _category_result["active_section"]
            category_management_create_form = _category_result["create_form"]
            category_management_edit_form = _category_result["edit_form"]
            category_management_edit_item = _category_result["edit_item"]
        elif submitted_form != "edit-profile":
            target_section = request.GET.get("section") or request.POST.get("section") or active_section
            if target_section not in allowed_sections:
                target_section = "profile-info"
            return _result(redirect(f"{reverse('accounts:profile')}?section={target_section}"))

    if submitted_form == "edit-profile":
        allowed_user_fields = ["first_name", "last_name", "email"]
        user_update_payload = {
            "first_name": (request.POST.get("first_name", request.user.first_name) or "").strip(),
            "last_name": (request.POST.get("last_name", request.user.last_name) or "").strip(),
            "email": (request.POST.get("email", request.user.email) or "").strip().lower(),
        }
        first_name = user_update_payload["first_name"]
        last_name = user_update_payload["last_name"]
        new_email = user_update_payload["email"]

        if not first_name or not last_name or not new_email:
            messages.error(request, pgettext_lazy("accounts.profile_edit.message", "required_fields_missing"))
            return _result(redirect(f"{reverse('accounts:profile')}?section=edit-profile"))

        if new_email and User.objects.exclude(pk=request.user.pk).filter(email__iexact=new_email).exists():
            messages.error(request, pgettext_lazy("accounts.profile_edit.message", "email_already_in_use"))
            return _result(redirect(f"{reverse('accounts:profile')}?section=edit-profile"))

        # Update user info
        for field_name, field_value in user_update_payload.items():
            setattr(request.user, field_name, field_value)
        request.user.save(update_fields=allowed_user_fields)

        # Update profile. Uzunluqlar model max_length-ə server tərəfdə kəsilir —
        # maxlength yalnız client atributudur, birbaşa POST DataError verərdi.
        profile.phone = (request.POST.get("phone", profile.phone) or "").strip()[:20]
        profile.phone_secondary = (request.POST.get("phone_secondary", profile.phone_secondary) or "").strip()[:20]
        profile.bio = (request.POST.get("bio", profile.bio) or "").strip()
        profile.location = (request.POST.get("location", profile.location) or "").strip()[:100]

        # Qurum üzvünün akademik strukturu (təşkilat/fakültə/ixtisas/qrup)
        # universitet tərəfindən idarə olunur — formdan gələn dəyərlər qəbul
        # edilmir. Fərdi istifadəçi (təşkilatsız və ya şəxsi INDIVIDUAL org)
        # öz təhsil müəssisəsi və ixtisas mətnini redaktə edə bilər.
        has_org = profile.is_academics_locked
        if not has_org:
            profile.student_university_name = (
                request.POST.get("student_university_name", profile.student_university_name) or ""
            ).strip()
            profile.student_specialization = (
                request.POST.get("student_specialization", profile.student_specialization) or ""
            ).strip()

        # Elmi ad / dərəcə — tələbə olmayan rollar üçün, yalnız etibarlı seçimlər.
        if not capabilities.get("is_student"):
            title_value = (request.POST.get("academic_title") or "").strip()
            degree_value = (request.POST.get("academic_degree") or "").strip()
            valid_titles = {choice[0] for choice in profile.AcademicTitle.choices}
            valid_degrees = {choice[0] for choice in profile.AcademicDegree.choices}
            if title_value in valid_titles or title_value == "":
                profile.academic_title = title_value
            if degree_value in valid_degrees or degree_value == "":
                profile.academic_degree = degree_value

        # Handle avatar upload
        uploaded_avatar = request.FILES.get("avatar")
        if uploaded_avatar is not None:
            avatar_error = validate_avatar_upload(uploaded_avatar)
            if avatar_error:
                messages.error(request, avatar_error)
                return _result(redirect(f"{reverse('accounts:profile')}?section=edit-profile"))
            randomize_uploaded_filename(uploaded_avatar)
            profile.avatar = uploaded_avatar

        # Only admins can change supervisor_code
        if getattr(request.user, "is_admin_level", False):
            profile.supervisor_code = request.POST.get("supervisor_code", "")

        if (
            not has_org
            and _user_has_any_role(request.user, {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT})
            and not (profile.student_university_name or profile.student_school_identifier)
        ):
            messages.error(
                request,
                pgettext_lazy("accounts.profile_edit.message", "student_university_or_school_required"),
            )
            return _result(redirect(f"{reverse('accounts:profile')}?section=edit-profile"))

        profile.save()

        # Audit log for profile update
        from core.constants import AuditAction

        log_action(
            action=AuditAction.UPDATE,
            user=request.user,
            obj=profile,
            reason="Profile updated by user",
            request=request,
            resource_type="UserProfile",
            resource_id=str(profile.pk),
            resource_repr=f"{request.user.username}",
        )

        messages.success(request, pgettext_lazy("accounts.profile_edit.message", "profile_updated_successfully"))
        return _result(redirect("accounts:profile"))

    return _result(None)
