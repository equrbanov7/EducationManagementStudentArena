"""P9: navbar org-switcher siyahısının per-user keşi üçün testlər."""

from django.contrib.auth import get_user_model
from django.core.cache import cache

import pytest

from apps.organizations.middleware import OrganizationMiddleware
from apps.organizations.models import Membership, Organization, Role

User = get_user_model()


@pytest.mark.django_db
class TestOrgSwitcherCache:
    @pytest.fixture(autouse=True)
    def _locmem_cache(self, settings):
        # Test settings qəsdən DummyCache işlədir (keş asılılığı olmasın deyə);
        # bu sinif keşin ÖZÜNÜ yoxladığı üçün locmem-ə keçirik.
        settings.CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "p9-test",
            }
        }
        cache.clear()
        yield
        cache.clear()

    def _make_membership(self, user, *, slug="kes-org"):
        owner = User.objects.create_user(username=f"owner-{slug}", password="x")
        org = Organization.objects.create(
            name=f"Keş Org {slug}", slug=slug, status="active", is_active=True, owner=owner
        )
        role = Role.objects.create(organization=org, name="teacher", level=60, is_active=True)
        return Membership.objects.create(user=user, organization=org, role=role, is_active=True)

    def test_second_call_hits_cache(self, django_assert_num_queries, django_user_model):
        user = django_user_model.objects.create_user(username="kes-user", password="x")
        self._make_membership(user)

        first = OrganizationMiddleware._cached_active_memberships(user)
        assert len(first) == 1

        with django_assert_num_queries(0):
            second = OrganizationMiddleware._cached_active_memberships(user)
        assert [m.pk for m in second] == [m.pk for m in first]

    def test_membership_change_invalidates(self, django_user_model):
        user = django_user_model.objects.create_user(username="kes-user-2", password="x")
        membership = self._make_membership(user)

        assert len(OrganizationMiddleware._cached_active_memberships(user)) == 1

        # Üzvlük deaktiv olunanda signal keşi silməli və siyahı dərhal boşalmalıdır.
        membership.is_active = False
        membership.save(update_fields=["is_active"])
        assert OrganizationMiddleware._cached_active_memberships(user) == []

    def test_cache_key_is_per_user(self, django_user_model):
        u1 = django_user_model.objects.create_user(username="kes-a", password="x")
        u2 = django_user_model.objects.create_user(username="kes-b", password="x")
        self._make_membership(u1)

        assert len(OrganizationMiddleware._cached_active_memberships(u1)) == 1
        assert OrganizationMiddleware._cached_active_memberships(u2) == []
