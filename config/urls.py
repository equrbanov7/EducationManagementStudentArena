# config/urls.py
import re

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from core.views import health_check, ping, test_error

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("blog/", include("apps.blog.urls")),
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
    path("health/", health_check, name="health_check"),
    path("ping/", ping, name="ping"),
    path("test-error/", test_error, name="test_error"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, "SERVE_MEDIA", False):
    media_prefix = settings.MEDIA_URL.lstrip("/")
    if media_prefix and not media_prefix.endswith("/"):
        media_prefix += "/"
    urlpatterns += [
        re_path(
            rf"^{re.escape(media_prefix)}(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]
