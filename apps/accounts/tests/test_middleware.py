"""
Tests for accounts middleware: SuspendedOrganizationMiddleware and SessionTimeoutMiddleware.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.accounts.middleware import SessionTimeoutMiddleware, SuspendedOrganizationMiddleware
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


def _make_user(username, password="StrongPass123!", role=ProfileRole.MEMBER):
    user = User.objects.create_user(username, f"{username}@example.com", password)
    user.profile.role = role
    user.profile.save(update_fields=["role", "updated_at"])
    return user


def _make_org(owner, *, status="active", is_active=True):
    return Organization.objects.create(
        name=f"Test Org {owner.username}",
        org_type=OrganizationType.SCHOOL,
        owner=owner,
        status=status,
        is_active=is_active,
    )


def _add_membership(user, org, *, is_active=True):
    role, _ = Role.objects.get_or_create(
        name="member",
        defaults={"level": 10, "scope": RoleScopeType.ORGANIZATION},
    )
    membership, _ = Membership.objects.get_or_create(
        user=user,
        organization=org,
        defaults={"role": role, "is_active": is_active, "is_primary": True},
    )
    if not is_active:
        membership.is_active = False
        membership.save(update_fields=["is_active"])
    return membership


class SuspendedOrganizationMiddlewareTest(TestCase):
    """
    Verify that SuspendedOrganizationMiddleware blocks users whose active
    organization is suspended or inactive, using the new request.organization
    context set by OrganizationMiddleware.
    """

    def setUp(self):
        self.client = Client()

    def test_suspended_org_with_new_membership_model(self):
        """
        A user whose active organization is suspended must be logged out and
        redirected to the login page. This test exercises the new membership-
        model path (request.organization) rather than the legacy profile.organization.
        """
        user = _make_user("susp_test_user")
        org = _make_org(user, status="suspended")
        _add_membership(user, org)

        # Associate profile for OrganizationMiddleware session lookup
        user.profile.organization = org
        user.profile.save(update_fields=["organization", "updated_at"])

        self.client.login(username="susp_test_user", password="StrongPass123!")
        # Seed the active_organization session key so OrganizationMiddleware
        # resolves request.organization before SuspendedOrganizationMiddleware runs.
        session = self.client.session
        session["active_organization"] = org.slug
        session.save()

        response = self.client.get(reverse("home"))
        # Must be redirected to login (not 200)
        self.assertNotEqual(response.status_code, 200)
        login_url = reverse("accounts:login")
        self.assertIn(login_url, response["Location"])

    def test_inactive_org_blocks_access(self):
        """
        A user whose active organization has status='inactive' must be blocked
        and redirected to the login page.
        """
        # Use is_active=True so OrganizationMiddleware resolves request.organization.
        # The "inactive" state is conveyed through the status field; deactivated
        # organizations (is_active=False) are purged from session by OrganizationMiddleware
        # before SuspendedOrganizationMiddleware runs.
        user = _make_user("inactive_org_user")
        org = _make_org(user, status="inactive", is_active=True)
        _add_membership(user, org)

        user.profile.organization = org
        user.profile.save(update_fields=["organization", "updated_at"])

        self.client.login(username="inactive_org_user", password="StrongPass123!")
        session = self.client.session
        session["active_organization"] = org.slug
        session.save()

        response = self.client.get(reverse("home"))
        self.assertNotEqual(response.status_code, 200)
        login_url = reverse("accounts:login")
        self.assertIn(login_url, response["Location"])

    def test_suspended_org_user_is_logged_out(self):
        """
        After hitting the middleware, the user's session must be invalidated
        (they cannot make a second authenticated request without re-logging in).
        """
        user = _make_user("susp_logout_user")
        org = _make_org(user, status="suspended")
        _add_membership(user, org)

        user.profile.organization = org
        user.profile.save(update_fields=["organization", "updated_at"])

        self.client.login(username="susp_logout_user", password="StrongPass123!")
        session = self.client.session
        session["active_organization"] = org.slug
        session.save()

        # First request triggers middleware → logout + redirect
        self.client.get(reverse("home"))

        # A second request should no longer see an authenticated user
        response = self.client.get(reverse("home"))
        # Either redirected to login or served as anonymous — not the authed home
        self.assertFalse(
            response.wsgi_request.user.is_authenticated,
            "User must be fully logged out after suspended org middleware fires",
        )

    def test_active_org_user_can_access(self):
        """A user in a healthy active org must pass through without being blocked."""
        user = _make_user("active_org_user")
        org = _make_org(user, status="active", is_active=True)
        _add_membership(user, org)

        user.profile.organization = org
        user.profile.save(update_fields=["organization", "updated_at"])

        self.client.login(username="active_org_user", password="StrongPass123!")
        session = self.client.session
        session["active_organization"] = org.slug
        session.save()

        response = self.client.get(reverse("home"))
        # Should not be redirected to login
        self.assertNotIn(reverse("accounts:login"), response.get("Location", ""))


class SessionTimeoutMiddlewareTest(TestCase):
    """
    Verify that SessionTimeoutMiddleware expires idle sessions after the
    configured timeout and updates last_activity on every request.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.user = _make_user("timeout_user")

    def _make_middleware(self, timeout_seconds=3600):
        """Return a SessionTimeoutMiddleware with a dummy get_response."""

        def get_response(request):
            from django.http import HttpResponse
            return HttpResponse("ok")

        with override_settings(SESSION_INACTIVITY_TIMEOUT=timeout_seconds):
            mw = SessionTimeoutMiddleware(get_response)
        # Bypass the override so we can call __call__ freely
        mw.timeout_seconds = timeout_seconds
        return mw

    def test_last_activity_set_on_first_request(self):
        """last_activity must be written to the session on the first authenticated request."""
        from django.test import RequestFactory
        from django.contrib.sessions.backends.db import SessionStore

        client = Client()
        client.login(username="timeout_user", password="StrongPass123!")

        # Hit an endpoint so the middleware runs
        client.get(reverse("home"))

        # The session must now have a last_activity key
        session_key = client.cookies[__import__("django.conf", fromlist=["settings"]).settings.SESSION_COOKIE_NAME].value
        store = SessionStore(session_key)
        self.assertIn("last_activity", store)

    def test_idle_session_expires(self):
        """
        Requests arriving after SESSION_INACTIVITY_TIMEOUT seconds of inactivity
        must result in the user being logged out.
        """
        from django.conf import settings as dj_settings
        from django.contrib.sessions.backends.db import SessionStore

        client = Client()
        client.login(username="timeout_user", password="StrongPass123!")
        client.get(reverse("home"))  # sets last_activity

        # Set last_activity far enough in the past to exceed the SESSION_INACTIVITY_TIMEOUT
        # configured for the middleware (default: 3 * 24 * 60 * 60 = 259200 seconds, see
        # SessionTimeoutMiddleware.__init__).  Using 4 days ensures the middleware's cached
        # timeout_seconds is exceeded without needing to override settings at runtime (which
        # would not affect an already-instantiated middleware instance).
        session_key = client.cookies[dj_settings.SESSION_COOKIE_NAME].value
        store = SessionStore(session_key)
        store["last_activity"] = (timezone.now() - timedelta(days=4)).isoformat()
        store.save()

        response = client.get(reverse("home"))

        # After logout, the user is anonymous
        self.assertFalse(
            response.wsgi_request.user.is_authenticated,
            "User must be logged out when the idle timeout is exceeded",
        )

    def test_active_session_not_expired(self):
        """A session with recent activity must not be expired."""
        from django.conf import settings as dj_settings
        from django.contrib.sessions.backends.db import SessionStore

        client = Client()
        client.login(username="timeout_user", password="StrongPass123!")
        client.get(reverse("home"))  # sets last_activity

        # Touch last_activity to now — well within any reasonable inactivity timeout.
        # Override settings to an explicit 1-hour timeout to make the assertion clear.
        session_key = client.cookies[dj_settings.SESSION_COOKIE_NAME].value
        store = SessionStore(session_key)
        store["last_activity"] = timezone.now().isoformat()
        store.save()

        with override_settings(SESSION_INACTIVITY_TIMEOUT=3600):
            response = client.get(reverse("home"))

        self.assertTrue(
            response.wsgi_request.user.is_authenticated,
            "A recently active session must remain valid",
        )
