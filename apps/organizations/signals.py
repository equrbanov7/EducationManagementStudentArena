"""
Signal handlers for the organizations app.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.cache import invalidate_signup_lookup_cache
from core.rls import set_rls_tenant
from core.rls_pooling import rls_worker_atomic

from .default_roles import get_default_roles_for_org_type
from .models import Country, Membership, Organization, Role


@receiver(post_save, sender=Organization)
def create_default_roles(sender, instance, created, **kwargs):
    """
    Automatically create default roles when a new organization is created.
    """
    if created:
        with rls_worker_atomic():
            set_rls_tenant(instance.pk)
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


# ── Signup lookup cache invalidation ──────────────────────────────────────────
# The register page caches the country + joinable-organization payload. Drop it
# whenever an organization or country is created/updated/deleted so the signup
# dropdowns never serve a stale list.


@receiver([post_save, post_delete], sender=Organization)
def invalidate_signup_lookup_on_organization_change(sender, instance, **kwargs):
    invalidate_signup_lookup_cache()


@receiver([post_save, post_delete], sender=Country)
def invalidate_signup_lookup_on_country_change(sender, instance, **kwargs):
    invalidate_signup_lookup_cache()


# ── Org-switcher keş invalidasiyası (P9) ──────────────────────────────────────
# Navbar org-switcher siyahısı 60s keşlənir (middleware). Üzvlük dəyişən kimi
# həmin istifadəçinin keşini dərhal sil ki, switcher köhnə siyahı göstərməsin.


@receiver([post_save, post_delete], sender=Membership)
def invalidate_org_switcher_on_membership_change(sender, instance, **kwargs):
    from django.core.cache import cache

    from .middleware import OrganizationMiddleware

    try:
        cache.delete(OrganizationMiddleware.org_switcher_cache_key(instance.user_id))
    except Exception:
        pass
