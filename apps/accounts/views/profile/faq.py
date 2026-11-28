"""Kabinetdə rol və icazə sahəsinə uyğun, səhifələnən təlimatlar."""

from dataclasses import dataclass

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
from .faq_featured import chapter_details, featured_player
from .faq_operational_access import operational_capabilities
from .faq_search import rank_guides
from .faq_search import search_words as search_words  # noqa: F401 (existing public import)
from .faq_tours import active_tour_roles, tour_capabilities, tour_catalog
from .faq_visibility import guide_allowed
from .section_assets import section_assets_payload

PAGE_SIZE = 5
RESULTS_TEMPLATE = "accounts/profile/sections/faq/_results.html"
PANEL_TEMPLATE = "accounts/profile/sections/_faq.html"


@dataclass
class _MatchedGuide:
    guide: object
    match_chapter: dict

    def __getattr__(self, name):
        return getattr(self.guide, name)


def faq_page(params, sections, capabilities, request=None, *, include_featured=True):
    query = params.get("faq_q", "").strip()[:120]
    selected = params.get("faq_guide", "")
    if request is None:
        guides = [g for g in GUIDES if guide_allowed(g, sections, capabilities)]
    else:
        guides = list_entries(request, sections=sections, capabilities=capabilities)
    allowed_guide_keys = frozenset(g.key for g in guides)
    candidates = [g for g in guides if g.key == selected] if selected else guides
    visible = candidates
    if query:
        visible = []
        for hit in rank_guides(candidates, query):
            guide = hit.guide
            if hit.chapter_start is not None:
                chapter = next((c for c in guide.chapters if c["start"] == hit.chapter_start), None)
                if chapter:
                    guide = _MatchedGuide(guide, chapter_details(chapter))
            visible.append(guide)
    page = Paginator(visible, PAGE_SIZE).get_page(params.get("faq_page"))
    numbers = page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    start, requested_chapter = 0, False
    if selected and visible:
        guide = visible[0]
        try:
            asked = float(params.get("faq_at", ""))
        except (TypeError, ValueError):
            asked = None
        requested_chapter = any(c["start"] == asked for c in guide.chapters)
        start = asked if requested_chapter else guide.start
    featured = None
    if include_featured:
        roles = (
            active_tour_roles(request)
            if request is not None
            else {r: d["label"] for r, d in tour_catalog().items() if capabilities.get("tour_member_" + r)}
        )
        featured = featured_player(guides, roles, ", ".join(dict.fromkeys(roles.values())))
    return {
        "allowed_guide_keys": allowed_guide_keys,
        "query": query,
        "page": page,
        "numbers": tuple(numbers),
        "can_manage_videos": bool(request and can_manage_videos(request)),
        "selected": selected,
        "chapter_start": start,
        "requested_chapter": requested_chapter,
        "featured": featured,
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
    results_only = request.GET.get("faq_results") == "1"
    context = {
        "active_section": "faq",
        "role_capabilities": capabilities,
        "profile_base_url": reverse("accounts:profile"),
        "faq": faq_page(request.GET, sections, capabilities, request=request, include_featured=not results_only),
    }
    if results_only:
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
