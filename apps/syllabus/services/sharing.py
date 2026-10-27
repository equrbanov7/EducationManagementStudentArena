"""BİR sillabus — bir neçə jurnal (sahib 2026-10-27): qaydalar, oxu və yazı.

Sahib: «müəllim istəsə eynisini istifadə etsin eyni qrupa öz yerində; köhnədən gələndə elə olsun — bir sillabus.
Əgər müəllim eyni sillabusu 2 qrup və s. üçün də istifadə edibsə əvvəl, elə də olsun (məsələn potok dərsləri)».

Model :class:`apps.syllabus.models.SyllabusShare`-dir: dosye öz açılışında qalır, əlavə açılış (jurnal) ona
SURƏTSİZ bağlanır — məzmun, versiyalar, təsdiq, tamamlanma faizi və həftəlik plan BİRDİR.  Bu, 2026-10-08-in
«bağla» (``reused_from``) əməlindən fərqlidir: orada hədəfə ayrıca dosye + eyni məzmunun nüsxəsi yazılır.

QAYDALAR
========
1. **Yalnız öz sillabusu** (sahib 2026-10-27): mənbənin müəllifi (və ya öz açılışının müəllimi) aktorun özüdür;
   hədəf açılışın müəllimi də aktordur.  Həmkarın sillabusu paylaşılmır.
2. **Eyni fənn + eyni semestr** — mənbə açılışlı, semestrli, aktiv KÖK dosyedir (bağlı nüsxə deyil).
3. **Yalnız boş jurnal** — hədəf açılışın öz dosyesi və ya başqa paylaşımı varsa YAZILMIR (fill-only).
4. **Tətbiq qapısı** (oxu tərəfi) — paylaşım yalnız açılışın CARİ müəllimi dosyenin müəllifi və ya öz açılışının
   müəllimi olanda görünür (:func:`effective_shares`).  Fənn başqa müəllimə təhvil veriləndə yeni müəllim köhnə
   müəllimin sillabusunu «öz sillabusu» kimi görmür.
5. **Açılışın öz dosyesi üstündür** — ``syllabus_for_offering``: öz → paylaşılan → fənn+semestr → baza.  Öz dosye
   yaradılanda (``create_draft``) paylaşım silinir (:func:`release_offering`).

Modul ``apps.registrar``-ı İDXAL ETMİR — açılış obyektindən yalnız ``pk``, ``organization_id``, ``subject_id``,
``period_id``, ``instructor_id`` oxunur.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import F, Q

from core.audit import log_action
from core.constants import AuditAction

from ..constants import PERM_EDIT
from ..models import ShareSource, Syllabus, SyllabusShare
from ..state_machine import TransitionDenied
from .reuse_rules import CODE_NOT_OWN, CODE_NOT_SIBLING
from .scoping import is_author

CODE_HAS_OWN = "share.target_has_own"
CODE_TAKEN = "share.target_taken"
CODE_ALREADY = "share.already"
CODE_NOT_SHARED = "share.not_shared"

REASON_CODES = (CODE_HAS_OWN, CODE_TAKEN, CODE_ALREADY, CODE_NOT_SHARED)

RESOURCE_TYPE = "syllabus.share"


def _guard_q() -> Q:
    """Qayda 4: açılışın müəllimi = dosyenin müəllifi və ya dosyenin öz açılışının müəllimi."""
    return Q(offering__instructor_id=F("syllabus__author_id")) | Q(
        offering__instructor_id=F("syllabus__offering__instructor_id")
    )


def effective_shares():
    """QÜVVƏDƏ olan paylaşımlar — aktiv dosye + tətbiq qapısı (qayda 4)."""
    return SyllabusShare.objects.filter(syllabus__is_active=True).filter(_guard_q())


def shared_syllabus_ids(offering_ids) -> dict:
    """``{offering_id: syllabus_id}`` — qüvvədə olan paylaşımlar (TƏK sorğu)."""
    ids = [pk for pk in offering_ids if pk is not None]
    if not ids:
        return {}
    return dict(effective_shares().filter(offering_id__in=ids).values_list("offering_id", "syllabus_id"))


def shares_of(syllabus):
    """Dosyeni öz yerində istifadə edən açılışlar (qüvvədə olanlar) — qrup adları ilə."""
    if syllabus is None:
        return SyllabusShare.objects.none()
    return (
        effective_shares()
        .filter(syllabus=syllabus)
        .select_related("offering", "offering__group")
        .order_by("offering__group__name", "created_at")
    )


def share_counts(syllabus_ids) -> dict:
    """``{syllabus_id: say}`` — siyahı sətirləri üçün (TƏK sorğu)."""
    from django.db.models import Count

    ids = [pk for pk in syllabus_ids if pk is not None]
    if not ids:
        return {}
    rows = effective_shares().filter(syllabus_id__in=ids).values("syllabus_id").annotate(total=Count("pk"))
    return {row["syllabus_id"]: row["total"] for row in rows}


# ── Qaydalar ───────────────────────────────────────────────────────────────────


def _same_slot(source, offering) -> bool:
    return (
        source.is_active
        and source.reused_from_id is None
        and source.offering_id is not None
        and source.period_id is not None
        and source.offering_id != offering.pk
        and source.organization_id == offering.organization_id
        and source.subject_id == offering.subject_id
        and source.period_id == offering.period_id
    )


def target_code(offering, *, syllabus_id=None) -> str:
    """Hədəf açılış boşdurmu (qayda 3): öz dosyesi / başqa paylaşımı varsa səbəb kodu."""
    # Passiv (``is_active=False``) dosye jurnalda görünmür — paylaşıma mane deyil (resolver ilə eyni qayda).
    if Syllabus.objects.filter(
        organization_id=offering.organization_id, offering_id=offering.pk, is_active=True
    ).exists():
        return CODE_HAS_OWN
    current = SyllabusShare.objects.filter(offering_id=offering.pk).values_list("syllabus_id", flat=True).first()
    if current is None:
        return ""
    return CODE_ALREADY if syllabus_id is not None and current == syllabus_id else CODE_TAKEN


def share_code(source, *, actor, offering, state_code=None) -> str:
    """Paylaşmanın qadağa səbəbi (``""`` — olar). ``state_code`` — :func:`target_code` əvvəlcədən hesablanıbsa."""
    if not actor.has(PERM_EDIT):
        return "transition.permission_denied"
    if not is_author(actor, source):
        return CODE_NOT_OWN
    if not _same_slot(source, offering):
        return CODE_NOT_SIBLING
    if offering.instructor_id is None or offering.instructor_id != actor.user_id:
        return "transition.author_only"
    return target_code(offering, syllabus_id=source.pk) if state_code is None else state_code


# ── Yazı ────────────────────────────────────────────────────────────────────────


def _audit(share, *, action, user=None, request=None, source=""):
    log_action(
        action,
        user=user,
        organization=share.organization,
        obj=share,
        request=request,
        resource_type=RESOURCE_TYPE,
        resource_id=str(share.pk),
        resource_repr=f"{share.syllabus_id} → {share.offering_id}",
        new_values=(
            {"syllabus": str(share.syllabus_id), "offering": str(share.offering_id), "source": source or share.source}
            if action == AuditAction.CREATE
            else None
        ),
        old_values=(
            {"syllabus": str(share.syllabus_id), "offering": str(share.offering_id), "source": share.source}
            if action == AuditAction.DELETE
            else None
        ),
    )


@transaction.atomic
def share(*, source, offering, actor, request=None):
    """«Eyni sillabusu bu qrupda da istifadə et» — müəllimin seçimi (qaydalar 1–3)."""
    Syllabus.objects.select_for_update(of=("self",)).filter(pk=source.pk).first()
    code = share_code(source, actor=actor, offering=offering)
    if code:
        raise TransitionDenied(code)
    try:
        with transaction.atomic():
            row = SyllabusShare.objects.create(
                organization_id=source.organization_id,
                syllabus=source,
                offering_id=offering.pk,
                source=ShareSource.TEACHER,
                created_by=actor.user,
            )
    except IntegrityError:
        # Yarış: eyni açılışa paralel paylaşım — üstündən yazılmır.
        raise TransitionDenied(target_code(offering, syllabus_id=source.pk) or CODE_TAKEN) from None
    _audit(row, action=AuditAction.CREATE, user=actor.user, request=request)
    return row


@transaction.atomic
def unshare(*, syllabus, offering_id, actor, request=None) -> None:
    """Paylaşımı ayır — jurnal yenidən «sillabus yoxdur» vəziyyətinə qayıdır; dosyeyə toxunulmur."""
    if not actor.has(PERM_EDIT):
        raise TransitionDenied("transition.permission_denied", params={"permission": PERM_EDIT})
    if not is_author(actor, syllabus):
        raise TransitionDenied("transition.author_only", params={"transition": "unshare"})
    row = SyllabusShare.objects.select_for_update().filter(syllabus=syllabus, offering_id=offering_id).first()
    if row is None:
        raise TransitionDenied(CODE_NOT_SHARED)
    _audit(row, action=AuditAction.DELETE, user=actor.user, request=request)
    row.delete()


def link_legacy(*, syllabus, offering, user=None) -> str:
    """Köhnə sistemin «bir sillabus — bir neçə jurnal» faktı (idxal / təmir) — FILL-ONLY, icazə yoxlamır.

    Qayıdış: ``"linked"`` və ya səbəb kodu (``"already"``, ``"has_own"``, ``"taken"``, ``"not_sibling"``,
    ``"other_teacher"``).  Yalnız idxal borusundan (management command / delta fazası) çağırılmalıdır.
    """
    if not _same_slot(syllabus, offering):
        return "not_sibling"
    owners = {syllabus.author_id, getattr(syllabus.offering, "instructor_id", None) if syllabus.offering_id else None}
    if offering.instructor_id is None or offering.instructor_id not in owners:
        return "other_teacher"
    state = target_code(offering, syllabus_id=syllabus.pk)
    if state:
        return {CODE_HAS_OWN: "has_own", CODE_ALREADY: "already", CODE_TAKEN: "taken"}[state]
    try:
        with transaction.atomic():
            row = SyllabusShare.objects.create(
                organization_id=syllabus.organization_id,
                syllabus=syllabus,
                offering_id=offering.pk,
                source=ShareSource.LEGACY,
                created_by=user,
            )
    except IntegrityError:
        return "taken"
    _audit(row, action=AuditAction.CREATE, user=user)
    return "linked"


def release_offering(*, organization, offering, user=None, request=None) -> int:
    """Açılışın ÖZ dosyesi yaranır — onun paylaşımı silinir (qayda 5). Silinən sətir sayı."""
    if offering is None:
        return 0
    rows = list(SyllabusShare.objects.filter(organization=organization, offering_id=offering.pk))
    for row in rows:
        _audit(row, action=AuditAction.DELETE, user=user, request=request)
        row.delete()
    return len(rows)


__all__ = [
    "CODE_ALREADY",
    "CODE_HAS_OWN",
    "CODE_NOT_SHARED",
    "CODE_TAKEN",
    "REASON_CODES",
    "RESOURCE_TYPE",
    "effective_shares",
    "link_legacy",
    "release_offering",
    "share",
    "share_code",
    "share_counts",
    "shared_syllabus_ids",
    "shares_of",
    "target_code",
    "unshare",
]
