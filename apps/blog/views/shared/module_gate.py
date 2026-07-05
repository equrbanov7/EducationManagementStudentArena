"""Postlar modulunun URL-səviyyəli qapısı (U20).

Kabinet "posts" modulu bağlıykən (susmaya görə bağlıdır) blog post/kateqoriya
view-larına birbaşa URL ilə də girmək mümkün olmur — 404. Superadmin üçün də
keçərlidir: modulu yalnız superadmin org-features panelindən açandan sonra
səhifələr işləyir ("URL ilə yazılsa da girməsin" tələbi).

UNIVERSITY_MODE-da aktiv təşkilat konteksti olmayan (anonim) sorğular da
bağlanır; adi (marketing) rejimdə org-suz sorğulara toxunulmur.
"""

from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.http import Http404


def posts_enabled_for(request) -> bool:
    organization = getattr(request, "organization", None)
    if organization is None:
        return not getattr(settings, "UNIVERSITY_MODE", True)
    from apps.organizations.cabinet_modules import is_module_enabled

    return is_module_enabled(organization, "posts")


def posts_module_required(view):
    """View dekoratoru: modul bağlıdırsa 404 (heç kimə istisna yoxdur)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not posts_enabled_for(request):
            raise Http404("Postlar modulu bu təşkilat üçün bağlıdır.")
        return view(request, *args, **kwargs)

    return wrapper
