"""Struktur vahidi (fakültə / kafedra) filtrləri üçün dərc qaydası — Audit 2026-09-28 SV-1.

PROBLEM: kafedra/fakültə filtri əvvəl «daraldıcı» sayılmırdı. Rektor universitetin
ortasını (8 cavab) və görünən kafedra A-nın ortasını (6 cavab) açıb «universitet × 8 −
A × 6» çıxması ilə k-dan az cavablı kafedra B-nin (2 cavab) ortasını tapırdı. Tək
tamamlayıcı yoxlama («valideyn − bu vahid» 0 və ya ≥ k) da kifayət deyil: A (5),
C (5) görünəndə «universitet − A − C» yenə B-ni (2) açır.

QAYDA (:func:`settle_units`). Eyni vahid-olmayan filtrlər altında (kampaniya, müəllim,
fənn, qrup, ixtisas, kurs — dəyişmir) görünə bilən vahid görünüşləri bunlardır: valideyn
(vahid filtri olmayan dəst), DƏRC OLUNAN fakültələr və DƏRC OLUNAN kafedralar. Bu
görünüşlərin yaratdığı bölgünün «atomları» (heç bir görünüşlə daha da bölünməyən
hissələr):

1. hər dərc olunan kafedra (tək fakültəyə aid olmalıdır, ``n ≥ k``);
2. hər dərc olunan fakültənin içində dərc olunmayan hissə ``R_F``;
3. qalan hissə — heç bir dərc olunan fakültəyə və ya kafedraya düşməyən cavablar.

Qayda hər atomun 0 və ya ≥ k cavab olmasını təmin edir: əvvəl hər fakültədə
``0 < R_F < k`` olarsa ən kiçik dərc olunan kafedralar (say, sonra id) dərcdən çıxarılır;
sonra qalan hissə ``0 < qalıq < k`` olarsa qalığa ən az əlavə edən element dərcdən
çıxarılır: fakültədən kənar kafedra, ``R_F > 0`` olan fakültə (kafedraları qalır) və ya
``R_F = 0`` olan fakültə kafedraları ilə birlikdə — hər seçim qalığa ≥ k əlavə edir.
Addım 2 addım 1-in zəmanətini pozmur (qalan fakültələrin daxilində heç nə dəyişmir).

NƏTİCƏ (sübut): istənilən iki görünən vahid görünüşünün fərqi, birləşməsi, kəsişməsi —
ümumiyyətlə görünən görünüşlərdən çoxluq cəbri ilə alınan istənilən dəst — atomların
birləşməsidir; hər atom 0 və ya ≥ k olduğundan belə dəst ya boşdur, ya da ≥ k
cavablıdır. Fakültə və ya kafedra görünüşü yalnız dərc olunubsa göstərilir
(:meth:`UnitPublish.allows`); bölgü cədvəllərində dərc olunmayan vahid sətri gizlidir;
müqayisə nöqtəsi (kafedra ortası) yalnız dərc olunan kafedra üçün verilir.

Əhatə: hesab izləyicinin ƏHATƏSİ daxilində aparılır (valideyn = əhatənin cəmi). Əhatəsi
təşkilatdan dar olan izləyici üçün «universitet» müqayisə nöqtəsi əlavə olaraq
``universitet − əhatə`` fərqinin 0 və ya ≥ k olmasını tələb edir (:func:`org_benchmark_ok`).

QALIQ RİSK: vahid filtri ilə daraldıcı filtrlərin (fənn/qrup/ixtisas/kurs) çarpaz
kombinasiyalarının ardıcıl çıxılması tam qəfəs üzrə yoxlanmır (bax ``analytics_guard``).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace

from django.db.models import Count

from ..constants import DEFAULT_MIN_GROUP_SIZE, Section
from . import filters as flt


@dataclass(frozen=True)
class UnitPublish:
    """Dərc olunan kafedra və fakültə id-ləri."""

    departments: frozenset = frozenset()
    faculties: frozenset = frozenset()

    def allows(self, filters) -> bool:
        """Vahid filtrli görünüş göstərilə bilərmi (vahid filtri yoxdursa — həmişə)."""
        if filters.department_id is not None:
            return filters.department_id in self.departments
        if filters.faculty_id is not None:
            return filters.faculty_id in self.faculties
        return True


def has_unit_filter(filters) -> bool:
    return filters is not None and (filters.faculty_id is not None or filters.department_id is not None)


def without_units(filters):
    return replace(filters, faculty_id=None, department_id=None)


def settle_units(rows, k) -> UnitPublish:
    """``rows`` — ``(department_id, faculty_id, say)`` üçlükləri; qayda modul sənədindədir."""
    department_n: Counter = Counter()
    department_faculties: dict = defaultdict(set)
    faculty_n: Counter = Counter()
    total = 0
    for department_id, faculty_id, count in rows:
        count = int(count or 0)
        total += count
        faculty_n[faculty_id] += count
        if department_id is not None:
            department_n[department_id] += count
            department_faculties[department_id].add(faculty_id)
    # Bir neçə fakültəyə düşən kafedra (snapshot sürüşməsi) ayrıca dərc olunmur — atom olmazdı.
    home = {dept: next(iter(facs)) for dept, facs in department_faculties.items() if len(facs) == 1}
    departments = {dept for dept in home if department_n[dept] >= k}
    faculties = {fac for fac, n in faculty_n.items() if fac is not None and n >= k}

    def order(dept):
        return (department_n[dept], str(dept))

    # 1) Fakültə daxilində dərc olunmayan hissə 0 və ya ≥ k.
    for faculty_id in sorted(faculties, key=str):
        members = sorted((dept for dept in departments if home[dept] == faculty_id), key=order)
        rest = faculty_n[faculty_id] - sum(department_n[dept] for dept in members)
        while 0 < rest < k and members:
            dept = members.pop(0)
            departments.discard(dept)
            rest += department_n[dept]

    def inner_rest(faculty_id):
        return faculty_n[faculty_id] - sum(department_n[d] for d in departments if home[d] == faculty_id)

    def outside():
        covered = sum(faculty_n[f] for f in faculties)
        covered += sum(department_n[d] for d in departments if home[d] not in faculties)
        return total - covered

    # 2) Heç bir dərc olunan vahidə düşməyən qalıq 0 və ya ≥ k. Seçimlər (qalığa əlavə etdiyi
    #    say ilə, ən kiçiyi): fakültədən kənar kafedra (n ≥ k); R_F > 0 olan fakültə (R_F ≥ k,
    #    kafedraları dərcdə qalır); R_F = 0 olan fakültə — kafedraları ilə birlikdə (n_F ≥ k).
    rest = outside()
    while 0 < rest < k:
        options = [(department_n[d], 0, str(d), d) for d in departments if home[d] not in faculties]
        for faculty_id in faculties:
            inner = inner_rest(faculty_id)
            options.append(
                (inner, 1, str(faculty_id), faculty_id)
                if inner > 0
                else (faculty_n[faculty_id], 2, str(faculty_id), faculty_id)
            )
        if not options:
            break  # heç nə dərc olunmayıb — valideynin özü n < k ilə gizlidir
        _size, kind, _key, value = min(options)
        if kind == 0:
            departments.discard(value)
        else:
            faculties.discard(value)
            if kind == 2:
                departments -= {d for d in departments if home[d] == value}
        rest = outside()
    return UnitPublish(departments=frozenset(departments), faculties=frozenset(faculties))


def _unit_rows(organization, scope, filters, campaign_ids, section, extra=()):
    return (
        flt.responses(organization, scope, without_units(filters), list(campaign_ids), section=section)
        .values("teacher_department_id", "faculty_id", *extra)
        .annotate(c=Count("id"))
    )


def publishable_units(organization, scope, filters, campaign_ids, k, *, section=Section.TEACHER) -> UnitPublish:
    """Kampaniya dəsti üzrə dərc olunan vahidlər (1 sorğu)."""
    campaign_ids = list(campaign_ids or [])
    if not campaign_ids or not scope.has_structure_access:
        return UnitPublish()
    rows = _unit_rows(organization, scope, filters, campaign_ids, section)
    return settle_units(((row["teacher_department_id"], row["faculty_id"], row["c"]) for row in rows), k)


def publishable_units_by_campaign(organization, scope, filters, campaign_ids, *, section=Section.TEACHER) -> dict:
    """``{campaign_id: UnitPublish}`` — hər kampaniya öz k-sı ilə (dinamika nöqtələri; 2 sorğu)."""
    from ..models import SurveyCampaign

    campaign_ids = list(campaign_ids or [])
    if not campaign_ids or not scope.has_structure_access:
        return {}
    thresholds = dict(SurveyCampaign.objects.filter(pk__in=campaign_ids).values_list("pk", "min_group_size"))
    grouped: dict = defaultdict(list)
    for row in _unit_rows(organization, scope, filters, campaign_ids, section, ("campaign_id",)):
        grouped[row["campaign_id"]].append((row["teacher_department_id"], row["faculty_id"], row["c"]))
    return {
        campaign_id: settle_units(
            grouped.get(campaign_id, []),
            max(int(thresholds.get(campaign_id) or DEFAULT_MIN_GROUP_SIZE), DEFAULT_MIN_GROUP_SIZE),
        )
        for campaign_id in campaign_ids
    }


def unit_view_ok(organization, scope, filters, campaign_ids, k, *, section=Section.TEACHER) -> bool:
    """Vahid filtrli dəst göstərilə bilərmi (vahid filtri yoxdursa sorğusuz ``True``)."""
    if not has_unit_filter(filters):
        return True
    return publishable_units(organization, scope, filters, campaign_ids, k, section=section).allows(filters)


def org_benchmark_ok(organization, scope, campaign_ids, k, *, section=Section.TEACHER) -> bool:
    """Əhatəsi dar izləyiciyə «universitet» müqayisə nöqtəsi: ``universitet − əhatə`` 0 və ya ≥ k."""
    from apps.organizations.public import ORG_WIDE_SCOPE

    if scope.is_org_wide:
        return True
    wide = flt.ResultFilters()
    org_n = flt.responses(organization, ORG_WIDE_SCOPE, wide, list(campaign_ids), section=section).count()
    scope_n = flt.responses(organization, scope, wide, list(campaign_ids), section=section).count()
    gap = org_n - scope_n
    return gap <= 0 or gap >= k


def org_blocked_campaigns(organization, scope, campaign_ids, *, section=Section.TEACHER) -> set:
    """Dinamikanın «universitet» xətti üçün: fərqi 1…k−1 olan kampaniyaların id-ləri (gizlədilməli)."""
    from apps.organizations.public import ORG_WIDE_SCOPE

    from ..models import SurveyCampaign

    campaign_ids = list(campaign_ids or [])
    if scope.is_org_wide or not campaign_ids:
        return set()
    wide = flt.ResultFilters()

    def counts(scope_):
        queryset = flt.responses(organization, scope_, wide, campaign_ids, section=section)
        return dict(queryset.values("campaign_id").annotate(c=Count("id")).values_list("campaign_id", "c"))

    org, own = counts(ORG_WIDE_SCOPE), counts(scope)
    thresholds = dict(SurveyCampaign.objects.filter(pk__in=campaign_ids).values_list("pk", "min_group_size"))
    blocked = set()
    for campaign_id in campaign_ids:
        k = max(int(thresholds.get(campaign_id) or DEFAULT_MIN_GROUP_SIZE), DEFAULT_MIN_GROUP_SIZE)
        gap = org.get(campaign_id, 0) - own.get(campaign_id, 0)
        if 0 < gap < k:
            blocked.add(campaign_id)
    return blocked
