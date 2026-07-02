"""Blog testləri üçün minimal seed fixture (--no-migrations sqlite dövrəsi).

CI migrasiyaları işlədir → 0002 seed-ləri mövcuddur və buradakı get_or_create
no-op olur. Yerli sürətli dövrədə isə testlərin arxalandığı minimal
"Technology → Programming" ağacı yaradılır.

QEYD: 0002-nin _seed funksiyasını REAL model registri ilə çağırmaq OLMAZ —
real Category.save() historical modeldə olmayan parent-validasiya işlədir.
Seed-in TAM formasını yoxlayan testlər (tree_seeded, demo_content) əvəzinə
`skip_unless_seed_migrations()` guard-ından istifadə edir.
"""

from apps.blog.models import Category


def ensure_blog_seed_data():
    technology, _ = Category.objects.get_or_create(
        slug="technology",
        defaults={"name": "Technology", "sort_order": 10, "show_in_navbar": True, "is_default": True},
    )
    Category.objects.get_or_create(
        slug="programming",
        defaults={"name": "Programming", "parent": technology, "sort_order": 10, "is_default": True},
    )
    education, _ = Category.objects.get_or_create(
        slug="education",
        defaults={"name": "Education", "sort_order": 30, "show_in_navbar": True, "is_default": True},
    )
    Category.objects.get_or_create(
        slug="study-tips",
        defaults={"name": "Study Tips", "parent": education, "sort_order": 10, "is_default": True},
    )
    return technology


def skip_unless_seed_migrations(test_case):
    """Seed migrasiyasının TAM nəticəsini yoxlayan testlər üçün guard."""
    if not Category.objects.filter(slug="data-ai").exists():
        test_case.skipTest(
            "0002 seed migrasiyası tələb olunur (--no-migrations sürətli dövrəsində atlanır; CI-də işləyir)"
        )
