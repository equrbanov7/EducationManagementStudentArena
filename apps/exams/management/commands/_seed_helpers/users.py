"""seed_group_demo_data — İstifadəçi/təşkilat/üzvlük seed köməkçiləri."""

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model

from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType
from core.roles import ProfileRole

User = get_user_model()


class UsersSeedMixin:
    """İstifadəçi/təşkilat/üzvlük seed köməkçiləri (Command tərəfindən MRO ilə istifadə olunur)."""

    def _ensure_user(self, username, email, password):
        user, _ = User.objects.get_or_create(username=username, defaults={"email": email})
        updated_fields = []
        if user.email != email:
            user.email = email
            updated_fields.append("email")

        user.is_active = True
        updated_fields.append("is_active")
        user.set_password(password)
        updated_fields.append("password")
        user.save(update_fields=updated_fields)
        return user

    def _assign_profile(self, user, organization, role):
        UserProfile = django_apps.get_model("accounts", "UserProfile")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.organization = organization
        profile.organization_type = organization.org_type if organization else OrganizationType.INDIVIDUAL
        profile.role = role
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        user.__dict__["profile"] = profile

    def _ensure_organization(self, name, org_type, owner):
        organization, created = Organization.objects.get_or_create(
            name=name,
            defaults={
                "org_type": org_type,
                "owner": owner,
                "status": "active",
                "is_active": True,
            },
        )
        if created:
            return organization

        update_fields = []
        if organization.org_type != org_type:
            organization.org_type = org_type
            update_fields.append("org_type")
        if organization.owner_id != owner.id:
            organization.owner = owner
            update_fields.append("owner")
        if organization.status != "active":
            organization.status = "active"
            update_fields.append("status")
        if not organization.is_active:
            organization.is_active = True
            update_fields.append("is_active")
        if update_fields:
            organization.save(update_fields=update_fields)
        return organization

    def _resolve_role(self, organization, profile_role, owner_role=None):
        roles = Role.objects.filter(organization=organization, is_active=True)
        if not roles.exists():
            return None

        if profile_role == ProfileRole.ORG_OWNER:
            return roles.order_by("-level").first()

        if profile_role == ProfileRole.ORG_ADMIN:
            if owner_role is not None:
                role = roles.filter(level__lt=owner_role.level).order_by("-level").first()
                if role:
                    return role
            return roles.order_by("-level").first()

        if profile_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}:
            for role_name in [
                "teacher",
                "instructor",
                "assistant_teacher",
                "assistant",
                "professor",
                "associate_professor",
            ]:
                role = roles.filter(name=role_name).first()
                if role:
                    return role
            if profile_role == ProfileRole.TEACHER:
                role, _ = Role.objects.get_or_create(
                    organization=organization,
                    name=ProfileRole.TEACHER,
                    defaults={
                        "display_name": "Teacher",
                        "description": "Demo teacher role created for group demo seed data",
                        "level": ProfileRole.LEVELS[ProfileRole.TEACHER],
                        "scope_type": RoleScopeType.COURSE,
                        "permissions": [
                            "course.view",
                            "course.create",
                            "course.edit",
                            "grade.view",
                            "grade.input",
                            "exam.view",
                            "exam.create",
                            "exam.edit",
                            "exam.host",
                        ],
                        "is_system": True,
                        "is_active": True,
                    },
                )
                return role
            return roles.filter(level__gte=50).order_by("level").first() or roles.order_by("-level").first()

        if profile_role == ProfileRole.STUDENT:
            return roles.filter(name="student").first() or roles.order_by("level").first()

        if profile_role == ProfileRole.MEMBER:
            return (
                roles.filter(name="member").first()
                or roles.filter(name="student").first()
                or roles.order_by("level").first()
            )

        return roles.order_by("level").first()

    def _ensure_membership(self, user, organization, role, assigned_by):
        if role is None:
            return None
        membership, _ = Membership.objects.get_or_create(
            user=user,
            organization=organization,
            defaults={
                "role": role,
                "is_primary": True,
                "is_active": True,
                "assigned_by": assigned_by,
            },
        )
        update_fields = []
        if membership.role_id != role.id:
            membership.role = role
            update_fields.append("role")
        if not membership.is_primary:
            membership.is_primary = True
            update_fields.append("is_primary")
        if not membership.is_active:
            membership.is_active = True
            update_fields.append("is_active")
        if membership.assigned_by_id != assigned_by.id:
            membership.assigned_by = assigned_by
            update_fields.append("assigned_by")
        if update_fields:
            membership.save(update_fields=update_fields + ["updated_at"])
        return membership
