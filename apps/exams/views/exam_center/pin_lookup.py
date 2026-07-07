"""exam_center paketi — istifadəçi adı üzrə PIN axtarışı.

İmtahan mərkəzi bir istifadəçi adını (username) axtarır və həmin tələbənin bu
təşkilatdakı BÜTÜN final imtahan biletlərini görür: imtahan, otaq, oturum vaxtı
və PIN. PIN yalnız:
  * icazəli imtahan mərkəzi üçün (``center_org_or_403``);
  * hələ etibarlı (revoked/expired olmayan, şifrəli nüsxəsi qalan) biletlərdə
açılır. Hər açılış audit-ə yazılır. Xam PIN URL/log-a düşmür.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.exams.models import FinalExamTicket
from apps.exams.services.final_center import decrypt_ticket_pin
from core.audit import log_action
from core.constants import AuditAction

from ._shared import center_org_or_403

User = get_user_model()


@login_required
def exam_center_pin_lookup(request):
    organization = center_org_or_403(request)
    username = (request.GET.get("username") or "").strip()
    searched_user = None
    not_found = False
    results = []

    if username:
        searched_user = (
            User.objects.filter(username__iexact=username, profile__organization=organization).first()
            or User.objects.filter(username__iexact=username).first()
        )
        if searched_user is None:
            not_found = True
        else:
            tickets = (
                FinalExamTicket.objects.filter(organization=organization, student=searched_user)
                .select_related("exam", "session", "session__room")
                .order_by("-created_at")
            )
            revealed = 0
            for ticket in tickets:
                pin = decrypt_ticket_pin(ticket)
                if pin:
                    revealed += 1
                results.append({"ticket": ticket, "pin": pin})
            if revealed:
                log_action(
                    AuditAction.VIEW,
                    user=request.user,
                    organization=organization,
                    reason=f"final_center_pin_lookup[{searched_user.username}:{revealed}]",
                    request=request,
                    resource_type="final_exam_pin",
                )

    return render(
        request,
        "exams/exam_center/pin_lookup.html",
        {
            "organization": organization,
            "username": username,
            "searched_user": searched_user,
            "not_found": not_found,
            "results": results,
        },
    )


__all__ = ["exam_center_pin_lookup"]
