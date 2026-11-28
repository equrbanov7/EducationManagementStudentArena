"""Kabinetdə rol və icazə sahəsinə uyğun, səhifələnən təlimatlar."""

import re
import unicodedata
from functools import lru_cache

from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_safe

from apps.applications.public import can_create_support_application
from apps.organizations.public import can_manage_journal_watch
from apps.registrar.public import language_cohort_navigation

from .._helpers import _load_user_profile, _role_capabilities
from .faq_academic_access import academic_capabilities
from .faq_catalog import GUIDES, PUBLIC_LOGIN_GUIDES
from .faq_editor_catalog import can_manage_videos, list_entries
from .faq_operational_access import operational_capabilities
from .faq_tours import tour_capabilities
from .faq_visibility import guide_allowed
from .section_assets import section_assets_payload

PAGE_SIZE = 5
RESULTS_TEMPLATE = "accounts/profile/sections/faq/_results.html"
PANEL_TEMPLATE = "accounts/profile/sections/_faq.html"


def search_words(value):
    value = unicodedata.normalize("NFKD", value.casefold().replace("ə", "e").replace("ı", "i"))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.findall(r"[^\W_]+", value, re.UNICODE)


def _search_text(guide):
    chapter_titles = (c["title"] for c in guide.chapters)
    return " ".join(search_words(" ".join((guide.title, guide.topic, guide.aliases, *guide.steps, *chapter_titles))))


@lru_cache(maxsize=1)
def _builtin_search():
    return {g.key: (g, _search_text(g)) for g in GUIDES}


def faq_page(params, sections, capabilities, request=None):
    query = params.get("faq_q", "").strip()[:120]
    terms = search_words(query)
    if request is None:
        guides = [g for g in GUIDES if guide_allowed(g, sections, capabilities)]
    else:
        guides = list_entries(request, sections=sections, capabilities=capabilities)
    allowed_guide_keys = frozenset(g.key for g in guides)
    visible = []
    for guide in guides:
        if params.get("faq_guide") and guide.key != params["faq_guide"]:
            continue
        if terms:
            item = _builtin_search().get(guide.key)
            text = item[1] if item and item[0] is guide else _search_text(guide)
            if not all(term in text for term in terms):
                continue
        visible.append(guide)
    page = Paginator(visible, PAGE_SIZE).get_page(params.get("faq_page"))
    numbers = page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    selected = params.get("faq_guide", "")
    start = 0
    if selected and visible:
        guide = visible[0]
        try:
            asked = float(params.get("faq_at", ""))
        except (TypeError, ValueError):
            asked = None
        start = next((c["start"] for c in guide.chapters if c["start"] == asked), guide.start)
    return {
        "allowed_guide_keys": allowed_guide_keys,
        "query": query,
        "page": page,
        "numbers": tuple(numbers),
        "can_manage_videos": bool(request and can_manage_videos(request)),
        "selected": selected,
        "chapter_start": start,
    }


def faq_capabilities(request, capabilities, required=None):
    result = dict(capabilities)
    if required is None or "faq_manage_journal_watch" in required:
        result["faq_manage_journal_watch"] = "journal-watch" in capabilities[
            "allowed_sections"
        ] and can_manage_journal_watch(request)
    if required is None or any(flag.startswith("tour_member_") for flag in required):
        result.update(tour_capabilities(request))
    if required is None or "can_manage_faq_videos" in required:
        result["can_manage_faq_videos"] = can_manage_videos(request)
    if required is None or required.intersection({"can_view_language_cohorts", "can_manage_language_cohorts"}):
        groups = language_cohort_navigation(request, capabilities)
        result.update(can_view_language_cohorts=groups["visible"], can_manage_language_cohorts=groups["staff"])
    if required is None or "can_create_support" in required:
        result["can_create_support"] = "applications" in capabilities[
            "allowed_sections"
        ] and can_create_support_application(request.user, getattr(request, "organization", None))
    result.update(academic_capabilities(request, capabilities, required))
    result.update(operational_capabilities(request, capabilities, required))
    return result


def faq_fragment(request):
    # FAQ sorğusu yalnız kabinetin mövcud icazələrini və statik təlimatları oxuyur.
    profile, _ = _load_user_profile(request.user)
    capabilities = faq_capabilities(request, _role_capabilities(request.user, profile))
    sections = capabilities["allowed_sections"]
    if "faq" not in sections:
        return JsonResponse({"ok": False, "error": "forbidden_or_unknown_section"}, status=403)
    context = {
        "active_section": "faq",
        "role_capabilities": capabilities,
        "profile_base_url": reverse("accounts:profile"),
        "faq": faq_page(request.GET, sections, capabilities, request=request),
    }
    if request.GET.get("faq_results") == "1":
        return HttpResponse(render_to_string(RESULTS_TEMPLATE, context))
    return JsonResponse(
        {
            "ok": True,
            "section": "faq",
            "html": render_to_string(PANEL_TEMPLATE, context, request=request),
            "assets": section_assets_payload("faq", sections),
            "extract_selector": '[data-profile-section-panel="faq"]',
        }
    )


@require_safe
def login_help(request):
    guides = [guide for guide in GUIDES if guide.key in PUBLIC_LOGIN_GUIDES]
    return render(
        request,
        "accounts/login_help.html",
        {"faq": {"page": Paginator(guides, PAGE_SIZE).page(1), "media_route": "accounts:faq_public_media"}},
    )
