"""
Model tests for blog app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import EmailOTP
from apps.blog.models import Category, Comment, Post, Question, Subscriber

User = get_user_model()


class EmailOTPTest(TestCase):
    """Test EmailOTP model functionality."""

    def setUp(self):
        self.user = User.objects.create_user("otpuser", "otp@example.com", "StrongPass123!")

    def test_emailotp_creation(self):
        """Test that EmailOTP can be created."""
        otp = EmailOTP.objects.create(
            user=self.user,
            code="123456",
        )
        self.assertNotEqual(otp.code, "123456")
        self.assertTrue(otp.matches_code("123456"))
        self.assertFalse(otp.is_used)
        self.assertIsNotNone(otp.expires_at)

    def test_emailotp_expires_at_auto_set(self):
        """Test that expires_at is automatically set if not provided."""
        otp = EmailOTP.objects.create(
            user=self.user,
            code="654321",
        )
        # expires_at should be set automatically in save()
        self.assertIsNotNone(otp.expires_at)
        # Should be approximately 3 minutes from now
        time_diff = otp.expires_at - timezone.now()
        self.assertLess(time_diff, timedelta(minutes=4))
        self.assertGreater(time_diff, timedelta(minutes=2))

    def test_emailotp_is_expired_method(self):
        """Test is_expired method."""
        # Create an OTP that expires in the future
        otp_future = EmailOTP.objects.create(
            user=self.user,
            code="111111",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        self.assertFalse(otp_future.is_expired())

        # Create an OTP that is already expired
        otp_past = EmailOTP.objects.create(
            user=self.user,
            code="222222",
            expires_at=timezone.now() - timedelta(minutes=5),
        )
        self.assertTrue(otp_past.is_expired())

    def test_emailotp_can_be_marked_as_used(self):
        """Test that OTP can be marked as used."""
        otp = EmailOTP.objects.create(
            user=self.user,
            code="333333",
        )
        self.assertFalse(otp.is_used)

        otp.is_used = True
        otp.save()
        self.assertTrue(otp.is_used)


class CategoryTest(TestCase):
    """Test Category model functionality."""

    def test_category_creation(self):
        """Test that Category can be created."""
        category = Category.objects.create(name="Python")
        self.assertEqual(category.name, "Python")
        self.assertIsNotNone(category.slug)

    def test_category_slug_auto_generated(self):
        """Test that slug is auto-generated from name."""
        category = Category.objects.create(name="Django Testing")
        self.assertEqual(category.slug, "django-testing")

    def test_category_slug_unique(self):
        """Test that colliding slugs are de-duplicated for distinct names."""
        cat1 = Category.objects.create(name="Test Category")
        cat2 = Category.objects.create(name="Test-Category")

        self.assertEqual(cat1.slug, "test-category")
        self.assertNotEqual(cat1.slug, cat2.slug)
        # Second category should have a numbered slug
        self.assertTrue(cat2.slug.startswith("test-category-"))

    def test_category_string_representation(self):
        """Test Category __str__ method."""
        category = Category.objects.create(name="JavaScript")
        self.assertEqual(str(category), "JavaScript")


class PostTest(TestCase):
    """Test Post model functionality."""

    def setUp(self):
        self.author = User.objects.create_user("postauthor", "author@example.com", "StrongPass123!")
        self.category = Category.objects.create(name="Technology")

    def test_post_creation(self):
        """Test that Post can be created."""
        post = Post.objects.create(
            author=self.author,
            category=self.category,
            title="Test Post",
            content="This is test content",
        )
        self.assertEqual(post.title, "Test Post")
        self.assertEqual(post.author, self.author)
        self.assertEqual(post.category, self.category)
        self.assertTrue(post.is_published)

    def test_post_slug_auto_generated(self):
        """Test that slug is auto-generated from title."""
        post = Post.objects.create(
            author=self.author,
            title="My Awesome Blog Post",
            content="Content here",
        )
        self.assertEqual(post.slug, "my-awesome-blog-post")

    def test_post_slug_unique(self):
        """Test that duplicate post titles get unique slugs."""
        post1 = Post.objects.create(
            author=self.author,
            title="Duplicate Title",
            content="Content 1",
        )
        post2 = Post.objects.create(
            author=self.author,
            title="Duplicate Title",
            content="Content 2",
        )

        self.assertEqual(post1.slug, "duplicate-title")
        self.assertNotEqual(post1.slug, post2.slug)
        self.assertTrue(post2.slug.startswith("duplicate-title-"))

    def test_post_get_image_with_uploaded_file(self):
        """Test get_image property with uploaded image."""
        post = Post.objects.create(
            author=self.author,
            title="Image Post",
            content="Content",
        )
        # Without image, should return default
        self.assertIn("placeholder", post.get_image)

    def test_post_approval_status_default(self):
        """Test that approval status defaults correctly."""
        post = Post.objects.create(
            author=self.author,
            title="Default Status",
            content="Content",
        )
        self.assertEqual(post.approval_status, Post.ApprovalStatus.APPROVED)
        self.assertFalse(post.requires_approval)

    def test_post_with_approval_required(self):
        """Test post with approval required."""
        post = Post.objects.create(
            author=self.author,
            title="Needs Approval",
            content="Content",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
        )
        self.assertTrue(post.requires_approval)
        self.assertEqual(post.approval_status, Post.ApprovalStatus.PENDING)
        self.assertFalse(post.is_published)  # Should not be published when pending

    def test_post_string_representation(self):
        """Test Post __str__ method."""
        post = Post.objects.create(
            author=self.author,
            title="Test Title",
            content="Content",
        )
        self.assertEqual(str(post), "Test Title")


class CommentTest(TestCase):
    """Test Comment model functionality."""

    def setUp(self):
        self.author = User.objects.create_user("commentauthor", "cauth@example.com", "StrongPass123!")
        self.commenter = User.objects.create_user("commenter", "commenter@example.com", "StrongPass123!")
        self.post = Post.objects.create(
            author=self.author,
            title="Post for Comments",
            content="Content",
        )

    def test_comment_creation(self):
        """Test that Comment can be created."""
        comment = Comment.objects.create(
            post=self.post,
            user=self.commenter,
            text="Great post!",
            rating=5,
        )
        self.assertEqual(comment.text, "Great post!")
        self.assertEqual(comment.rating, 5)
        self.assertEqual(comment.post, self.post)
        self.assertEqual(comment.user, self.commenter)

    def test_comment_default_rating(self):
        """Test that comment has default rating of 5."""
        comment = Comment.objects.create(
            post=self.post,
            user=self.commenter,
            text="Comment without explicit rating",
        )
        self.assertEqual(comment.rating, 5)

    def test_comment_string_representation(self):
        """Test Comment __str__ method."""
        comment = Comment.objects.create(
            post=self.post,
            user=self.commenter,
            text="Test comment",
            rating=4,
        )
        expected = f"{self.commenter.username} → {self.post.title} (4)"
        self.assertEqual(str(comment), expected)


class SubscriberTest(TestCase):
    """Test Subscriber model functionality."""

    def test_subscriber_creation(self):
        """Test that Subscriber can be created."""
        subscriber = Subscriber.objects.create(email="subscriber@example.com")
        self.assertEqual(subscriber.email, "subscriber@example.com")
        self.assertFalse(subscriber.is_active)

    def test_subscriber_unique_email(self):
        """Test that subscriber email must be unique."""
        Subscriber.objects.create(email="unique@example.com")

        with self.assertRaises(Exception):
            Subscriber.objects.create(email="unique@example.com")

    def test_subscriber_string_representation(self):
        """Test Subscriber __str__ method."""
        subscriber = Subscriber.objects.create(email="sub@example.com")
        self.assertEqual(str(subscriber), "sub@example.com")


class QuestionTest(TestCase):
    """Test Question model functionality."""

    def setUp(self):
        self.author = User.objects.create_user("qauthor", "qauthor@example.com", "StrongPass123!")
        self.viewer = User.objects.create_user("viewer", "viewer@example.com", "StrongPass123!")

    def test_question_creation(self):
        """Test that Question can be created."""
        question = Question.objects.create(
            author=self.author,
            question_text="How do I learn Django?",
            answer_text="Start with the official tutorial.",
            visible_to_all=True,
        )
        self.assertEqual(question.question_text, "How do I learn Django?")
        self.assertTrue(question.visible_to_all)

    def test_question_can_user_see_public(self):
        """Test can_user_see method for public questions."""
        question = Question.objects.create(
            author=self.author,
            question_text="Public question",
            visible_to_all=True,
        )
        # Public questions visible to everyone
        self.assertTrue(question.can_user_see(self.viewer))
        self.assertTrue(question.can_user_see(self.author))

    def test_question_can_user_see_private(self):
        """Test can_user_see method for private questions."""
        question = Question.objects.create(
            author=self.author,
            question_text="Private question",
            visible_to_all=False,
        )
        # Author can see their own question
        self.assertTrue(question.can_user_see(self.author))
        # Others cannot see private question
        self.assertFalse(question.can_user_see(self.viewer))

    def test_question_can_user_see_with_specific_users(self):
        """Test can_user_see method with specific users."""
        question = Question.objects.create(
            author=self.author,
            question_text="Restricted question",
            visible_to_all=False,
        )
        question.visible_users.add(self.viewer)

        # Viewer should now be able to see it
        self.assertTrue(question.can_user_see(self.viewer))

    def test_question_string_representation(self):
        """Test Question __str__ method."""
        question = Question.objects.create(
            author=self.author,
            question_text="This is a very long question text that should be truncated in the string representation",
        )
        # Should be truncated to 50 chars
        self.assertEqual(len(str(question)), 50)
