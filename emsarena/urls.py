# emsarena/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("blog/", include("blog.urls")),
    path("", include("blog.urls")),
    path("", include("liveExam.urls")),
    path("courses/", include("courses.urls")),
    path("assignments/", include("assignments.urls")),
    path("projects/", include("projects.urls")),
    path("labs/", include("labs.urls")),
    # exams
    path("exams/", include(("exams.urls", "exams"), namespace="exams")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
