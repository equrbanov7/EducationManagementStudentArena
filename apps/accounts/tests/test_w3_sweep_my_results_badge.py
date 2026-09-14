"""W3 `w3sweep` (2026-09-14): «Nəticələrim» kartındakı status nişanı tərcümə olunur.

Brauzer süpürgəsi (qa.student → Nəticələrim): kart başlığında `status-badge`
xam açarı («submitted», CSS `capitalize` ilə «Submitted») göstərirdi — yanında
isə eyni vəziyyət tərcümə ilə («Təqdim edilib») yazılırdı.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import translation

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


class MyResultsStatusBadgeTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("w3mr_teacher", "w3mr_t@example.com", "pw")
        self.student = User.objects.create_user("w3mr_student", "w3mr_s@example.com", "pw")
        self.org = Organization.objects.create(
            name="W3MR Org", org_type=OrganizationType.SCHOOL, owner=self.teacher, status="active", is_active=True
        )
        for user, role, name in (
            (self.teacher, ProfileRole.TEACHER, "teacher"),
            (self.student, ProfileRole.STUDENT, "student"),
        ):
            profile = user.profile
            profile.organization = self.org
            profile.organization_type = self.org.org_type
            profile.role = role
            profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
            Membership.objects.update_or_create(
                user=user,
                organization=self.org,
                defaults={"role": self.org.roles.get(name=name), "is_primary": True, "is_active": True},
            )
        self.exam = Exam.objects.create(author=self.teacher, title="W3MR Exam", is_active=True, is_public=True)
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted")
        self.client = Client()
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def test_badge_shows_translated_label_not_raw_key(self):
        with translation.override("az"):
            response = self.client.get(reverse("accounts:profile"), {"section": "my-results", "results_type": "exams"})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn('class="status-badge status-submitted">Təqdim edilib</span>', html)
        self.assertNotIn('class="status-badge status-submitted">submitted</span>', html)
