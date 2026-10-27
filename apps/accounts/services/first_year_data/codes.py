"""«Tələbə kodu» (``UserProfile.institutional_identifier``) olmayan 1-ci kurs tələbələrinə kod (sahib 2026-10-27).

İki mənbə, bu sıra ilə:

1. **Köhnə sistemin tələbə id-si** — legacy delta paketində (``ems-legacy-delta/1``: ``students`` +
   ``expelled_students``) tələbənin FİN-i ilə tapılan legacy ``students.id``. Delta bu tələbələri FİN ilə tutub,
   amma id-ni kod kimi yazmayıb. Yalnız heç bir hesabda kod olmayan VƏ cutover ledger-ində başqa hesaba bağlı
   olmayan id verilir; eyni FİN-in iki legacy sətri varsa: azad edilməyən → legacy qrupu cari qrupla eyni adlı →
   ən kiçik id.
2. **Qrup nömrəsi** (legacy id-si olmayanlar) — format ``<N><GG><SS>`` (yalnız rəqəmlər):

   * ``N``  — qrup adındakı ilk ≥2 rəqəmli ədəd, öndəki sıfırlar atılır («236 İT» → 236, «3/336F1» → 336,
     «036 ing» → 36);
   * ``GG`` — qrupun eyni ``N``-li qruplar arasında sıra nömrəsi (təşkilatın BÜTÜN qrup vahidləri, ad açarı + pk
     sırası ilə; 01–99) — «236 İT» və «236 BİO» eyni ``N`` daşıyır, ``GG`` onları ayırır;
   * ``SS`` — tələbənin qrup daxilində sıra nömrəsi (01–99): soyad, ad, hesab id-si sırası ilə, həmin prefiksdə
     artıq olan ən böyük nömrədən sonra.

   Nəticə ən azı 6 rəqəmdir (``N`` ≥ 10) — legacy id-lər (hazırda ≤ 5 rəqəm) ilə üst-üstə düşmür; hər kod yazılmadan
   əvvəl təşkilatdakı bütün mövcud kodlarla (registr/NFKC dözümlü) yoxlanılır, toqquşanda növbəti ``SS`` götürülür.

Yazı FILL-ONLY-dir: ``UPDATE … WHERE institutional_identifier IS NULL OR = ''`` — dolu kod heç vaxt dəyişmir.
"""

from __future__ import annotations

import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from django.apps import apps as django_apps
from django.db.models import Q
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ...identity import canonical_identity
from .scope import name_key

BATCH_RESOURCE = "accounts.first_year_codes_batch"
LEGACY_FORMAT_PREFIX = "ems-legacy-delta/"
_NUMBER_RE = re.compile(r"\d{2,}")
MAX_ORDINAL = 99
MAX_SEQUENCE = 99
SHOWN = (
    "targets",
    "legacy_assigned",
    "legacy_multi_by_group",
    "legacy_multi_lowest",
    "group_assigned",
    "group_collision_bumped",
    "written",
)


class CodesError(Exception):
    """Fayl / giriş xətası (sabit kod, şəxsi data yoxdur)."""


class LegacyIndex:
    """Legacy delta paketindən FİN → legacy id-lər (və qrup adları)."""

    def __init__(self, by_fin: dict, groups: dict, expelled: set):
        self.by_fin = by_fin
        self.groups = groups
        self.expelled = expelled

    @classmethod
    def load(cls, path) -> "LegacyIndex":
        try:
            raw = Path(path).read_bytes()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            data = json.loads(raw)
        except (OSError, ValueError):
            raise CodesError("legacy_bundle_unreadable") from None
        if not isinstance(data, dict) or not str(data.get("format") or "").startswith(LEGACY_FORMAT_PREFIX):
            raise CodesError("legacy_bundle_bad_format")
        by_fin: dict = defaultdict(dict)
        expelled: set = set()
        for section in ("students", "expelled_students"):
            for row in data.get(section) or []:
                if not isinstance(row, dict):
                    continue
                legacy_id = str(row.get("id") or "").strip()
                fin = str(row.get("fincode") or "").strip().upper()
                if not legacy_id.isdigit() or not fin:
                    continue
                by_fin[fin].setdefault(legacy_id, row)
                if section == "expelled_students" or str(row.get("azadedildi") or "0") == "1":
                    expelled.add(legacy_id)
        groups = {
            str(group.get("id")): str(group.get("name") or "")
            for group in data.get("groups") or []
            if isinstance(group, dict)
        }
        return cls(dict(by_fin), groups, expelled)


def group_number(name) -> str:
    """Qrup adındakı ilk ≥2 rəqəmli ədəd (öndəki sıfırsız); yoxdursa / sıfırdırsa ``""``."""

    match = _NUMBER_RE.search(str(name or ""))
    if match is None:
        return ""
    number = match.group(0).lstrip("0")
    return number if len(number) >= 2 else ""


def _is_empty(value) -> bool:
    return not str(value or "").strip()


