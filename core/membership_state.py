"""Request-local authorization caches are valid until membership inputs change."""

import itertools

_epoch_source = itertools.count(1)
_epoch = 0


def membership_epoch():
    return _epoch


def bump_membership_epoch(*_args, **_kwargs):
    global _epoch
    _epoch = next(_epoch_source)


def has_active_role(membership, org_id):
    role = getattr(membership, "role", None)
    return bool(
        membership.is_active
        and membership.organization_id == org_id
        and role
        and role.is_active
        and role.organization_id == org_id
    )
