"""Request-ömürlü aktiv üzvlük snapshot-u — ``OrganizationMiddleware`` → istehlakçılar.

NİYƏ (perf 2026-10-07): bir kabinet sorğusunda EYNİ ``Membership(user, aktiv
org, is_active=True)`` sətirləri 4–5 dəfə oxunurdu — middleware, unit-scope
(``scoping._permission_scope_memberships``), müraciət emalçısı yoxlaması
(``applications.services.access.active_memberships``), «Ana səhifə» rol adı
(``dashboard._role_label``). Middleware sətirləri artıq
``select_related("organization", "role", "scope_unit")`` ilə yükləyir; burada
onlar İSTEHLAKÇININ ÖZ CANLI SORĞUSU ilə EYNİ nəticəni verdiyi halda təkrar
istifadə olunur, əks halda ``None`` qaytarılır və istehlakçı canlı sorğuya düşür.

Eynilik müqaviləsi (istehlakçı sorğusu aktiv org = RLS tenant altında işləyir):

* snapshot YALNIZ superuser/superadmin OLMAYAN istifadəçi üçün bağlanır — onun
  sorğuları həmişə ``tenant = request.organization`` RLS-i altındadır;
* rolu başqa təşkilata aid sətir atılır (canlı sorğuda ``organizations_role``
  RLS-i INNER JOIN-i düşürür, ``role__organization=org`` süzgəci də eynidir);
* ``scope_unit``-i yüklənməmiş / başqa təşkilata aid sətir varsa snapshot
  BÜTÖVLÜKDƏ rədd edilir (canlı sorğuda LEFT JOIN həmin obyekti ``None`` edir);
* fərqli org, fərqli epoxa, açıq etibarsızlaşdırma → ``None``.

Köhnəlmə qoruması (cross-request keş YOXDUR — atribut ``request.user``
instansındadır, o isə hər request-də təzədən yaradılır; middleware hər çağırışda
əvvəlcə köhnə snapshot-u silir):

* ``Membership`` / ``Role`` / ``OrgUnit`` / ``Organization`` ``post_save`` /
  ``post_delete`` siqnalı proses-qlobal epoxanı artırır (``signals.py``) —
  snapshot oxunandan sonrakı istənilən ORM yazısı onu etibarsız edir;
* üzvlüyü ``QuerySet.update()`` ilə dəyişən yol (siqnal yoxdur) mövcud
  qayda ilə ``invalidate_permission_scope_cache(user)`` çağırır — o da
  snapshot-u silir.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

_SNAPSHOT_ATTR = "_org_request_membership_snapshot"
_epoch_source = itertools.count(1)
_epoch = 0


def membership_epoch() -> int:
    """Cari epoxa — middleware onu üzvlük oxusundan ƏVVƏL götürür."""
    return _epoch


def bump_membership_epoch(*_args, **_kwargs) -> None:
    """Üzvlük/rol/struktur yazısı oldu — bütün açıq snapshot-lar etibarsızdır.

    ``itertools.count`` CPython-da atomikdir: yarışan iki artım da epoxanı
    snapshot-un yadda saxladığı dəyərdən fərqli edir (fail-closed).
    """
    global _epoch
    _epoch = next(_epoch_source)


@dataclass(frozen=True)
class _Snapshot:
    organization_id: object
    rows: tuple
    epoch: int


def bind_request_memberships(user, organization, memberships, *, epoch: int) -> None:
    """Middleware: aktiv org-un TAM aktiv üzvlük siyahısını ``user``-ə bağla."""
    if user is None or organization is None or not memberships:
        return
    try:
        setattr(user, _SNAPSHOT_ATTR, _Snapshot(organization.pk, tuple(memberships), epoch))
    except Exception:  # noqa: BLE001 — dəyişməz user obyektləri (nadir)
        pass


def drop_request_memberships(user) -> None:
    """Snapshot-u sil — mutasiyadan sonra və hər middleware çağırışının əvvəlində."""
    try:
        if user is not None and getattr(user, _SNAPSHOT_ATTR, None) is not None:
            delattr(user, _SNAPSHOT_ATTR)
    except Exception:  # noqa: BLE001 — dəyişməz obyektlər üçün (nadir)
        pass


def _row_matches(membership, org_pk) -> bool | None:
    """``True`` — saxla; ``False`` — canlı sorğu da atır; ``None`` — snapshot yararsızdır."""
    from .models import Membership

    if not membership.is_active or membership.organization_id != org_pk:
        return None
    if not Membership.role.is_cached(membership) or not Membership.scope_unit.is_cached(membership):
        return None
    if membership.role.organization_id != org_pk:
        return False
    if membership.scope_unit_id is not None:
        unit = membership.scope_unit
        if unit is None or unit.organization_id != org_pk:
            return None
    return True


def request_active_memberships(user, organization) -> list | None:
    """``Membership(user, organization, is_active=True, role__organization=organization)``
    sətirləri (``role``/``scope_unit`` yüklü) middleware snapshot-undan; yararsızdırsa ``None``.

    Sıra middleware-inkidir (``-is_primary, -role__level``); fərqli sıra lazım
    olan istehlakçı özü sıralayır. Qaytarılan siyahı surətdir.
    """
    if user is None or organization is None:
        return None
    snapshot = getattr(user, _SNAPSHOT_ATTR, None)
    if snapshot is None:
        return None
    org_pk = getattr(organization, "pk", None)
    if org_pk is None or snapshot.organization_id != org_pk or snapshot.epoch != _epoch:
        return None
    rows = []
    for membership in snapshot.rows:
        verdict = _row_matches(membership, org_pk)
        if verdict is None:
            return None
        if verdict:
            rows.append(membership)
    return rows


__all__ = [
    "bind_request_memberships",
    "bump_membership_epoch",
    "drop_request_memberships",
    "membership_epoch",
    "request_active_memberships",
]
