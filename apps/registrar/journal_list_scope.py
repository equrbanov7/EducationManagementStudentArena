"""Jurnal siyahısının görünüş əhatəsi — siyahı ilə onun axtarışlı seçicilərinin TƏK mənbəyi (2026-10-29).

Əvvəl ``page_contexts.journal_list_context`` siyahını ``journal.correct`` / ``journal.roster`` /
``journal.view`` (+ öz/bölünmüş jurnal) əhatəsi ilə qururdu, «MÜƏLLİM» seçicisi isə
``accounts:journal_teacher_search``-dən — TAMAMİLƏ BAŞQA açarın (``student.records_view``) və
qrup-yolu əhatəsinin müəllimlərini oxuyurdu. Nəticə (sahib şikayəti 2026-10-29: «müəllim
search işləmir»): ``journal.correct``/``journal.roster``/``journal.view`` daşıyan, amma
``student.records_view`` daşımayan, ya da əhatəsi KAFEDRA olan aktor siyahıda jurnalları
görürdü, seçicidə isə müəllim tapılmırdı (boş menyu) — və ya siyahıda olmayan müəllim
çıxırdı (seçəndə boş siyahı). İndi hər ikisi :func:`journal_list_base`-dən gəlir.
"""

from __future__ import annotations

from django.db.models import Q

from apps.registrar import journal_scope
from apps.registrar.models import CourseOffering


def journal_list_base(user, request=None):
    """``(base_qs, is_broad)`` — aktorun jurnal siyahısında görə biləcəyi aktiv açılışlar.

    * korrektor (``journal.correct`` / superadmin) → bütün təşkilat;
    * ``journal.roster`` / ``journal.view`` əhatəsi → əhatədəki cari dövr jurnalları + öz jurnalları;
    * adi müəllim → öz (və bölünmüş) jurnalları + təhvil verdiyi (yalnız-oxu) jurnallar.

    ``is_broad`` — geniş (korrektor/koordinator) görünüş: əlavə süzgəclər (müəllim, qrup …) göstərilir.
    """
    from apps.registrar import corrections as corrections_service
    from apps.registrar import guest_roster, journal_shares

    # Korrektorlar (İKT rəhbəri / admin / superadmin — journal.correct icazəsi) BÜTÜN
    # təşkilatın jurnallarını görür (öz dərsi olmasa da); adi müəllim yalnız özününkünü.
    can_correct = bool(request is not None and corrections_service.can_correct_journal(request))
    organization = getattr(request, "organization", None) if request is not None else None
    base_qs = CourseOffering.objects.filter(is_active=True)
    if organization is not None:
        base_qs = base_qs.filter(organization=organization)
    # Jurnal siyahısını idarə edən (koordinator/dekanlıq — `journal.roster`) öz
    # ALT-AĞACININ jurnallarını görür ki, «alt qrupdan tələbə əlavə et»
    # düyməsinə çata bilsin. Korrektordan fərqi: əhatə org-wide DEYİL.
    can_roster = bool(
        request is not None and organization is not None and guest_roster.can_manage_roster(user, organization)
    )
    # `journal.view` (audit F-06, 2026-09-14): əhatəli YALNIZ-OXU jurnallar siyahıya da düşür.
    view_q = journal_scope.journal_view_q(user, organization) if organization is not None else None
    own_q = journal_shares.own_or_shared_q(user)  # öz jurnalı + bölünmüş jurnalın payı (sahib 2026-10-26)
    if can_correct and organization is not None:
        return base_qs.filter(organization=organization), True
    if can_roster or view_q is not None:
        # Əhatə üzrə görünən jurnallar YALNIZ aktiv cari dövrdən gəlir: köçürülmüş
        # tarixi semestrlərin jurnalı koordinatorun siyahısında ÇIXMAMALIDIR (əks
        # halda düymə oradadır və köhnə transkript dəyişər — bax guest_roster.
        # assert_roster_open). Müəllimin ÖZ jurnalları toxunulmaz qalır: onun
        # tarixçəsi dövr süzgəcindən keçmir.
        scoped_groups = guest_roster.scoped_group_queryset(user, organization) if can_roster else []
        visible = Q(group__in=scoped_groups, period__is_current=True, period__is_active=True) | own_q
        return base_qs.filter(organization=organization).filter(visible | (view_q or Q(pk__in=[]))), True
    # Fənni TƏHVİL VERMİŞ köhnə müəllim jurnalı YALNIZ-OXU görməyə davam edir (bax
    # apps/registrar/handover.is_handover_observer) — siyahıda sətir olmasaydı, ona gedən
    # yeganə keçid itərdi. Yazma hüququ `is_direct_editor`-dədir, təhvildən sonra False.
    from apps.registrar.handover import observer_offering_ids

    observed = observer_offering_ids(user, organization) if organization is not None else set()
    return (base_qs.filter(own_q | Q(pk__in=observed)) if observed else base_qs.filter(own_q)), False


__all__ = ["journal_list_base"]
