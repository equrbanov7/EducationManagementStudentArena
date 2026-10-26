"""«İstifadəçi profilinə bax» — məzun/xaric (arxiv) tələbə (sahib 2026-10-26).

* RİM rəhbəri / RİM əməkdaşı / superadmin arxiv hesabı tapır və YALNIZ-OXU rejimində açır;
* dekan/tyutor/org-admin kimi digər aktorlar arxiv hesabı nə görür, nə açır;
* baxışda nəticə bölmələri (məzun səthi) və «Giriş tarixçəsi» paneli görünür;
* baxış altında yazma əməli bloklanır;
* arxiv tələbənin ÖZ girişi bağlı qalır.
"""

from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole, UserProfile
from apps.accounts.services.view_as import MODE_READONLY, VIEW_AS_SESSION_KEY, validate_target
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, Role
from core.constants import AuditAction, OrganizationType, RoleScopeType

User = get_user_model()
PROFILE_URL = "/accounts/profile/"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"


def _secret() -> str:
    """Testə xas parol — kodda sabit parol saxlanmır (gitleaks)."""
    return secrets.token_urlsafe(12) + "aA7!"


def _role(organization, name, level, permissions=()):
    return Role.objects.update_or_create(
        organization=organization,
        name=name,
        defaults={
            "display_name": name,
            "level": level,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": list(permissions),
            "is_system": False,
            "is_active": True,
        },
    )[0]


def _user(username, organization, role, *, first="", last=""):
    user = User.objects.create_user(username, f"{username}@arch.example.com", _secret())
    user.first_name, user.last_name = first, last
    user.save(update_fields=["first_name", "last_name"])
    Membership.objects.create(user=user, organization=organization, role=role, is_active=True, is_primary=True)
    return user


class ArchivedViewAsBase(TestCase):
    def setUp(self):
        owner = User.objects.create_user("arch_owner", "arch_owner@arch.example.com", _secret())
        self.org = Organization.objects.create(
            name="Arxiv Univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
        )
        self.rim_head = _user("rim.rehber", self.org, _role(self.org, ProfileRole.IKT_REHBER, 88, ["member.view"]))
        self.rim_staff = _user("rim.isci", self.org, _role(self.org, ProfileRole.RIM_STAFF, 60, ["member.view"]))
        self.org_admin = _user("org.admin", self.org, _role(self.org, ProfileRole.ORG_ADMIN, 80))
        self.hr = _user("kadr.isci", self.org, _role(self.org, ProfileRole.HR, 70))
        self.student = _user("aktiv.telebe", self.org, _role(self.org, ProfileRole.STUDENT, 10))
        self.graduate = _user("mezun.telebe", self.org, _role(self.org, "alumni", 1), first="Nərmin", last="Məzunova")
        self.graduate_password = _secret()
        self.graduate.set_password(self.graduate_password)
        self.graduate.save(update_fields=["password"])
        profile, _ = UserProfile.objects.get_or_create(user=self.graduate)
        profile.patronymic = "Rauf"
        profile.access_state = UserProfile.AccessState.ARCHIVED
        profile.save(update_fields=["patronymic", "access_state"])
        self.superuser = User.objects.create_superuser("arch_root", "arch_root@arch.example.com", _secret())

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def search(self, **params):
        params.setdefault("type", "users")
        if self.client.session.get("_auth_user_id") == str(self.superuser.pk):
            params.setdefault("org", str(self.org.pk))
        return self.client.get(reverse("accounts:view_as_search"), params)

    def start(self, target):
        data = {"user_id": target.pk}
        if self.client.session.get("_auth_user_id") == str(self.superuser.pk):
            data["org"] = str(self.org.pk)
        return self.client.post(reverse("accounts:view_as_start"), data)


class ArchivedTargetScopeTest(ArchivedViewAsBase):
    def test_rim_and_superuser_find_archived_by_name_and_patronymic(self):
        for actor in (self.rim_head, self.rim_staff, self.superuser):
            self.login(actor)
            response = self.search(q="Rauf", role="alumni")
            self.assertEqual(response.status_code, 200, actor.username)
            rows = response.json()["results"]
            self.assertEqual([row["username"] for row in rows], ["mezun.telebe"], actor.username)
            self.assertTrue(rows[0]["archived"])

    def test_other_actors_do_not_see_archived(self):
        for actor in (self.org_admin, self.hr):
            self.login(actor)
            response = self.search(q="mezun")
            self.assertEqual(response.status_code, 200, actor.username)
            self.assertEqual(response.json()["results"], [], actor.username)
            self.assertEqual(validate_target(actor, self.org, self.graduate.pk), (None, None))

    def test_archived_target_is_always_readonly(self):
        target, mode = validate_target(self.rim_head, self.org, self.graduate.pk)
        self.assertEqual(target, self.graduate)
        self.assertEqual(mode, MODE_READONLY)
        # Aktiv tələbəyə isə RİM rəhbəri əvvəlki kimi FULL rejimdədir.
        self.assertEqual(validate_target(self.rim_head, self.org, self.student.pk)[1], "full")


