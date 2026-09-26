"""Struktur planı — təşkilat ağacını verilmiş YENİ formaya salır (sahib 2026-09-27).

Sahib: «Bu yeni strukturdur, artıq hər şey bu formadadır; sistemə baxanda mənim
göndərdiyim görünsün. Köhnə dataya baxanda bilinsin ki, əvvəl bu adda idi / buna
aid idi.» Plan JSON faylıdır (``scripts/data/qku_structure_*.json``) — yalnız
vahid adları, şəxs YOX. Hər plan vahidi üçün:

* ``from`` — mövcud vahid (tip + ad). Tapılsa ADI və/və ya VALİDEYNİ plana görə
  dəyişir, ID eyni qalır (üzvlüklər, jurnallar, qruplar bağlı qalır). Köhnə ad və
  köhnə valideyn ``settings["history"]``-yə yazılır — struktur ekranı onu
  «Əvvəlki ad / yer» kimi göstərir.
* ``from`` yoxdursa (və ya tapılmırsa) — YENİ vahid yaradılır.
* ``merge`` — başqa mövcud vahid bu vahidə QOVUŞUR: alt vahidləri və əhatə
  üzvlükləri köçürülür, özü arxivlənir (yalnız başqa istinad qalmayıbsa).
* ``specialties`` — plandakı fakültələrin altındakı bu adlı ixtisaslar (qrupları
  ilə birlikdə — ``OrgUnit.save`` path kaskadı) bu vahidin altına keçir.
* ``aliases`` — siyahıdakı bölmə başlığının yazılışı (``seed_staff_roster`` bölməni
  bununla DƏQİQ tanıyır; bax ``staff_roster.match_unit``).

İDEMPOTENT: tətbiq olunan vahid ``settings["structure_key"]`` alır, təkrar qaçış onu
açarla tapır və heç nə dəyişmir. Dry-run defolt; yazı yalnız ``apply=True`` ilə.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from types import SimpleNamespace

from django.utils.text import slugify

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

_WS = re.compile(r"\s+")
_FOLD = str.maketrans({"İ": "i", "I": "i", "ı": "i", "ə": "e", "ö": "o", "ü": "u", "ğ": "g", "ş": "s", "ç": "c"})


def norm(value) -> str:
    """Ad müqayisəsi: kiçik hərf, AZ hərfləri qatlanır, diakritiksiz, tək boşluq."""
    text = unicodedata.normalize("NFC", str(value or "")).translate(_FOLD).lower().translate(_FOLD)
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return _WS.sub(" ", text).strip()


def load_plan(path) -> dict:
    with open(path, encoding="utf-8") as handle:
        plan = json.load(handle)
    keys = set()
    for spec in plan.get("units", []):
        if not spec.get("key") or not spec.get("name") or not spec.get("type"):
            raise ValueError(f"Plan vahidi natamamdır: {spec}")
        if spec["key"] in keys:
            raise ValueError(f"Təkrar açar: {spec['key']}")
        if spec.get("parent") and spec["parent"] not in keys:
            raise ValueError(f"Valideyn əvvəl gəlməlidir: {spec['key']} → {spec['parent']}")
        keys.add(spec["key"])
    return plan


@dataclass
class Report:
    lines: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)

    def add(self, kind, text):
        self.counts[kind] = self.counts.get(kind, 0) + 1
        self.lines.append(f"[{kind}] {text}")


def _unique_slug(organization, name, taken):
    from .models import OrgUnit

    base = slugify(name.translate(_FOLD)) or "unit"
    slug, suffix = base, 2
    while slug in taken or OrgUnit.objects.filter(organization=organization, slug=slug).exists():
        slug, suffix = f"{base}-{suffix}", suffix + 1
    taken.add(slug)
    return slug


def _history_entry(plan, unit, parent_names) -> dict:
    return {
        "date": plan.get("date", ""),
        "source": plan.get("source", ""),
        "name": unit.name,
        "parent": parent_names.get(unit.parent_id, "") if unit.parent_id else "",
        "parent_id": str(unit.parent_id) if unit.parent_id else "",
    }


class _Planner:
    def __init__(self, organization, plan, *, apply, actor=None):
        from .models import OrgUnit

        self.org, self.plan, self.apply, self.actor = organization, plan, apply, actor
        self.source = plan.get("source", "structure-plan")
        self.report = Report()
        self.units = list(OrgUnit.objects.filter(organization=organization))
        self.names = {unit.id: unit.name for unit in self.units}  # cari (plan gedişində yenilənir)
        self.orig_names = dict(self.names)  # tarixçə üçün: vahidlərin plandan ƏVVƏLKİ adları
        self.resolved: dict = {}  # plan key → OrgUnit (və ya dry-run-da yaradılacaq yer tutucu)
        self.used_ids: set = set()
        self.slugs: set = set()

    # ── axtarış ──────────────────────────────────────────────────────────────
    def _by_key(self, key):
        wanted = f"{self.source}:{key}"
        return next((u for u in self.units if (u.settings or {}).get("structure_key") == wanted), None)

    def _find(self, unit_type, name):
        target = norm(name)
        hits = [
            u
            for u in self.units
            if u.is_active and u.unit_type == unit_type and norm(u.name) == target and u.id not in self.used_ids
        ]
        if len(hits) > 1:
            self.report.problems.append(f"«{name}» ({unit_type}) adında {len(hits)} aktiv vahid var — atlanır")
            return None
        return hits[0] if hits else None

    def _label(self, unit):
        return getattr(unit, "name", "—") if unit is not None else "— (kök)"

    # ── əsas ─────────────────────────────────────────────────────────────────
    def run(self):
        for spec in self.plan.get("units", []):
            self._unit(spec)
        for spec in self.plan.get("units", []):
            for merge in spec.get("merge", []):
                self._merge(spec, merge)
        for spec in self.plan.get("units", []):
            if spec.get("specialties"):
                self._specialties(spec)
        self._campuses()
        return self.report

    def _unit(self, spec):
        parent = self.resolved.get(spec.get("parent")) if spec.get("parent") else None
        unit = self._by_key(spec["key"])
        if unit is None:
            for source in spec.get("from", []):
                unit = self._find(source["type"], source["name"])
                if unit is not None:
                    break
        if unit is None:
            unit = self._find(spec["type"], spec["name"])
        if unit is None:
            self.report.add("YARADILIR", f"{spec['name']} [{spec['type']}] ← {self._label(parent)}")
            self.resolved[spec["key"]] = self._create(spec, parent)
            return
        self.used_ids.add(unit.id)
        self.resolved[spec["key"]] = unit
        new_parent_id = getattr(parent, "id", None)
        rename = unit.name != spec["name"]
        move = unit.parent_id != new_parent_id
        if rename or move:
            parts = []
            if rename:
                parts.append(f"ad: «{unit.name}» → «{spec['name']}»")
            if move:
                parts.append(f"yer: {self.names.get(unit.parent_id, '— (kök)')} → {self._label(parent)}")
            self.report.add("DƏYİŞİR", f"{spec['name']} [{unit.unit_type}] — " + "; ".join(parts))
        else:
            self.report.add("EYNİDİR", f"{spec['name']} [{unit.unit_type}]")
        if not self.apply:
            self.names[unit.id] = spec["name"]  # dry-run hesabatında alt vahidlər yeni adı görsün
            return
        settings = dict(unit.settings or {})
        if rename or move:
            settings.setdefault("history", []).append(_history_entry(self.plan, unit, self.orig_names))
        settings["structure_key"] = f"{self.source}:{spec['key']}"
        settings["aliases"] = sorted(set(settings.get("aliases") or []) | set(spec.get("aliases") or []))
        old = {"name": unit.name, "parent": str(unit.parent_id or "")}
        unit.name, unit.parent_id, unit.settings = spec["name"], new_parent_id, settings
        unit.save()
        self.names[unit.id] = unit.name
        if rename or move:
            self._audit(AuditAction.UPDATE, unit, old, {"name": unit.name, "parent": str(unit.parent_id or "")})

    def _create(self, spec, parent):
        if not self.apply:
            return SimpleNamespace(id=None, name=spec["name"], planned=True)
        from .models import OrgUnit

        unit = OrgUnit.objects.create(
            organization=self.org,
            parent_id=getattr(parent, "id", None),
            unit_type=spec["type"],
            name=spec["name"],
            slug=_unique_slug(self.org, spec["name"], self.slugs),
            settings={
                "structure_key": f"{self.source}:{spec['key']}",
                "aliases": sorted(set(spec.get("aliases") or [])),
                "history": [{"date": self.plan.get("date", ""), "source": self.source, "created": True}],
            },
        )
        self.units.append(unit)
        self.used_ids.add(unit.id)
        self.names[unit.id] = unit.name
        self._audit(AuditAction.CREATE, unit, None, {"name": unit.name, "unit_type": unit.unit_type})
        return unit

    def _merge(self, spec, merge):
        from .models import Membership, OrgUnit

        target = self.resolved.get(spec["key"])
        victim = self._find(merge["type"], merge["name"])
        if victim is None or target is None:
            if victim is None:
                self.report.add("QOVUŞMA-YOX", f"«{merge['name']}» tapılmadı (artıq qovuşub?)")
            return
        already = any(
            entry.get("merged_into") == str(getattr(target, "id", ""))
            for entry in (victim.settings or {}).get("history") or []
        )
        if already:
            self.report.add(
                "QOVUŞUB", f"«{victim.name}» artıq «{spec['name']}»-ə qovuşub (istinad qaldığı üçün aktivdir)"
            )
            return
        children = list(OrgUnit.objects.filter(parent=victim))
        memberships = Membership.objects.filter(scope_unit=victim)
        other_refs = self._other_references(victim)
        tail = f"; digər istinad: {other_refs} — ARXİVLƏNMİR" if other_refs else "; arxivlənir"
        self.report.add(
            "QOVUŞUR",
            f"«{victim.name}» → «{spec['name']}» (alt vahid {len(children)}, üzvlük {memberships.count()}{tail})",
        )
        if not self.apply or getattr(target, "id", None) is None:
            return
        for child in children:
            child.settings = dict(child.settings or {})
            child.settings.setdefault("history", []).append(_history_entry(self.plan, child, self.orig_names))
            child.parent_id = target.id
            child.save()
        memberships.update(scope_unit=target)
        settings = dict(victim.settings or {})
        settings.setdefault("history", []).append(
            {
                **_history_entry(self.plan, victim, self.orig_names),
                "merged_into": str(target.id),
                "merged_into_name": target.name,
            }
        )
        victim.settings = settings
        if not other_refs:
            victim.is_active = False
        victim.save()
        self._audit(AuditAction.UPDATE, victim, {"is_active": True}, {"merged_into": str(target.id)})

    def _other_references(self, unit) -> int:
        """Vahidə yönələn (alt vahid və üzvlük xaric) FK istinadlarının sayı."""
        from .models import Membership, OrgUnit

        total = 0
        for rel in unit._meta.related_objects:
            if rel.many_to_many or not rel.field.concrete:
                continue
            if (rel.related_model is OrgUnit and rel.field.name == "parent") or (
                rel.related_model is Membership and rel.field.name == "scope_unit"
            ):
                continue
            total += rel.related_model._base_manager.filter(**{rel.field.name: unit}).count()
        return total

    def _specialties(self, spec):
        target = self.resolved.get(spec["key"])
        faculty_ids = {
            getattr(self.resolved.get(s["key"]), "id", None) for s in self.plan["units"] if s["type"] == "faculty"
        } - {None}
        wanted = {norm(name) for name in spec["specialties"]}
        for unit in self.units:
            if not (unit.is_active and unit.unit_type == OrgUnitType.SPECIALTY and unit.parent_id in faculty_ids):
                continue
            if norm(unit.name) not in wanted or unit.parent_id == getattr(target, "id", None):
                continue
            self.report.add("İXTİSAS", f"{unit.name}: {self.names.get(unit.parent_id)} → {spec['name']}")
            if not self.apply or getattr(target, "id", None) is None:
                continue
            old_parent = unit.parent_id
            unit.settings = dict(unit.settings or {})
            unit.settings.setdefault("history", []).append(_history_entry(self.plan, unit, self.orig_names))
            unit.parent_id = target.id
            unit.save()
            self._audit(AuditAction.UPDATE, unit, {"parent": str(old_parent)}, {"parent": str(target.id)})

    def _campuses(self):
        wanted = self.plan.get("campuses") or {}
        if not wanted:
            return
        settings = dict(self.org.settings or {})
        campuses = [dict(item) for item in settings.get("campuses") or [] if isinstance(item, dict)]
        changed = False
        for item in campuses:
            extra = wanted.get(item.get("building"))
            if not extra:
                continue
            units = list(item.get("units") or [])
            known = {norm(u) for u in units}
            for name in extra:
                if norm(name) not in known:
                    units.append(name)
                    known.add(norm(name))
                    changed = True
                    self.report.add("KORPUS", f"{item.get('building')}: + {name}")
            item["units"] = units
        if changed and self.apply:
            settings["campuses"] = campuses
            self.org.settings = settings
            self.org.save(update_fields=["settings", "updated_at"])

    def _audit(self, action, unit, old, new):
        log_action(
            action=action,
            user=self.actor,
            organization=self.org,
            obj=unit,
            reason=f"structure plan {self.source}",
            old_values=old,
            new_values=new,
        )


def apply_structure_plan(organization, plan, *, apply=False, actor=None) -> Report:
    """Planı dry-run (defolt) və ya tətbiq rejimində işlədir; hesabat qaytarır."""
    return _Planner(organization, plan, apply=apply, actor=actor).run()


def unit_history(unit) -> list:
    """Struktur ekranı üçün «əvvəlki ad / yer» sətirləri (yaradılış qeydi xaric)."""
    rows = []
    for entry in (getattr(unit, "settings", None) or {}).get("history") or []:
        if entry.get("created"):
            continue
        rows.append(entry)
    return rows
