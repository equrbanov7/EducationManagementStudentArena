"""
Create the deterministic university user used by CI Playwright smoke tests.

The command is intentionally idempotent so the CI job can run it on every
execution against a fresh or reused database without creating duplicates.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import ProfileRole
from apps.organizations.default_roles import get_default_roles_for_org_type
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the CI E2E university user with all default university roles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="ci_university_e2e",
            help="Username for the CI E2E user.",
        )
        parser.add_argument(
            "--password",
            default="CiE2EUniversity2026!",
            help="Password for the CI E2E user.",
        )
        parser.add_argument(
            "--email",
            default="ci-university-e2e@emsarena.local",
            help="Email address for the CI E2E user.",
        )
        parser.add_argument(
            "--org-name",
            default="CI E2E University",
            help="Display name for the seeded university organization.",
        )
        parser.add_argument(
            "--org-slug",
            default="ci-e2e-university",
            help="Slug for the seeded university organization.",
        )

    def _ensure_roles(self, organization):
        roles = {}
        for role_template in get_default_roles_for_org_type(OrganizationType.UNIVERSITY):
            role, _ = Role.objects.update_or_create(
                organization=organization,
                name=role_template["name"],
                defaults={
                    "display_name": role_template["display_name"],
                    "description": role_template.get("description", ""),
                    "level": role_template["level"],
                    "scope_type": role_template["scope_type"],
                    "permissions": role_template["permissions"],
                    "is_system": True,
                    "is_active": True,
                },
            )
            roles[role.name] = role
        return roles

    def _ensure_units(self, organization, owner):
        rectorate, _ = OrgUnit.objects.update_or_create(
            organization=organization,
            slug="ci-e2e-rectorate",
            defaults={
                "parent": None,
                "unit_type": "rectorate",
                "name": "CI Rectorate",
                "code": "RECT",
                "head": owner,
                "is_active": True,
            },
        )
        faculty, _ = OrgUnit.objects.update_or_create(
            organization=organization,
            slug="ci-e2e-faculty",
            defaults={
                "parent": None,
                "unit_type": "faculty",
                "name": "Faculty of Platform Testing",
                "code": "FPT",
                "head": owner,
                "is_active": True,
            },
        )
        department, _ = OrgUnit.objects.update_or_create(
            organization=organization,
            slug="ci-e2e-department",
            defaults={
                "parent": faculty,
                "unit_type": "department",
                "name": "Department of Smoke Automation",
                "code": "DSA",
                "head": owner,
                "is_active": True,
            },
        )
        return {
            "rectorate": rectorate,
            "faculty": faculty,
            "department": department,
        }

    @staticmethod
    def _scope_for_role(role_name, units):
        if role_name == "dean":
            return units["faculty"]
        if role_name in {"chair_head", "student"}:
            return units["department"]
        return None

    def _ensure_membership(self, user, organization, role, *, scope_unit):
        memberships = list(
            Membership.objects.filter(
                user=user,
                organization=organization,
                role=role,
            ).order_by("created_at")
        )

        if memberships:
            membership = memberships[0]
        else:
            membership = Membership(
                user=user,
                organization=organization,
                role=role,
            )

        membership.scope_unit = scope_unit
        membership.title = role.display_name
        membership.assigned_by = user
        membership.is_active = True
        membership.save()

        for extra_membership in memberships[1:]:
            if extra_membership.is_active:
                extra_membership.is_active = False
                extra_membership.save(update_fields=["is_active"])

        return membership

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        email = options["email"]
        org_name = options["org_name"]
        org_slug = options["org_slug"]

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": "CI",
                "last_name": "University",
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )

        user.email = email
        user.first_name = user.first_name or "CI"
        user.last_name = user.last_name or "University"
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_password(password)
        user.save()

        organization, org_created = Organization.objects.update_or_create(
            slug=org_slug,
            defaults={
                "name": org_name,
                "org_type": OrganizationType.UNIVERSITY,
                "owner": user,
                "description": "Deterministic organization used by CI E2E smoke tests.",
                "country": "Azerbaijan",
                "organization_identifier": "CI-E2E-UNI",
                "email": "ci-e2e@emsarena.local",
                "phone": "+994000000000",
                "address": "CI Test Campus",
                "website": "https://emsarena.local/ci-e2e-university",
                "is_active": True,
                "status": "active",
            },
        )

        roles = self._ensure_roles(organization)
        units = self._ensure_units(organization, user)

        profile = user.profile
        profile.organization = organization
        profile.organization_type = OrganizationType.UNIVERSITY
        profile.country = "Azerbaijan"
        profile.student_university_name = organization.name
        profile.role = ProfileRole.ORG_OWNER
        profile.save(
            update_fields=[
                "organization",
                "organization_type",
                "country",
                "student_university_name",
                "role",
                "updated_at",
            ]
        )

        seeded_memberships = []
        for role_name in sorted(roles):
            role = roles[role_name]
            membership = self._ensure_membership(
                user,
                organization,
                role,
                scope_unit=self._scope_for_role(role_name, units),
            )
            seeded_memberships.append(membership)

        rector_membership = next(
            (membership for membership in seeded_memberships if membership.role.name == "rector"),
            None,
        )
        if rector_membership and not rector_membership.is_primary:
            rector_membership.is_primary = True
            rector_membership.save(update_fields=["is_primary"])

        action = "Created" if created else "Updated"
        org_action = "created" if org_created else "updated"
        self.stdout.write(self.style.SUCCESS(f"{action} CI E2E user '{username}'."))
        self.stdout.write(self.style.SUCCESS(f"Organization '{org_slug}' {org_action}."))
        self.stdout.write(
            self.style.SUCCESS(
                "Seeded university memberships: "
                + ", ".join(sorted(membership.role.name for membership in seeded_memberships))
            )
        )
