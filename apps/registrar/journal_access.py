"""Jurnal giriş/redaktə hüquq köməkçiləri (paylaşılan — views + journal_actions).

İki fərqli səviyyə var:

* :func:`can_edit_journal` — GİRİŞ + korrektor səlahiyyəti. Müəllim / org sahibi /
  superuser / İKT Rəhbəri jurnalı aça bilər. İKT texniki super-operatordur.
* :func:`can_observe_journal` — YALNIZ-OXU: fənni TƏHVİL VERMİŞ köhnə müəllim
  VƏ YA əhatəsi açılışın qrupunu örtən ``journal.view`` daşıyıcısı (2026-09-14; kafedra
  kökü kafedraya aid açılışları da örtür — 2026-10-24, ``journal_scope.journal_view_q``).
  Yazma hüququ dərhal gedir, görünüş qalır (bax :func:`apps.registrar.handover.
  is_handover_observer` şərhi: apellyasiya/komissiya sualı təhvildən sonra da gəlir).
* :func:`is_direct_editor` — BİRBAŞA (audit-siz) redaktə hüququ: müəllim, org
  sahibi, superuser və — SAHİBİN QƏRARI (2026-09-14) — RİM rəhbəri (İKT). Əvvəl
  İKT yalnız korrektor idi (normal görünüş read-only, dəyişiklik ancaq «Jurnal
  düzəlişi» rejimində sənədli); indi başqa müəllimin jurnalında dərs əlavə edir,
  bal yazır. Kilidli (2 saat / bağlı semestr) hallarda düzəliş rejimi yenə qalır.
  views.py + journal_actions.py hər ikisi buradan idxal edir (modul-ölçü limiti
  üçün ayrıca kiçik modul).

Həmçinin :func:`offering_or_404` — offering-in TENANT-SCOPE-lu yüklənməsi.
"""

from __future__ import annotations


def offering_or_404(request, offering_id, *, select_related=True):
    """Offering-i AKTİV TƏŞKİLAT kontekstinə bağlı yükləyir (tapılmasa 404).

    TƏHLÜKƏSİZLİK: əvvəllər jurnal səthləri ``get_object_or_404(CourseOffering,
    pk=...)`` edirdi — tenant sərhədi tamamilə Postgres RLS-ə qalırdı. RLS
    non-Postgres backend-də no-op-dur və tətbiq DB rolu ``rolbypassrls``
    daşıyırsa mühərrik səviyyəsində keçilir; hər iki halda başqa təşkilatın
    jurnalı pk təxmini ilə açıla bilərdi.

    Aktiv və etibarlı org konteksti yoxdursa fail-closed 404 qaytarılır. Beləliklə
    multi-tenant müəllimin başqa təşkilatdakı offering PK-sı ilə cari tenantdan
    çıxması və SQLite/owner DB rolunda RLS-dən yan keçməsi mümkün deyil.
    """
    from django.http import Http404
    from django.shortcuts import get_object_or_404

    from core.tenancy import get_request_organization, request_has_active_organization_context

    from .models import CourseOffering

    queryset = CourseOffering.objects.all()
    if select_related:
        queryset = queryset.select_related("subject", "period", "group", "organization")

    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        raise Http404
    return get_object_or_404(queryset, pk=offering_id, organization=organization)


def _is_live_assigned_instructor(user, offering) -> bool:
    if not offering.instructor_id or offering.instructor_id != getattr(user, "id", None):
        return False

    from .integrity import is_authorized_instructor

    snapshot_verdict = _snapshot_grade_input(user, offering.organization)
    if snapshot_verdict is not None:
        return snapshot_verdict
    return is_authorized_instructor(
        organization=offering.organization,
        instructor=user,
    )


def _snapshot_grade_input(user, organization) -> bool | None:
    """PERF-1 F-15: ``is_authorized_instructor``-un cavabı middleware-in request üzvlük snapshot-undan.

    Snapshot = ``Membership(user, org, is_active=True, role__organization=org)`` (aktiv org, rol yüklü);
    canlı sorğunun qalan şərtləri (aktiv istifadəçi, aktiv rol) burada Python-da yoxlanılır. Snapshot
    yararsızdırsa (başqa org / epoxa / superuser) ``None`` — çağıran canlı sorğuya düşür. Jurnal açılışında
    eyni yoxlama iki dəfə (`can_edit_journal` + `is_direct_editor`) ayrıca SELECT idi.
    """
    if organization is None or not getattr(organization, "is_active", False):
        return None
    from apps.organizations.public import request_active_memberships

    rows = request_active_memberships(user, organization)
    if rows is None:
        return None
    if not getattr(user, "is_active", False):
        return False

    from core.permissions import has_permission

    from .integrity import INSTRUCTOR_PERMISSION

    return any(
        membership.role.is_active and has_permission(list(membership.role.permissions or []), INSTRUCTOR_PERMISSION)
        for membership in rows
    )


