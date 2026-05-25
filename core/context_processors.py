"""
Core context processors.

``seo_context`` exposes a single ``seo`` dictionary to every template so the
shared ``partials/_seo_head.html`` head fragment can render correct meta
tags, canonical URLs, Open Graph / Twitter cards, hreflang links and
JSON-LD structured data without each view having to pass SEO data manually.

Per-page overrides
------------------
Any view may override individual values by adding ``seo_*`` keys to its own
template context, e.g.::

    return render(request, "blog/about.html", {
        "seo_title": "Haqqımızda — EMSArena",
        "seo_description": "EMSArena komandası və missiyamız.",
    })

The processor merges those overrides on top of the site-wide defaults, so a
view only needs to specify what differs.  It performs **no** database
queries — everything is derived from ``settings`` and the ``request``.
"""

from __future__ import annotations

from django.conf import settings
from django.templatetags.static import static

# Canonical public origin, e.g. "https://emsarena.com" (no trailing slash).
SITE_ORIGIN = getattr(settings, "SITE_URL", "https://emsarena.com").rstrip("/")

# Brand / organization constants reused across structured data.
ORG_NAME = "EMSArena"
ORG_DESCRIPTION_AZ = (
    "EMSArena universitetlər, məktəblər, kurs mərkəzləri və müəllimlər üçün "
    "LMS, onlayn imtahan, elektron jurnal, qiymətləndirmə və analitika "
    "platformasıdır."
)
ORG_DESCRIPTION_EN = (
    "EMSArena is a modern LMS, education management and online exam platform "
    "for universities, schools, training centers, teachers and students."
)

# Default meta description per active language.
DEFAULT_DESCRIPTIONS = {
    "az": ORG_DESCRIPTION_AZ,
    "en": ORG_DESCRIPTION_EN,
    "ru": (
        "EMSArena — современная платформа LMS, управления образованием и "
        "онлайн-экзаменов для университетов, школ и учебных центров."
    ),
    "tr": ("EMSArena; üniversiteler, okullar ve kurs merkezleri için LMS, " "online sınav ve e-günlük platformudur."),
}

DEFAULT_KEYWORDS = (
    "EMSArena, LMS Azərbaycan, təhsil idarəetmə sistemi, onlayn imtahan "
    "sistemi, elektron jurnal, EdTech Azərbaycan, universitet idarəetmə "
    "sistemi, məktəb idarəetmə sistemi, kurs mərkəzi platforması"
)

# Official social profiles.  Leave empty until real, verified accounts
# exist — Google ignores (and may distrust) broken sameAs links.
SOCIAL_PROFILES: list[str] = []

# URL path prefixes that are tenant-scoped / private and must NOT be
# indexed.  Any request whose path starts with one of these gets a
# "noindex, nofollow" robots default (a stronger guarantee than robots.txt
# alone, which only discourages crawling, not indexing of linked URLs).
# A view under one of these prefixes can still opt back in by passing
# ``seo_robots="index, follow"`` in its render context.
NOINDEX_PREFIXES = (
    "/admin/",
    "/manage/",
    "/dashboard/",
    "/teacher/",
    "/student/",
    "/organization/",
    "/organizations/",
    "/api/",
    "/exams/",
    "/courses/",
    "/assignments/",
    "/projects/",
    "/labs/",
    "/notifications/",
    "/audit/",
    "/accounts/dashboard/",
    "/accounts/profile/",
    "/accounts/manage-roles/",
    "/accounts/grading-queue/",
    "/accounts/superadmin/",
    "/i18n/",
)


def _abs(path: str) -> str:
    """Return an absolute URL for a root-relative path or pass through an
    already-absolute URL unchanged."""
    if path.startswith(("http://", "https://")):
        return path
    return f"{SITE_ORIGIN}/{path.lstrip('/')}"


def seo_context(request):
    """Inject the ``seo`` dict consumed by ``partials/_seo_head.html``."""
    lang = getattr(request, "LANGUAGE_CODE", None) or settings.LANGUAGE_CODE
    lang = (lang or "az").split("-")[0]

    # Absolute canonical URL of the current page, without query string.
    # Crawlers should treat ?q=, ?page= etc. as the same canonical page.
    canonical = _abs(request.path)

    default_description = DEFAULT_DESCRIPTIONS.get(lang, ORG_DESCRIPTION_AZ)

    # Private/tenant pages default to noindex; public pages default to index.
    path = request.path
    is_private = any(path.startswith(p) for p in NOINDEX_PREFIXES)
    default_robots = "noindex, nofollow" if is_private else "index, follow"

    # hreflang alternates.  The project serves all languages on the SAME
    # URLs (language is selected via cookie / Accept-Language), so every
    # alternate points at the current path.  x-default falls back to it too.
    languages = [code for code, _name in getattr(settings, "LANGUAGES", [])]
    hreflang = [(code, canonical) for code in languages]
    hreflang.append(("x-default", canonical))

    seo = {
        "site_name": ORG_NAME,
        "site_origin": SITE_ORIGIN,
        "lang": lang,
        "canonical": canonical,
        "title": ORG_NAME,
        "description": default_description,
        "keywords": DEFAULT_KEYWORDS,
        "robots": default_robots,
        "og_type": "website",
        "og_image": _abs(static("brand/og-image.jpg")),
        "twitter_card": "summary_large_image",
        "theme_color": "#0f766e",
        "hreflang": hreflang,
        "logo_url": _abs(static("brand/logo-square.png")),
        "social_profiles": SOCIAL_PROFILES,
        # Per-page JSON-LD breadcrumb: list of (name, absolute_url) tuples.
        "breadcrumbs": [],
        # Whether to emit the homepage-only Organization/WebSite/Software
        # structured data.  Set True only on the home view.
        "is_home": False,
    }

    # Per-view overrides: a context processor cannot see a view's render()
    # context, so ``partials/_seo_head.html`` resolves ``seo_title`` /
    # ``seo_description`` / ``seo_breadcrumbs`` etc. itself, falling back to
    # the ``seo`` defaults provided here.
    return {
        "seo": seo,
        "SEO_ABS_ORIGIN": SITE_ORIGIN,
    }
