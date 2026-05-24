"""
Tenant isolation tests for the Blog app.

The blog Post model uses author-based ownership (no organization FK).
Tenant isolation here means:

- A user cannot edit or delete another user's post by swapping the post ID
- A user can only manage their own posts
- Moderation (review/teacher_moderate) is reserved for staff/superusers
- Anonymous users are redirected to login for write operations
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.blog.models import Category, Post

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_post(author, title, *, is_published=True):
    return Post.objects.create(
        author=author,
        title=title,
        content="Test content for isolation.",
        is_published=is_published,
        approval_status=Post.ApprovalStatus.APPROVED,
    )


# ---------------------------------------------------------------------------
# Test: Post Ownership Isolation (edit / delete)
# ---------------------------------------------------------------------------


class BlogPostOwnershipIsolationTest(TestCase):
    """
    Users can only edit or delete their own posts.
    Swapping a post_id / pk in the URL for another user's post must be blocked.
    """

    def setUp(self):
        self.client = Client()

        self.user_a = User.objects.create_user(
            username="blog_user_a", email="blog_a@example.com", password="StrongPass123!"
        )
        self.user_b = User.objects.create_user(
            username="blog_user_b", email="blog_b@example.com", password="StrongPass123!"
        )

        self.category = Category.objects.create(
            name="Test Category",
            name_en="Test Category",
            slug="test-category-iso",
        )

        self.post_a = _create_post(self.user_a, "User A Post")
        self.post_b = _create_post(self.user_b, "User B Post")

    # ------------------------------------------------------------------
    # Edit (AJAX POST) cross-ownership
    # ------------------------------------------------------------------

    def test_user_a_cannot_edit_user_b_post(self):
        """User A receives a 404 when trying to edit User B's post."""
        self.client.force_login(self.user_a)
        url = reverse("post_edit_ajax", kwargs={"pk": self.post_b.id})
        response = self.client.post(
            url,
            {"title": "Hacked Title", "content": "Hacked content"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        # get_object_or_404(Post, pk=pk, author=request.user) raises 404 for other authors
        self.assertEqual(response.status_code, 404)
        self.post_b.refresh_from_db()
        self.assertEqual(self.post_b.title, "User B Post")

    def test_user_a_can_edit_own_post(self):
        """User A can successfully edit their own post."""
        self.client.force_login(self.user_a)
        url = reverse("post_edit_ajax", kwargs={"pk": self.post_a.id})
        response = self.client.post(
            url,
            {"title": "Updated Title", "content": "Updated content", "category": self.category.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.post_a.refresh_from_db()
        self.assertEqual(self.post_a.title, "Updated Title")

    # ------------------------------------------------------------------
    # Delete cross-ownership
    # ------------------------------------------------------------------

    def test_user_a_cannot_delete_user_b_post(self):
        """User A receives a 404 when trying to delete User B's post."""
        self.client.force_login(self.user_a)
        url = reverse("delete_post", kwargs={"post_id": self.post_b.id})
        response = self.client.post(url)
        # get_object_or_404(Post, pk=post_id, author=request.user) → 404
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Post.objects.filter(id=self.post_b.id).exists())

    def test_user_a_can_delete_own_post(self):
        """User A can delete their own post."""
        self.client.force_login(self.user_a)
        url = reverse("delete_post", kwargs={"post_id": self.post_a.id})
        response = self.client.post(url)
        self.assertIn(response.status_code, (200, 302))
        self.assertFalse(Post.objects.filter(id=self.post_a.id).exists())

    # ------------------------------------------------------------------
    # Anonymous write access
    # ------------------------------------------------------------------

    def test_anonymous_cannot_delete_any_post(self):
        """Anonymous users are redirected when attempting to delete a post."""
        url = reverse("delete_post", kwargs={"post_id": self.post_a.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
        self.assertTrue(Post.objects.filter(id=self.post_a.id).exists())

    def test_anonymous_cannot_edit_any_post(self):
        """Anonymous users are redirected when attempting to edit a post (login_required)."""
        url = reverse("post_edit_ajax", kwargs={"pk": self.post_a.id})
        response = self.client.post(url, {"title": "Anon Edit", "content": "content"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)


# ---------------------------------------------------------------------------
# Test: Moderation permission boundary
# ---------------------------------------------------------------------------


class BlogModerationIsolationTest(TestCase):
    """
    Only users with appropriate permissions can moderate (review/moderate) posts.
    A regular authenticated user cannot approve or moderate another user's post.
    """

    def setUp(self):
        self.client = Client()

        self.author = User.objects.create_user(
            username="mod_author", email="mod_author@example.com", password="StrongPass123!"
        )
        self.regular_user = User.objects.create_user(
            username="mod_regular", email="mod_regular@example.com", password="StrongPass123!"
        )
        self.superuser = User.objects.create_superuser(
            username="mod_superuser", email="mod_superuser@example.com", password="StrongPass123!"
        )

        self.post = Post.objects.create(
            author=self.author,
            title="Post Needing Approval",
            content="Awaiting review.",
            is_published=False,
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
        )

    def test_regular_user_cannot_approve_post(self):
        """A regular authenticated user cannot approve another user's pending post."""
        self.client.force_login(self.regular_user)
        url = reverse("review_post", kwargs={"post_id": self.post.id})
        response = self.client.post(url, {"action": "approve", "feedback": ""})
        # PermissionDenied → 403
        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertEqual(self.post.approval_status, Post.ApprovalStatus.PENDING)
        self.assertFalse(self.post.is_published)

    def test_regular_user_cannot_teacher_moderate_post(self):
        """A regular user cannot perform teacher moderation on any post."""
        self.client.force_login(self.regular_user)
        url = reverse("teacher_moderate_post", kwargs={"post_id": self.post.id})
        response = self.client.post(url, {"action": "delete", "feedback": "inappropriate"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Post.objects.filter(id=self.post.id).exists())

    def test_anonymous_cannot_review_post(self):
        """Anonymous users cannot access the review_post endpoint."""
        url = reverse("review_post", kwargs={"post_id": self.post.id})
        response = self.client.post(url, {"action": "approve"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_superuser_can_review_post(self):
        """Superusers have moderation access and can approve posts."""
        self.client.force_login(self.superuser)
        url = reverse("review_post", kwargs={"post_id": self.post.id})
        response = self.client.post(url, {"action": "approve", "feedback": ""})
        # Successful review → redirect (302)
        self.assertIn(response.status_code, (200, 302))
        self.post.refresh_from_db()
        self.assertEqual(self.post.approval_status, Post.ApprovalStatus.APPROVED)

    def test_org_admin_cannot_review_pending_post_outside_own_organization(self):
        from apps.accounts.models import ProfileRole, UserProfile
        from apps.organizations.models import Membership, Organization
        from core.constants import OrganizationType

        org_admin = User.objects.create_user(
            username="mod_org_admin",
            email="mod_org_admin@example.com",
            password="StrongPass123!",
        )
        UserProfile.objects.update_or_create(user=org_admin, defaults={"role": ProfileRole.ORG_ADMIN})

        owner = User.objects.create_user(
            username="mod_org_owner",
            email="mod_org_owner@example.com",
            password="StrongPass123!",
        )
        organization = Organization.objects.create(
            name="Moderation Org",
            slug="moderation-org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        Membership.objects.create(
            user=org_admin,
            organization=organization,
            role=organization.roles.order_by("-level", "name").first(),
            is_active=True,
            is_primary=True,
        )

        self.client.force_login(org_admin)
        url = reverse("review_post", kwargs={"post_id": self.post.id})
        response = self.client.post(url, {"action": "approve", "feedback": ""})

        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertEqual(self.post.approval_status, Post.ApprovalStatus.PENDING)


# ---------------------------------------------------------------------------
# Test: Post detail read access
# ---------------------------------------------------------------------------


class BlogPostReadIsolationTest(TestCase):
    """
    Published posts are publicly readable; unpublished posts must not
    be accessible to users other than the author or staff.
    """

    def setUp(self):
        self.client = Client()

        self.author = User.objects.create_user(
            username="read_author", email="read_author@example.com", password="StrongPass123!"
        )
        self.other_user = User.objects.create_user(
            username="read_other", email="read_other@example.com", password="StrongPass123!"
        )

        self.published_post = _create_post(self.author, "Public Post", is_published=True)
        self.draft_post = Post.objects.create(
            author=self.author,
            title="Draft Post",
            content="Not yet published.",
            is_published=False,
            approval_status=Post.ApprovalStatus.PENDING,
        )

    def test_published_post_readable_by_anyone(self):
        """A published post is accessible without authentication."""
        url = reverse("article_detail", kwargs={"slug": self.published_post.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_unpublished_post_not_visible_to_other_user(self):
        """An unpublished/draft post returns 404 for users who are not the author."""
        self.client.force_login(self.other_user)
        url = reverse("article_detail", kwargs={"slug": self.draft_post.slug})
        response = self.client.get(url)
        # Unpublished posts should not be served to other users (404 or redirect)
        self.assertIn(response.status_code, (302, 403, 404))


# ---------------------------------------------------------------------------
# Test: Blog post creation is audit-logged (FAZA 3)
# ---------------------------------------------------------------------------


class BlogPostAuditLogTest(TestCase):
    """Creating a blog post must leave an audit-trail entry so that
    unapproved-content attempts are reviewable."""

    def setUp(self):
        self.client = Client()
        self.author = User.objects.create_user(
            username="audit_author", email="audit_author@example.com", password="StrongPass123!"
        )
        self.category = Category.objects.create(name="Audit", slug="audit")

    def test_post_creation_writes_audit_log(self):
        from apps.audit.models import AuditLog

        self.client.force_login(self.author)
        before = AuditLog.objects.count()

        response = self.client.post(
            reverse("create_post"),
            data={
                "title": "Audit Test Post",
                "content": "Body content for audit.",
                "category": self.category.pk,
            },
        )
        self.assertIn(response.status_code, (200, 302))

        self.assertEqual(AuditLog.objects.count(), before + 1)
        log = AuditLog.objects.latest("created_at")
        self.assertEqual(log.user_id, self.author.id)
        self.assertEqual(log.resource_type, "blog.Post")


# ---------------------------------------------------------------------------
# Test: Question ownership & visibility isolation
# ---------------------------------------------------------------------------


class BlogQuestionIsolationTest(TestCase):
    """
    Teachers author questions; students must not create questions, and
    a user must not see private questions they were not granted access to.
    """

    def setUp(self):
        self.client = Client()

        self.teacher = User.objects.create_user(
            username="q_teacher", email="q_teacher@example.com", password="StrongPass123!"
        )
        self.teacher.profile.role = "teacher"
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.student = User.objects.create_user(
            username="q_student", email="q_student@example.com", password="StrongPass123!"
        )
        # student profile role stays default (student)

        self.other_teacher = User.objects.create_user(
            username="q_other_teacher", email="q_other@example.com", password="StrongPass123!"
        )
        self.other_teacher.profile.role = "teacher"
        self.other_teacher.profile.save(update_fields=["role", "updated_at"])

        from apps.blog.models import Question

        self.private_question = Question.objects.create(
            author=self.teacher,
            question_text="Private question from teacher",
            answer_text="Secret answer",
            visible_to_all=False,
        )

    def test_student_cannot_create_question(self):
        """Students are denied access to create_question (teacher_only guard)."""
        self.client.force_login(self.student)
        url = reverse("create_question")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_post_create_question(self):
        """Students cannot create a question via POST."""
        self.client.force_login(self.student)
        url = reverse("create_question")
        response = self.client.post(url, {"question_text": "injected", "answer_text": "hack"})
        self.assertEqual(response.status_code, 403)

    def test_my_questions_shows_only_own(self):
        """my_questions returns only the current user's questions."""
        self.client.force_login(self.other_teacher)
        url = reverse("my_questions")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        for q in response.context["questions"]:
            self.assertEqual(q.author_id, self.other_teacher.id)

    def test_private_question_not_visible_to_unauthorised_user(self):
        """A private question is not returned in questions_i_can_see for a non-granted user."""
        self.client.force_login(self.other_teacher)
        url = reverse("questions_i_can_see")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        returned_ids = [q.id for q in response.context["questions"]]
        self.assertNotIn(self.private_question.id, returned_ids)

    def test_private_question_visible_to_author(self):
        """A private question is visible in questions_i_can_see for its author."""
        self.client.force_login(self.teacher)
        url = reverse("questions_i_can_see")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        returned_ids = [q.id for q in response.context["questions"]]
        self.assertIn(self.private_question.id, returned_ids)

    def test_anonymous_cannot_access_questions(self):
        """Anonymous users are redirected to login for question pages."""
        for url_name in ("create_question", "my_questions", "questions_i_can_see"):
            url = reverse(url_name)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, f"{url_name} should redirect anon")
            self.assertIn("login", response.url, f"{url_name} should redirect to login")


# ---------------------------------------------------------------------------
# Test: Blog Question visible_to_all – intentional cross-org visibility
# ---------------------------------------------------------------------------


class BlogQuestionVisibleToAllCrossOrgTest(TestCase):
    """
    Document / verify that ``visible_to_all=True`` intentionally makes a
    Question visible across organizations.

    The Question model has no organization FK; visibility is controlled
    solely by the ``visible_to_all`` flag and the ``visible_users`` M2M.
    This is by design – the blog / Q&A subsystem is a global, non-tenant-
    scoped feature.
    """

    def setUp(self):
        self.client = Client()

        self.teacher_org_a = User.objects.create_user(
            username="bqva_teacher_a", email="bqva_a@orga.com", password="StrongPass123!"
        )
        self.teacher_org_a.profile.role = "teacher"
        self.teacher_org_a.profile.save(update_fields=["role", "updated_at"])

        self.teacher_org_b = User.objects.create_user(
            username="bqva_teacher_b", email="bqva_b@orgb.com", password="StrongPass123!"
        )
        self.teacher_org_b.profile.role = "teacher"
        self.teacher_org_b.profile.save(update_fields=["role", "updated_at"])

        from apps.blog.models import Question

        self.public_question = Question.objects.create(
            author=self.teacher_org_a,
            question_text="Cross-org public question",
            answer_text="Visible everywhere",
            visible_to_all=True,
        )
        self.private_question = Question.objects.create(
            author=self.teacher_org_a,
            question_text="Cross-org private question",
            answer_text="Only for author",
            visible_to_all=False,
        )

    def test_visible_to_all_question_seen_by_other_org_teacher(self):
        """
        A question with visible_to_all=True is intentionally shown to
        users from any organization.  This is expected behaviour — the
        blog Question model is not org-scoped.
        """
        self.client.force_login(self.teacher_org_b)
        url = reverse("questions_i_can_see")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        returned_ids = [q.id for q in response.context["questions"]]
        self.assertIn(self.public_question.id, returned_ids)

    def test_private_question_hidden_from_other_org_teacher(self):
        """A private question is not visible to teachers in other orgs."""
        self.client.force_login(self.teacher_org_b)
        url = reverse("questions_i_can_see")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        returned_ids = [q.id for q in response.context["questions"]]
        self.assertNotIn(self.private_question.id, returned_ids)
