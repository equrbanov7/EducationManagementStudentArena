"""Sillabusun struktur bağı — ``chair_unit``-in KAFEDRA kimi həlli (R-2).

Niyə ayrıca modul
-----------------
Sillabusun təsdiq əhatəsi ``Syllabus.chair_unit``-dən çıxır: kafedra müdirinin
``scope_unit``-i həmin bölmənin ÖZÜ və ya ƏCDADI olmalıdır (bax
``services/scoping.py`` → ``apps.organizations.scoping``).  Müəllim səthi isə
``chair_unit``-i ``offering.group.parent``-dən götürürdü — köçürülmüş
strukturda qrupun valideyni **ixtisasdır**, kafedra deyil.  Nəticə: kafedra
müdiri öz kafedrasının sillabusunu nə növbədə görürdü, nə də qərar verə bilirdi.

Qayda
-----
Ağacın DƏRİNLİYİ fərz edilmir (universitetlərin strukturu fərqlidir):
verilmiş bölmədən yuxarı qalxılır və ``chair`` / ``department`` tipli İLK
bölmə seçilir.  Belə əcdad yoxdursa dəyər OLDUĞU KİMİ qalır — uydurma bağ
yaratmaqdansa köhnə davranış saxlanılır (fail-soft).
"""

from __future__ import annotations

from django.apps import apps as django_apps

from apps.organizations.unit_heads import ancestor_unit_ids, resolve_ancestor
from core.constants import OrgUnitType

#: Kafedra rolunu daşıyan bölmə tipləri.  ``department`` tarixi sinonimdir —
#: fixture-lər və bəzi tenant-lar kafedranı bu tiplə yaradıb.  Sıra
#: ƏHƏMİYYƏTLİDİR: kanonik tip birinci axtarılır.
CHAIR_UNIT_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)


def resolve_chair_unit(unit):
    """``unit``-dən yuxarı ən yaxın kafedra; tapılmasa ``unit``-in özü.

    ``None`` → ``None`` (fail-closed: uydurma əcdad yoxdur).  Ağac gəzişməsi
    ``apps.organizations.unit_heads.resolve_ancestor``-dadır — yeni scope
    məntiqi icad edilmir.
    """

    if unit is None:
        return None
    for unit_type in CHAIR_UNIT_TYPES:
        found = resolve_ancestor(unit, unit_type)
        if found is not None:
            return found
    return unit


def author_chair_unit(author, organization):
    """Müəllifin AKTİV kafedra üzvlüyünün bölməsi — struktur bağı olmayan hal.

    Köçürülmüş tenant-da ixtisas KAFEDRAYA yox, birbaşa FAKÜLTƏYƏ bağlıdır
    (mənbədə `speciality.department_id` 83 sətrin 80-ində fakültəni göstərir),
    ona görə qrupdan yuxarı qalxmaqla kafedra TAPILMIR.  Amma müəllimin özü
    kafedraya bağlıdır: klonda 702 aktiv `teacher` üzvlüyünün `scope_unit`-i
    məhz `chair` tipindədir.  Sillabusun sahibi müəllif olduğu üçün onun
    kafedrası ən doğru ikinci mənbədir.
    """

    if author is None or organization is None:
        return None
    Membership = django_apps.get_model("organizations", "Membership")
    membership = (
        Membership.objects.filter(
            organization=organization,
            user=author,
            is_active=True,
            scope_unit__unit_type__in=CHAIR_UNIT_TYPES,
        )
        .select_related("scope_unit")
        .order_by("-is_primary", "pk")
        .first()
    )
    return membership.scope_unit if membership else None


