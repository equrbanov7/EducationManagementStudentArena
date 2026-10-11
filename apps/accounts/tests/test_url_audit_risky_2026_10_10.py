"""URL auditi — RİSKLİ marşrutların bağlanması (WP8, 2026-10-10) üçün reqressiya testləri.

Hər bənd ayrıca sinifdir:

* B1  — ictimai profil: anonim → login, özgə təşkilat / yoxdur → eyni 404, ortaq təşkilat → 200;
  GET ``UserProfile`` sətri YARATMIR; köhnə ``blog/users/<username>/`` ləqəbi silinib.
* B2  — ``subscribe/`` + ``blog/subscribe/`` universitet rejimində 404 (məktub getmir).
* B3/A7 — ``student-leave-organization/`` və ``student-organization-request/`` silinib.
* B5  — profil şəkli (``accounts/profile-avatar/<id>/`` + ``/media/avatars/`` yoxlayıcısı).
* B6  — ``delete-account/`` silinib (servis qalır).
* B7  — ``technology/`` postlar modulu bağlıykən 404, açıq olanda 200 (sahib: «qalsın»).
* Sahib 2026-10-10 («sil»): açıq qeydiyyat axını (register / verify-code / verify-email / resend-code) yoxdur.
* B9  — ``exams/center/stats/data/`` POST → 405 (əvvəl 500).
* B11 — ``appeals/<id>/``: «yoxdur» və «sənin deyil» eyni cavab.
* B13 — robots.txt admin yollarını elan etmir; sitemap-da ``home`` / ``register`` yoxdur.
"""

import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, Resolver404, resolve, reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole, UserProfile
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.media_views import _check_avatar_access
from core.people_visibility import can_view_person

User = get_user_model()

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00"
    b"\x00\x00\x02\x00\x01\xe5'\xde\xfc\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _org(name, owner):
    return Organization.objects.create(
        name=name,
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )


def _member(user, organization, role_name="student", *, is_active=True):
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": organization.roles.get(name=role_name), "is_primary": True, "is_active": is_active},
    )


def _assert_route_gone(test, path, url_name):
    with test.assertRaises(NoReverseMatch):
        reverse(url_name)
    with test.assertRaises(Resolver404):
        resolve(path)


class _PeopleFixture(TestCase):
    """İki universitet: ``owner`` + ``colleague`` A-da, ``stranger`` B-də."""

    def setUp(self):
        self.owner = User.objects.create_user("wp8.owner", "wp8.owner@example.com", "pw-12345")
        self.colleague = User.objects.create_user("wp8.colleague", "wp8.colleague@example.com", "pw-12345")
        self.stranger = User.objects.create_user("wp8.stranger", "wp8.stranger@example.com", "pw-12345")
        self.org_a = _org("WP8 Univ A", self.owner)
        self.org_b = _org("WP8 Univ B", self.stranger)
        _member(self.owner, self.org_a, "teacher")
        _member(self.colleague, self.org_a)
        _member(self.stranger, self.org_b)


class PeopleVisibilityRuleTests(_PeopleFixture):
    def test_rule_self_superuser_same_org_only(self):
        self.assertTrue(can_view_person(self.owner, self.owner.pk))
        self.assertTrue(can_view_person(self.colleague, self.owner.pk))
        self.assertFalse(can_view_person(self.stranger, self.owner.pk))
        admin = User.objects.create_superuser("wp8.admin", "wp8.admin@example.com", "pw-12345")
        self.assertTrue(can_view_person(admin, self.owner.pk))

    def test_inactive_membership_does_not_count(self):
        _member(self.colleague, self.org_a, is_active=False)
        self.assertFalse(can_view_person(self.colleague, self.owner.pk))

    def test_anonymous_never(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(can_view_person(AnonymousUser(), self.owner.pk))
        self.assertFalse(can_view_person(None, self.owner.pk))


class PublicProfileB1Tests(_PeopleFixture):
    def _url(self, username):
        return reverse("accounts:public_profile", args=[username])

    def test_anonymous_is_sent_to_login_without_profile_content(self):
        response = self.client.get(self._url(self.owner.username))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_same_org_member_gets_200(self):
        self.client.force_login(self.colleague)
        self.assertEqual(self.client.get(self._url(self.owner.username)).status_code, 200)

    def test_foreign_and_missing_users_get_identical_404(self):
        self.client.force_login(self.stranger)
        foreign = self.client.get(self._url(self.owner.username))
        missing = self.client.get(self._url("no.such.person"))
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(missing.status_code, 404)

    def test_get_does_not_create_user_profile_row(self):
        UserProfile.objects.filter(user=self.owner).delete()
        self.client.force_login(self.colleague)
        response = self.client.get(self._url(self.owner.username))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserProfile.objects.filter(user=self.owner).exists())

    def test_legacy_blog_user_alias_is_gone(self):
        self.client.force_login(self.colleague)
        self.assertEqual(self.client.get(f"/blog/users/{self.owner.username}/").status_code, 404)
        with self.assertRaises(NoReverseMatch):
            reverse("user_profile", args=[self.owner.username])


