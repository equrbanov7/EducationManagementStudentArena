"""Jurnal giriş/redaktə hüquq köməkçiləri (paylaşılan — views + journal_actions).

İki fərqli səviyyə var:

* :func:`can_edit_journal` — GİRİŞ + korrektor səlahiyyəti. Müəllim / org sahibi /
  superuser / İKT Rəhbəri jurnalı aça bilər. İKT texniki super-operatordur.
* :func:`can_observe_journal` — YALNIZ-OXU: fənni TƏHVİL VERMİŞ köhnə müəllim.
  Yazma hüququ dərhal gedir, görünüş qalır (bax :func:`apps.registrar.handover.
  is_handover_observer` şərhi: apellyasiya/komissiya sualı təhvildən sonra da gəlir).
* :func:`is_direct_editor` — BİRBAŞA (audit-siz) redaktə hüququ: YALNIZ müəllim,
  org sahibi, superuser. Korrektor (İKT) buraya DAXİL DEYİL — o, dəyişikliyi yalnız
  «Jurnal düzəlişi» rejimində sənədli (audited, PDF) yolla edir; normal görünüşdə
  hər şey read-only-dir. views.py + journal_actions.py hər ikisi buradan idxal edir
  (modul-ölçü limiti üçün ayrıca kiçik modul).

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


def schedule_slot_or_404(request, slot_id):
    """Load a schedule slot only inside a verified active tenant context."""
    from django.http import Http404
    from django.shortcuts import get_object_or_404

    from core.tenancy import get_request_organization, request_has_active_organization_context

    from .models import ScheduleSlot

    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        raise Http404
    return get_object_or_404(
        ScheduleSlot.objects.select_related("offering", "offering__organization"),
        pk=slot_id,
        offering__organization=organization,
    )


def _is_live_assigned_instructor(user, offering) -> bool:
    if not offering.instructor_id or offering.instructor_id != getattr(user, "id", None):
        return False

    from .integrity import is_authorized_instructor

    return is_authorized_instructor(
        organization=offering.organization,
        instructor=user,
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
    return offering.organization.owner_id == user.id


def can_observe_journal(user, offering) -> bool:
    """YALNIZ-OXU giriş: bu açılışı təhvil vermiş KÖHNƏ müəllim.

    QƏSDƏN ``can_edit_journal``-dan AYRIDIR. Onu genişləndirsəydik köhnə müəllim
    ``is_direct_editor`` olmadan da POST səthlərinə (dərs əlavəsi, bal yazma)
    çata bilərdi — jurnalın iki sahibi yaranardı. Ayrı funksiya çağıran tərəfi
    «görmək» ilə «yazmaq» arasında seçim etməyə MƏCBUR edir.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    from .handover import is_handover_observer

    return is_handover_observer(user, offering)


def is_direct_editor(user, offering) -> bool:
    """Birbaşa (audit-siz) redaktə — YALNIZ müəllim / org sahibi / superuser.

    Korrektor (İKT Rəhbəri) buraya daxil deyil: jurnalı yalnız düzəliş rejimində
    sənədli dəyişir, normal görünüşdə read-only."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if _is_live_assigned_instructor(user, offering):
        return True
    return offering.organization.owner_id == user.id
