"""Özü yazılmış (təsdiqlənməmiş) FİN və rəsmi idxal — sahib 2026-10-17, SEC-1 F2 (tövsiyə olunan variant).

«Məlumatlarınızı tamamlayın» səhifəsində yazılan FİN ``UserProfile.fin_self_reported=True`` ilə saxlanılır. FİN
qlobal unikaldır, ona görə başqasının FİN-ini (və ya səhv yazılmış FİN-i) tutan hesab əvvəllər rəsmi ATİS / kadr
idxalında əsl sahibin sətrini «Bu FİN artıq sistemdə var» deyə ötürdürdü. İndi:

* ad + soyad UYĞUNDUR → eyni adamdır: sətir əvvəlki kimi ötürülür, FİN isə rəsmi mənbə ilə TƏSDİQLƏNİR
  (bayraq düşür) — ``confirm_matching_claims``;
* ad + soyad FƏRQLİDİR → rəsmi mənbə üstündür: sətir yaradılır, FİN həmin anda (eyni savepoint-də) özü yazan
  hesabdan GÖTÜRÜLÜR — ``release_claim``; o hesabın qapısı FİN-i yenidən soruşur, audit-ə yalnız sahə adı düşür.

Ön baxış (``build_plans``) heç nə yazmır — yalnız ``load_claims`` oxuyur. FİN / ad DƏYƏRLƏRİ audit-ə yazılmır.
"""

from __future__ import annotations

import logging

from django.utils.translation import pgettext

from apps.audit.public import log_action
from core.constants import AuditAction

from ..teacher_roster.parsing import key as name_key

logger = logging.getLogger(__name__)

_CTX = "student_intake"

PLAN_RELEASE_KEY = "release_self_reported_fin_from"
CODE_SELF_REPORTED_MATCH = "fin_exists_self_reported_match"
AUDIT_REASON_RELEASED = "fin_self_reported_released"
AUDIT_REASON_CONFIRMED = "fin_self_reported_confirmed"


def load_claims(fins) -> dict:
    """``{fin: (user_id, first_name, last_name)}`` — yalnız özü yazılmış FİN-lər üçün (oxu)."""
    from ...models import UserProfile

    fins = [fin for fin in fins if fin]
    if not fins:
        return {}
    rows = UserProfile.objects.filter(fin__in=fins, fin_self_reported=True).values_list(
        "fin", "user_id", "user__first_name", "user__last_name"
    )
    return {fin: (user_id, first or "", last or "") for fin, user_id, first, last in rows}


def _name_keys(text: str) -> set:
    """«Məmmədova» latın klaviaturasında həm «Memmedova», həm «Mammadova» yazılır — hər iki açar."""
    return {name_key(text), name_key(str(text or "").replace("ə", "a").replace("Ə", "A"))} - {""}


def same_person(claim, first_name: str, last_name: str) -> bool:
    _user_id, first, last = claim
    return bool(_name_keys(first) & _name_keys(first_name)) and bool(_name_keys(last) & _name_keys(last_name))


def resolve(plan, claim, first_name: str, last_name: str) -> bool:
    """FİN özü yazılmış hesabdadır. ``True`` → sətir yaradılmağa davam edir (FİN götürüləcək)."""
    if same_person(claim, first_name, last_name):
        plan.skip(
            CODE_SELF_REPORTED_MATCH,
            pgettext(_CTX, "Bu FİN artıq sistemdə var (sahibi özü daxil edib, ad-soyad uyğundur) — FİN təsdiqlənir."),
        )
        plan.targets["confirm_fin_user_id"] = claim[0]
        return False
    plan.values[PLAN_RELEASE_KEY] = claim[0]
    plan.warnings.append(
        pgettext(
            _CTX,
            "Bu FİN-i başqa adlı hesab özü daxil edib (təsdiqlənməyib) — rəsmi sətir üstündür: FİN o hesabdan "
            "götürüləcək, sahibi FİN-i yenidən yazacaq.",
        )
    )
    return True


def _audit(user, *, actor, organization, request, reason: str) -> None:
    try:
        log_action(
            action=AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=user,
            reason=reason,
            changes={"fields": ["fin"]},
            request=request,
            resource_type="User",
            resource_id=str(user.pk),
            resource_repr=user.username,
        )
    except Exception:  # noqa: BLE001 — audit xətası idxalı dayandırmamalıdır
        logger.exception("fin claim audit failed")


def release_claim(values: dict, *, actor, organization, request=None) -> None:
    """Rəsmi sətir yaradılmazdan ƏVVƏL (eyni savepoint-də) özü yazılmış FİN-i köhnə hesabdan götürür."""
    from django.contrib.auth import get_user_model

    from ...models import UserProfile

    user_id = values.pop(PLAN_RELEASE_KEY, None)
    if not user_id:
        return
    profile = (
        UserProfile.objects.select_for_update()
        .select_related("user")
        .filter(user_id=user_id, fin=values.get("fin"), fin_self_reported=True)
        .first()
    )
    if profile is None:  # ön baxışdan sonra vəziyyət dəyişib — unikal indeks yenə qoruyur
        return
    profile.fin = None
    profile.fin_self_reported = False
    profile.profile_completed_at = None
    profile.save(update_fields=["fin", "fin_self_reported", "profile_completed_at", "updated_at"])
    user = profile.user if profile.user_id else get_user_model().objects.get(pk=user_id)
    _audit(user, actor=actor, organization=organization, request=request, reason=AUDIT_REASON_RELEASED)


def confirm_matching_claims(plans, *, actor, organization, request=None) -> int:
    """Ad-soyadı uyğun gələn özü yazılmış FİN-ləri rəsmi mənbə ilə təsdiqləyir (bayraq düşür)."""
    from ...models import UserProfile

    done = 0
    for plan in plans:
        if plan.code != CODE_SELF_REPORTED_MATCH:
            continue
        user_id = plan.targets.get("confirm_fin_user_id")
        profile = (
            UserProfile.objects.select_related("user")
            .filter(user_id=user_id, fin=plan.fin, fin_self_reported=True)
            .first()
        )
        if profile is None:
            continue
        profile.fin_self_reported = False
        profile.save(update_fields=["fin_self_reported", "updated_at"])
        _audit(profile.user, actor=actor, organization=organization, request=request, reason=AUDIT_REASON_CONFIRMED)
        done += 1
    return done


__all__ = [
    "AUDIT_REASON_CONFIRMED",
    "AUDIT_REASON_RELEASED",
    "CODE_SELF_REPORTED_MATCH",
    "PLAN_RELEASE_KEY",
    "confirm_matching_claims",
    "load_claims",
    "release_claim",
    "resolve",
]
