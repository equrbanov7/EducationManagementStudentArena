"""Dərc oluna bilən müəllimlər — görünüşlər arası çıxmaya qarşı VAHİD qayda.

PROBLEM: müəllim sətri k-dan az cavabla gizlədilsə də, eyni ekranda (və ya başqa
görünüşdə) kafedranın/fakültənin/universitetin ortası və həmin vahidin GÖRÜNƏN
müəllimləri varsa, «vahid ortası × N − görünən müəllimlər» çıxması gizli
müəllimin (bir-iki tələbənin) ortasını açır. Kafedra ortası müəllim cədvəlində
«Fərq: kafedra» sütunu, müəllim kartında isə müqayisə işarəsi kimi görünür.

QAYDA (kampaniya dəsti üzrə, əhatədən və filtrdən ASILI OLMAYARAQ, deterministik):
1. ``n ≥ k`` olan müəllim namizəddir; ``n < k`` və müəllimsiz cavablar «gizli qalıq»dır.
2. Hər kafedrada, sonra hər fakültədə, sonda təşkilatda gizli qalıq ``0 < qalıq < k``
   olarsa, ən kiçik namizədlər (say, sonra id) qalıq ≥ k olana qədər dərc edilmir.
   Sonrakı addım yalnız qalığı artırır — əvvəlki səviyyənin zəmanəti pozulmur.
Nəticə: istənilən kafedra/fakültə/təşkilat cəmindən dərc olunan müəllimlər çıxılanda
qalan hissə ya boşdur, ya da ≥ k cavabdır. Müəllim kafedrası/fakültəsi — ən çox
cavabının düşdüyü vahid (F1 ``teacher_table`` ilə eyni).

Daraldıcı filtr (fənn/qrup/ixtisas/kurs) kombinasiyalarının ardıcıl çıxılması
bununla tam bağlanmır — F1-in sənədləşdirdiyi qalıq risk olaraq qalır.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.db.models import Count

from ..constants import DEFAULT_MIN_GROUP_SIZE
from . import filters as flt


def _settle(teachers, published, key, extra, k):
    groups: dict = defaultdict(list)
    for teacher_id, entry in teachers.items():
        groups[entry[key]].append(teacher_id)
    for unit in set(groups) | set(extra):
        members = groups.get(unit, [])
        hidden = extra.get(unit, 0) + sum(teachers[t]["n"] for t in members if t not in published)
        if not 0 < hidden < k:
            continue
        for teacher_id in sorted((t for t in members if t in published), key=lambda t: (teachers[t]["n"], t)):
            published.discard(teacher_id)
            hidden += teachers[teacher_id]["n"]
            if hidden >= k:
                break


def _publishable(rows, k) -> set:
    teachers: dict = {}
    extra_department: dict = defaultdict(int)
    extra_faculty: dict = defaultdict(int)
    extra_org = 0
    for row in rows:
        count = row["c"]
        if row["teacher_id"] is None:
            extra_department[row["teacher_department_id"]] += count
            extra_faculty[row["faculty_id"]] += count
            extra_org += count
            continue
        entry = teachers.setdefault(row["teacher_id"], {"n": 0, "departments": Counter(), "faculties": Counter()})
        entry["n"] += count
        entry["departments"][row["teacher_department_id"]] += count
        entry["faculties"][row["faculty_id"]] += count
    for entry in teachers.values():
        entry["department"] = entry["departments"].most_common(1)[0][0]
        entry["faculty"] = entry["faculties"].most_common(1)[0][0]
        entry["org"] = None
    published = {teacher_id for teacher_id, entry in teachers.items() if entry["n"] >= k}
    _settle(teachers, published, "department", extra_department, k)
    _settle(teachers, published, "faculty", extra_faculty, k)
    _settle(teachers, published, "org", {None: extra_org}, k)
    return published


def _rows(organization, campaign_ids, extra_fields=()):
    from apps.organizations.public import ORG_WIDE_SCOPE

    return (
        flt.responses(organization, ORG_WIDE_SCOPE, flt.ResultFilters(), list(campaign_ids))
        .values("teacher_id", "teacher_department_id", "faculty_id", *extra_fields)
        .annotate(c=Count("id"))
    )


def publishable_teachers(organization, campaign_ids) -> set:
    """Kampaniya dəsti üzrə dərc oluna bilən müəllim id-ləri (2 sorğu)."""
    campaign_ids = list(campaign_ids or [])
    if not campaign_ids:
        return set()
    return _publishable(list(_rows(organization, campaign_ids)), flt.k_threshold(campaign_ids))


def publishable_by_campaign(organization, campaign_ids) -> dict:
    """``{campaign_id: {teacher_id, …}}`` — dinamika nöqtələri üçün (hər kampaniya öz k-sı ilə; 2 sorğu)."""
    from ..models import SurveyCampaign

    campaign_ids = list(campaign_ids or [])
    if not campaign_ids:
        return {}
    thresholds = dict(SurveyCampaign.objects.filter(pk__in=campaign_ids).values_list("pk", "min_group_size"))
    by_campaign: dict = defaultdict(list)
    for row in _rows(organization, campaign_ids, ("campaign_id",)):
        by_campaign[row["campaign_id"]].append(row)
    return {
        campaign_id: _publishable(
            by_campaign.get(campaign_id, []),
            max(int(thresholds.get(campaign_id) or DEFAULT_MIN_GROUP_SIZE), DEFAULT_MIN_GROUP_SIZE),
        )
        for campaign_id in campaign_ids
    }
