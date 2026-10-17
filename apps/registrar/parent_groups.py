"""Alt qruplar üçün ORTAQ ana qrup (sahib 2026-10-17).

Sahib: «234 K-1 var, 234 K-2 var, onların ortaq qrupu 234 K da olsun. Bu formada bəziləri var,
olmayanları doldur özün.»

MODEL (``organizations.group_split`` ilə eyni): ana qrup və alt qruplar EYNİ ixtisasın (``OrgUnit.parent``)
altında QARDAŞ ``OrgUnit(group)``-lardır; alt qrupun ``settings["parent_group"]`` ana qrupun id-sini saxlayır
(jurnal «alt qrup birləşməsi», imtahan təyinatı, dərs cədvəli ailəsi bu izi tanıyır). Tələbələr ALT QRUPDA
qalır — ana qrup birgə mühazirələrin (TAPŞIRIQ kitabçasının birləşik sətri) açılış konteyneridir. Bu modul
tələbə KÖÇÜRMÜR, açılış/qeydiyyat yaratmır; yalnız:

* çatışmayan ana qrupu yaradır (alt qrupların ixtisası, kurs/qəbul ili, dil sektoru, təhsil forması ilə);
* izi olmayan alt qrupa ``settings.parent_group`` yazır (mövcud ana qrupa və ya yenisinə).

ALT QRUP TANINMASI: ``schedule_docx_parse.parse_group_label`` («234 K-1», «234 K-2 ing», «235 İ-1 az»);
onun tutmadığı «234 K ing-1» (sektordan sonra «-N») da alt qrupdur. «534 TB 1» (boşluq + rəqəm) KÖHNƏ
formadır — yalnız ≥2 belə qardaş və mövcud ana qrup olanda bağlanır (yeni ana qrup yaradılmır).

ANA QRUPUN ADI: ``<rəqəm> <kod>`` + sektor («ing»/«rus»); az sektorunda kursun (eyni rəqəmli qrupların)
çoxluq konvensiyası: «234 BİO az», «234 K az» → « az» şəkilçisi; «235 K», «235 KE» → şəkilçisiz.

QEYRİ-MÜƏYYƏN (yazılmır, hesabata düşür): alt qruplar fərqli ixtisasda; ixtisası yoxdur; metadata
ziddiyyəti; eyni adlı bir neçə ana qrup; ana qrup başqa ixtisasdadır; arxiv qrupla ad toqquşması; iz
başqa/qeyri-aktiv qrupa baxır; tək alt qrup və ana qrup yoxdur; köhnə forma və ana qrup yoxdur.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from django.utils.text import slugify

from apps.organizations.models import OrgUnit
from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

from .schedule_docx_match import label_key
from .schedule_docx_parse import GroupLabel, parse_group_label, squash

#: Ana qrupa metadatadan köçürülən açarlar (``groups_registry.SETTING_KEYS`` + köhnə idxal açarları).
COPY_KEYS = (
    "language_sector",
    "sector",
    "course_year",
    "admission_year",
    "curriculum_id",
    "education_form",
    "degree_level",
)
#: Alt qruplar arasında FƏRQLİ ola bilməyən açarlar (boş dəyər müqayisəyə girmir).
CONSISTENT_KEYS = ("course_year", "admission_year", "education_form")
ORIGIN_KEY = "created_by_command"
ORIGIN = "ensure_parent_groups"
AUDIT_REASON = "groups: ortaq ana qrup (ensure_parent_groups) — sahibin 2026-10-17 tapşırığı"

_SECTOR_WORD = {"ing": "ing", "rus": "rus"}
_DASH_TAIL = re.compile(r"^(?P<base>.*\D)\s*-\s*(?P<num>\d)$")
_SPACE_TAIL = re.compile(r"^(?P<base>.*[^\W\d_])\s+(?P<num>\d)$")
_AZ_SUFFIX = re.compile(r"\s(az)$", re.IGNORECASE)

REPORT_HEADER = ("family", "specialty", "subgroups", "parent", "action", "reason", "linked")

ACTION_EXISTING = "existing"
ACTION_CREATED = "created"
ACTION_AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class SubLabel:
    label: GroupLabel
    legacy: bool = False


def subgroup_label(name: str) -> SubLabel | None:
    """Ad alt qrupdursa → :class:`SubLabel` (``label.sub`` dolu), deyilsə ``None``."""
    label = parse_group_label(name)
    if label is None:
        return None
    if label.sub:
        return SubLabel(label)
    text = squash(name)
    for pattern, legacy in ((_DASH_TAIL, False), (_SPACE_TAIL, True)):
        match = pattern.match(text)
        if not match:
            continue
        base = parse_group_label(match.group("base"))
        if base is not None and not base.sub:
            sub = GroupLabel(raw=base.raw, digits=base.digits, code=base.code, sector=base.sector, sub=match["num"])
            return SubLabel(sub, legacy=legacy)
    return None


def _settings(unit) -> dict:
    return unit.settings if isinstance(unit.settings, dict) else {}


def _trail(unit) -> str:
    return str(_settings(unit).get("parent_group") or "")


def _norm_name(name: str) -> str:
    return squash(name).casefold()


@dataclass
class Family:
    key: tuple
    subgroups: list = field(default_factory=list)
    legacy: bool = False
    parent: object = None
    action: str = ""
    reason: str = ""
    proposed_name: str = ""
    linked: int = 0

    @property
    def code(self) -> str:
        """Alt qrupların kod yazılışı: böyük hərfli forma, sonra ən çox işlənən («BİO» > «Bio»)."""
        codes = [sub.label.code for _unit, sub in self.subgroups]
        ranked = sorted(set(codes), key=lambda code: (code != code.upper(), -codes.count(code), code))
        return ranked[0] if ranked else ""

    @property
    def display(self) -> str:
        digits, _code, sector = self.key
        return f"{digits} {self.code} {sector}".strip()


class ParentGroupPlanner:
    """Təşkilatın bütün qruplarını oxuyur, ailələri qurur, qərarı verir; ``apply`` yazır."""

    def __init__(self, organization):
        self.organization = organization
        self.units = list(
            OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP).select_related("parent")
        )
        self.by_pk = {str(unit.pk): unit for unit in self.units}
        self.families: dict[tuple, Family] = {}
        self.parents_by_key: dict[tuple, list] = {}
        self.sub_pks: set[str] = set()
        for unit in self.units:
            sub = subgroup_label(unit.name)
            if sub is not None:
                self.sub_pks.add(str(unit.pk))
                if unit.is_active:
                    family = self.families.setdefault(label_key(sub.label), Family(key=label_key(sub.label)))
                    family.subgroups.append((unit, sub))
                    family.legacy = family.legacy or sub.legacy
                continue
            label = parse_group_label(unit.name)
            if label is not None:
                self.parents_by_key.setdefault(label_key(label), []).append(unit)
        for family in self.families.values():
            family.subgroups.sort(key=lambda pair: _norm_name(pair[0].name))
        self.az_suffix_by_digits = self._az_conventions()

    # ── ad konvensiyası ─────────────────────────────────────────────────
    def _az_conventions(self) -> dict:
        votes: dict[str, Counter] = {}
        for units in self.parents_by_key.values():
            for unit in units:
                label = parse_group_label(unit.name)
                if not unit.is_active or label is None or label.sector != "az":
                    continue
                explicit = bool(_AZ_SUFFIX.search(squash(unit.name)))
                votes.setdefault(label.digits, Counter())[explicit] += 1
        return {digits: counter[True] > counter[False] for digits, counter in votes.items()}

    def proposed_name(self, family: Family) -> str:
        digits, _code, sector = family.key
        name = f"{digits} {family.code}"
        if sector in _SECTOR_WORD:
            return f"{name} {_SECTOR_WORD[sector]}"
        if sector == "az" and self.az_suffix_by_digits.get(digits):
            return f"{name} az"
        return name

    # ── qərar ───────────────────────────────────────────────────────────
    def _ambiguous(self, family: Family, reason: str) -> Family:
        family.action, family.reason = ACTION_AMBIGUOUS, reason
        return family

    def decide(self, family: Family) -> Family:
        subgroups = [unit for unit, _sub in family.subgroups]
        specialties = {unit.parent_id for unit in subgroups}
        if len(specialties) > 1:
            return self._ambiguous(family, "subgroups_in_different_specialties")
        specialty_id = next(iter(specialties))
        if specialty_id is None:
            return self._ambiguous(family, "no_specialty")
        for key in CONSISTENT_KEYS:
            values = {str(_settings(unit).get(key) or "").strip() for unit in subgroups} - {""}
            if len(values) > 1:
                return self._ambiguous(family, f"metadata_conflict:{key}")

        same_name = self.parents_by_key.get(family.key, [])
        active_here = [unit for unit in same_name if unit.is_active and unit.parent_id == specialty_id]
        trails = {_trail(unit) for unit in subgroups} - {""}
        trail_parent = None
        if trails:
            if len(trails) > 1:
                return self._ambiguous(family, "trail_conflict")
            target = self.by_pk.get(next(iter(trails)))
            if (
                target is None
                or not target.is_active
                or target.parent_id != specialty_id
                or str(target.pk) in self.sub_pks
            ):
                return self._ambiguous(family, "trail_stale")
            if active_here and target not in active_here:
                return self._ambiguous(family, "trail_conflict")
            trail_parent = target

        if trail_parent is None and len(active_here) > 1:
            return self._ambiguous(family, "duplicate_parent")
        parent = trail_parent or (active_here[0] if active_here else None)
        if parent is not None:
            for key in CONSISTENT_KEYS:
                mine = str(_settings(parent).get(key) or "").strip()
                theirs = {str(_settings(unit).get(key) or "").strip() for unit in subgroups} - {""}
                if mine and theirs and mine not in theirs:
                    return self._ambiguous(family, f"parent_metadata_conflict:{key}")
            if family.legacy and len(subgroups) < 2:
                return self._ambiguous(family, "legacy_single_subgroup")
            family.parent, family.action = parent, ACTION_EXISTING
            return family

        if family.legacy:
            return self._ambiguous(family, "legacy_form_no_parent")
        if len(subgroups) < 2:
            return self._ambiguous(family, "single_subgroup_no_parent")
        if any(unit.is_active for unit in same_name):
            return self._ambiguous(family, "parent_in_other_specialty")
        family.proposed_name = self.proposed_name(family)
        wanted = _norm_name(family.proposed_name)
        if same_name or any(_norm_name(unit.name) == wanted for unit in self.units):
            return self._ambiguous(family, "archived_name_clash")
        family.action = ACTION_CREATED
        return family

    def plan(self) -> list[Family]:
        return [self.decide(family) for _key, family in sorted(self.families.items())]

    # ── yazı ────────────────────────────────────────────────────────────
    def _unique_slug(self, name: str) -> str:
        base = slugify(name) or "group"
        slug, suffix = base, 2
        while OrgUnit.objects.filter(organization=self.organization, slug=slug).exists():
            slug, suffix = f"{base}-{suffix}", suffix + 1
        return slug

    def _create_parent(self, family: Family):
        source = family.subgroups[0][0]
        raw = _settings(source)
        blob = {key: raw[key] for key in COPY_KEYS if key in raw and raw[key] not in ("", None)}
        blob[ORIGIN_KEY] = ORIGIN
        unit = OrgUnit.objects.create(
            organization=self.organization,
            parent_id=source.parent_id,
            unit_type=OrgUnitType.GROUP,
            name=family.proposed_name,
            slug=self._unique_slug(family.proposed_name),
            code="",
            settings=blob,
            is_active=True,
        )
        log_action(
            action=AuditAction.CREATE,
            organization=self.organization,
            obj=unit,
            reason=AUDIT_REASON,
            new_values={"subgroups": [str(sub.pk) for sub, _label in family.subgroups], "name": unit.name},
        )
        return unit

    def _link(self, unit, parent) -> bool:
        if _trail(unit) == str(parent.pk):
            return False
        blob = dict(_settings(unit))
        old = blob.get("parent_group")
        blob["parent_group"] = str(parent.pk)
        unit.settings = blob
        unit.save(update_fields=["settings", "updated_at"])
        log_action(
            action=AuditAction.UPDATE,
            organization=self.organization,
            obj=unit,
            reason=AUDIT_REASON,
            old_values={"parent_group": old},
            new_values={"parent_group": str(parent.pk), "parent_group_name": parent.name},
        )
        return True

    def apply(self, families: list[Family]) -> None:
        for family in families:
            if family.action == ACTION_CREATED:
                family.parent = self._create_parent(family)
            if family.action in (ACTION_CREATED, ACTION_EXISTING):
                family.linked = sum(1 for unit, _sub in family.subgroups if self._link(unit, family.parent))


def counters(families: list[Family]) -> dict:
    """``apply``-dan sonra (dry-run-da da — yazı tranzaksiyada gedib geri alınır) saylar."""
    out = Counter(parents_existing=0, parents_created=0, subgroups_linked=0, subgroups_already_linked=0, ambiguous=0)
    out["families"] = len(families)
    for family in families:
        if family.action == ACTION_AMBIGUOUS:
            out["ambiguous"] += 1
            continue
        out["parents_existing" if family.action == ACTION_EXISTING else "parents_created"] += 1
        out["subgroups_linked"] += family.linked
        out["subgroups_already_linked"] += len(family.subgroups) - family.linked
    return dict(out)


def report_rows(families: list[Family]):
    for family in families:
        specialty = family.subgroups[0][0].parent.name if family.subgroups and family.subgroups[0][0].parent else ""
        parent = family.parent.name if family.parent is not None else family.proposed_name
        yield (
            family.display,
            specialty,
            " | ".join(unit.name for unit, _sub in family.subgroups),
            parent,
            family.action,
            family.reason,
            family.linked,
        )


__all__ = [
    "ACTION_AMBIGUOUS",
    "ACTION_CREATED",
    "ACTION_EXISTING",
    "REPORT_HEADER",
    "ParentGroupPlanner",
    "counters",
    "report_rows",
    "subgroup_label",
]
