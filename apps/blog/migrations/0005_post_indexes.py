"""Add performance indexes to blog Post (FAZA 3).

The blog is a public, high-read surface (landing pages, category pages,
article detail). These composite indexes back the most frequent query
patterns: public published-post lists, category pages, an author's own
posts, and the superadmin approval-review queue.

No schema/field change — index-only migration, safe to apply online.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0004_post_view_count"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="post",
            index=models.Index(
                fields=["is_published", "approval_status", "-created_at"],
                name="blog_post_public_list_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="post",
            index=models.Index(
                fields=["category", "-created_at"],
                name="blog_post_category_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="post",
            index=models.Index(
                fields=["author", "-created_at"],
                name="blog_post_author_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="post",
            index=models.Index(
                fields=["approval_status", "-approval_requested_at"],
                name="blog_post_review_idx",
            ),
        ),
    ]
