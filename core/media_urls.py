"""Storage backend-dən asılı olmayan, tətbiq-RBAC-dan keçən media URL-ləri."""

from __future__ import annotations

import posixpath

from django.urls import reverse


def protected_media_url(value) -> str:
    """FieldFile/storage adını lokal ``protected_media`` route-una proyeksiya et."""

    name = str(getattr(value, "name", value) or "").replace("\\", "/").lstrip("/")
    clean = posixpath.normpath(name)
    if not name or clean in (".", "..") or clean.startswith("../"):
        return ""
    return reverse("protected_media", kwargs={"path": clean})


__all__ = ["protected_media_url"]
