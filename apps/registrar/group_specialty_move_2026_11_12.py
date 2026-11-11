"""Qrupu tələbələrinin proqram ixtisasının altına köçür (sahib 2026-11-12) — ``move_groups_to_program_specialty``.

Problem: tələbənin dekanlığa müraciəti qrupdan yuxarı ilk ``faculty`` əcdadına gedir
(``applications.routing.resolve_scope_unit``). Qrup səhv ixtisasın altında olanda (məs. «136 T ing» — «Turizm işi»,
«Magistratura və doktorantura» altında; tələbələrin proqramı isə «Tarix (Tədris Ingilis Dilində)», «Siyasi və ictimai
elmlər məktəbi») müraciət yanlış dekanlığa düşür. Prob: ``scripts/prod_ops/org_tree_probe.py``.

Qayda — qrup YALNIZ bu halda köçürülür: qrupun (``unit_type=group``, aktiv, valideyni qrup deyil) BÜTÜN aktiv
tələbələrinin (``StudentAcademicRecord.is_active``) ``Program.specialty_unit``-i EYNİDİR, o ixtisas aktivdir,
bir məktəbin (``faculty``) altındadır və qrupun cari valideynindən fərqlidir. Köçürmə ``unit.save()`` ilə
(path nəsillərə ötürülür; ``queryset.update`` YOX). Köhnə valideyn ``settings["history"]``-də qalır
(``structure_plan._history_entry`` ilə eyni açarlar + ``batch`` / ``to``), hər köçürmə audit sətri yazır.

Atlananlar (hər biri ``group_move: skipped group=<ad> reason=<kod>``): tələbələr bir neçə ixtisasa bölünüb
(``split_specialties``), proqramın ixtisası yoxdur (``no_program_specialty``), 3-dən az aktiv tələbə
(``too_few_students``), Kollec / Lifelong / İngilis dili mərkəzi (qrupun özü və ya hədəf — ``college`` /
``lifelong`` / ``language_centre``), hədəf səviyyə məktəbinin («Magistratura…», «Bakalavriat…») altındadır
(``level_school``), qrupun ``settings.degree_level``-i tələbələrin proqram səviyyəsindən fərqlidir və məktəb
dəyişir (``level_mismatch``), hədəf ixtisas passiv / ixtisas deyil / məktəbsizdir. Alt qruplar (valideyni qrup)
valideynlə birlikdə gedir — yalnız sayılır (``nested``).

``undo(batch)`` yalnız HƏLƏ həmin paketin hədəfində olan qrupları köhnə valideynə qaytarır.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

PREFIX = "group_move:"
SOURCE = "move_groups_to_program_specialty"
RESOURCE = "registrar.group_specialty_move_2026_11_12"
REASON = "Sahib 2026-11-12: qrup tələbələrinin proqram ixtisasının altına (müraciət düzgün dekanlığa getsin)"
UNDO_REASON = "Sahib 2026-11-12: qrupun ixtisas köçürməsinin geri qaytarılması"
MIN_STUDENTS = 3
BATCH_RE = re.compile(r"^groupmove-\d{8}-\d{6}-[0-9a-f]{4}$")

#: Qatlanmış (ascii, kiçik hərf) ad parçaları → atlama kodu. Əcdad zəncirində (özü daxil) axtarılır.
_EXCLUDED = (
    ("kollec", "college"),
    ("kolec", "college"),
    ("college", "college"),
    ("lifelong", "lifelong"),
    ("ingilis dili merkezi", "language_centre"),
    ("english language cent", "language_centre"),
)
#: Səviyyə məktəbləri — struktur bölməsidir, ixtisasın düzgün evi deyil (hədəf üçün yoxlanılır).
_LEVEL_SCHOOLS = ("magistratura", "bakalavriat", "doktorantura")
_FOLD = str.maketrans({"ə": "e", "Ə": "e", "ı": "i", "İ": "i", "I": "i"})


def fold(text) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").translate(_FOLD))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).lower()


def slug(text) -> str:
    return re.sub(r"[^a-z0-9]+", "_", fold(text)).strip("_") or "none"


def new_batch() -> str:
    return f"groupmove-{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _model(app, name):
    return django_apps.get_model(app, name)


class Tree:
    """Təşkilatın bütün bölmələri yaddaşda — əcdad zənciri, məktəb, istisna markerləri."""

    def __init__(self, organization):
        OrgUnit = _model("organizations", "OrgUnit")
        self.units = {unit.pk: unit for unit in OrgUnit.objects.filter(organization=organization)}

    def chain(self, unit):
        """Özü + əcdadlar (aşağıdan yuxarı), dövr qoruyucusu ilə."""
        out, seen = [], set()
        while unit is not None and unit.pk not in seen:
            seen.add(unit.pk)
            out.append(unit)
            unit = self.units.get(unit.parent_id)
        return out

    def school(self, unit):
        return next((node for node in self.chain(unit) if node.unit_type == "faculty"), None)

    def excluded(self, unit) -> str:
        settings = unit.settings if isinstance(unit.settings, dict) else {}
        legacy = settings.get("legacy") if isinstance(settings.get("legacy"), dict) else {}
        if fold(legacy.get("kollec_or_uni")).strip() in ("kollec", "college"):
            return "college"
        for node in self.chain(unit):
            name = fold(node.name)
            for marker, code in _EXCLUDED:
                if marker in name:
                    return code
        return ""


def _line(command, **pairs):
    command.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in pairs.items()))


def _skip(command, counts, unit, reason):
    counts["skipped"] += 1
    command.stdout.write(f"{PREFIX} skipped group={slug(unit.name)} reason={reason}")


def _student_rows(organization):
    SAR = _model("registrar", "StudentAcademicRecord")
    rows = defaultdict(list)
    for group_id, spec_id, level in SAR.objects.filter(
        organization=organization, is_active=True, group__isnull=False
    ).values_list("group_id", "program__specialty_unit_id", "program__degree_level"):
        rows[group_id].append((spec_id, str(level or "").strip().lower()))
    return rows


def _decide(tree, unit, rows):
    """``(hədəf, None)`` köçürmə üçün, ``(None, kod)`` atlama, ``(None, "")`` artıq yerindədir."""

    if len(rows) < MIN_STUDENTS:
        return None, "too_few_students"
    spec_ids = {spec_id for spec_id, _level in rows}
    if None in spec_ids:
        return None, "no_program_specialty"
    if len(spec_ids) > 1:
        return None, "split_specialties"
    target = tree.units.get(next(iter(spec_ids)))
    if target is None or not target.is_active:
        return None, "target_inactive"
    if target.unit_type != "specialty":
        return None, "target_not_specialty"
    if target.pk == unit.parent_id:
        return None, ""
    excluded = tree.excluded(unit) or tree.excluded(target)
    if excluded:
        return None, excluded
    school = tree.school(target)
    if school is None:
        return None, "target_no_school"
    if any(marker in fold(school.name) for marker in _LEVEL_SCHOOLS):
        return None, "level_school"
    settings = unit.settings if isinstance(unit.settings, dict) else {}
    group_level = str(settings.get("degree_level") or "").strip().lower()
    levels = {level for _spec, level in rows if level}
    current_school = tree.school(unit)
    if group_level and levels and group_level not in levels and getattr(current_school, "pk", None) != school.pk:
        return None, "level_mismatch"
    return target, None


def _reparent(unit, new_parent, history_entry):
    OrgUnit = _model("organizations", "OrgUnit")
    locked = OrgUnit.objects.select_for_update().get(pk=unit.pk)
    settings = dict(locked.settings or {})
    settings["history"] = [*list(settings.get("history") or []), history_entry]
    locked.parent_id, locked.settings = new_parent.pk, settings
    locked.save()  # path + nəsillərin path-i (OrgUnit.save kaskadı)
    return locked


def run(command, *, organization, actor, apply: bool, group_name: str = "") -> dict:
    """Köçürmə planı (dry-run) və ya tətbiqi; saylar qaytarılır."""

    tree = Tree(organization)
    by_group = _student_rows(organization)
    counts = Counter(candidates=0, moved=0, skipped=0)
    groups = [u for u in tree.units.values() if u.unit_type == "group" and u.is_active]
    if group_name:
        wanted = group_name.strip().casefold()
        groups = [u for u in groups if u.name.strip().casefold() == wanted]
        if not groups:
            raise LookupError("group_move_group_unknown")
    batch = new_batch() if apply else ""
    today = timezone.localdate().isoformat()
    for unit in sorted(groups, key=lambda u: (u.name, str(u.pk))):
        rows = by_group.get(unit.pk) or []
        parent = tree.units.get(unit.parent_id)
        if not rows:
            if group_name:
                _skip(command, counts, unit, "no_active_students")
            continue
        if parent is not None and parent.unit_type == "group":
            counts["nested"] += 1
            continue
        target, reason = _decide(tree, unit, rows)
        if target is None:
            if reason:
                _skip(command, counts, unit, reason)
            else:
                counts["already_ok"] += 1
            continue
        counts["candidates"] += 1
        old_school, new_school = tree.school(unit), tree.school(target)
        _line(
            command,
            group=slug(unit.name),
            to=slug(target.name),
            students=len(rows),
            **{"from": slug(getattr(parent, "name", "")), "from_school": slug(getattr(old_school, "name", ""))},
            to_school=slug(getattr(new_school, "name", "")),
        )
        if not apply:
            continue
        entry = {
            "date": today,
            "source": SOURCE,
            "batch": batch,
            "name": unit.name,
            "parent": getattr(parent, "name", ""),
            "parent_id": str(unit.parent_id or ""),
            "to": target.name,
            "to_id": str(target.pk),
        }
        moved = _reparent(unit, target, entry)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=moved,
            old_values={"parent": str(unit.parent_id or "")},
            new_values={"parent": str(target.pk)},
            changes={"batch": batch, "students": len(rows)},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr=moved.name,
        )
        counts["moved"] += 1
    counts["batch"] = batch if counts["moved"] else ""
    return counts


def undo(command, *, organization, actor, apply: bool, batch: str) -> dict:
    """``batch`` paketinin köçürdüyü və HƏLƏ hədəfdə olan qrupları köhnə valideynə qaytarır."""

    OrgUnit = _model("organizations", "OrgUnit")
    tree = Tree(organization)
    by_group = _student_rows(organization)
    counts = Counter(candidates=0, moved=0, skipped=0)
    today = timezone.localdate().isoformat()
    units = OrgUnit.objects.filter(organization=organization, settings__history__contains=[{"batch": batch}])
    for unit in sorted(units, key=lambda u: (u.name, str(u.pk))):
        entry = next(
            (
                item
                for item in reversed(unit.settings.get("history") or [])
                if isinstance(item, dict) and item.get("batch") == batch and item.get("source") == SOURCE
            ),
            None,
        )
        if entry is None:
            continue
        if str(unit.parent_id or "") != entry.get("to_id"):
            _skip(command, counts, unit, "moved_since")
            continue
        old = tree.units.get(_uuid_or_none(entry.get("parent_id")))
        if old is None or not old.is_active:
            _skip(command, counts, unit, "old_parent_missing")
            continue
        counts["candidates"] += 1
        current = tree.units.get(unit.parent_id)
        _line(
            command,
            group=slug(unit.name),
            to=slug(old.name),
            students=len(by_group.get(unit.pk) or []),
            **{"from": slug(getattr(current, "name", ""))},
        )
        if not apply:
            continue
        back = {
            "date": today,
            "source": SOURCE,
            "undo_of": batch,
            "name": unit.name,
            "parent": getattr(current, "name", ""),
            "parent_id": str(unit.parent_id or ""),
            "to": old.name,
            "to_id": str(old.pk),
        }
        moved = _reparent(unit, old, back)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=moved,
            old_values={"parent": str(unit.parent_id or "")},
            new_values={"parent": str(old.pk)},
            changes={"undo_of": batch},
            reason=UNDO_REASON,
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr=moved.name,
        )
        counts["moved"] += 1
    counts["batch"] = batch
    return counts


def _uuid_or_none(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


__all__ = ["BATCH_RE", "MIN_STUDENTS", "PREFIX", "RESOURCE", "SOURCE", "fold", "new_batch", "run", "slug", "undo"]
