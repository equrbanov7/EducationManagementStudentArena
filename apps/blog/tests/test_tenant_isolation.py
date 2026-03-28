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