class ArchivedViewAsSessionTest(ArchivedViewAsBase):
    def _start_as(self, actor):
        self.login(actor)
        response = self.start(self.graduate)
        self.assertEqual(response.status_code, 302)
        state = self.client.session.get(VIEW_AS_SESSION_KEY)
        self.assertIsNotNone(state, actor.username)
        self.assertEqual(state["mode"], MODE_READONLY)
        self.assertTrue(state["archived"])

    def test_rim_head_opens_results_and_login_history(self):
        AuditLog.objects.create(user=self.graduate, action=AuditAction.LOGIN, ip_address="10.20.30.40", user_agent=_UA)
        AuditLog.objects.create(user=self.graduate, action=AuditAction.LOGOUT, ip_address="10.20.30.40")
        self._start_as(self.rim_head)

        response = self.client.get(PROFILE_URL + "?section=profile-info")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.is_view_as)
        self.assertEqual(response.wsgi_request.user, self.graduate)
        self.assertContains(response, "data-view-as-login-history")
        self.assertContains(response, "10.20.30.40")
        self.assertContains(response, "Chrome 129 · Windows")
        allowed = response.context["allowed_sections"]
        self.assertIn("my-results", allowed)
        self.assertIn("overall-academic", allowed)

        for section in ("my-results", "overall-academic"):
            page = self.client.get(PROFILE_URL + f"?section={section}")
            self.assertEqual(page.status_code, 200, section)
            self.assertTrue(page.wsgi_request.is_view_as, section)

        # Növbəti sorğularda (60 san. tam yoxlamadan əvvəl də) sessiya davam edir.
        self.assertEqual(self.client.get(PROFILE_URL).status_code, 200)
        self.assertIsNotNone(self.client.session.get(VIEW_AS_SESSION_KEY))

    def test_superuser_opens_archived_profile(self):
        self._start_as(self.superuser)
        response = self.client.get(PROFILE_URL + "?section=profile-info")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-view-as-login-history")

    def test_write_is_blocked_under_archived_view(self):
        self._start_as(self.rim_head)
        response = self.client.post(
            PROFILE_URL, {"profile_form": "update-bio", "bio": "x"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()["view_as_blocked"])

    def test_login_history_hidden_for_non_archive_viewer(self):
        AuditLog.objects.create(user=self.student, action=AuditAction.LOGIN, ip_address="10.9.8.7")
        self.login(self.hr)
        self.assertEqual(self.start(self.student).status_code, 302)
        self.assertIsNotNone(self.client.session.get(VIEW_AS_SESSION_KEY))
        response = self.client.get(PROFILE_URL + "?section=profile-info")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.is_view_as)
        self.assertNotContains(response, "data-view-as-login-history")
        self.assertNotContains(response, "10.9.8.7")

    def test_own_cabinet_has_no_login_history_panel(self):
        self.login(self.rim_head)
        response = self.client.get(PROFILE_URL + "?section=profile-info")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-view-as-login-history")

    def test_hr_cannot_start_archived_view(self):
        self.login(self.hr)
        self.start(self.graduate)
        self.assertIsNone(self.client.session.get(VIEW_AS_SESSION_KEY))


class ArchivedStudentStillCannotLoginTest(ArchivedViewAsBase):
    def test_password_login_is_refused(self):
        client = Client()
        response = client.post(
            reverse("accounts:student_login"), {"username": "mezun.telebe", "password": self.graduate_password}
        )
        self.assertNotEqual(client.session.get("_auth_user_id"), str(self.graduate.pk))
        self.assertIn(response.status_code, (200, 302))

    def test_existing_session_is_logged_out(self):
        client = Client()
        client.force_login(self.graduate)
        response = client.get(PROFILE_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(client.session.get("_auth_user_id"))

    def test_archived_view_does_not_unlock_the_student(self):
        self.login(self.rim_head)
        self.start(self.graduate)
        client = Client()
        client.post(reverse("accounts:student_login"), {"username": "mezun.telebe", "password": self.graduate_password})
        self.assertNotEqual(client.session.get("_auth_user_id"), str(self.graduate.pk))
