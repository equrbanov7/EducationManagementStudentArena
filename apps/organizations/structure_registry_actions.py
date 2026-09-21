"""Fakültələr / Kafedralar kabinet reyestri — JSON əməl endpoint-ləri (2026-09-08).

Sahib istəyi: fakültəyə DEKAN, DEKAN MÜAVİNİ və PROQRAM KOORDİNATORU, kafedraya
KAFEDRA MÜDİRİ və MÜƏLLİM təyin etmək; vahidi yaratmaq / redaktə etmək /
arxivləmək — hamısı kabinetin içində, səhifə yenilənmədən (`teaching_office.js`
formanı JSON POST edir, cavabdan sonra bölmə fraqmenti yenidən yüklənir).

Üç endpoint:

* ``structure_unit_action`` (POST) — ``action`` açarı ilə tək giriş nöqtəsi:
  ``save_unit`` · ``archive_unit`` · ``assign_head`` · ``add_role`` ·
  ``add_teacher`` · ``remove_role``;
* ``structure_unit_staff`` (GET) — «Heyət» çekmecəsi üçün vahidin rəhbəri, rol
  qrupları və alt bölmələri (JSON);
* ``structure_role_candidates`` (GET) — axtarışlı seçici (`EMSSearchableSelect`)
  üçün namizədlər: ``kind=staff`` (rəhbər/müavin/koordinator — idarəetmə
  səviyyəli aktiv üzvlər) və ``kind=teacher`` (müəllim üzvlükləri).

QAPILAR (fail-closed, RBAC kataloqu ilə eyni açarlar):

* baxış/əhatə — ``unit.view`` (``tree_scope``; dekan yalnız öz fakültəsini görür);
* yaratma/redaktə/arxiv — ``unit.create`` / ``unit.edit`` / ``unit.delete``;
* rəhbər (dekan/müdir) — ``unit.assign_head`` VƏ YA ``member.edit``;
* müavin/koordinator/müəllim — ``member.edit``.

TƏLƏBƏ QORUMASI: aktiv akademik qeydi və ya tələbə rolu olan hesaba heç bir
heyət rolu verilmir (sahib, 2026-09-07) — 409 ``target_is_student``.

RƏHBƏR = ROL: dekan/müdir təyinatı ``OrgUnit.head``-i yazmaqla yanaşı həmin
vahidə əhatəli ``dean`` / ``chair_head`` üzvlüyünü də yaradır (varsa aktivləşdirir);
əvvəlki rəhbərin eyni vahiddəki rol üzvlüyü deaktiv edilir ki, köhnə dekan
fakültə üzərində icazə saxlamasın. Hər əməl auditə düşür.

MODUL BÖLGÜSÜ (2026-09-21, modul-ölçü qapısı): ortaq köməkçilər
``structure_registry_helpers.py``, əməl işləyiciləri
``structure_registry_unit_actions.py``, çekmecə/namizəd endpoint-ləri
``structure_registry_lookups.py``-dadır; bu modul dispetçeri saxlayır və
endpoint-ləri yenidən ixrac edir (``urls.py`` dəyişmir).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from .models import Organization
from .structure_registry_helpers import (  # noqa: F401 — yenidən ixrac
    ARCHIVE_REASON_MIN,
    CANDIDATE_MAX_PAGE_SIZE,
    CANDIDATE_PAGE_SIZE,
    REGISTRY_UNIT_TYPES,
    _error,
    _forbidden,
)
from .structure_registry_lookups import structure_role_candidates, structure_unit_staff  # noqa: F401
from .structure_registry_unit_actions import _HANDLERS
from .structure_views.registry import registry_flags
from .structure_views.tree import tree_scope

# i18n skaneri kontekst sabitini MODUL daxilində axtarır — yerli təyin.
_CTX = "organizations.registry"


@login_required
@require_POST
def structure_unit_action(request, slug):
    """Fakültə/kafedra reyestri əməlləri — tək JSON endpoint."""
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = tree_scope(request, organization)
    if not scope.has_structure_access:
        return _forbidden(pgettext(_CTX, "Struktur əhatəniz yoxdur."))
    handler = _HANDLERS.get((request.POST.get("action") or "").strip())
    if handler is None:
        return _error(pgettext(_CTX, "Naməlum əməl."), code="unknown_action")
    return handler(request, organization, scope, registry_flags(request, organization))


__all__ = ["structure_unit_action", "structure_unit_staff", "structure_role_candidates", "ARCHIVE_REASON_MIN"]
