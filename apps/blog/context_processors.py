from .models import Category
from .selectors import DEFAULT_TECHNOLOGY_CATEGORY_SLUG


def blog_navigation_context(request):
    active_category_slug = None
    resolver_match = getattr(request, "resolver_match", None)

    if resolver_match:
        if resolver_match.url_name == "home":
            category_slug = request.GET.get("category")
            if category_slug:
                category = (
                    Category.objects.select_related("parent", "parent__parent").filter(slug=category_slug).first()
                )
                if category:
                    active_category_slug = category.get_root().slug
        elif resolver_match.url_name == "category_detail":
            category_slug = resolver_match.kwargs.get("slug")
            if category_slug:
                category = (
                    Category.objects.select_related("parent", "parent__parent").filter(slug=category_slug).first()
                )
                if category:
                    active_category_slug = category.get_root().slug
        elif resolver_match.url_name == "technology":
            active_category_slug = DEFAULT_TECHNOLOGY_CATEGORY_SLUG

    return {
        "active_blog_nav_slug": active_category_slug,
    }
