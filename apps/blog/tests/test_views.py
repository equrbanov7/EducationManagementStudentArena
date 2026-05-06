"""
View tests for blog app.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.blog.models import Category, Post, Question
from apps.exams.models import StudentGroup
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()
LOCMEM_CACHE_SETTINGS = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "blog-rate-limit-tests",
    }
}


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):
    membership_role_name = membership_role_name or {
        ProfileRole.TEACHER: "instructor" if organization.org_type == OrganizationType.COURSE_CENTER else "teacher",
        ProfileRole.STUDENT: "student",
    }.get(profile_role, "member")

    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )


@override_settings(
    CACHES=LOCMEM_CACHE_SETTINGS,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SUBSCRIBE_RATE_LIMIT="1/1m",
)
class SubscribeRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.subscribe_url = reverse("subscribe")

    def test_subscribe_blocks_after_rate_limit(self):
        first = self.client.post(self.subscribe_url, {"email": "rate-limit@example.com"})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

        blocked = self.client.post(self.subscribe_url, {"email": "rate-limit@example.com"})

        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Çox sayda cəhd edildi", status_code=429)
        self.assertEqual(len(mail.outbox), 1)

    def test_subscribe_rejects_malformed_email_payloads_without_500(self):
        for payload in ("'", '"', ";", "'("):
            with self.subTest(payload=payload):
                cache.clear()
                mail.outbox = []
                response = self.client.post(self.subscribe_url, {"email": payload})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(mail.outbox), 0)
                self.assertIn("email", response.context["form"].errors)


class BlogRoleAccessTest(TestCase):
    def _activate_org(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.organization.slug
        session.save()

    def setUp(self):
        cache.clear()

        self.teacher = User.objects.create_user(
            username="blog_teacher",
            email="blog_teacher@example.com",
            password="StrongPass123!",
        )
        self.student = User.objects.create_user(
            username="blog_student",
            email="blog_student@example.com",
            password="StrongPass123!",
        )

        self.organization = Organization.objects.create(
            name="Blog Approval Org",
            slug="blog-approval-org",
            org_type=OrganizationType.COURSE_CENTER,
            owner=self.teacher,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

        self.other_teacher = User.objects.create_user(
            username="blog_other_teacher",
            email="blog_other_teacher@example.com",
            password="StrongPass123!",
        )
        _assign_user_to_org(self.other_teacher, self.organization, ProfileRole.TEACHER)

        self.tech_category = Category.objects.create(
            name="Test Technology",
            slug="test-technology",
            show_in_navbar=True,
        )
        self.ai_category = Category.objects.create(
            name="Test AI",
            slug="test-ai",
            parent=self.tech_category,
        )
        self.education_category = Category.objects.create(
            name="Test Education",
            slug="test-education",
            show_in_navbar=True,
        )

        self.teacher_post = Post.objects.create(
            author=self.teacher,
            title="Teacher Post",
            content="Teacher content",
            is_published=True,
            category=self.ai_category,
        )
        self.student_group = StudentGroup.objects.create(
            teacher=self.teacher,
            organization=self.organization,
            name="Qrup 101",
        )
        self.student_group.students.add(self.student)

    def test_homepage_is_available_at_root(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "blog/home.html")

    def test_homepage_treats_malformed_q_payload_as_plain_text(self):
        response = self.client.get("/?q=ZAP%27%28")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["query"], "ZAP'(")
        self.assertEqual(list(response.context["page_obj"]), [])

    def test_homepage_rejects_non_numeric_page_payload_with_trailing_quote_and_paren(self):
        response = self.client.get("/?page=1%27%28")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Invalid page parameter.", status_code=400)

    def test_homepage_rejects_non_numeric_page_payload_with_trailing_quote(self):
        response = self.client.get("/?page=4%27")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Invalid page parameter.", status_code=400)

    def test_homepage_preserves_valid_search_and_pagination_behavior(self):
        for index in range(1, 7):
            Post.objects.create(
                author=self.teacher,
                title=f"Teacher Search Result {index}",
                content="Teacher content",
                is_published=True,
            )

        response = self.client.get(reverse("home"), {"q": "Teacher", "page": "2"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["query"], "Teacher")
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["page_obj"].paginator.count, 7)
        self.assertContains(response, "?q=Teacher&page=1")

    def test_homepage_filters_posts_by_selected_category_without_leaving_home(self):
        matching_post = Post.objects.create(
            author=self.teacher,
            title="Technology Filter Match",
            content="Tech content",
            is_published=True,
            category=self.tech_category,
        )
        other_post = Post.objects.create(
            author=self.teacher,
            title="Education Filter Miss",
            content="Education content",
            is_published=True,
            category=self.education_category,
        )

        response = self.client.get(reverse("home"), {"category": self.tech_category.slug})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_category"], self.tech_category)
        self.assertEqual(response.context["active_category_slug"], self.tech_category.slug)
        self.assertContains(response, "Hamısını göstər")
        self.assertIn(matching_post, response.context["page_obj"].object_list)
        self.assertIn(self.teacher_post, response.context["page_obj"].object_list)
        self.assertNotIn(other_post, response.context["page_obj"].object_list)

    def test_homepage_combines_search_and_category_filter_in_links(self):
        Post.objects.create(
            author=self.teacher,
            title="Technology Teacher Search Result",
            content="Teacher content",
            is_published=True,
            category=self.tech_category,
        )
        Post.objects.create(
            author=self.teacher,
            title="Education Teacher Search Result",
            content="Teacher content",
            is_published=True,
            category=self.education_category,
        )

        response = self.client.get(reverse("home"), {"q": "Teacher", "category": self.tech_category.slug})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["query"], "Teacher")
        self.assertEqual(response.context["selected_category"], self.tech_category)
        self.assertEqual(response.context["extra_query"], "q=Teacher&category=test-technology")
        self.assertContains(response, "/?category=test-technology&q=Teacher")

    def test_legacy_blog_home_redirects_to_root(self):
        response = self.client.get("/blog/?q=Teacher&page=2")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "/?q=Teacher&page=2")

    def test_student_can_open_create_post_page(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("create_post"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="new_category"')
        self.assertContains(response, 'name="subcategory"')

    def test_teacher_question_pages_render_without_server_error(self):
        Question.objects.create(
            author=self.teacher,
            question_text="What is EMS Arena?",
            answer_text="A learning platform.",
            visible_to_all=True,
        )

        self._activate_org(self.teacher)

        for url_name in ("questions_i_can_see", "my_questions", "create_question"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertLess(response.status_code, 500)

    def test_question_pages_redirect_anonymous_users_to_login(self):
        for url_name in ("questions_i_can_see", "my_questions", "create_question"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("accounts:login"), response.url)

    def test_student_cannot_edit_other_users_post(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("post_edit_ajax", args=[self.teacher_post.id]),
            {
                "title": "Updated",
                "content": "Updated content",
                "excerpt": "",
                "category": "",
                "image_url": "",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_teacher_can_open_create_post_page(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("create_post"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="new_category"')
        self.assertContains(response, 'name="subcategory"')

    def test_normal_users_cannot_submit_legacy_new_category_payload(self):
        for user in (self.student, self.teacher):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.post(
                    reverse("create_post"),
                    {
                        "title": "Legacy Category Attempt",
                        "content": "Student content",
                        "excerpt": "",
                        "category": str(self.tech_category.id),
                        "subcategory": "",
                        "new_category": "Unauthorized Student Category",
                        "image_url": "",
                    },
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(Category.objects.filter(name="Unauthorized Student Category").exists())
                self.assertIn("SuperAdmin", response.json()["errors"]["category"][0])

    def test_author_can_delete_own_post_via_ajax(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("delete_post", args=[self.teacher_post.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("Teacher Post", payload["message"])
        self.assertFalse(Post.objects.filter(id=self.teacher_post.id).exists())

    def test_other_user_cannot_delete_post(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("delete_post", args=[self.teacher_post.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Post.objects.filter(id=self.teacher_post.id).exists())

    def test_author_delete_post_non_ajax_redirects_to_new_profile(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("delete_post", args=[self.teacher_post.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('accounts:profile')}?section=posts")

    def test_legacy_user_profile_redirects_own_username_to_accounts_profile(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("user_profile", args=[self.teacher.username]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

    def test_legacy_user_profile_redirects_other_username_to_accounts_public_profile(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("user_profile", args=[self.student.username]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:public_profile", args=[self.student.username]))

    def test_article_detail_renders_back_link_with_public_profile_fallback(self):
        response = self.client.get(reverse("article_detail", args=[self.teacher_post.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Geri qayıt")
        self.assertContains(response, reverse("accounts:public_profile", args=[self.teacher.username]))
        self.assertContains(response, "data-history-back")

    def test_article_detail_increments_view_count_once_per_session(self):
        detail_url = reverse("article_detail", args=[self.teacher_post.slug])

        first_response = self.client.get(detail_url)
        second_response = self.client.get(detail_url)
        self.teacher_post.refresh_from_db()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(self.teacher_post.view_count, 1)
        self.assertContains(second_response, "1 baxış")

    def test_article_detail_counts_new_browser_session_as_new_view(self):
        detail_url = reverse("article_detail", args=[self.teacher_post.slug])

        self.client.get(detail_url)
        self.client.cookies.clear()
        self.client.get(detail_url)
        self.teacher_post.refresh_from_db()

        self.assertEqual(self.teacher_post.view_count, 2)

    def test_legacy_blog_article_detail_redirects_to_article_route(self):
        response = self.client.get(f"/blog/posts/{self.teacher_post.slug}/")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, reverse("article_detail", args=[self.teacher_post.slug]))

    def test_author_can_create_post_via_ajax(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("create_post"),
            {
                "title": "Ajax Created Post",
                "content": "Ajax content",
                "excerpt": "Ajax excerpt",
                "category": str(self.tech_category.id),
                "subcategory": str(self.ai_category.id),
                "image_url": "",
                "is_published": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"success": true')
        created_post = Post.objects.get(author=self.teacher, title="Ajax Created Post")
        self.assertEqual(created_post.category, self.ai_category)

    def test_legacy_blog_create_post_ajax_endpoint_still_works(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            "/blog/posts/create/",
            {
                "title": "Legacy Ajax Created Post",
                "content": "Legacy ajax content",
                "excerpt": "Legacy ajax excerpt",
                "category": str(self.education_category.id),
                "subcategory": "",
                "image_url": "",
                "is_published": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"success": true')
        created_post = Post.objects.get(author=self.teacher, title="Legacy Ajax Created Post")
        self.assertEqual(created_post.category, self.education_category)

    def test_student_created_post_stays_pending_until_approval(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("create_post"),
            {
                "title": "Student Pending Post",
                "content": "Student content",
                "excerpt": "",
                "category": str(self.tech_category.id),
                "subcategory": "",
                "image_url": "",
                "is_published": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        created_post = Post.objects.get(author=self.student, title="Student Pending Post")
        self.assertTrue(created_post.requires_approval)
        self.assertEqual(created_post.approval_status, Post.ApprovalStatus.PENDING)
        self.assertFalse(created_post.is_published)

    def test_group_teacher_can_approve_student_post(self):
        pending_post = Post.objects.create(
            author=self.student,
            title="Approval Candidate",
            content="Needs teacher approval",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )

        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("review_post", args=[pending_post.id]),
            {
                "action": "approve",
                "feedback": "Yaxşı hazırlanıb.",
            },
        )
        self.assertEqual(response.status_code, 302)

        pending_post.refresh_from_db()
        self.assertTrue(pending_post.is_published)
        self.assertEqual(pending_post.approval_status, Post.ApprovalStatus.APPROVED)
        self.assertEqual(pending_post.approved_by, self.teacher)
        self.assertEqual(pending_post.approval_feedback, "Yaxşı hazırlanıb.")

    def test_teacher_outside_group_cannot_approve_student_post(self):
        pending_post = Post.objects.create(
            author=self.student,
            title="Blocked Candidate",
            content="Only assigned teacher can approve",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )

        self.client.force_login(self.other_teacher)
        response = self.client.post(
            reverse("review_post", args=[pending_post.id]),
            {"action": "approve"},
        )
        self.assertEqual(response.status_code, 403)
        pending_post.refresh_from_db()
        self.assertEqual(pending_post.approval_status, Post.ApprovalStatus.PENDING)
        self.assertFalse(pending_post.is_published)

    def test_reviewer_can_open_pending_article_detail(self):
        pending_post = Post.objects.create(
            author=self.student,
            title="Pending Detail Access",
            content="Teacher should still review this post",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )

        self.client.force_login(self.teacher)
        response = self.client.get(reverse("article_detail", args=[pending_post.slug]))
        self.assertEqual(response.status_code, 200)

    def test_pending_post_approvals_section_shows_show_more_toggle_for_long_content(self):
        pending_post = Post.objects.create(
            author=self.student,
            title="Long Approval Content",
            content="Uzun content " * 80,
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )

        self._activate_org(self.teacher)
        response = self.client.get(reverse("accounts:profile") + "?section=pending-post-approvals")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pending_post.title)
        self.assertContains(response, "Show more")
        self.assertContains(response, "data-pending-post-toggle")
        self.assertContains(response, "data-pending-post-full")

    def test_superadmin_can_deactivate_published_post_without_approval_flag(self):
        superadmin = User.objects.create_superuser(
            username="blog_post_superadmin",
            email="blog_post_superadmin@example.com",
            password="StrongPass123!",
        )

        self._activate_org(superadmin)
        response = self.client.post(
            reverse("teacher_moderate_post", args=[self.teacher_post.id]),
            {
                "action": "deactivate",
                "feedback": "Yenilənməlidir.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.teacher_post.refresh_from_db()
        self.assertFalse(self.teacher_post.is_published)
        self.assertEqual(self.teacher_post.approval_feedback, "Yenilənməlidir.")

    def test_org_admin_can_deactivate_published_org_post_without_approval_flag(self):
        org_admin = User.objects.create_user(
            username="blog_post_org_admin",
            email="blog_post_org_admin@example.com",
            password="StrongPass123!",
        )
        _assign_user_to_org(org_admin, self.organization, ProfileRole.ORG_ADMIN, membership_role_name="manager")

        self._activate_org(org_admin)
        response = self.client.post(
            reverse("teacher_moderate_post", args=[self.teacher_post.id]),
            {
                "action": "deactivate",
                "feedback": "Təşkilat qaydalarına uyğun yenilə.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.teacher_post.refresh_from_db()
        self.assertFalse(self.teacher_post.is_published)
        self.assertEqual(self.teacher_post.approval_feedback, "Təşkilat qaydalarına uyğun yenilə.")


class BlogCategoryHierarchyTest(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username="categoryauthor",
            email="categoryauthor@example.com",
            password="StrongPass123!",
        )
        self.parent_category = Category.objects.get(slug="technology")
        self.child_category = Category.objects.get(slug="programming")
        self.demo_category = Category.objects.create(name="Demo xəbərlər", slug="demo-xeberler")

        Post.objects.create(
            author=self.author,
            category=self.parent_category,
            title="Technology Parent Post",
            content="Parent category content",
            is_published=True,
        )
        Post.objects.create(
            author=self.author,
            category=self.child_category,
            title="Programming Child Post",
            content="Child category content",
            is_published=True,
        )
        Post.objects.create(
            author=self.author,
            category=self.demo_category,
            title="Demo Category Post",
            content="Demo category content",
            is_published=True,
        )

    def test_parent_category_page_includes_child_category_posts(self):
        response = self.client.get(reverse("category_detail", args=[self.parent_category.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Technology Parent Post")
        self.assertContains(response, "Programming Child Post")

    def test_technology_page_uses_default_category_scope(self):
        response = self.client.get(reverse("technology"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Technology Parent Post")
        self.assertContains(response, "Programming Child Post")

    def test_section_sidebar_prioritizes_most_populated_category_and_hides_root_row(self):
        response = self.client.get(reverse("category_detail", args=[self.parent_category.slug]))

        self.assertEqual(response.status_code, 200)
        category_slugs = [category.slug for category in response.context["categories"]]

        self.assertGreater(len(category_slugs), 0)
        self.assertEqual(category_slugs[0], "programming")
        self.assertNotIn("technology", category_slugs)

    def test_category_detail_rejects_non_numeric_page_payloads(self):
        for payload in ("'", '"', ";", "'("):
            with self.subTest(payload=payload):
                response = self.client.get(
                    reverse("category_detail", args=[self.demo_category.slug]),
                    {"page": payload},
                )

                self.assertEqual(response.status_code, 400)
                self.assertContains(response, "Invalid page parameter.", status_code=400)
