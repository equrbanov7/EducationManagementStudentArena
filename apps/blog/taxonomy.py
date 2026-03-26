from django.utils.translation import get_language

SUPPORTED_CATEGORY_LANGUAGES = ("az", "en", "ru", "tr")

DEFAULT_CATEGORY_PLACEHOLDERS = {
    "technology": "images/placeholders/category-technology.svg",
    "education": "images/placeholders/category-education.svg",
    "research-science": "images/placeholders/category-science.svg",
    "business-startup": "images/placeholders/category-business.svg",
    "personal-development": "images/placeholders/category-lifestyle.svg",
    "marketing-media": "images/placeholders/category-creative.svg",
}


def get_language_code(language=None):
    normalized = (language or get_language() or "az").split("-")[0].lower()
    return normalized if normalized in SUPPORTED_CATEGORY_LANGUAGES else "en"


def get_localized_category_name(category, fallback):
    if category is None:
        return fallback

    language = get_language_code()
    translated_value = getattr(category, f"name_{language}", "") if hasattr(category, f"name_{language}") else ""
    if translated_value:
        return translated_value

    fallback_languages = ("en", "az", "ru", "tr")
    for fallback_language in fallback_languages:
        translated_value = getattr(category, f"name_{fallback_language}", "")
        if translated_value:
            return translated_value

    return fallback


def get_category_placeholder_static_path(category_slug, *, fallback="images/tech-placeholder.svg"):
    return DEFAULT_CATEGORY_PLACEHOLDERS.get(category_slug, fallback)
