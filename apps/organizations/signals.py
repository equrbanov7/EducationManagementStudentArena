"""
Signal handlers for the organizations app.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .default_roles import get_default_roles_for_org_type
from .models import Organization, OrgUnit, Role


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


@receiver(post_save, sender=OrgUnit)
def update_descendant_paths(sender, instance, **kwargs):
    """
    Update paths for all descendants when a unit's path changes.
    """
    # Get all descendants
    descendants = OrgUnit.objects.filter(
        path__startswith=f"{instance.path}/",
        organization=instance.organization,
    ).exclude(pk=instance.pk)

    # Update each descendant's path
    for descendant in descendants:
        # Recalculate path based on parent
        if descendant.parent:
            new_path = f"{descendant.parent.path}/{descendant.id}"
            new_level = descendant.parent.level + 1

            if descendant.path != new_path or descendant.level != new_level:
                descendant.path = new_path
                descendant.level = new_level
                descendant.save(update_fields=["path", "level"])
