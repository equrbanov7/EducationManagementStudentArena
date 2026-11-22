"""Öz qrupunun BAŞQA bölmədəki jurnalları — YALNIZ-OXU (sahib 2026-11-22).

Sahib (RİM rəhbəri): «tyutorlar, laborantlar, kafedra müdirləri və dekanlıqlar — onlara aid olan qrup başqa yerdə dərs
keçirsə onu görsünlər; yəni onlara aid olan qruplar üçün jurnalda dərslərə baxa bilsinlər, jurnal başqa bölmədə olsa
belə». Məs. Biznes məktəbinin qrupunun «Xarici dil» jurnalı Xarici dillər kafedrasındadır (başqa məktəb, çox vaxt
səviyyə kohortu — açılışın qrupu kohortdur, tələbələr ev qrupundan gəlir): dekanlıq/tyutor onu görmürdü.

ÖZ QRUPLAR — aktorun jurnal açarlarının (``journal.view`` / ``journal.roster``) struktur əhatəsindəki AKADEMİK qruplar:

* əhatə kökünün ``OrgUnit`` alt-ağacı (dekan / dekan müavini / məktəb tyutoru / məktəb laborantı → fakültə →
  ixtisas → qrup; kafedra altında qrup varsa kafedra müdiri / laborantı üçün həmin qruplar);
* ``journal.view`` daşıyan tyutor / proqram koordinatorunun fakültəsi (``faculty_watcher_paths``, MR-000380 —
  kafedraya təyin olunsa da; yalnız ``journal.roster`` daşıyan kafedra tyutoru öz kafedrasının alt-ağacı ilə qalır);
* Kollec qrupları SAYILMIR (sahib 2026-11-10: Kollec bu sistemdə yazılmır), tələbə + heyət rolunun öz qrupu da.

Org-wide aktor (RİM, rektor, monitorinq …) onsuz da hər şeyi görür — bu modul ona heç nə əlavə etmir.

ƏLÇATAN JURNAL — CARİ (``is_current`` + aktiv) dövrün AKTİV açılışı:

* qrupu öz qrupdur; VƏ YA
* öz qrupun tələbəsi (aktiv akademik qeydi o qrupdadır) orada AKTİV qeydiyyatdadır — səviyyə/dil kohortu, intensiv,
  əcnəbi tələbənin ikinci qrupu, başqa qrupun jurnalına qonaq; VƏ YA
* sətir öz qrupdan qonaq kimi əlavə olunub (``Enrollment.source_group``).

Patok / birgə jurnal fiziki olaraq qrup başına ayrı açılışdır — qrupun öz açılışı birinci şərtlə düşür.

YALNIZ OXU: :func:`apps.registrar.journal_access.can_observe_journal` buradan keçir (müşahidəçi rejimi); yazma qapıları
(``is_direct_editor`` / ``can_edit_journal`` / ``journal.roster`` əməlləri) bu modula BAXMIR. Tenant sərhədi: hər sorğu
``organization`` ilə süzülür, detal isə onsuz da ``offering_or_404`` ilə aktiv təşkilata bağlıdır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q

from core.constants import OrgUnitType

#: «Öz qrup» əhatəsini verən jurnal açarları (oxu — siyahı/müşahidə; siyahı idarəsi — dekanlıq/tyutor).
REACH_PERMISSIONS = ("journal.view", "journal.roster")
#: Kollec əlaməti (``college_journals_hide_2026_11_10`` və ``group_education_form`` ilə eyni markerlər).
_COLLEGE_RE = r"(kollec|kolec|college)"
_CACHE_ATTR = "_ems_group_reach_ids"


def _model(app_label, name):
    return django_apps.get_model(app_label, name)


def _scopes(user, organization) -> list:
    """``[(açar, UnitScope)]`` — yalnız struktur əhatəsi olan jurnal açarları (üzvlüklər memoizasiya olunub)."""
    org_unit = _model("organizations", "OrgUnit")
    found = []
    for permission in REACH_PERMISSIONS:
        scope = org_unit.user_permission_scope(user, organization, permission)
        if scope.has_structure_access:
            found.append((permission, scope))
    return found


def college_groups(organization, *, roots=None):
    """Kollec qrupları (queryset): legacy ``kollec_or_uni`` işarəsi və ya əcdad bölmənin adında marker.

    ``roots`` — artıq oxunmuş Kollec kök yolları (:func:`_college_roots`); verilməzsə bir sorğu ilə oxunur.
    """
    org_unit = _model("organizations", "OrgUnit")
    if roots is None:
        roots = (
            org_unit.objects.filter(organization=organization, name__iregex=_COLLEGE_RE)
            .exclude(unit_type=OrgUnitType.GROUP)
            .values_list("path", flat=True)
        )
    query = Q(settings__legacy__kollec_or_uni__iregex=rf"^\s*{_COLLEGE_RE}\s*$")
    for path in roots:
        if path:
            query |= Q(path__startswith=f"{path}/")
    return org_unit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP).filter(query)


def _user_cache(user) -> dict:
    return user.__dict__.setdefault(_CACHE_ATTR, {})


def _college_roots(user, organization) -> tuple:
    """Kollec kök bölmələrinin yolları — istifadəçi instansında təşkilat üzrə keşlənir (bir sorğu)."""
    cache = _user_cache(user)
    key = ("college", organization.pk)
    if key not in cache:
        cache[key] = tuple(
            _model("organizations", "OrgUnit")
            .objects.filter(organization=organization, name__iregex=_COLLEGE_RE)
            .exclude(unit_type=OrgUnitType.GROUP)
            .values_list("path", flat=True)
        )
    return cache[key]


def own_group_ids(user, organization) -> frozenset:
    """Aktorun ÖZ qruplarının id-ləri (bax modul başlığı); əhatə yoxdursa / org-wide-dırsa boş dəst.

    Nəticə ``user`` instansında təşkilat üzrə saxlanılır (bir sorğuda siyahı + detal + seçicilər eyni dəsti işlədir).
    """
    if organization is None or not getattr(user, "is_authenticated", False):
        return frozenset()
    cache = _user_cache(user)
    if organization.pk not in cache:
        cache[organization.pk] = _compute_own_group_ids(user, organization)
    return cache[organization.pk]


def _compute_own_group_ids(user, organization) -> frozenset:
    scopes = _scopes(user, organization)
    if not scopes or any(scope.is_org_wide for _permission, scope in scopes):
        return frozenset()
    from apps.organizations.public import faculty_watcher_paths, own_scope

    query = Q(pk__in=[])
    for _permission, scope in scopes:
        query |= scope.unit_subtree_q()
    # MR-000380 ilə EYNİ qayda: fakültə genişlənməsi yalnız ``journal.view`` daşıyan tyutor / koordinatora.
    for path in faculty_watcher_paths(user, organization, "journal.view"):
        query |= Q(path__startswith=f"{path}/")
    groups = (
        _model("organizations", "OrgUnit")
        .objects.filter(organization=organization, unit_type=OrgUnitType.GROUP, is_active=True)
        .filter(query)
        .exclude(pk__in=college_groups(organization, roots=_college_roots(user, organization)).values("pk"))
    )
    own = own_scope(user, organization)
    if own.group_ids:
        groups = groups.exclude(pk__in=sorted(own.group_ids))
    return frozenset(groups.values_list("pk", flat=True))


def reach_q(user, organization):
    """Öz qrupların CARİ jurnallarının :class:`CourseOffering` ``Q``-su; öz qrup yoxdursa ``None``."""
    group_ids = sorted(own_group_ids(user, organization))
    if not group_ids:
        return None
    enrollment = _model("registrar", "Enrollment")
    students = (
        _model("registrar", "StudentAcademicRecord")
        .objects.filter(organization=organization, is_active=True, group_id__in=group_ids)
        .values("student_id")
    )
    enrolled = (
        enrollment.objects.filter(organization=organization, status=enrollment.Status.ENROLLED)
        .filter(Q(student_id__in=students) | Q(source_group_id__in=group_ids))
        .values("offering_id")
    )
    query = Q(organization=organization, is_active=True, period__is_current=True, period__is_active=True)
    query &= Q(group_id__in=group_ids) | Q(pk__in=enrolled)
    query &= ~Q(group__in=college_groups(organization, roots=_college_roots(user, organization)).values("pk"))
    from apps.organizations.public import own_scope

    own = own_scope(user, organization)
    if own.offering_ids:
        query &= ~Q(pk__in=sorted(own.offering_ids))
    return query


def offering_in_reach(user, offering) -> bool:
    """Detal qarşılığı :func:`reach_q`: bu açılış aktorun öz qrupunun cari jurnalıdırmı (YALNIZ-OXU)."""
    if offering is None or not getattr(offering, "is_active", False):
        return False
    query = reach_q(user, offering.organization)
    if query is None:
        return False
    offerings = _model("registrar", "CourseOffering").objects
    return offerings.filter(pk=offering.pk).filter(query).exists()


def attach(offerings, *, user, organization) -> None:
    """Siyahı sətirləri: YALNIZ bu qayda ilə görünən jurnala ``group_reach = {"chair": ad}`` bağlanır (etiket üçün).

    Aktorun bu qaydadan ƏVVƏLKİ əhatəli görünüşündə (``journal_list_scope.prior_visibility_q``) olan sətir
    etiketlənmir. Öz qrup yoxdursa sorğusuz qayıdır; əks halda səhifə üçün sabit sayda sorğu.
    """
    for offering in offerings:
        offering.group_reach = None
    query = reach_q(user, organization) if offerings else None
    if query is None:
        return
    model = _model("registrar", "CourseOffering")
    page = model.objects.filter(pk__in=[offering.pk for offering in offerings])
    reach_ids = set(page.filter(query).values_list("pk", flat=True))
    from .journal_list_scope import prior_visibility_q

    prior_q = prior_visibility_q(user, organization) if reach_ids else None
    if prior_q is not None:
        reach_ids -= set(page.filter(pk__in=reach_ids).filter(prior_q).values_list("pk", flat=True))
    if not reach_ids:
        return
    from . import offering_chairs

    chairs = offering_chairs.offering_chairs(model.objects.filter(pk__in=reach_ids), organization.pk)
    names = offering_chairs.chair_paths(organization.pk, {chair for found in chairs.values() for chair in found})
    for offering in offerings:
        if offering.pk in reach_ids:
            labels = sorted(names[chair][0] for chair in chairs.get(offering.pk, ()) if chair in names)
            offering.group_reach = {"chair": ", ".join(labels)}


__all__ = ["REACH_PERMISSIONS", "attach", "college_groups", "offering_in_reach", "own_group_ids", "reach_q"]
