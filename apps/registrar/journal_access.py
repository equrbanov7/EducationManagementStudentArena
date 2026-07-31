"""Jurnal giriş/redaktə hüquq köməkçiləri (paylaşılan — views + journal_actions).

İki fərqli səviyyə var:

* :func:`can_edit_journal` — GİRİŞ + korrektor səlahiyyəti. Müəllim / org sahibi /
  superuser / İKT Rəhbəri jurnalı aça bilər. İKT texniki super-operatordur.
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

    Filtr aktiv org konteksti VARSA tətbiq olunur — bu, real hücum yolunu
    (öz org-una girmiş istifadəçi başqa org-un pk-sını sınayır) bağlayır.
    Kontekst yoxdursa (məs. üzvlüyü olmayan, amma offering-in instructor-u olan
    müəllim) obyekt qaytarılır və giriş qərarı çağırana — ``can_edit_journal``
    sahiblik yoxlamasına — qalır. Yəni bu qat mövcud yoxlamanı ƏVƏZ ETMİR,
    onun ÜSTÜNƏ əlavə olunur (defence-in-depth); RLS üçüncü xətt kimi qalır.
    """
    from django.shortcuts import get_object_or_404

    from core.tenancy import get_request_organization

    from .models import CourseOffering

    queryset = CourseOffering.objects.all()
    if select_related:
        queryset = queryset.select_related("subject", "period", "group", "organization")

    organization = get_request_organization(request)
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    return get_object_or_404(queryset, pk=offering_id)


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
    if offering.instructor_id and offering.instructor_id == user.id:
        return True
    return offering.organization.owner_id == user.id


def is_direct_editor(user, offering) -> bool:
    """Birbaşa (audit-siz) redaktə — YALNIZ müəllim / org sahibi / superuser.

    Korrektor (İKT Rəhbəri) buraya daxil deyil: jurnalı yalnız düzəliş rejimində
    sənədli dəyişir, normal görünüşdə read-only."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if offering.instructor_id and offering.instructor_id == user.id:
        return True
    return offering.organization.owner_id == user.id
