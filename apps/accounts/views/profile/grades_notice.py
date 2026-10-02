"""Parol bərpasından sonrakı ilk girişdə «köçürülmüş ballar» xəbərdarlığının təsdiqi (sahib 2026-10-02).

Modal kabinetdə ``UserProfile.grades_notice_pending`` qalxıqdırsa göstərilir (tələbələrə); «Başa düşdüm»
bu endpoint-ə POST edir və bayraq endirilir — xəbərdarlıq bir daha çıxmır.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST


@login_required
@require_POST
def grades_notice_ack(request):
    profile = getattr(request.user, "profile", None)
    if profile is not None and profile.grades_notice_pending:
        profile.grades_notice_pending = False
        profile.save(update_fields=["grades_notice_pending", "updated_at"])
    return JsonResponse({"ok": True})


__all__ = ["grades_notice_ack"]