def resolve_syllabus_chair_unit(*, unit=None, author=None, organization=None):
    """Sillabusun kafedrası: struktur əcdadı → müəllifin kafedrası → verilən dəyər.

    Sıra qəsdlidir: ağacda kafedra VARSA o həqiqətin özüdür; yoxdursa müəllifin
    üzvlüyü yeganə real bağdır; o da yoxdursa köhnə dəyər saxlanılır (fail-soft,
    heç bir sillabus «sahibsiz» qalmır).
    """

    resolved = resolve_chair_unit(unit)
    if resolved is not None and getattr(resolved, "unit_type", "") in CHAIR_UNIT_TYPES:
        return resolved
    return author_chair_unit(author, organization) or resolved


def is_chair_unit(unit) -> bool:
    """Bölmə KAFEDRA səviyyəsindədirmi (kanonik tip və ya tarixi sinonim)."""
    return unit is not None and getattr(unit, "unit_type", "") in CHAIR_UNIT_TYPES


def ensure_chair_unit(syllabus, *, save: bool = True):
    """Dosyenin ``chair_unit``-i kafedra deyilsə YENİDƏN həll edir (self-healing).

    Yeni versiya açılışı kimi səthlərdə çağırılır: köçürmə vaxtı ixtisasa
    bağlanmış köhnə dosye yeni versiyada özü kafedraya çəkilir, ayrıca əmr
    gözləmədən.  Kafedra tapılmasa dəyər OLDUĞU KİMİ qalır (fail-soft —
    heç bir dosye «sahibsiz» edilmir).
    """
    current = syllabus.chair_unit
    if is_chair_unit(current):
        return current
    target = resolve_syllabus_chair_unit(
        unit=current,
        author=syllabus.author,
        organization=syllabus.organization,
    )
    if target is None or (current is not None and target.pk == current.pk):
        return current
    syllabus.chair_unit = target
    if save:
        type(syllabus).objects.filter(pk=syllabus.pk).update(chair_unit=target)
    return target


def chair_level_scope_covers(scope_unit_ids, chair_unit_id) -> bool:
    """Aktorun KAFEDRA səviyyəli scope bölməsi verilmiş kafedranı tuturmu.

    Adi ``user_scope_covers_unit`` alt-ağac yoxlamasıdır — fakültə scope-u
    altındakı bütün kafedraları örtür, ona görə DEKAN de-fakto təsdiqçi olurdu.
    Sahibin qərarı (2026-09-03) ilə QƏRAR üçün əhatə KAFEDRA SƏVİYYƏSİNDƏ
    olmalıdır: aktoru sillabusa bağlayan ``Membership.scope_unit`` ya
    kafedranın ÖZÜ, ya da kafedra tipli bir əcdadı olmalıdır.  Fakültə/
    universitet tipli scope bölməsi bu yoxlamadan KEÇMİR (fail-closed);
    org-wide override çağıran tərəfdə ayrıca həll olunur.
    """
    if not scope_unit_ids or chair_unit_id is None:
        return False
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    target = OrgUnit.objects.filter(pk=chair_unit_id).first()
    if target is None:
        return False
    covering = set(ancestor_unit_ids(target))
    candidates = [unit_id for unit_id in scope_unit_ids if str(unit_id) in covering]
    if not candidates:
        return False
    return OrgUnit.objects.filter(pk__in=candidates, unit_type__in=CHAIR_UNIT_TYPES, is_active=True).exists()


def has_chair_level_unit(organization, scope_unit_ids) -> bool:
    """Scope dəstində ÜMUMİYYƏTLƏ kafedra səviyyəli bölmə varmı (UI üçün)."""
    if not scope_unit_ids:
        return False
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    queryset = OrgUnit.objects.filter(pk__in=list(scope_unit_ids), unit_type__in=CHAIR_UNIT_TYPES, is_active=True)
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    return queryset.exists()


__all__ = [
    "CHAIR_UNIT_TYPES",
    "author_chair_unit",
    "chair_level_scope_covers",
    "ensure_chair_unit",
    "has_chair_level_unit",
    "is_chair_unit",
    "resolve_chair_unit",
    "resolve_syllabus_chair_unit",
]
