"""Sahib 2026-11-07: köhnə sillabus məzmunu REPODA açıq JSON plan kimi — şəxsi bölmələrsiz, sabitlənmiş hash ilə.

Plan (``apps/legacy_import/legacy_syllabi_2026_11_07.json``) iki hissədir:

* ``sources`` — köhnə sistem sillabusu (``id`` açar) artıq ``build_section_data`` ilə çevrilmiş bölmə xəritəsi kimi.
  Saxlanılır: təsvir/məqsəd, həftəlik mövzular + saatlar, ədəbiyyat, yoxlama/qiymətləndirmə forması, nəticələr,
  dərsin keçirilmə forması, sərbəst iş mövzuları. ÇIXARILIR (boş olmalıdır): qarşılama mesajı, elmi maraqlar,
  sertifikatlar, müəllim/qəbul saatı (əlaqə), imtahan sualları. Heç bir mətndə e-poçt / telefon ola bilməz.
* ``targets`` — jurnal (``offering_id``; yoxdursa fənn + qrup + müəllim üzrə axtarılır) → hərəkət:
  ``restore`` (mənbədən TƏSDİQLİ versiya) və ya ``plan_sync`` (təsdiqli dosyenin plan saatı rəsmi yükə).

Faylın sha256-sı burada sabitdir (``PLAN_SHA256``) — plan dəyişərsə əmr heç nə yazmadan imtina edir.
"""

import hashlib
import json
import re
from pathlib import Path

from . import exact_syllabus_recovery as core

RestoreError = core.RestoreError
PLAN_PATH = Path(__file__).resolve().parents[1] / "legacy_syllabi_2026_11_07.json"
PLAN_SHA256 = "cfeee2c2f81e5f55088668818956130e253d6929d449951b7a9de3f327c4a656"
FORMAT = "legacy-syllabi/1"
MAX_PLAN = 8_000_000
KINDS = ("lecture", "seminar", "practical", "lab")
ACTIONS = ("restore", "plan_sync")
SECTION_KEYS = {"info", "desc", "out", "week", "method", "assess", "self", "lit", "prev", "send"}
#: Şəxsi bölmələr — planda BOŞ olmalıdır (sahib 2026-11-07).
PERSONAL_INFO = {"teacher": "", "office_hours": "", "welcome": "", "research_interests": [], "certificates": []}
KEY = re.compile(r"[a-z0-9_]{1,32}")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?994|\b0)[\s()-]*\d{2}[\s()-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}|\d{7,}")
TARGET_KEYS = {"key", "teacher", "offering_id", "group_id", "subject_ids", "lesson_hours", "plan", "action"}
OPTIONAL_TARGET_KEYS = {"source", "retire_base", "week_gap_ok", "skip_if_receipt"}


def plan_of(hours):
    """``{növ: saat}`` — yalnız sıfırdan böyük növlər (plan forması ilə eyni)."""
    return {kind: int(value) for kind, value in (hours or {}).items() if int(value or 0)}


def week_hours(sections):
    rows = (sections.get("week") or {}).get("rows") or []
    return plan_of({kind: sum(int(row.get(kind) or 0) for row in rows if isinstance(row, dict)) for kind in KINDS})


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _check_source(source):
    sections = source["sections"]
    if set(sections) != SECTION_KEYS or not isinstance(source["teacher"], int):
        raise RestoreError("source_shape")
    info = sections["info"]
    if any(info.get(field) != empty for field, empty in PERSONAL_INFO.items()) or sections["assess"].get(
        "exam_questions"
    ):
        raise RestoreError("personal_content_present")
    if any(EMAIL.search(text) or PHONE.search(text) for text in _strings(sections)):
        raise RestoreError("personal_content_present")
    if core.digest(sections) != source["content_sha256"]:
        raise RestoreError("source_content_changed")
    if week_hours(sections) != plan_of(source["hours"]) or not sections["week"]["rows"]:
        raise RestoreError("source_week_hours")


def _check_target(target, sources):
    if not TARGET_KEYS <= set(target) <= TARGET_KEYS | OPTIONAL_TARGET_KEYS:
        raise RestoreError("target_shape")
    if not KEY.fullmatch(target["key"]) or target["action"] not in ACTIONS:
        raise RestoreError("target_shape")
    ids = [target["group_id"], *target["subject_ids"]] + ([target["offering_id"]] if target["offering_id"] else [])
    if not target["subject_ids"] or not all(isinstance(i, str) and UUID.fullmatch(i) for i in ids):
        raise RestoreError("target_shape")
    plan = target["plan"]
    if plan != plan_of(plan) or not plan or sum(plan.values()) != target["lesson_hours"]:
        raise RestoreError("target_plan_shape")
    if target["action"] == "restore":
        source = sources.get(target.get("source"))
        if source is None or source["teacher"] != target["teacher"]:
            raise RestoreError("target_source_mismatch")
        hours = plan_of(source["hours"])
        # Sahib 2026-11-09 (235 EM Tətbiqi riyaziyyat): köhnə sillabusun həftəlik saatı rəsmi plandan AZ ola bilər
        # (L30+S15 → L30+S30); ``week_gap_ok`` ilə plan saatı rəsmi yükdən, mövzular mənbədən — növ artırılmır.
        if hours != plan and not (
            target.get("week_gap_ok") and set(hours) == set(plan) and all(hours[k] <= plan[k] for k in plan)
        ):
            raise RestoreError("target_source_mismatch")
    elif "source" in target or "retire_base" in target:
        raise RestoreError("target_shape")


def load(path=None, expected=None):
    """→ ``plan`` dict (yoxlanmış). Sha256, format, şəxsi bölmələr və saatlar yoxlanılır."""
    path = Path(path or PLAN_PATH)
    raw = path.read_bytes()
    if len(raw) > MAX_PLAN or hashlib.sha256(raw).hexdigest() != (expected or PLAN_SHA256):
        raise RestoreError("pinned_plan_changed")
    try:
        plan = json.loads(raw)
        if set(plan) != {"format", "organization_id", "period_id", "sources", "targets"} or plan["format"] != FORMAT:
            raise RestoreError("plan_shape")
        for source in plan["sources"].values():
            _check_source(source)
        keys = [target["key"] for target in plan["targets"]]
        if len(set(keys)) != len(keys) or not keys:
            raise RestoreError("target_shape")
        for target in plan["targets"]:
            _check_target(target, plan["sources"])
        return plan
    except RestoreError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RestoreError("plan_shape") from None
