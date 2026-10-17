"""Test / zibil qruplar (QA-2 F-16, sahib 2026-10-17: «tövsiyə olunan kimi et»).

Qrup seçicilərinin başında «.», «test1543», «Silinmelidir», «aaa» kimi vahidlər görünürdü. Qayda:

* namizəd = adı açıq-aşkar test / zibil olan QRUP və ya İXTİSAS vahidi (yalnız işarə, «test», «silinməli», «aaa» …);
  real adlara (məs. «Xaric olanlar») toxunulmur;
* İSTİFADƏ OLUNAN namizədə toxunulmur — ``OrgUnit``-ə istinad edən HƏR əlaqə (tələbə qeydi, açılış, üzvlük, alt vahid,
  dərs yükü …) Django metadatasından avtomatik yoxlanılır, yeni əlaqə əlavə olunanda da qayda pozulmur;
* istifadə olunmayan namizəd SİLİNMİR — ``is_active=False`` + ``settings.junk_archived`` izi (geri qaytarıla bilər).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.utils import timezone

from core.constants import OrgUnitType

CANDIDATE_TYPES = (OrgUnitType.GROUP, OrgUnitType.SPECIALTY)
JUNK_SETTING = "junk_archived"

_FOLD = str.maketrans({"ə": "e", "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u"})
_JUNK_PATTERNS = (
    re.compile(r"test"),
    re.compile(r"silinmel|silinecek|silmek|\bsil\b"),
    re.compile(r"^(a{2,}|x{2,}|q{2,}|z{2,}|qwe\w*|asd\w*|deneme|temp|tmp)$"),
)

REPORT_HEADER = ("unit_id", "unit_type", "name", "faculty_path", "reason", "references", "action")


def fold(name: str) -> str:
    value = unicodedata.normalize("NFC", str(name or "")).replace("İ", "i").replace("I", "ı").lower()
    return " ".join(value.translate(_FOLD).split())


def junk_reason(name: str) -> str:
    """Boş sətir = real ad. Əks halda səbəb kodu."""
    value = fold(name)
    if not re.search(r"[0-9a-z]", value) or len(re.sub(r"[^0-9a-z]", "", value)) < 2:
        return "no_letters"
    for pattern in _JUNK_PATTERNS:
        if pattern.search(value):
            return "test_name"
    return ""


def _reference_relations():
    """``OrgUnit``-ə istinad edən bütün əlaqələr (FK / O2O / M2M) — avtomatik."""
    model = django_apps.get_model("organizations", "OrgUnit")
    relations = []
    for relation in model._meta.related_objects:
        if relation.related_model is None:
            continue
        relations.append(relation)
    return relations


def reference_counts(unit) -> dict:
    """``{"app.Model.field": say}`` — bu vahidə istinad edən sətirlər (bütün əlaqələr üzrə, yalnız sıfırdan böyük)."""
    counts = {}
    for relation in _reference_relations():
        related = relation.related_model
        if relation.many_to_many:
            accessor = relation.get_accessor_name()
            count = getattr(unit, accessor).count() if accessor else 0
        else:
            count = related._base_manager.filter(**{relation.field.name: unit}).count()
        if count:
            counts[f"{related._meta.label}.{relation.field.name}"] = count
    return counts


def references(unit) -> int:
    return sum(reference_counts(unit).values())


@dataclass
class Row:
    unit: object
    reason: str
    refs: dict
    action: str

    def csv_row(self):
        return (
            str(self.unit.pk),
            self.unit.unit_type,
            self.unit.name,
            self.unit.path,
            self.reason,
            "; ".join(f"{key}={value}" for key, value in sorted(self.refs.items())),
            self.action,
        )


def plan(organization) -> list[Row]:
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    rows = []
    for unit in OrgUnit.objects.filter(organization=organization, unit_type__in=CANDIDATE_TYPES).order_by("path"):
        reason = junk_reason(unit.name)
        if not reason:
            continue
        if not unit.is_active:
            rows.append(Row(unit, reason, {}, "already_inactive"))
            continue
        refs = reference_counts(unit)
        rows.append(Row(unit, reason, refs, "skip_in_use" if refs else "archive"))
    return rows


def apply(rows) -> int:
    done = 0
    stamp = timezone.now().isoformat()
    for row in rows:
        if row.action != "archive":
            continue
        unit = row.unit
        settings = dict(unit.settings or {})
        settings[JUNK_SETTING] = {"at": stamp, "reason": row.reason}
        unit.settings = settings
        unit.is_active = False
        unit.save(update_fields=["is_active", "settings", "updated_at"])
        row.action = "archived"
        done += 1
    return done


def counters(rows) -> dict:
    return {
        "candidates": len(rows),
        "archive": sum(1 for row in rows if row.action in ("archive", "archived")),
        "skip_in_use": sum(1 for row in rows if row.action == "skip_in_use"),
        "already_inactive": sum(1 for row in rows if row.action == "already_inactive"),
    }


__all__ = [
    "CANDIDATE_TYPES",
    "JUNK_SETTING",
    "REPORT_HEADER",
    "apply",
    "counters",
    "junk_reason",
    "plan",
    "reference_counts",
    "references",
]
