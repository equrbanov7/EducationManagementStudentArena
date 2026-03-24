"""
Data migration: seed default blog categories and minimal demo content.

Creates the category tree expected by test_models and test_views, plus a
demo post with two comments so that test_default_demo_content_seeded_with_comments
passes without any manual setup.
"""

from django.db import migrations


def _seed(apps, schema_editor):
    Category = apps.get_model("blog", "Category")
    Post = apps.get_model("blog", "Post")
    Comment = apps.get_model("blog", "Comment")
    User = apps.get_model("auth", "User")

    # --- Root categories --------------------------------------------------
    technology, _ = Category.objects.get_or_create(
        slug="technology",
        defaults={
            "name": "Technology",
            "sort_order": 10,
            "show_in_navbar": True,
            "is_default": True,
        },
    )

    education, _ = Category.objects.get_or_create(
        slug="education",
        defaults={
            "name": "Education",
            "sort_order": 30,
            "show_in_navbar": True,
            "is_default": True,
        },
    )

    data_ai, _ = Category.objects.get_or_create(
        slug="data-ai",
        defaults={
            "name": "Data & AI",
            "sort_order": 50,
            "show_in_navbar": False,
            "is_default": True,
        },
    )

    # --- Child categories -------------------------------------------------
    Category.objects.get_or_create(
        slug="programming",
        defaults={
            "name": "Programming",
            "parent": technology,
            "sort_order": 20,
            "show_in_navbar": True,
            "is_default": True,
        },
    )

    Category.objects.get_or_create(
        slug="study-tips",
        defaults={
            "name": "Study Tips",
            "parent": education,
            "sort_order": 40,
            "show_in_navbar": False,
            "is_default": True,
        },
    )

    # --- Demo author (system account for seeded content) ------------------
    demo_user, _ = User.objects.get_or_create(
        username="blog_system",
        defaults={
            "email": "blog_system@emsarena.local",
            "is_active": True,
        },
    )

    # --- Demo post --------------------------------------------------------
    demo_post, created = Post.objects.get_or_create(
        slug="ai-saglamliq-analizinde-nece-komek-edir",
        defaults={
            "author": demo_user,
            "category": data_ai,
            "title": "AI sağlamlıq analizində necə kömək edir?",
            "excerpt": "Süni intellektin tibbi sahədə tətbiqi haqqında məlumat.",
            "content": (
                "Süni intellekt (AI) müasir tibbdə inqilabi dəyişikliklərə yol açır. "
                "Xəstəliklərin erkən aşkarlanması, müalicə planlarının optimallaşdırılması "
                "və tibbi şəkillərin analizi sahələrində AI sistemləri həkimlərə böyük "
                "dəstək verir."
            ),
            "is_published": True,
            "approval_status": "approved",
        },
    )

    # --- Demo comments (at least 2) --------------------------------------
    if demo_post.comments.count() < 2:
        commenters = []
        for i in range(1, 3):
            commenter, _ = User.objects.get_or_create(
                username=f"demo_commenter_{i}",
                defaults={
                    "email": f"demo_commenter_{i}@emsarena.local",
                    "is_active": True,
                },
            )
            commenters.append(commenter)

        existing_count = demo_post.comments.count()
        for idx, commenter in enumerate(commenters):
            if existing_count + idx >= 2:
                break
            Comment.objects.get_or_create(
                post=demo_post,
                user=commenter,
                defaults={
                    "text": f"Demo şərh {idx + 1}",
                    "rating": 5,
                },
            )


def _unseed(apps, schema_editor):
    Category = apps.get_model("blog", "Category")
    Post = apps.get_model("blog", "Post")
    User = apps.get_model("auth", "User")

    Post.objects.filter(slug="ai-saglamliq-analizinde-nece-komek-edir").delete()
    for slug in ("study-tips", "programming", "data-ai", "education", "technology"):
        Category.objects.filter(slug=slug).delete()
    User.objects.filter(username__in=["blog_system", "demo_commenter_1", "demo_commenter_2"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_seed, _unseed),
    ]
