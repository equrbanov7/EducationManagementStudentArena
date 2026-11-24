"""Tələbə əlavə edərkən MƏNBƏ qrupları — universitet əhatəli kafedrada bütün təşkilat (sahib 2026-11-22).

Sahib (RİM rəhbəri): «Xarici dil kafedrasında tyutorlar və dekanlıq işçiləri … alt qrupa tələbə əlavə edəndə bütün
universitetdən qrupları götürürlər». Qayda və kafedra seçimi :mod:`apps.organizations.university_wide_scope`-dadır;
bu modul onu registrar seçicilərinə tətbiq edir:

* «Alt qrupdan tələbə əlavə et» (``/jurnal/<açılış>/alt-qrup/…``) — jurnalın qrupu belə kafedranın alt-ağacındadırsa
  (səviyyə qrupunun jurnalı) mənbə qrupları bütün təşkilatın akademik qruplarıdır (:func:`source_group_queryset`);
* «Xarici dil səviyyə qrupları» — kohortun kafedrası belədirsə namizədlər və yerləşdirmə qapısı bütün təşkilat
  (:func:`cohort_source_groups`, :func:`cohort_allows_group`).

Siyahını kim idarə edə bilər (``journal.roster`` + jurnalın aktorun əhatəsində olması) DƏYİŞMİR — yalnız
namizəd tələbələrin gəldiyi qruplar genişlənir. «Öz qrupu» istisnası (tələbə + heyət rolu) qalır; səviyyə
qrupları (``language_cohort``) mənbə sayılmır — tələbənin akademik (ev) qrupu deyil.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from core.constants import OrgUnitType

from . import guest_roster


def _widened_groups(user, organization):
    """Bütün təşkilatın AKTİV akademik qrupları — aktorun «öz qrupu» istisnası çıxılmaqla."""
    from apps.organizations.public import widen_to_university

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    queryset = org_unit_model.objects.filter(
        organization=organization, is_active=True, unit_type=OrgUnitType.GROUP, language_cohort__isnull=True
    )
    scope = widen_to_university(
        org_unit_model.user_permission_scope(user, organization, guest_roster.ROSTER_PERMISSION)
    )
    if scope.excluded_unit_ids:
        queryset = queryset.exclude(pk__in=sorted(scope.excluded_unit_ids))
    return queryset


def _is_wide(user, organization, unit) -> bool:
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return False  # onsuz da bütün təşkilat
    if not guest_roster.can_manage_roster(user, organization):
        return False
    from apps.organizations.public import unit_is_university_wide

    return unit_is_university_wide(organization, unit)


def source_group_queryset(user, offering):
    """«Alt qrupdan tələbə əlavə et» seçicisinin mənbə qrupları (axtarış, siyahı, önbaxış, əlavə — eyni mənbə)."""
    organization = offering.organization
    if offering.group_id is not None and _is_wide(user, organization, offering.group_id):
        return _widened_groups(user, organization)
    return guest_roster.scoped_group_queryset(user, organization)


def cohort_is_wide(user, cohort) -> bool:
    """Səviyyə qrupunun kafedrası universitet əhatəlidir (aktor siyahını idarə edən heyətdir).

    2026-11-19 («qrup dövrəsi»): məktəb tyutoru dil kafedrasında ÖZ açdığı qrupa yalnız yaradıcı yolu ilə çatır —
    universitet genişliyi ona keçmir, yalnız öz əhatəsinin tələbələri (``language_cohorts.creator_only_access``).
    """
    from . import language_cohorts

    if getattr(cohort, "created_by_id", None) is not None and language_cohorts.creator_only_access(user, cohort):
        return False
    return _is_wide(user, cohort.organization, cohort.department)


def cohort_source_groups(user, cohort):
    """Səviyyə qrupuna namizədlərin akademik qrupları."""
    if cohort_is_wide(user, cohort):
        return _widened_groups(user, cohort.organization)
    return guest_roster.scoped_group_queryset(user, cohort.organization)


def _wide_group(user, cohort, group_id) -> bool:
    if group_id is None or not cohort_is_wide(user, cohort):
        return False
    return _widened_groups(user, cohort.organization).filter(pk=group_id).exists()


def cohort_allows_group(user, cohort, group_id) -> bool:
    """Yerləşdirmə qapısı: tələbənin qrupu aktorun əhatəsində və ya kohort universitet əhatəlidir."""
    return guest_roster.unit_in_scope(user, cohort.organization, group_id) or _wide_group(user, cohort, group_id)


def cohort_allows_source(user, cohort, offering) -> bool:
    """Universitet əhatəli kohort: tələbənin öz (başqa məktəbdəki) səviyyə jurnalından keçid — öz jurnalı deyilsə."""
    from .journal_scope import own_offering_conflict

    if own_offering_conflict(user, cohort.organization, offering):
        return False
    return _wide_group(user, cohort, offering.group_id)


__all__ = [
    "cohort_allows_group",
    "cohort_allows_source",
    "cohort_is_wide",
    "cohort_source_groups",
    "source_group_queryset",
]
