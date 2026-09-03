"""İmtahan Mərkəzi — «İmtahan balının daxil edilməsi» (profil bölməsi).

SAHİBİN QƏRARI (2026-08): yazılı və praktiki imtahan kağız üzərində (praktikidə
kodda) keçir — sistemdən getmir. Balları sonradan İmtahan Mərkəzi köçürür:
dövr (tədris ili + semestr) → fənn → QRUP (açılış) → tələbə siyahısı → formada
bir-bir bal + (opsional) imtahan vərəqinin şəkli/PDF-i və mətn qeydi.

POST bölməyə redirect edir; GET ``_render_profile_section`` ilə profil bölməsini
render edir (``journal_close`` / ``kollokvium_windows`` pattern-i).

İcazə qapısı: ``final_score.entry`` (bax ``apps/registrar/exam_score_entry.py``).
Sətir-sətir yazı servis qatındadır — orada ilk daxiletmə sərbəst, SONRAKI
dəyişiklik isə səbəb + qeyd + sənəd tələb edir.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext

from apps.registrar import exam_score_entry as service
from apps.registrar.models import CourseOffering

from ._helpers import (
    _append_query_params,
    _get_active_organization,
    _is_superadmin_user,
    _render_profile_section,
    _resolve_next_url,
)

logger = logging.getLogger(__name__)

_CTX = "accounts.exam_score_entry"

SECTION = "exam-score-entry"


class ExamScoreEntryError(Exception):
    """Bölmənin istifadəçi-üzlü xətası (dispatcher-də tutulur)."""


def _can_manage(user, organization):
    """`final_score.entry` icazəsi + superadmin bypass."""
    if not getattr(user, "is_authenticated", False):
        return False
    if _is_superadmin_user(user):
        return True
    if organization is None:
        return False
    return service.can_enter_exam_scores(user, organization)


def _resolve_target_org(request):
    """Bu sorğunun idarə etdiyi təşkilat (superadmin: ?ese_org / POST organization_id)."""
    from apps.organizations.models import Organization

    if _is_superadmin_user(request.user):
        org_id = (request.POST.get("organization_id") or request.GET.get("ese_org") or "").strip()
        if org_id:
            return Organization.objects.filter(pk=org_id).first()
        return Organization.objects.filter(is_active=True).order_by("name").first()
    return _get_active_organization(request)


@login_required
def exam_score_entry(request):
    """İmtahan balının daxil edilməsi (profil SPA bölməsi)."""
    organization = _resolve_target_org(request) if request.method == "POST" else _get_active_organization(request)
    if not _can_manage(request.user, organization or _get_active_organization(request)):
        return HttpResponseForbidden(
            pgettext(_CTX, "Bu bölmə yalnız imtahan balı daxil etmə səlahiyyəti olanlar üçündür.")
        )

    fallback_next = _append_query_params(reverse("accounts:profile"), section=SECTION)

    if request.method == "POST":
        next_url = _resolve_next_url(request, fallback_next)
        # `_resolve_next_url` onsuz da same-origin yoxlayır; yoxlama BURADA da
        # təkrarlanır ki, statik analiz (CodeQL `py/url-redirection`) sanitizer-i
        # redirect nöqtəsinin ÖZ funksiyasında görsün. Davranış dəyişmir —
        # `fallback_next` `reverse()`-dən gəlir, yəni həmişə daxili URL-dir.
        if not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            next_url = fallback_next
        if organization is None:
            messages.error(request, pgettext(_CTX, "Təşkilat konteksti tapılmadı."))
            return redirect(next_url)
        try:
            next_url = _handle_save(request, organization, next_url)
        except (ExamScoreEntryError, PermissionDenied) as exc:
            messages.error(request, str(exc) or pgettext(_CTX, "Bu əməliyyat üçün icazəniz yoxdur."))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect(next_url)

    return _render_profile_section(request, SECTION)


def _offering_or_error(request, organization):
    offering_id = (request.POST.get("offering_id") or "").strip()
    offering = (
        CourseOffering.objects.filter(organization=organization, pk=offering_id)
        .select_related("subject", "period", "group")
        .first()
        if offering_id
        else None
    )
    if offering is None:
        raise ExamScoreEntryError(pgettext(_CTX, "Fənn açılışı tapılmadı."))
    return offering


def _collect_rows(request):
    """POST açarlarından sətir siyahısı: ``score__<enr>`` + eyni sonluqlu köməkçilər."""
    rows = []
    for key, raw in request.POST.items():
        if not key.startswith("score__"):
            continue
        enrollment_id = key[len("score__") :]
        rows.append(
            {
                "enrollment_id": enrollment_id,
                "score": raw,
                "reason": request.POST.get(f"reason__{enrollment_id}", ""),
                "note": request.POST.get(f"note__{enrollment_id}", ""),
                "evidence": request.FILES.get(f"evidence__{enrollment_id}"),
            }
        )
    return rows


def _handle_save(request, organization, next_url):
    """Toplu yadda saxlama — sətirlər servis qatında bir-bir yazılır."""
    action = (request.POST.get("action") or "").strip()
    if action != "save_scores":
        raise ExamScoreEntryError(pgettext(_CTX, "Naməlum əməliyyat."))

    offering = _offering_or_error(request, organization)
    # Unit-scoped aktor (dekan/kafedra müdiri `exam.*` ilə) yalnız öz alt-ağacına
    # yaza bilər — servis qatında fail-closed yoxlanır.
    if not _is_superadmin_user(request.user):
        service.assert_offering_in_actor_scope(request.user, organization, offering)
    result = service.save_roster_scores(
        offering=offering,
        rows=_collect_rows(request),
        by_user=request.user,
        request=request,
    )

    if result["written"]:
        messages.success(request, _written_message(result["written"], result["skipped"]))
    elif not result["errors"]:
        messages.info(request, pgettext(_CTX, "Dəyişiklik yoxdur — heç bir bal yenilənmədi."))
    for student_name, problem in result["errors"]:
        messages.error(request, f"{student_name}: {problem}")

    return _append_query_params(
        next_url,
        ese_offering=str(offering.pk),
    )


def _written_message(written, skipped):
    """Nəticə mesajı — msgid-lərdə `%` yoxdur (i18n qapısı tələbi)."""
    head = pgettext(_CTX, "bal yazıldı")
    tail = pgettext(_CTX, "sətir dəyişmədi")
    if not skipped:
        return f"{written} {head}."
    return f"{written} {head} · {skipped} {tail}."


__all__ = ["exam_score_entry"]
