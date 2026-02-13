"""
Django management command to create all role groups.
Usage: python manage.py create_roles
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from core.constants import ORGANIZATION_ROLES


class Command(BaseCommand):
    help = "Create all role groups for the role hierarchy system"

    def handle(self, *args, **options):
        """
        Create all role groups from ORGANIZATION_ROLES.
        """
        self.stdout.write(self.style.WARNING("Creating role groups..."))

        # Collect all unique role names
        all_roles = set()
        for _org_type, roles in ORGANIZATION_ROLES.items():
            all_roles.update(roles.keys())

        # Sort roles alphabetically
        all_roles = sorted(all_roles)

        created_count = 0
        existing_count = 0

        for role_name in all_roles:
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Created group: {role_name}"))
            else:
                existing_count += 1
                self.stdout.write(
                    self.style.WARNING(f"  ℹ Group already exists: {role_name}")
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Summary:"))
        self.stdout.write(self.style.SUCCESS(f"  - Created: {created_count} new groups"))
        self.stdout.write(self.style.SUCCESS(f"  - Existing: {existing_count} groups"))
        self.stdout.write(self.style.SUCCESS(f"  - Total: {len(all_roles)} role groups"))
