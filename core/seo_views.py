# core/seo_views.py
"""
SEO infrastructure views for EMSArena.

Responsibilities
----------------
* Serve the *root-path* assets that crawlers and browsers expect at the
  domain root (``/favicon.ico``, ``/site.webmanifest``, ``/logo.png``,
  ``/og-image.jpg`` ...).  The actual binary files live under
  ``static/brand/`` so they go through the normal WhiteNoise pipeline
  (compression + far-future caching).  These views are thin redirects.
* Serve a dynamic ``/robots.txt`` (host-aware).
* Serve a dynamic ``/sitemap.xml`` built from the real, public URL
  patterns of the project — no hand-maintained URL list that can rot.

Design notes
------------
* The canonical site origin comes from ``settings.SITE_URL`` so the same
  code is correct in local / staging / production without edits.
* Only genuinely public pages are listed in the sitemap.  Tenant-scoped
  dashboards, the admin, the API and exam-session URLs are intentionally
  excluded (and also ``Disallow``-ed in robots.txt).
* All responses are cacheable for a day; crawlers do not need fresher.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils.timezone import now
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

# --------------------------------------------------------------------------
# Canonical origin helpers
# --------------------------------------------------------------------------
#: Public origin of the site, e.g. "https://emsarena.com" (no trailing slash).
SITE_ORIGIN = getattr(settings, "SITE_URL", "https://emsarena.com").rstrip("/")


def _abs(path: str) -> str:
    """Return an absolute URL for a root-relative ``path``."""
    return f"{SITE_ORIGIN}/{path.lstrip('/')}"


# --------------------------------------------------------------------------
# Root-path brand assets  ->  redirect to the hashed static file
# --------------------------------------------------------------------------
# Maps the URL the *crawler* requests to the logical static asset name.
# ``static()`` resolves the (possibly hashed) final URL via WhiteNoise's
# manifest storage in production and the plain path in development.
ROOT_ASSET_MAP = {
    "favicon.ico": "brand/favicon.ico",
    "favicon-16x16.png": "brand/favicon-16x16.png",
    "favicon-32x32.png": "brand/favicon-32x32.png",
    "favicon-48x48.png": "brand/favicon-48x48.png",
    "favicon-96x96.png": "brand/favicon-96x96.png",
    "favicon-192x192.png": "brand/favicon-192x192.png",
    "favicon-512x512.png": "brand/favicon-512x512.png",
    "apple-touch-icon.png": "brand/apple-touch-icon.png",
    "logo.png": "brand/logo.png",
    "og-image.jpg": "brand/og-image.jpg",
}


@require_GET
@cache_control(max_age=86400, public=True)
def root_asset(request, asset_name: str):
    """Permanent-redirect a well-known root asset to its static URL.

    Browsers and Google look for e.g. ``/favicon.ico`` at the site root.
    Rather than duplicating the binary, we 301 to the cache-busted static
    path.  Search engines follow the redirect and index the target.
    """
    from django.http import Http404, HttpResponsePermanentRedirect

    static_name = ROOT_ASSET_MAP.get(asset_name)
    if static_name is None:
        raise Http404("Unknown asset")
    return HttpResponsePermanentRedirect(static(static_name))


@require_GET
@cache_control(max_age=86400, public=True)
def site_webmanifest(request):
    """Serve the PWA web app manifest with correct content-type.

    Icon URLs point at the static brand assets.  The manifest itself is
    generated here (not a static file) so the icon URLs stay correct even
    when WhiteNoise hashes the filenames.
    """
    import json

    manifest = {
        "name": "EMSArena",
        "short_name": "EMSArena",
        "description": (
            "Education management, LMS and online exam platform for " "universities, schools and training centers."
        ),
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0f766e",
        "icons": [
            {
                "src": static("brand/favicon-192x192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": static("brand/favicon-512x512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }
    return HttpResponse(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        content_type="application/manifest+json; charset=utf-8",
    )


# --------------------------------------------------------------------------
# robots.txt
# --------------------------------------------------------------------------
# Path prefixes that must never be crawled: tenant dashboards, admin, the
# API surface and live/active exam pages (which leak nothing useful and
# would waste crawl budget).
ROBOTS_DISALLOW = [
    "/admin/",
    "/manage/",  # ADMIN_URL_PREFIX may relocate admin here
    "/dashboard/",
    "/teacher/",
    "/student/",
    "/organization/",
    "/organizations/",
    "/api/",
    "/accounts/",  # login/register handled separately below
    "/exams/",  # exam taking, teacher exam mgmt — all private
    "/courses/",
    "/assignments/",
    "/projects/",
    "/labs/",
    "/notifications/",
    "/audit/",
    "/media/private/",
    "/i18n/",
]

# Explicitly allow the public auth landing pages even though /accounts/ is
# disallowed — they carry brand keywords and are safe to index.
ROBOTS_ALLOW = [
    "/accounts/login/",
    "/accounts/register/",
    "/favicon.ico",
    "/og-image.jpg",
    "/logo.png",
    "/site.webmanifest",
]


@require_GET
@cache_control(max_age=86400, public=True)
def robots_txt(request):
    """Dynamic robots.txt — references the sitemap at the live host."""
    lines = ["User-agent: *"]
    lines += [f"Allow: {p}" for p in ROBOTS_ALLOW]
    lines += [f"Disallow: {p}" for p in ROBOTS_DISALLOW]
    lines.append("")
    lines.append(f"Sitemap: {_abs('sitemap.xml')}")
    lines.append("")
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


# --------------------------------------------------------------------------
# sitemap.xml
# --------------------------------------------------------------------------
# Public, indexable pages.  Each entry: (url_name_or_path, priority,
# changefreq).  A leading "/" means a literal path; anything else is
# treated as a Django URL name and reverse()-d (so the sitemap stays
# correct if a route moves).
SITEMAP_ENTRIES = [
    ("home", "1.0", "weekly"),
    ("about", "0.7", "monthly"),
    ("login", "0.5", "yearly"),
    ("register", "0.5", "yearly"),
]


def _resolve(entry_key: str) -> str | None:
    """Resolve a sitemap entry key to a root-relative path, or None."""
    if entry_key.startswith("/"):
        return entry_key
    for namespace in ("", "accounts:"):
        try:
            return reverse(f"{namespace}{entry_key}")
        except NoReverseMatch:
            continue
    return None


@require_GET
@cache_control(max_age=86400, public=True)
def sitemap_xml(request):
    """Dynamic sitemap.xml covering only public, indexable URLs."""
    today = now().date().isoformat()
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    seen: set[str] = set()
    for key, priority, changefreq in SITEMAP_ENTRIES:
        path = _resolve(key)
        if not path or path in seen:
            continue
        seen.add(path)
        parts += [
            "  <url>",
            f"    <loc>{_abs(path)}</loc>",
            f"    <lastmod>{today}</lastmod>",
            f"    <changefreq>{changefreq}</changefreq>",
            f"    <priority>{priority}</priority>",
            "  </url>",
        ]
    parts.append("</urlset>")
    return HttpResponse("\n".join(parts), content_type="application/xml; charset=utf-8")
