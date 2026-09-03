"""«Köçürülmüş nəticələrin dəqiqləşdirilməsi» bölməsinin AKTOR qapısı.

İKİ AYRI SƏLAHİYYƏT, QƏSDƏN AYRI SAXLANIR
-----------------------------------------
* ``final_score.entry`` — **qərar** vermək (təsdiq/mübahisə) və **düzəliş**
  yazmaq. Bu, ``LegacyGradeReview`` modelinin ÖZ qapısıdır
  (``LEGACY_GRADE_REVIEW_PERMISSION``) və ``exam_score_entry``-nin də qapısıdır,
  yəni səth başqa açar seçsəydi düymə görünər, əməl isə modeldə 403 alardı.
* ``journal.correct`` — auditli düzəliş səlahiyyəti (İKT rəhbəri). Bu açar
  növbəni **oxumağa** icazə verir, çünki düzəliş mədəniyyətinin sahibi odur;
  amma köhnə rəsmi balın **qərarını** o vermir.

Ona görə qapı iki bayraq qaytarır: ``can_view`` və ``can_review``. Yalnız
``journal.correct`` daşıyan aktor növbəni oxu rejimində görür və səth ona
«qərar səlahiyyətiniz yoxdur» qeydini AÇIQ göstərir — səssiz 403 yoxdur.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.registrar import legacy_grade_review as review_read
from apps.registrar.corrections import CORRECT_PERMISSION


@dataclass(frozen=True)
class LegacyReviewActor:
    """Sorğu üçün həll olunmuş dəqiqləşdirmə konteksti (fail-closed)."""

    user: object
    organization: object | None
    can_review: bool
    can_observe: bool
    is_superadmin: bool

    @property
    def has_access(self) -> bool:
        """Bölmə ümumiyyətlə açılırmı (oxu kifayətdir)."""
        return bool(self.organization is not None and (self.can_review or self.can_observe))


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def _has_correct_permission(user, organization) -> bool:
    """``journal.correct`` — yalnız OXU qapısı üçün."""
    from apps.accounts.views._helpers.rbac import _collect_actor_permissions
    from core.permissions import has_permission

    permissions, _grantable = _collect_actor_permissions(user, organization)
    return has_permission(list(permissions), CORRECT_PERMISSION)


def resolve_actor(request) -> LegacyReviewActor:
    """Sorğudan aktoru qurur; heç vaxt exception atmır."""
    from apps.accounts.views._helpers.tenant import _get_active_organization

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return LegacyReviewActor(user=None, organization=None, can_review=False, can_observe=False, is_superadmin=False)

    organization = _get_active_organization(request)
    if organization is None:
        return LegacyReviewActor(
            user=user, organization=None, can_review=False, can_observe=False, is_superadmin=_is_superadmin(user)
        )

    can_review = review_read.can_review(user, organization)
    # Qərar səlahiyyəti onsuz da oxunu əhatə edir; ayrıca sorğu atmırıq.
    can_observe = can_review or _has_correct_permission(user, organization)
    return LegacyReviewActor(
        user=user,
        organization=organization,
        can_review=can_review,
        can_observe=can_observe,
        is_superadmin=_is_superadmin(user),
    )


__all__ = ["LegacyReviewActor", "resolve_actor"]
