"""
Management command to backfill explicit Membership rows for legacy admin profiles.

Background
----------
The old ``UserProfile.role`` + ``UserProfile.organization`` fields were the sole
authority for org-admin / org-owner access.  The new RBAC stack requires an
explicit ``Membership`` row.  A transitional helper in the middleware
(``_can_bootstrap_admin``) prevented lock-outs during the migration window,
but it must be removed once all legacy admins have real memberships.

This command performs the one-time data backfill so that ``_can_bootstrap_admin``
can be safely deleted from the middleware.

Usage
-----
Audit (dry-run, no writes):
    python manage.py backfill_admin_memberships --dry-run

Backfill all legacy admins:
    python manage.py backfill_admin_memberships

Limit to a specific organization:
    python manage.py backfill_admin_memberships --org <slug>

Verbose output:
    python manage.py backfill_admin_memberships --verbosity 2
"""

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Backfill explicit Membership rows for every legacy ORG_OWNER / ORG_ADMIN profile "
        "that does not yet have a real membership record. "
        "Run with --dry-run to audit without writing anything."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be done without writing to the database.",
        )
        parser.add_argument(
            "--org",
            metavar="SLUG",
            default=None,
            help="Restrict the backfill to a single organization identified by its slug.",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _select_admin_role(self, organization):
        """
        Return the best Role to assign to a backfilled legacy admin.

        Strategy (in priority order):
        1. A system role whose name is ``org_owner`` or ``org_admin``.
        2. The highest-level active role in the organization.
        3. ``None`` — caller must handle the no-role edge-case.
        """
        from apps.organizations.models import Role

        qs = Role.objects.filter(organization=organization, is_active=True)

        # Prefer a named admin role if one exists.
        admin_role = qs.filter(name__in=["org_owner", "org_admin"]).order_by("-level").first()
        if admin_role:
            return admin_role

        # Fall back to the highest-level role available.
        return qs.order_by("-level").first()

    def _backfill_user(self, user, organization, profile_role_label, *, dry_run, verbosity):
        """
        Ensure *user* has an active Membership in *organization*.

        Returns ``"created"``, ``"skipped"``, or ``"no_role"``.
        """
        from apps.organizations.models import Membership

        already_exists = Membership.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
        ).exists()

        if already_exists:
            if verbosity >= 2:
                self.stdout.write(f"  SKIP  {user.username} ({profile_role_label}) — active membership already exists")
            return "skipped"

        role = self._select_admin_role(organization)
        if role is None:
            self.stderr.write(
                self.style.WARNING(
                    f"  WARN  {user.username} — no active roles found in {organization.slug!r}; skipping"
                )
            )
            return "no_role"

        if verbosity >= 1:
            action = "Would create" if dry_run else "Creating"
            self.stdout.write(
                f"  {action} membership: {user.username} ({profile_role_label})"
                f" → role={role.name!r} in org={organization.slug!r}"
            )

        if not dry_run:
            with transaction.atomic():
                Membership.objects.create(
                    user=user,
                    organization=organization,
                    role=role,
                    is_primary=not Membership.objects.filter(user=user, is_primary=True).exists(),
                    is_active=True,
                    assigned_by=None,
                )

        return "created"

    # ------------------------------------------------------------------
    # Main handler
    # ------------------------------------------------------------------

    @rls_worker_atomic()
    @bypass_rls()
    def handle(self, *args, **options):
        from django.apps import apps as django_apps

        from core.roles import ProfileRole

        UserProfile = django_apps.get_model("accounts", "UserProfile")
        from apps.organizations.models import Organization

        dry_run = options["dry_run"]
        org_slug = options["org"]
        verbosity = options["verbosity"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN mode — no changes will be written.\n"))

        # Resolve target org(s).
        if org_slug:
            try:
                target_orgs = {Organization.objects.get(slug=org_slug)}
            except Organization.DoesNotExist:
                raise CommandError(f"Organization with slug {org_slug!r} does not exist.")
        else:
            target_orgs = None  # noqa: F841 – resolved per-profile below when org_slug is absent

        # Fetch legacy admin profiles.
        admin_roles = {ProfileRole.ORG_OWNER, ProfileRole.ORG_ADMIN}
        profiles_qs = UserProfile.objects.filter(role__in=admin_roles, organization__isnull=False).select_related(
            "user", "organization"
        )
        if org_slug:
            profiles_qs = profiles_qs.filter(organization__slug=org_slug)

        profiles = list(profiles_qs)

        if not profiles:
            self.stdout.write(self.style.SUCCESS("No legacy admin profiles found. Nothing to do."))
            return

        self.stdout.write(
            f"Found {len(profiles)} legacy admin profile(s) to evaluate"
            + (f" in org {org_slug!r}" if org_slug else "")
            + ".\n"
        )

        counts = {"created": 0, "skipped": 0, "no_role": 0}

        for profile in profiles:
            user = profile.user
            org = profile.organization

            # Guard: skip if the org itself is not active.
            if not org.is_active:
                if verbosity >= 2:
                    self.stdout.write(f"  SKIP  {user.username} — org {org.slug!r} is inactive")
                continue

            result = self._backfill_user(
                user,
                org,
                profile.role,
                dry_run=dry_run,
                verbosity=verbosity,
            )
            counts[result] = counts.get(result, 0) + 1

        # Summary.
        self.stdout.write("")
        verb = "Would create" if dry_run else "Created"
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {verb} {counts['created']} membership(s). "
                f"Skipped {counts['skipped']} (already had membership). "
                f"Skipped {counts['no_role']} (no role available in org)."
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY-RUN complete. Re-run without --dry-run to apply changes."))
