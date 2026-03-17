"""
Signal handlers for the organizations app.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .default_roles import get_default_roles_for_org_type
from .models import Organization, Role


@receiver(post_save, sender=Organization)
def create_default_roles(sender, instance, created, **kwargs):
    """
    Automatically create default roles when a new organization is created.
    """
    if created:
        # Get default role templates for this organization type
        role_templates = get_default_roles_for_org_type(instance.org_type)

        # Create each role using get_or_create to avoid duplicates
        for role_data in role_templates:
            Role.objects.get_or_create(
                organization=instance,
                name=role_data["name"],
                defaults={
                    "display_name": role_data["display_name"],
                    "level": role_data["level"],
                    "scope_type": role_data["scope_type"],
                    "permissions": role_data["permissions"],
                    "description": role_data.get("description", ""),
                    "is_system": True,
                    "is_active": True,
                },
            )
