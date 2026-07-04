"""Seed a demo "Qərbi Kaspi Universiteti" tenant with the full role hierarchy.

Creates one University organization, its academic-unit tree
(Faculty → Chair → Specialty → Group) and one sample user per university role
(rector … student), each wired to the matching organization Role via a
Membership (unit-scoped where the role is unit-scoped).

Idempotent: safe to re-run — users, org, units and memberships are
get_or_create / update_or_create keyed on stable slugs/usernames.

Usage::

    python manage.py seed_western_caspian --password "DemoPass123!"

The password is required so seeded credentials are always explicit (never a
baked-in default). Every sample user shares that password and (per the
e-university provisioning model) is flagged to set their own password + verify
their email on first login when that flow is enabled.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic
from core.roles import ProfileRole

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the Qərbi Kaspi Universiteti demo tenant with all university roles and the academic hierarchy."

    ORG_NAME = "Qərbi Kaspi Universiteti"
    ORG_SLUG = "qerbi-kaspi-universiteti"

    FACULTY_NAME = "Mühəndislik və Tətbiqi Elmlər fakültəsi"
    CHAIR_NAME = "Kompüter elmləri kafedrası"
    SPECIALTY_NAME = "Kompüter elmləri (ixtisas)"
    GROUP_NAME = "KE-101"

    # (username, role_name, ProfileRole, scope) — scope: None | "faculty" | "chair" | "group"
    ROLE_USERS = [
        ("wcu_rector", "rector", ProfileRole.ORG_ADMIN, None),
        ("wcu_vice_rector", "vice_rector", ProfileRole.ORG_ADMIN, None),
        ("wcu_exam_center", "exam_center", ProfileRole.MEMBER, None),
        ("wcu_hr", "hr", ProfileRole.HR, None),
        ("wcu_dean", "dean", ProfileRole.ORG_ADMIN, "faculty"),
        ("wcu_department_head", "chair_head", ProfileRole.ORG_ADMIN, "chair"),
        ("wcu_teacher", "teacher", ProfileRole.TEACHER, None),
        ("wcu_assistant", "assistant", ProfileRole.ASSISTANT_TEACHER, None),
        ("wcu_lab_assistant", "lab_assistant", ProfileRole.ASSISTANT_TEACHER, None),
        ("wcu_tutor", "tutor", ProfileRole.MEMBER, "group"),
        ("wcu_lead_student", "lead_student", ProfileRole.LEAD_STUDENT, "group"),
        ("wcu_student1", "student", ProfileRole.STUDENT, "group"),
        ("wcu_student2", "student", ProfileRole.STUDENT, "group"),
        ("wcu_student3", "student", ProfileRole.STUDENT, "group"),
    ]

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Shared password for every seeded user (required).")
        parser.add_argument(
            "--no-first-login-flow",
            action="store_true",
            help="Do not flag seeded users for the first-login password/email step.",
        )

    def handle(self, *args, **options):
        password = (options.get("password") or "").strip()
        if not password:
            raise CommandError("--password is required so seeded credentials are explicit.")
        flag_first_login = not options.get("no_first_login_flow")

        with rls_worker_atomic(), bypass_rls():
            owner = self._ensure_user(
                username="wcu_rector",
                password=password,
                email="rector@qku.edu.az",
                first_name="Rəşad",
                last_name="Rektorov",
                flag_first_login=flag_first_login,
            )
            org = self._ensure_org(owner)
            roles = {role.name: role for role in Role.objects.filter(organization=org)}
            units = self._ensure_academic_hierarchy(org)

            created = 0
            for username, role_name, profile_role, scope_key in self.ROLE_USERS:
                role = roles.get(role_name)
                if role is None:
                    self.stdout.write(self.style.WARNING(f"  role '{role_name}' missing on org — skipped {username}"))
                    continue
                user = self._ensure_user(
                    username=username,
                    password=password,
                    email=f"{username}@qku.edu.az",
                    first_name=username.replace("wcu_", "").replace("_", " ").title(),
                    last_name="Test",
                    flag_first_login=flag_first_login and username != "wcu_rector",
                )
                self._configure_profile(user, org, profile_role, units, scope_key)
                scope_unit = self._scope_unit_for(role, units, scope_key)
                self._ensure_membership(
                    user=user, organization=org, role=role, scope_unit=scope_unit, assigned_by=owner
                )
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Qərbi Kaspi Universiteti seeded: org='{org.slug}', {created} role users, "
                f"{len(units)} academic units. Shared password set as provided."
            )
        )

    # ── helpers ────────────────────────────────────────────────────────────

    def _ensure_user(self, *, username, password, email, first_name, last_name, flag_first_login):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "first_name": first_name, "last_name": last_name, "is_active": True},
        )
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.is_active = True
        user.set_password(password)
        user.save()
        # Flag the first-login password/email step when that flow is enabled
        # (only applied if the profile has the fields; ignored otherwise).
        profile = getattr(user, "profile", None)
        if profile is not None:
            updated = []
            if flag_first_login and hasattr(profile, "password_change_required"):
                profile.password_change_required = True
                updated.append("password_change_required")
            if hasattr(profile, "email_verified"):
                profile.email_verified = not flag_first_login
                updated.append("email_verified")
            if updated:
                profile.save(update_fields=[*updated, "updated_at"])
        return user

    def _ensure_org(self, owner):
        org, _ = Organization.objects.get_or_create(
            slug=self.ORG_SLUG,
            defaults={
                "name": self.ORG_NAME,
                "org_type": OrganizationType.UNIVERSITY,
                "owner": owner,
                "status": "active",
                "is_active": True,
            },
        )
        if org.owner_id != owner.id:
            org.owner = owner
            org.save(update_fields=["owner", "updated_at"])
        return org

    def _ensure_unit(self, *, org, unit_type, name, parent=None):
        unit, _ = OrgUnit.objects.get_or_create(
            organization=org,
            name=name,
            defaults={"unit_type": unit_type, "parent": parent},
        )
        changed = []
        if unit.unit_type != unit_type:
            unit.unit_type = unit_type
            changed.append("unit_type")
        if unit.parent_id != (parent.id if parent else None):
            unit.parent = parent
            changed.append("parent")
        if changed:
            unit.save(update_fields=[*changed, "updated_at"])
        return unit

    def _ensure_academic_hierarchy(self, org):
        faculty = self._ensure_unit(org=org, unit_type=OrgUnitType.FACULTY, name=self.FACULTY_NAME)
        chair = self._ensure_unit(org=org, unit_type=OrgUnitType.CHAIR, name=self.CHAIR_NAME, parent=faculty)
        specialty = self._ensure_unit(org=org, unit_type=OrgUnitType.SPECIALTY, name=self.SPECIALTY_NAME, parent=chair)
        group = self._ensure_unit(org=org, unit_type=OrgUnitType.GROUP, name=self.GROUP_NAME, parent=specialty)
        return {"faculty": faculty, "chair": chair, "specialty": specialty, "group": group}

    def _configure_profile(self, user, org, profile_role, units, scope_key):
        profile = user.profile
        profile.organization = org
        profile.organization_type = OrganizationType.UNIVERSITY
        profile.country = "Azerbaijan"
        profile.role = profile_role
        if profile_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
            profile.student_university_name = org.name
            profile.student_specialization = self.SPECIALTY_NAME
            profile.student_group_number = self.GROUP_NAME
        profile.save()
        return profile

    def _scope_unit_for(self, role, units, scope_key):
        # Only unit/course-scoped roles carry a scope_unit; org-scoped roles stay org-wide.
        if role.scope_type not in {RoleScopeType.UNIT, RoleScopeType.COURSE}:
            return None
        return units.get(scope_key) if scope_key else None

    def _ensure_membership(self, *, user, organization, role, scope_unit, assigned_by):
        membership, _ = Membership.objects.update_or_create(
            user=user,
            organization=organization,
            role=role,
            scope_unit=scope_unit,
            defaults={"assigned_by": assigned_by, "is_primary": True, "is_active": True},
        )
        return membership