class AvatarAccessB5Tests(_PeopleFixture):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="wp8_avatar_")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.avatar_name = default_storage.save("avatars/wp8_owner.png", ContentFile(TINY_PNG))
        UserProfile.objects.filter(user=self.owner).update(avatar=self.avatar_name)
        self.url = reverse("accounts:profile_avatar", args=[self.owner.pk])

    def test_view_serves_self_and_same_org(self):
        for viewer in (self.owner, self.colleague):
            with self.subTest(viewer=viewer.username):
                self.client.force_login(viewer)
                self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_view_hides_from_foreign_org_like_missing(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(reverse("accounts:profile_avatar", args=[987654])).status_code, 404)

    def test_view_requires_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_media_checker_uses_same_rule(self):
        self.assertTrue(_check_avatar_access(self.owner, self.avatar_name))
        self.assertTrue(_check_avatar_access(self.colleague, self.avatar_name))
        self.assertFalse(_check_avatar_access(self.stranger, self.avatar_name))
        # Sahibi olmayan fayl → rədd.
        self.assertFalse(_check_avatar_access(self.colleague, "avatars/orphan.png"))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SubscribeB2Tests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []

    @override_settings(UNIVERSITY_MODE=True)
    def test_university_mode_returns_404_and_sends_nothing(self):
        url = reverse("subscribe")
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"email": "spam@example.com"}).status_code, 404)
        self.assertEqual(self.client.post("/blog/subscribe/", {"email": "spam@example.com"}).status_code, 404)
        self.assertEqual(self.client.get("/blog/subscribe/").status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(UNIVERSITY_MODE=False)
    def test_marketing_mode_keeps_page(self):
        self.assertEqual(self.client.get(reverse("subscribe")).status_code, 200)


class RemovedRoutesTests(TestCase):
    """B3/A7, B6 və sahibin «açıq qeydiyyatı sil» qərarı — marşrutlar yoxdur."""

    def setUp(self):
        self.user = User.objects.create_user("wp8.gone", "wp8.gone@example.com", "pw-12345")

    def test_leave_and_request_organization_routes_gone(self):
        _assert_route_gone(self, "/accounts/student-leave-organization/", "accounts:student_leave_organization")
        _assert_route_gone(self, "/accounts/student-organization-request/", "accounts:student_organization_request")

    def test_delete_account_route_gone_but_service_kept(self):
        _assert_route_gone(self, "/accounts/delete-account/", "accounts:delete_account")
        from apps.accounts.services import account_deletion  # RİM/superadmin istifadə edir

        self.assertTrue(callable(account_deletion.soft_delete_account))

    def test_public_signup_routes_gone(self):
        for path, name in (
            ("/accounts/register/", "accounts:register"),
            ("/accounts/verify-code/", "accounts:verify_code"),
            ("/accounts/verify-email/", "accounts:verify_email_link"),
            ("/accounts/resend-code/", "accounts:resend_code"),
        ):
            with self.subTest(path=path):
                _assert_route_gone(self, path, name)

    def test_removed_paths_return_404_over_http(self):
        self.client.force_login(self.user)
        for path in (
            "/accounts/student-leave-organization/",
            "/accounts/student-organization-request/",
            "/accounts/delete-account/",
            "/accounts/register/",
            "/accounts/verify-code/",
            "/accounts/verify-email/",
            "/accounts/resend-code/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path).status_code, 404)

    def test_login_page_has_no_signup_link(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/accounts/register/")


class TechnologyPageB7Tests(TestCase):
    def setUp(self):
        from apps.blog.tests.seed_helpers import ensure_blog_seed_data

        ensure_blog_seed_data()
        self.user = User.objects.create_user("wp8.reader", "wp8.reader@example.com", "pw-12345")
        self.org = _org("WP8 Posts Univ", self.user)
        _member(self.user, self.org)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _set_posts(self, enabled):
        from apps.organizations.cabinet_modules import set_module_enabled

        set_module_enabled(self.org, "posts", enabled)

    def test_404_while_posts_module_closed(self):
        self._set_posts(False)
        self.assertEqual(self.client.get(reverse("technology")).status_code, 404)

    def test_200_when_posts_module_open(self):
        self._set_posts(True)
        self.assertEqual(self.client.get(reverse("technology")).status_code, 200)

    @override_settings(UNIVERSITY_MODE=True)
    def test_anonymous_404_in_university_mode(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("technology")).status_code, 404)


class ExamCenterStatsDataB9Tests(TestCase):
    def test_post_is_405_not_500(self):
        user = User.objects.create_user("wp8.stats", "wp8.stats@example.com", "pw-12345")
        self.client.force_login(user)
        self.assertEqual(self.client.post(reverse("exams:exam_center_stats_data")).status_code, 405)

    def test_anonymous_redirects_to_login(self):
        self.assertEqual(self.client.get(reverse("exams:exam_center_stats_data")).status_code, 302)


class AppealDetailB11Tests(TestCase):
    def setUp(self):
        from apps.appeals.constants import APPEAL_MIN_COMMENT_LENGTH, APPEAL_TYPE_WRONG_ANSWER_KEY
        from apps.appeals.services import create_appeal
        from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption

        teacher = User.objects.create_user("wp8.ap.teacher", "wp8.ap.t@example.com", "pw-12345")
        self.student = User.objects.create_user("wp8.ap.student", "wp8.ap.s@example.com", "pw-12345")
        self.other = User.objects.create_user("wp8.ap.other", "wp8.ap.o@example.com", "pw-12345")
        self.org = _org("WP8 Appeal Univ", teacher)
        for user, profile_role, role_name in (
            (teacher, ProfileRole.TEACHER, "teacher"),
            (self.student, ProfileRole.STUDENT, "student"),
            (self.other, ProfileRole.STUDENT, "student"),
        ):
            profile = user.profile
            profile.organization = self.org
            profile.organization_type = self.org.org_type
            profile.role = profile_role
            profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
            _member(user, self.org, role_name)
        exam = Exam.objects.create(
            title="WP8 Appeal Exam",
            author=teacher,
            organization=self.org,
            exam_type="test",
            exam_type_extended="midterm",
            is_active=True,
            is_public=True,
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Sual")
        ExamQuestionOption.objects.create(question=question, label="A", text="Düz", is_correct=True)
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=exam, status="submitted", finished_at=timezone.now()
        )
        ExamAnswer.objects.create(attempt=attempt, question=question)
        self.appeal = create_appeal(
            attempt=attempt,
            student=self.student,
            items=[
                {
                    "question_id": question.id,
                    "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY,
                    "comment": "x" * APPEAL_MIN_COMMENT_LENGTH,
                }
            ],
        )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_foreign_appeal_looks_exactly_like_missing_one(self):
        client = self._client(self.other)
        for suffix in ("", "?fragment=1"):
            with self.subTest(suffix=suffix):
                foreign = client.get(reverse("appeals:appeal_detail", args=[self.appeal.id]) + suffix)
                missing = client.get(reverse("appeals:appeal_detail", args=[987654]) + suffix)
                self.assertEqual(foreign.status_code, missing.status_code)
                self.assertEqual(foreign["Location"], missing["Location"])
                self.assertNotEqual(foreign.status_code, 403)

    def test_owner_still_gets_fragment(self):
        client = self._client(self.student)
        response = client.get(reverse("appeals:appeal_detail", args=[self.appeal.id]) + "?fragment=1")
        self.assertEqual(response.status_code, 200)


class RobotsSitemapB13Tests(TestCase):
    def test_robots_does_not_advertise_admin_or_signup(self):
        body = self.client.get("/robots.txt").content.decode()
        self.assertNotIn("/admin/", body)
        self.assertNotIn("/manage/", body)
        self.assertNotIn("/accounts/register/", body)
        self.assertIn("Disallow: /accounts/", body)
        self.assertIn("Allow: /accounts/login/", body)

    def test_sitemap_drops_home_and_register(self):
        from core.seo_views import SITEMAP_ENTRIES

        names = [entry[0] for entry in SITEMAP_ENTRIES]
        self.assertNotIn("home", names)
        self.assertNotIn("register", names)
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(reverse("accounts:login"), body)
        self.assertNotIn("/accounts/register/", body)
        self.assertNotIn("<loc>http://testserver/</loc>", body)
