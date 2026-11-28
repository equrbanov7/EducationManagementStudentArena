"""Hazırda açıq bölməyə uyğun, giriş hüququ olan təlimatın fəsli."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .._helpers import _load_user_profile, _role_capabilities
from .faq import faq_capabilities
from .faq_editor_catalog import resolve_entry
from .faq_tours import guide_url, tour_catalog, tour_key, tour_roles

EXTERNAL_GUIDES = {
    "external-journal": "missing-journal",
    "external-language": "language-cohort",
    "external-rooms": "room-monitor",
    "external-seals": "sealed-register",
}


@login_required
@never_cache
@require_safe
def section_help(request, section):
    profile, _ = _load_user_profile(request.user)
    caps = faq_capabilities(request, _role_capabilities(request.user, profile))
    allowed = caps["allowed_sections"]
    if section in allowed or section in EXTERNAL_GUIDES:
        for role in tour_roles(request):
            chapters = tour_catalog()[role]["sections"]
            group = request.GET.get("ss_group") if section == "system-settings" else None
            chapter = chapters.get(f"{section}-{group}") if group else None
            chapter = chapter or chapters.get(section)
            if chapter is None:
                continue
            key = tour_key(role)
            guide = resolve_entry(request, key, sections=allowed, capabilities=caps)
            if guide:
                start = next((c["start"] for c in guide.chapters if c["title"] == chapter), None)
                if start is not None:
                    return redirect(guide_url(key, start))
        key = EXTERNAL_GUIDES.get(section, "section-" + section)
        if resolve_entry(request, key, sections=allowed, capabilities=caps):
            return redirect(guide_url(key))
    return redirect(reverse("accounts:profile") + "?section=faq")
