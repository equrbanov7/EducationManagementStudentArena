"""
Teacher dashboard view (legacy URL → unified profile cabinet).

URL auditi A6 (2026-10-10): köhnə ``grading-queue/`` səhifəsi silindi — onu
kabinetin «Yoxlanılacaqlar» (`pending-review`) bölməsi əvəz edir.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def teacher_dashboard(request):
    """Legacy teacher dashboard URL; the unified profile cabinet is canonical."""
    return redirect("accounts:profile")
