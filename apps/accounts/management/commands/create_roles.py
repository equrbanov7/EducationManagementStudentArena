"""
Deprecated compatibility command for legacy auth-group setup.
Usage: python manage.py create_roles
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Deprecated no-op. Organization-scoped roles replaced Django auth groups."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "create_roles is deprecated: Django auth groups are no longer used. "
                "Organization memberships and roles are created through the RBAC model."
            )
        )
