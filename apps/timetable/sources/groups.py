"""Qrup metadatası, alt qrup AİLƏLƏRİ, kohortlar və növbə siyasəti.

**Pillə (bakalavr/magistr)** mənbə sırası: qrupun ``settings["degree_level"]``
(legacy/ATİS idxalı) → aktiv tələbələrin proqramı (çoxluq) → ixtisasın YEGANƏ
proqramı → bakalavr. ⚠️ ``Program.specialty_unit`` çox vaxt HƏM bakalavr, HƏM
magistr proqramına bağlıdır (klon: «Kompüter Mühəndisliyi»), ona görə
``plan_hours.program_for_offering``-in «ilk proqram» qaydası burada yetərli deyil.

**Ailə**: birləşik qrup («234 K ing») + alt qrupları («234 K ing-1/-2») —
``settings["parent_group"]`` izi və ya ``subgroup_rollup.is_subgroup_of`` ad
qaydası. Birləşik qrup olmadan nömrəli bacı-qruplar («235 İT-1 az / -2 az»)
«virtual ailə» sayılır (yalnız eyni müəllimli mühazirələr birləşir).

**Kohort** = tələbə vaxt xətti: alt qrupu olmayan qrup və ya birbaşa tələbəsi
olan birləşik qrup. Birləşik qrupun dərsi bütün alt qrup kohortlarını tutur.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.db.models import Count

from apps.registrar.public import schedule_publish, subgroup_rollup

from ..constants import BUILTIN_POLICY, PolicyLevel

#: Alt qrup nömrəsi: ayırıcıdan sonra 1–2 rəqəm («235 İT-1 az», «229 PM /2»). Üç rəqəmli
#: son («A-101», «A-102») qrupun ÖZ nömrəsidir — alt qrup sayılmır.
_TRAILING_NUMBER = re.compile(r"^(?P<base>.*?\D)[\s\-/]+\d{1,2}(?:\s+(?P<sector>az|ing|ru|en))?$", re.IGNORECASE)


@dataclass
class GroupInfo:
    id: str
    name: str
    unit_id: str
    degree: str = "bachelor"
    form: str = "full_time"
    students: int = 0
    curriculum_id: str = ""
    sector: str = "az"
    parent: str = ""
    children: list = field(default_factory=list)
    family: str = ""
    building: str = ""
    policy: dict = field(default_factory=dict)
    cohort: int | None = None
    cohorts: tuple = ()

    @property
    def is_master(self) -> bool:
        return self.degree in (PolicyLevel.MASTER, PolicyLevel.PHD)

    @property
    def policy_level(self) -> str:
        return PolicyLevel.PART_TIME if self.form == "part_time" else (self.degree or PolicyLevel.BACHELOR)


def _record_stats(organization, group_ids) -> dict:
    """Qrup → {students, degree, form, curriculum} — BİR aqreqat sorğusu."""
    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    rows = (
        Record.objects.filter(organization=organization, group_id__in=group_ids, status="enrolled")
        .values("group_id", "program__degree_level", "program__education_form", "curriculum_id")
        .annotate(n=Count("id"))
    )
    stats: dict = {}
    for row in rows:
        item = stats.setdefault(
            str(row["group_id"]), {"students": 0, "degree": Counter(), "form": Counter(), "curriculum": Counter()}
        )
        item["students"] += row["n"]
        item["degree"][row["program__degree_level"] or ""] += row["n"]
        item["form"][row["program__education_form"] or ""] += row["n"]
        if row["curriculum_id"]:
            item["curriculum"][str(row["curriculum_id"])] += row["n"]
    return stats


def _unique_program_degree(organization, unit_ids) -> dict:
    Program = django_apps.get_model("registrar", "Program")
    degrees: dict = {}
    for row in Program.objects.filter(organization=organization, specialty_unit_id__in=unit_ids).values(
        "specialty_unit_id", "degree_level"
    ):
        degrees.setdefault(str(row["specialty_unit_id"]), set()).add(row["degree_level"])
    return {unit: next(iter(values)) for unit, values in degrees.items() if len(values) == 1}


def _majority(counter: Counter) -> str:
    items = [(n, key) for key, n in counter.items() if key]
    return max(items)[1] if items else ""


def _settings(group) -> dict:
    return group.settings if isinstance(group.settings, dict) else {}


def _families(infos: dict, groups) -> None:
    """``parent`` / ``children`` / ``family`` sahələrini doldur."""
    by_unit: dict = {}
    for group in groups:
        by_unit.setdefault(str(group.parent_id or ""), []).append(group)
    for group in groups:
        info = infos[str(group.pk)]
        explicit = str(_settings(group).get("parent_group") or "")
        if explicit and explicit in infos and explicit != info.id:
            info.parent = explicit
            continue
        for other in by_unit.get(info.unit_id, []):
            if str(other.pk) != info.id and subgroup_rollup.is_subgroup_of(other.name, group.name):
                info.parent = str(other.pk)
                break
    for info in infos.values():
        if info.parent:
            infos[info.parent].children.append(info.id)
    for info in sorted(infos.values(), key=lambda item: item.name):
        info.children.sort(key=lambda gid: infos[gid].name)
        if info.parent:
            info.family = info.parent
        elif info.children:
            info.family = info.id
    # Virtual ailə — birləşik qrupu olmayan nömrəli bacı-qruplar.
    for unit_groups in by_unit.values():
        buckets: dict = {}
        for group in unit_groups:
            info = infos[str(group.pk)]
            if info.family:
                continue
            match = _TRAILING_NUMBER.match(" ".join(group.name.split()))
            if not match or not match.group("base"):
                continue
            sector = (match.group("sector") or subgroup_rollup.group_sector(group.name)).lower()
            combined = f"{match.group('base').strip()} {sector}"
            if subgroup_rollup.is_subgroup_of(combined, group.name):
                buckets.setdefault((match.group("base").strip().casefold(), sector), []).append(info)
        for members in buckets.values():
            if len(members) > 1:
                key = "v:" + min(member.id for member in members)
                for member in members:
                    member.family = key


def resolve_policy(info, rows_by_group: dict, rows_by_level: dict) -> dict:
    """Qrupun effektiv növbə siyasəti: qrup istisnası → pillə defoltu → daxili defolt."""
    level = info.policy_level
    builtin = dict(BUILTIN_POLICY.get(level) or BUILTIN_POLICY[PolicyLevel.BACHELOR])
    policy = {"bands": list(builtin["bands"]), "weekdays": [], "max_pairs_per_day": builtin["max_pairs_per_day"]}
    policy.update({"is_excluded": builtin["is_excluded"], "source": "builtin", "level": level})
    level_row = rows_by_level.get(level)
    if level_row is not None:
        if level_row.bands:
            policy["bands"] = list(level_row.bands)
        policy["weekdays"] = list(level_row.weekdays or [])
        if level_row.max_pairs_per_day:
            policy["max_pairs_per_day"] = level_row.max_pairs_per_day
        policy["is_excluded"] = bool(level_row.is_excluded)
        policy["source"] = "level"
    group_row = rows_by_group.get(info.id)
    if group_row is not None:
        if group_row.bands:
            policy["bands"] = list(group_row.bands)
        if group_row.weekdays:
            policy["weekdays"] = list(group_row.weekdays)
        if group_row.max_pairs_per_day:
            policy["max_pairs_per_day"] = group_row.max_pairs_per_day
        policy["is_excluded"] = bool(group_row.is_excluded)
        policy["source"] = "group"
    return policy


def policy_rows(organization) -> tuple[dict, dict]:
    Policy = django_apps.get_model("timetable", "GroupTimePolicy")
    by_group, by_level = {}, {}
    for row in Policy.objects.filter(organization=organization):
        if row.group_id:
            by_group[str(row.group_id)] = row
        elif row.level:
            by_level[row.level] = row
    return by_group, by_level


def load_groups(organization, groups) -> dict:
    """``{group_id: GroupInfo}`` — metadata + ailə + siyasət + korpus."""
    groups = list(groups)
    ids = [group.pk for group in groups]
    stats = _record_stats(organization, ids)
    unit_degrees = _unique_program_degree(organization, {group.parent_id for group in groups if group.parent_id})
    buildings = schedule_publish.group_buildings(organization, groups)
    by_group, by_level = policy_rows(organization)
    infos: dict = {}
    for group in groups:
        key = str(group.pk)
        meta = _settings(group)
        stat = stats.get(key) or {"students": 0, "degree": Counter(), "form": Counter(), "curriculum": Counter()}
        degree = (
            str(meta.get("degree_level") or "")
            or _majority(stat["degree"])
            or unit_degrees.get(str(group.parent_id or ""), "")
            or "bachelor"
        )
        form = str(meta.get("education_form") or "") or _majority(stat["form"]) or "full_time"
        infos[key] = GroupInfo(
            id=key,
            name=group.name,
            unit_id=str(group.parent_id or ""),
            degree=degree,
            form=form,
            students=int(stat["students"]),
            curriculum_id=_majority(stat["curriculum"]) or str(meta.get("curriculum_id") or ""),
            sector=str(meta.get("sector") or subgroup_rollup.group_sector(group.name) or "az").lower(),
            building=buildings.get(key, ""),
        )
    _families(infos, groups)
    for info in infos.values():
        info.policy = resolve_policy(info, by_group, by_level)
    return infos


def prune_groups(infos: dict, active_ids) -> dict:
    """Yalnız bu semestr açılışı olan qruplar + onların ailəsi (ata/alt qruplar) qalır.

    Fakültədə yüzlərlə köhnə (legacy) qrup ola bilər; açılışı olmayan qrupun
    tələbəsi yalnız ailə üzvü kimi (birləşik qrupun dərsinə gələn alt qrup) önəmlidir."""
    keep = {gid for gid in active_ids if gid in infos}
    for gid in list(keep):
        info = infos[gid]
        if info.parent:
            keep.add(info.parent)
    for gid in list(keep):
        keep.update(infos[gid].children)
    pruned = {gid: infos[gid] for gid in sorted(keep)}
    for info in pruned.values():
        info.children = [child for child in info.children if child in pruned]
        if info.parent and info.parent not in pruned:
            info.parent = ""
    return pruned


def assign_cohorts(infos: dict) -> list:
    """Kohort indeksləri: alt qrupsuz qrup və ya birbaşa tələbəli birləşik qrup.

    Qaytarır: kohort siyahısı ``[group_id]``; hər ``GroupInfo.cohorts`` = qrupun
    dərsinin tutduğu kohortlar (özü + alt qrupları, rekursiv)."""
    order = sorted(infos.values(), key=lambda item: (item.name, item.id))
    cohort_groups = []
    for info in order:
        if info.policy.get("is_excluded"):
            continue
        active_children = [c for c in info.children if not infos[c].policy.get("is_excluded")]
        if not active_children or info.students > 0:
            info.cohort = len(cohort_groups)
            cohort_groups.append(info.id)

    def collect(info, seen):
        if info.id in seen:
            return []
        seen.add(info.id)
        out = [info.cohort] if info.cohort is not None else []
        for child in info.children:
            out.extend(collect(infos[child], seen))
        return out

    for info in order:
        info.cohorts = tuple(dict.fromkeys(collect(info, set())))
    return cohort_groups


__all__ = ["GroupInfo", "assign_cohorts", "load_groups", "policy_rows", "prune_groups", "resolve_policy"]