class CodePlanner:
    """Kod planı (YAZMIR). ``plan()`` → ``[(record, code, source)]``; saylar ``counts``-dadır."""

    def __init__(self, organization, records, legacy: LegacyIndex, counts: Counter):
        self.organization = organization
        self.records = records
        self.legacy = legacy
        self.counts = counts
        UserProfile = django_apps.get_model("accounts", "UserProfile")
        self.used = {
            canonical_identity(value)
            for value in UserProfile.objects.exclude(institutional_identifier=None).values_list(
                "institutional_identifier", flat=True
            )
            if not _is_empty(value)
        }
        LegacyEntityMap = django_apps.get_model("legacy_import", "LegacyEntityMap")
        self.ledger = dict(
            LegacyEntityMap.objects.filter(organization=organization, entity_type="student").values_list(
                "legacy_pk", "target_pk"
            )
        )
        self.examples: list = []

    # ── 1. legacy id ────────────────────────────────────────────────────
    def _available(self, legacy_id: str, user_pk) -> bool:
        if canonical_identity(legacy_id) in self.used:
            return False
        target = self.ledger.get(legacy_id)
        return target is None or str(target) == str(user_pk)

    def _pick(self, record, ids: list) -> str:
        active = [legacy_id for legacy_id in ids if legacy_id not in self.legacy.expelled] or ids
        if len(active) == 1:
            return active[0]
        current = name_key(getattr(record.group, "name", ""))
        rows = self.legacy.by_fin[(record.student.profile.fin or "").strip().upper()]
        same_group = [
            legacy_id
            for legacy_id in active
            if current and name_key(self.legacy.groups.get(str(rows[legacy_id].get("group_id")), "")) == current
        ]
        if len(same_group) == 1:
            self.counts["legacy_multi_by_group"] += 1
            return same_group[0]
        self.counts["legacy_multi_lowest"] += 1
        return min(active, key=int)

    def _legacy_pass(self, targets) -> tuple[list, list]:
        planned, rest = [], []
        for record in targets:
            fin = (record.student.profile.fin or "").strip().upper()
            rows = self.legacy.by_fin.get(fin) if fin else None
            if not rows:
                rest.append(record)
                continue
            ids = sorted((legacy_id for legacy_id in rows if self._available(legacy_id, record.student_id)), key=int)
            if not ids:
                self.counts["skip_legacy_id_taken"] += 1
                continue
            legacy_id = ids[0] if len(ids) == 1 else self._pick(record, ids)
            self.used.add(canonical_identity(legacy_id))
            planned.append((record, legacy_id, "legacy"))
            self.counts["legacy_assigned"] += 1
        return planned, rest

    # ── 2. qrup nömrəsi ─────────────────────────────────────────────────
    def _ordinals(self) -> dict:
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        by_number: dict = defaultdict(list)
        for pk, name in OrgUnit.objects.filter(organization=self.organization, unit_type="group").values_list(
            "pk", "name"
        ):
            number = group_number(name)
            if number:
                by_number[number].append((name_key(name), str(pk), pk))
        ordinals = {}
        for number, units in by_number.items():
            for index, (_key, _spk, pk) in enumerate(sorted(units), start=1):
                ordinals[pk] = (number, index)
        return ordinals

    def _next_sequence(self, prefix: str) -> int:
        width = len(prefix) + 2
        taken = [
            int(code[len(prefix) :])
            for code in self.used
            if len(code) == width and code.startswith(prefix) and code[len(prefix) :].isdigit()
        ]
        return max(taken, default=0) + 1

    def _group_pass(self, rest) -> list:
        ordinals = self._ordinals()
        by_prefix: dict = defaultdict(list)
        for record in rest:
            if record.group_id is None:
                self.counts["skip_no_group"] += 1
                continue
            number, ordinal = ordinals.get(record.group_id, ("", 0))
            if not number:
                self.counts["skip_group_without_number"] += 1
                continue
            if ordinal > MAX_ORDINAL:
                self.counts["skip_group_ordinal_overflow"] += 1
                continue
            by_prefix[f"{number}{ordinal:02d}"].append(record)
        planned = []
        for prefix in sorted(by_prefix):
            members = sorted(
                by_prefix[prefix],
                key=lambda rec: (name_key(rec.student.last_name), name_key(rec.student.first_name), rec.student_id),
            )
            sequence = self._next_sequence(prefix)
            for record in members:
                code = f"{prefix}{sequence:02d}"
                while canonical_identity(code) in self.used and sequence <= MAX_SEQUENCE:
                    self.counts["group_collision_bumped"] += 1
                    sequence += 1
                    code = f"{prefix}{sequence:02d}"
                if sequence > MAX_SEQUENCE:
                    self.counts["skip_group_sequence_overflow"] += 1
                    continue
                self.used.add(canonical_identity(code))
                planned.append((record, code, "group"))
                self.counts["group_assigned"] += 1
                sequence += 1
        return planned

    def plan(self) -> list:
        targets = [record for record in self.records if _is_empty(record.student.profile.institutional_identifier)]
        self.counts["targets"] += len(targets)
        legacy_planned, rest = self._legacy_pass(targets)
        group_planned = self._group_pass(rest)
        self.examples = sorted(code for _record, code, _source in group_planned)[:3]
        return legacy_planned + group_planned


def write_codes(organization, planned, *, actor, batch: str, counts: Counter) -> None:
    """FILL-ONLY yazı + BİR audit sətri (id → kod → mənbə; şəxsi data yoxdur)."""

    UserProfile = django_apps.get_model("accounts", "UserProfile")
    empty = Q(institutional_identifier__isnull=True) | Q(institutional_identifier="")
    written = []
    now = timezone.now()
    for record, code, source in planned:
        updated = (
            UserProfile.objects.filter(pk=record.student.profile.pk)
            .filter(empty)
            .update(institutional_identifier=code, updated_at=now)
        )
        if updated:
            written.append([record.student_id, code, source])
    counts["written"] += len(written)
    if not written:
        return
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=organization,
        new_values={"counts": dict(sorted(counts.items())), "assigned": written},
        reason=f"first_year_student_codes {batch}",
        resource_type=BATCH_RESOURCE,
        resource_id=batch,
        resource_repr=batch,
    )


__all__ = ["BATCH_RESOURCE", "CodePlanner", "CodesError", "LegacyIndex", "SHOWN", "group_number", "write_codes"]
