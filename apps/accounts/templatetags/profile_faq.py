from django import template

from ..views.profile.faq import faq_capabilities, faq_page

register = template.Library()


@register.simple_tag(takes_context=True)
def profile_faq(context):
    if "faq" in context:
        return context["faq"]
    request = context["request"]
    return faq_page(
        request.GET,
        context["allowed_sections"],
        faq_capabilities(request, context["role_capabilities"]),
        request=request,
    )


@register.simple_tag(takes_context=True)
def cabinet_tour_links(context):
    from ..views.profile.faq_tours import guide_url, tour_catalog, tour_key, tour_roles

    request = context.get("request")
    if request is None:
        return ()
    allowed = context.get("faq", {}).get("allowed_guide_keys", ())
    return [
        {"label": tour_catalog()[role]["label"], "url": guide_url(tour_key(role))}
        for role in tour_roles(request)
        if tour_key(role) in allowed
    ]
