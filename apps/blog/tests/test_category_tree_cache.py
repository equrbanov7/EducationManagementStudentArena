"""P10: default kateqoriya-ağacı keşi üçün testlər."""

from django.core.cache import cache

import pytest

from apps.blog.models import Category
from apps.blog.selectors import get_post_category_tree

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _locmem_cache(settings):
    # Test settings DummyCache işlədir; keşin özünü yoxlamaq üçün locmem.
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "p10-test",
        }
    }
    cache.clear()
    yield
    cache.clear()


def _make_category(name, parent=None, slug=None):
    return Category.objects.create(
        name_az=name, name_en=name, name_ru=name, name_tr=name, slug=slug or name.lower(), parent=parent
    )


def test_second_default_call_hits_cache(django_assert_num_queries):
    root = _make_category("Elm")
    _make_category("Fizika", parent=root, slug="fizika")

    first = get_post_category_tree()
    assert len(first) == 1 and len(first[0].child_categories) == 1

    with django_assert_num_queries(0):
        second = get_post_category_tree()
    assert [c.pk for c in second] == [c.pk for c in first]


def test_custom_queryset_bypasses_cache(django_assert_num_queries):
    _make_category("Elm")
    get_post_category_tree()  # keşi doldur

    with django_assert_num_queries(1):
        custom = get_post_category_tree(category_queryset=Category.objects.all())
    assert len(custom) == 1


def test_category_change_invalidates(django_assert_num_queries):
    _make_category("Elm")
    assert len(get_post_category_tree()) == 1

    _make_category("Tarix", slug="tarix")  # post_save siqnalı keşi silməlidir
    tree = get_post_category_tree()
    assert len(tree) == 2


def test_cached_copies_are_isolated():
    _make_category("Elm")
    first = get_post_category_tree()
    first[0].child_categories = ["MUTASIYA"]

    second = get_post_category_tree()
    # pickle-copy sayəsində əvvəlki çağırışın mutasiyası keşə sızmır
    assert second[0].child_categories != ["MUTASIYA"]
