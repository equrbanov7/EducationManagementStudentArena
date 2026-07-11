"""Profil view-i — nazik HTTP giriş nöqtəsi.

Bütün context-yığımı ``context_builder.build_profile_response``-dədir (view/logika
ayrılığı — SoC). Bax: docs/architecture/REFACTOR_PLAN_profile_main.md (Mərhələ A).
"""

from django.contrib.auth.decorators import login_required

from .context_builder import build_profile_response


@login_required
def user_profile(request):
    return build_profile_response(request)
