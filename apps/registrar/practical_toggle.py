"""«Praktiki məşğələ» bayrağının jurnaldan dəyişdirilməsi — kafedra müdiri və RİM (sahib 2026-10-28).

Bayraq YALNIZ görünüşdür (:mod:`apps.registrar.practical_label`): saxlanan dərs / slot növü ``seminar`` qalır, bal,
pay, yük və cədvəl dəyişmir. Ona görə qapı dardır, amma sənəd tələb olunmur:

* ``workload.distribute`` icazəsinin təşkilat əhatəsi — istənilən açılış;
* həmin icazənin struktur əhatəsi — açılışın KAFEDRASI
  (:func:`apps.registrar.offering_chairs.offering_chairs`) həmin alt-ağacda olmalıdır.

Kataloq konsolunda (RİM) eyni sahə açılış formasındadır (``OfferingForm``). Hər dəyişiklik auditə düşür.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from core.audit import log_action
from core.constants import AuditAction

from .journal_access import offering_or_404

_CTX = "registrar.practical"


def can_toggle(user, offering) -> bool:
    """Mərkəzi ``workload.distribute`` icazəsi və açılışın kafedra əhatəsi."""
    if offering is None or not getattr(user, "is_authenticated", False):
        return False
    from .journal_scope import permission_scope_for
    from .models import CourseOffering
    from .offering_chairs import offering_chairs

    scope = permission_scope_for(user, offering.organization, "workload.distribute")
    if not scope.has_structure_access:
        return False
    if scope.is_org_wide:
        return True
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    units = {
        str(unit_id)
        for unit_id in (
            OrgUnit.objects.filter(organization_id=offering.organization_id)
            .filter(scope.unit_subtree_q())
            .values_list("pk", flat=True)
        )
    }
    chairs = offering_chairs(CourseOffering.objects.filter(pk=offering.pk), offering.organization_id)
    return bool(units & set(chairs.get(offering.pk, ())))


def context(user, offering) -> dict | None:
    """Jurnal başlığındakı keçid (yalnız icazəlilər üçün); qalanlara ``None``."""

    if not can_toggle(user, offering):
        return None
    return {
        "on": bool(offering.seminar_is_practical),
        "url": reverse("registrar:journal_practical_toggle", args=[offering.pk]),
    }


@login_required
@require_POST
def toggle(request, offering_id):
    offering = offering_or_404(request, offering_id)
    if not can_toggle(request.user, offering):
        raise Http404
    wanted = request.POST.get("on") == "1"
    if offering.seminar_is_practical != wanted:
        old = offering.seminar_is_practical
        offering.seminar_is_practical = wanted
        offering.save(update_fields=["seminar_is_practical", "updated_at"])
        log_action(
            action=AuditAction.UPDATE,
            user=request.user,
            organization=offering.organization,
            obj=offering,
            reason="registrar: seminar görünüşü «Praktiki məşğələ» (yalnız etiket)",
            old_values={"seminar_is_practical": old},
            new_values={"seminar_is_practical": wanted},
            request=request,
        )
    if wanted:
        messages.success(request, pgettext(_CTX, "Seminar dərsləri bu jurnalda «Praktiki məşğələ» adlanır."))
    else:
        messages.success(request, pgettext(_CTX, "Seminar dərsləri yenidən «Seminar» adlanır."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


__all__ = ["can_toggle", "context", "toggle"]
