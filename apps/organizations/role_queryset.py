from django.core.cache import cache
from django.db import models, transaction

from core.membership_state import bump_membership_epoch


def invalidate_role_memberships(using):
    """Expire current-process grants now and shared navbar rows after commit."""
    from uuid import uuid4

    bump_membership_epoch()

    def expire_navbar():
        # A concurrent reader may have refreshed before this transaction committed.
        bump_membership_epoch()
        cache.set("ems:org_switcher:role_version", uuid4().hex, timeout=None)

    transaction.on_commit(expire_navbar, using=using, robust=True)


class RoleQuerySet(models.QuerySet):
    def update(self, **values):
        count = super().update(**values)
        if count and "is_active" in values:
            invalidate_role_memberships(self.db)
        return count
