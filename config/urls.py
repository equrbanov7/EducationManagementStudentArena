# config/urls.py
import re

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path, reverse_lazy

from core.media_views import protected_media
from core.seo_views import (
    ROOT_ASSET_MAP,
    robots_txt,
    root_asset,
    site_webmanifest,
    sitemap_xml,
)
from core.views import handler400 as handler400  # noqa: F401
from core.views import handler403 as handler403  # noqa: F401
from core.views import handler404 as handler404  # noqa: F401
from core.views import handler500 as handler500  # noqa: F401
from core.views import health_check, metrics_view, ping, test_error

admin.site.site_url = reverse_lazy("home")

# Allow the admin URL to be relocated away from the default /admin/ path via
# the ADMIN_URL_PREFIX setting (e.g. set to "manage/" in production to avoid
# exposing the well-known endpoint).
_admin_prefix = getattr(settings, "ADMIN_URL_PREFIX", "admin/").lstrip("/")

# Well-known root-path SEO files.  Crawlers and browsers request these at
# the site root; the views below either serve generated content (robots.txt,
# sitemap.xml, the web manifest) or 301-redirect to the cache-busted static
# brand asset (favicon.ico, logo.png, og-image.jpg, ...).
_seo_urlpatterns = [
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap_xml"),
    path("site.webmanifest", site_webmanifest, name="site_webmanifest"),
] + [
    path(asset_name, root_asset, {"asset_name": asset_name}, name=f"root_asset_{asset_name}")
    for asset_name in ROOT_ASSET_MAP
]

urlpatterns = [
    path(_admin_prefix, admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    *_seo_urlpatterns,
    path("blog/", include("apps.blog.legacy_urls")),
    path("", include("apps.blog.urls")),
    path("", include("apps.live_exam.urls")),
    path("courses/", include("apps.courses.urls")),
    path("assignments/", include("apps.assignments.urls")),
    path("projects/", include("apps.projects.urls")),
    path("labs/", include("apps.labs.urls")),
    # accounts
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    # exams
    path("exams/", include(("apps.exams.urls", "exams"), namespace="exams")),
    # organizations
    path(
        "organizations/",
        include(("apps.organizations.urls", "organizations"), namespace="organizations"),
    ),
    # audit
    path("audit/", include(("apps.audit.urls", "audit"), namespace="audit")),
    # notifications
    path(
        "notifications/",
        include(("apps.notifications.urls", "notifications"), namespace="notifications"),
    ),
    # AI assistant API
    path("api/ai-assistant/", include(("apps.ai_assistant.urls", "ai_assistant"), namespace="ai_assistant")),
    # API versioned endpoints
    path("api/v1/", include(("apps.live_exam.api.v1.urls", "live_exam_api_v1"), namespace="live_exam_api_v1")),
    path("health/", health_check, name="health_check"),
    path("ping/", ping, name="ping"),
    path("metrics/", metrics_view, name="metrics"),
]

if settings.DEBUG:
    # Only expose this endpoint in development.  In production, triggering a
    # Sentry test error must not be possible by unauthenticated third parties.
    urlpatterns += [
        path("test-error/", test_error, name="test_error"),
    ]

# Always register the protected_media view so that Django can enforce
# authentication and return X-Accel-Redirect headers for authorised requests.
#
# In DEBUG mode or when SERVE_MEDIA=True (simple/staging), Django serves
# media files directly via FileResponse as a fallback.
#
# In production with MEDIA_ACCEL_REDIRECT_URL configured, the protected_media
# view performs auth checks and delegates actual file delivery to nginx via an
# X-Accel-Redirect header (the /internal_media/ internal location).  Nginx
# proxies /media/<private_path> to Django; if auth fails, Django returns
# 403/404; if auth passes, nginx serves the file at high performance without
# the response body passing through Python.
media_prefix = settings.MEDIA_URL.lstrip("/")
if media_prefix and not media_prefix.endswith("/"):
    media_prefix += "/"
urlpatterns += [
    re_path(
        rf"^{re.escape(media_prefix)}(?P<path>.*)$",
        protected_media,
    )
]

# Django looks for these module-level names in ROOT_URLCONF when DEBUG=False
# to dispatch 4xx/5xx responses.  The aliased imports above ensure the names
# exist at module scope explicitly.  See Django docs: "Customizing error views".
