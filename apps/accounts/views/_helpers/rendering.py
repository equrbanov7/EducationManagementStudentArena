"""
Profile shell rendering helper.

Re-renders the profile page with a specific section active. The ``user_profile``
import is deferred to function scope to avoid a circular import.
"""


def _render_profile_section(request, section):
    """
    Render the profile shell with a specific section active while preserving filters.
    """
    request.direct_profile_section = section
    request.GET = request.GET.copy()
    request.GET["section"] = section
    from ..profile import user_profile

    return user_profile(request)
