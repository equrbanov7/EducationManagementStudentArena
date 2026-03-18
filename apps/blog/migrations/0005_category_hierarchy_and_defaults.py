from django.db import migrations, models
import django.db.models.deletion


DEFAULT_CATEGORY_TREE = [
    {
        "name": "Technology",
        "slug": "technology",
        "sort_order": 10,
        "show_in_navbar": True,
        "children": [
            {"name": "Programming", "slug": "programming", "sort_order": 11},
            {"name": "Web Development", "slug": "web-development", "sort_order": 12},
            {"name": "Data & AI", "slug": "data-ai", "sort_order": 13},
            {"name": "Cybersecurity", "slug": "cybersecurity", "sort_order": 14},
            {"name": "Cloud & DevOps", "slug": "cloud-devops", "sort_order": 15},
        ],
    },
    {
        "name": "Education",
        "slug": "education",
        "sort_order": 20,
        "show_in_navbar": True,
        "children": [
            {"name": "Study Tips", "slug": "study-tips", "sort_order": 21},
            {"name": "Online Learning", "slug": "online-learning", "sort_order": 22},
            {"name": "Career Development", "slug": "career-development", "sort_order": 23},
            {"name": "Language Learning", "slug": "language-learning", "sort_order": 24},
        ],
    },
    {
        "name": "Business",
        "slug": "business",
        "sort_order": 30,
        "show_in_navbar": True,
        "children": [
            {"name": "Entrepreneurship", "slug": "entrepreneurship", "sort_order": 31},
            {"name": "Marketing", "slug": "marketing", "sort_order": 32},
            {"name": "Finance", "slug": "finance", "sort_order": 33},
            {"name": "Management", "slug": "management", "sort_order": 34},
        ],
    },
    {
        "name": "Science",
        "slug": "science",
        "sort_order": 40,
        "children": [
            {"name": "Mathematics", "slug": "mathematics", "sort_order": 41},
            {"name": "Physics", "slug": "physics", "sort_order": 42},
            {"name": "Biology", "slug": "biology", "sort_order": 43},
            {"name": "Research", "slug": "research", "sort_order": 44},
        ],
    },
    {
        "name": "Lifestyle",
        "slug": "lifestyle",
        "sort_order": 50,
        "children": [
            {"name": "Productivity", "slug": "productivity", "sort_order": 51},
            {"name": "Health & Wellness", "slug": "health-wellness", "sort_order": 52},
            {"name": "Travel", "slug": "travel", "sort_order": 53},
            {"name": "Food", "slug": "food", "sort_order": 54},
        ],
    },
    {
        "name": "Creative",
        "slug": "creative",
        "sort_order": 60,
        "children": [
            {"name": "Design", "slug": "design", "sort_order": 61},
            {"name": "Writing", "slug": "writing", "sort_order": 62},
            {"name": "Photography", "slug": "photography", "sort_order": 63},
            {"name": "Video & Audio", "slug": "video-audio", "sort_order": 64},
        ],
    },
]


def seed_default_categories(apps, schema_editor):
    Category = apps.get_model("blog", "Category")
    db_alias = schema_editor.connection.alias

    def get_existing_category(slug, name):
        slug_match = Category.objects.using(db_alias).filter(slug=slug).first()
        name_match = Category.objects.using(db_alias).filter(name__iexact=name).first()

        if slug_match and name_match and slug_match.pk != name_match.pk:
            return slug_match, slug_match.name, False
        if slug_match:
            return slug_match, name, False
        if name_match:
            return name_match, name, True
        return None, name, True

    def ensure_category(spec, parent=None):
        category, desired_name, can_update_slug = get_existing_category(spec["slug"], spec["name"])

        if category is None:
            category = Category.objects.using(db_alias).create(
                name=spec["name"],
                slug=spec["slug"],
                parent=parent,
                sort_order=spec.get("sort_order", 0),
                show_in_navbar=spec.get("show_in_navbar", False),
                is_default=True,
            )
        else:
            update_fields = []

            if category.name != desired_name:
                category.name = desired_name
                update_fields.append("name")
            if can_update_slug and category.slug != spec["slug"]:
                category.slug = spec["slug"]
                update_fields.append("slug")
            if category.parent_id != (parent.id if parent else None):
                category.parent = parent
                update_fields.append("parent")
            if category.sort_order != spec.get("sort_order", 0):
                category.sort_order = spec.get("sort_order", 0)
                update_fields.append("sort_order")
            if category.show_in_navbar != spec.get("show_in_navbar", False):
                category.show_in_navbar = spec.get("show_in_navbar", False)
                update_fields.append("show_in_navbar")
            if not category.is_default:
                category.is_default = True
                update_fields.append("is_default")

            if update_fields:
                category.save(update_fields=update_fields)

        for child_spec in spec.get("children", []):
            ensure_category(child_spec, parent=category)

        return category

    for category_spec in DEFAULT_CATEGORY_TREE:
        ensure_category(category_spec)


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0004_remove_emailotp"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="is_default",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="category",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="children",
                to="blog.category",
            ),
        ),
        migrations.AddField(
            model_name="category",
            name="show_in_navbar",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="category",
            name="sort_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name="category",
            options={
                "ordering": ["sort_order", "name"],
                "verbose_name": "Kateqoriya",
                "verbose_name_plural": "Kateqoriyalar",
            },
        ),
        migrations.RunPython(seed_default_categories, migrations.RunPython.noop),
    ]