def can_edit_journal(user, offering) -> bool:
    """Giriş + redaktə/korrektor səlahiyyəti: müəllim / sahib / superuser / İKT Rəhbəri.

    TENANT SƏRHƏDİ burada YOXLANMIR — ``is_ikt_rehber`` (bax
    ``apps/accounts/roles._has_role``) onsuz da yalnız AKTİV təşkilatdakı AKTİV
    üzvlükdən həll olunur, offering isə view-lara :func:`offering_or_404` ilə
    aktiv təşkilata bağlı gəlir. Yəni A universitetinin İKT-si B-nin jurnalını
    aça bilmir: fetch mərhələsində 404 alır.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_ikt_rehber", False):
        return True
    if _is_live_assigned_instructor(user, offering):
        return True
    if offering.organization.owner_id == user.id:
        return True
    # Bölünmüş jurnalın pay sahibi (sahib 2026-10-26) — əhatəsi ``journal_shares.journal_scope``-dadır.
    from .journal_shares import has_writable_share

    return has_writable_share(user, offering)


#: Əhatəli YALNIZ-OXU jurnal girişi (audit 2026-09-13 `access` F-06, 2026-09-14).
#: Açar reyestrdə var idi, amma kodda heç yerdə yoxlanmırdı — icazə redaktorunda
#: «yalançı düymə». İndi: bu açarı daşıyan (ORGANIZATION rolu → org-wide, UNIT
#: rolu → ``scope_unit`` alt-ağacı) aktor əhatəsindəki açılışın jurnalını OXUYA
#: bilir; yazma hüququ vermir (``is_direct_editor`` dəyişməyib). Heç bir default
#: şablona əlavə edilmir — tenant istəsə redaktordan verir (fail-closed).
VIEW_PERMISSION = "journal.view"


def can_observe_journal(user, offering) -> bool:
    """YALNIZ-OXU giriş: bu açılışı təhvil vermiş KÖHNƏ müəllim və ya
    əhatəsi açılışın qrupunu örtən ``journal.view`` daşıyıcısı.

    QƏSDƏN ``can_edit_journal``-dan AYRIDIR. Onu genişləndirsəydik köhnə müəllim
    ``is_direct_editor`` olmadan da POST səthlərinə (dərs əlavəsi, bal yazma)
    çata bilərdi — jurnalın iki sahibi yaranardı. Ayrı funksiya çağıran tərəfi
    «görmək» ilə «yazmaq» arasında seçim etməyə MƏCBUR edir.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    from .handover import is_handover_observer

    if is_handover_observer(user, offering):
        return True
    from .journal_scope import offering_in_journal_view_scope

    # Siyahı (``journal_scope.journal_view_q``) ilə EYNİ əhatə: kafedra kökü kafedraya aid açılışları da
    # örtür (2026-10-24). Yalnız OXU — yazma qapıları (``is_direct_editor``) bu açara baxmır.
    return offering_in_journal_view_scope(user, offering.organization, offering)


def offering_accepts_writes(offering) -> bool:
    """Ləğv edilmiş açılış (``is_active=False``) jurnalına HEÇ BİR yazı getmir.

    Audit 2026-09-28 J-09: semestr idarəsində ləğv olunan açılış siyahılardan
    gizlənirdi, amma URL ilə dərs/bal/düzəliş yazıla bilirdi. Oxu (jurnalı açmaq,
    PDF/ixrac) açıq qalır — tarixçə itmir."""
    return bool(getattr(offering, "is_active", True))


def writable_offering_or_404(offering):
    """Yazı səthləri üçün qapı: ləğv edilmiş açılışda 404 (J-09)."""
    if not offering_accepts_writes(offering):
        from django.http import Http404

        raise Http404
    return offering


def is_direct_editor(user, offering) -> bool:
    """Birbaşa (audit-siz) redaktə — müəllim / org sahibi / superuser / RİM rəhbəri.

    Sahibin qərarı (2026-09-14): RİM rəhbəri («hər şeyin icazəsi») başqa müəllimin
    jurnalında da birbaşa dərs əlavə edir və bal yazır; əvvəl yalnız korrektor idi.
    Tenant sərhədi `can_edit_journal`-dakı kimi fetch mərhələsində (`offering_or_404`).
    Ləğv edilmiş açılışda heç kim birbaşa redaktor deyil (J-09 — jurnal yalnız-oxu)."""
    if not getattr(user, "is_authenticated", False):
        return False
    if not offering_accepts_writes(offering):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_ikt_rehber", False):
        return True
    if _is_live_assigned_instructor(user, offering):
        return True
    if offering.organization.owner_id == user.id:
        return True
    # Pay sahibi yalnız ÖZ sətir/sütunlarına yazır — POST qapıları ``journal_share_guard``-dadır.
    from .journal_shares import has_writable_share

    return has_writable_share(user, offering)
