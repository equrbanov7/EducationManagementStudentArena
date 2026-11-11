"""Dublikat fənlərin BİRLƏŞDİRİLMƏSİ — seçim, önizləmə (dry-run) və iz (2026-10-19).

Tədris şöbəsi «saxlanılacaq fənn» (hədəf) və bir neçə «birləşdiriləcək fənn» (mənbə) seçir;
önizləmə hər cədvəl üzrə köçəcək sətirləri sayır, toqquşmaları (:mod:`.subject_merge_conflicts`)
göstərir və sətir id-lərindən İZ (digest) hesablayır. Tətbiq (:mod:`.subject_merge_apply`) eyni
izi tələb edir — önizləmə ilə təsdiq arasında məlumat dəyişibsə heç nə yazılmır (journal-hygiene
naxışı).

QƏRARLAR
* Mənbə kartı SİLİNMİR — arxivlənir (``is_archived=True``, ``is_active=False``, səbəb
  «Birləşdirildi → <hədəf kodu>»).
* Təsdiqlənmiş (və baxışdakı) planın sətrində fənn FK-sının dəyişməsi İCAZƏLİDİR: bu, planın
  MƏZMUNU (kredit, saat, semestr, forma) deyil, eyni fənnin kataloq kartının identiklik
  düzəlişidir. Plan sətirləri id-ləri ilə audit-ə yazılır, plan id-ləri ayrıca qeyd olunur.
  Həmin planlarda sətri SİLMƏK (toqquşmanın həlli) isə məzmun dəyişikliyidir → bloklanır.
* Kredit fərqi: transkript krediti ``offering.subject.ects``-dən oxunur. Fərqli ECTS-li mənbə üzrə yekun
  qiymətli tələbə varsa birləşmə BLOKLANIR (keçmiş ÜOMG dəyişməsin); qiymət yoxdursa — xəbərdarlıq.
* ``ExamChanceGrant`` dəyişməz tarixçədir (append-only trigger) — arxivlənmiş mənbədə qalır.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict

from django.apps import apps as django_apps
from django.utils.translation import pgettext

from . import subject_merge_conflicts as conflicts_service
from . import subject_merge_scope as merge_scope
from .models import CurriculumSubject, Subject
from .models.catalog_meta import ARCHIVE_REASON_MIN_LENGTH
from .subject_duplicates import normalized_subject_key
from .subject_merge_inventory import KEEP, M2M, RELATIONS, REPOINT, SOFT_JSON_KEYS, SOFT_JSON_TITLE

_CTX = "registrar.subject_merge"

MAX_SOURCES = 10
AUDIT_RESOURCE = "registrar.subject_merge"
AUDIT_UNDO_RESOURCE = "registrar.subject_merge_undo"
CHANGES_VERSION = 1
REASON_MIN_LENGTH = ARCHIVE_REASON_MIN_LENGTH
CURRICULUM_KEY = "registrar.CurriculumSubject.subject"
OFFERING_KEY = "registrar.CourseOffering.subject"
SYLLABUS_KEY = "syllabus.Syllabus.subject"


class MergeError(Exception):
    """Rədd edilmiş birləşdirmə. Konstruktor pozisiyalıdır (B042)."""

    def __init__(self, code: str = "invalid", message: str = "", status: int = 400, details=None):
        super().__init__(code, message, status, details)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


def archive_reason_for(target) -> str:
    return f"Birləşdirildi → {target.code}"


def clean_reason(value) -> str:
    reason = " ".join(str(value or "").split())
    if len(reason) < REASON_MIN_LENGTH:
        raise MergeError(
            "reason_too_short",
            pgettext(_CTX, "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil."),
        )
    return reason[:2000]


def _uuid_or_none(value):
    try:
        return uuid.UUID(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _split_ids(values) -> list:
    if isinstance(values, str):
        values = [values]
    parts = []
    for value in values or ():
        parts.extend(part for part in str(value or "").replace(";", ",").split(",") if part.strip())
    return [part.strip() for part in parts]


def resolve_subjects(organization, target_ref, source_refs, *, by_code=False):
    """Hədəf + mənbələr (tenant daxilində). ``by_code`` — idarə əmri üçün (kodla)."""
    target_ref = str(target_ref or "").strip()
    refs = list(dict.fromkeys(_split_ids(source_refs)))
    if not target_ref:
        raise MergeError("target_required", pgettext(_CTX, "Saxlanılacaq fənni seçin."))
    if not refs:
        raise MergeError("sources_required", pgettext(_CTX, "Ən azı bir birləşdiriləcək fənn seçin."))
    if len(refs) > MAX_SOURCES:
        raise MergeError(
            "too_many_sources",
            pgettext(_CTX, "Bir dəfəyə ən çox %(n)s fənn birləşdirilə bilər.") % {"n": MAX_SOURCES},
        )
    base = Subject.objects.filter(organization=organization)

    def lookup(ref):
        if by_code:
            return base.filter(code=ref).first()
        pk = _uuid_or_none(ref)
        return base.filter(pk=pk).first() if pk else None

    target = lookup(target_ref)
    sources = [lookup(ref) for ref in refs]
    if target is None or any(source is None for source in sources):
        raise MergeError("not_found", pgettext(_CTX, "Fənn tapılmadı."), status=404)
    if any(source.pk == target.pk for source in sources):
        raise MergeError("same_subject", pgettext(_CTX, "Saxlanılacaq fənn birləşdiriləcəklər siyahısında ola bilməz."))
    if target.is_archived or not target.is_active:
        raise MergeError(
            "target_archived", pgettext(_CTX, "Saxlanılacaq fənn arxivdədir — əvvəlcə onu arxivdən qaytarın.")
        )
    return target, sources


# ── Sətirlərin toplanması ───────────────────────────────────────────────────


def _rows_by_source(relation, source_ids) -> dict:
    model = relation.model()
    attname = model._meta.get_field(relation.field).attname
    grouped = defaultdict(list)
    rows = model._base_manager.filter(**{f"{attname}__in": source_ids}).values_list("pk", attname).order_by("pk")
    for pk, subject_id in rows:
        grouped[str(subject_id)].append(str(pk))
    return dict(grouped)


def _m2m_plan(relation, target_id, source_ids) -> dict:
    through = relation.model()._meta.get_field(relation.field).remote_field.through
    links = list(
        through.objects.filter(subject_id__in=[target_id, *source_ids])
        .values_list("pk", "studentgroup_id", "subject_id")
        .order_by("studentgroup_id", "pk")
    )
    order = {target_id: -1, **{pk: index for index, pk in enumerate(source_ids)}}
    by_group = defaultdict(list)
    for link_id, group_id, subject_id in links:
        by_group[group_id].append((order[subject_id], link_id, subject_id))
    move, drop = [], []
    for group_id, items in by_group.items():
        items.sort()
        has_target = items[0][2] == target_id
        for index, (_rank, link_id, subject_id) in enumerate(items):
            if subject_id == target_id:
                continue
            entry = {"id": str(link_id), "group": str(group_id), "from": str(subject_id)}
            (drop if has_target or index > 0 else move).append(entry)
    return {"move": move, "drop": drop}


def _json_refs(target_id, source_ids) -> list:
    refs = []
    wanted = {str(pk) for pk in source_ids}
    for label, field in SOFT_JSON_KEYS:
        model = django_apps.get_model(label)
        rows = model._base_manager.filter(**{f"{field}__has_any_keys": sorted(wanted)}).values_list("pk", field)
        for pk, value in rows.order_by("pk"):
            before = dict(value or {})
            after = {key: item for key, item in before.items() if key not in wanted}
            merged = [before[key] for key in before if key in wanted]
            if str(target_id) in before:
                merged.append(before[str(target_id)])
            after[str(target_id)] = max(merged, key=lambda item: int(item or 0))
            refs.append({"model": label, "field": field, "id": str(pk), "before": before, "after": after})
    return refs


def _subject_card(subject) -> dict:
    return {
        "id": str(subject.pk),
        "code": subject.code,
        "name": subject.name,
        "ects": subject.ects,
        "kind": subject.kind,
        "is_archived": subject.is_archived,
        "is_active": subject.is_active,
        "archived_reason": subject.archived_reason,
        "archived_at": subject.archived_at.isoformat() if subject.archived_at else None,
        "archived_by_id": subject.archived_by_id,
    }


def _syllabi_of(offering_ids) -> set:
    if not offering_ids:
        return set()
    rows = django_apps.get_model("syllabus", "Syllabus")._base_manager.filter(offering_id__in=offering_ids)
    return {str(pk) for pk in rows.values_list("pk", flat=True)}


def collect(organization, target, sources, *, drop_attendance_only=False, current_only=False) -> dict:
    """Birləşmənin tam planı — həm önizləmə, həm tətbiq, həm də iz bundan qurulur.

    ``current_only`` (sahib 2026-11-11, :mod:`.subject_merge_scope`): mənbənin keçmiş dövr sətirləri mənbə kartda qalır,
    onların toqquşması bloklamır."""
    source_ids = [source.pk for source in sources]
    past = merge_scope.staying_rows(organization, sources) if current_only else {}
    found = conflicts_service.detect(
        organization, target, sources, drop_attendance_only=drop_attendance_only, stay=past
    )
    resolvable = found["resolvable"]
    dropped_rows = set(conflicts_service.resolved_ids(resolvable, conflicts_service.CURRICULUM_ROW))
    deleted_offerings = conflicts_service.resolved_ids(resolvable, conflicts_service.OFFERING_TWIN)
    twin_keep = {
        pk: item["keep"]
        for item in resolvable
        if item["code"] == conflicts_service.OFFERING_TWIN
        for pk in item["drop"]
    }
    # K4: birləşdirilmiş passiv dublikat jurnal (və onun sillabusu) arxivlənən mənbə kartda QALIR — köçürülmür.
    stay_offerings = conflicts_service.resolved_ids(resolvable, conflicts_service.OFFERING_RETIRED)
    stay = {OFFERING_KEY: set(stay_offerings), SYLLABUS_KEY: _syllabi_of(stay_offerings)}
    for key, ids in past.items():
        stay[key] = stay.get(key, set()) | set(ids)
    moved, kept = {}, {}
    m2m = {"move": [], "drop": []}
    for relation in RELATIONS:
        if relation.strategy == M2M:
            m2m = _m2m_plan(relation, target.pk, source_ids)
            continue
        rows = _rows_by_source(relation, source_ids)
        gone = dropped_rows if relation.key == CURRICULUM_KEY else set(deleted_offerings)
        gone = gone | stay.get(relation.key, set())
        if relation.key in (CURRICULUM_KEY, OFFERING_KEY, SYLLABUS_KEY) or relation.key in past:
            rows = {sid: [pk for pk in ids if pk not in gone] for sid, ids in rows.items()}
            rows = {sid: ids for sid, ids in rows.items() if ids}
        if relation.strategy == KEEP:
            kept[relation.key] = rows
        elif relation.strategy == REPOINT:
            moved[relation.key] = rows
    plan_rows = [pk for ids in moved.get(CURRICULUM_KEY, {}).values() for pk in ids]
    locked_plans = sorted(
        {
            str(pk)
            for pk in CurriculumSubject.objects.filter(pk__in=plan_rows)
            .exclude(curriculum__status__in=conflicts_service.EDITABLE_PLAN_STATUSES)
            .values_list("curriculum_id", flat=True)
        }
    )
    offering_ids = [pk for ids in moved.get(OFFERING_KEY, {}).values() for pk in ids]
    Enrollment = django_apps.get_model("registrar", "Enrollment")
    evidence_offerings = (
        Enrollment.objects.filter(offering_id__in=offering_ids).values("offering_id").distinct().count()
        if offering_ids
        else 0
    )
    return {
        "target": _subject_card(target),
        "sources": [_subject_card(source) for source in sources],
        "moved": moved,
        "kept": kept,
        "m2m": m2m,
        "json_refs": _json_refs(target.pk, source_ids),
        "dropped_plan_rows": sorted(dropped_rows),
        "deleted_offerings": deleted_offerings,
        "twin_keep": twin_keep,
        "stay": {key: sorted(ids) for key, ids in stay.items() if ids},
        "dropped_enrollments": conflicts_service.resolved_ids(resolvable, conflicts_service.ENROLLMENT_UNGRADED),
        "locked_plans": locked_plans,
        "evidence_offerings": evidence_offerings,
        "conflicts": found,
        "current_only": bool(current_only),
        "past_stay": past,
    }


def plan_digest(plan) -> str:
    """İz: kartlar + hər cədvəlin sətir id-ləri + toqquşma/həll siyahısı (sabit sıra)."""
    payload = {
        "target": plan["target"],
        "sources": plan["sources"],
        "moved": plan["moved"],
        "kept": plan["kept"],
        "m2m": plan["m2m"],
        "json_refs": plan["json_refs"],
        "dropped": plan["dropped_plan_rows"],
        "deleted_offerings": plan["twin_keep"],
        "stay": plan.get("stay", {}),
        "dropped_enrollments": plan["dropped_enrollments"],
        "blocking": [(item["code"], sorted(item["ids"])) for item in plan["conflicts"]["blocking"]],
    }
    if plan.get("current_only"):  # köhnə izlər dəyişməsin — açar yalnız yeni rejimdə
        payload["current_only"] = plan.get("past_stay", {})
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def counts(plan) -> dict:
    """Cədvəl → köçən sətir sayı (audit + hesabat)."""
    result = {key: sum(len(ids) for ids in rows.values()) for key, rows in plan["moved"].items()}
    result["exams.StudentGroup.subjects"] = len(plan["m2m"]["move"])
    result["exams.StudentGroup.subjects:dropped"] = len(plan["m2m"]["drop"])
    result["registrar.CurriculumSubject.subject:dropped"] = len(plan["dropped_plan_rows"])
    result["soft_json"] = len(plan["json_refs"])
    result["registrar.CourseOffering:deleted_empty_twins"] = len(plan.get("deleted_offerings", []))
    result["registrar.Enrollment:dropped_ungraded"] = len(plan.get("dropped_enrollments", []))
    for key, ids in (plan.get("past_stay") or {}).items():
        result[f"{key}:left_past"] = len(ids)
    return result


# ── Önizləmə ────────────────────────────────────────────────────────────────


def _warnings(target, sources, plan) -> list:
    warnings = []
    ects = {target.ects, *(source.ects for source in sources)}
    credit_blocked = any(item["code"] == "credit_mismatch" for item in plan["conflicts"]["blocking"])
    if len(ects) > 1 and not credit_blocked:
        warnings.append(
            pgettext(
                _CTX,
                "Kredit fərqlidir: %(list)s. Fərqli kreditli fənn üzrə yekun qiymət yoxdur — birləşmədən sonra "
                "saxlanılan fənnin krediti (%(ects)s ECTS) işlənir; plan sətirlərindəki kredit dəyişmir.",
            )
            % {
                "list": ", ".join(f"{item.code} — {item.ects} ECTS" for item in (target, *sources)),
                "ects": target.ects,
            }
        )
    if len({target.kind, *(source.kind for source in sources)}) > 1:
        warnings.append(pgettext(_CTX, "Fənn növləri fərqlidir — saxlanılan fənnin növü qalır."))
    key = normalized_subject_key(target.name)
    if any(normalized_subject_key(source.name) != key for source in sources):
        warnings.append(
            pgettext(
                _CTX, "Adlar (boşluq/registr nəzərə alınmadan) fərqlidir — bunun həqiqətən eyni fənn olduğunu yoxlayın."
            )
        )
    if any(source.is_archived for source in sources):
        warnings.append(
            pgettext(_CTX, "Birləşdiriləcək fənlərdən biri artıq arxivdədir — istinadları yenə köçürüləcək.")
        )
    warnings.extend(plan["conflicts"]["warnings"])
    return warnings


def _info(plan) -> list:
    info = []
    if plan["locked_plans"]:
        info.append(
            pgettext(
                _CTX,
                "%(n)s təsdiqlənmiş və ya baxışdakı planın sətrində fənn kartı dəyişəcək — bu, məzmun deyil, "
                "identiklik düzəlişidir (kredit/saat/semestr dəyişmir) və audit-ə yazılır.",
            )
            % {"n": len(plan["locked_plans"])}
        )
    if plan["evidence_offerings"]:
        info.append(
            pgettext(_CTX, "%(n)s açılışın qeydiyyatı var — açılışlar qiymət və davamiyyətləri ilə birlikdə köçür.")
            % {"n": plan["evidence_offerings"]}
        )
    if plan["m2m"]["drop"]:
        info.append(
            pgettext(_CTX, "%(n)s imtahan qrupunda hər iki fənn var — təkrar əlaqə çıxarılacaq.")
            % {"n": len(plan["m2m"]["drop"])}
        )
    kept_total = sum(len(ids) for rows in plan["kept"].values() for ids in rows.values())
    if kept_total:
        info.append(
            pgettext(_CTX, "%(n)s imtahan şansı qeydi dəyişməz tarixçədir — arxivlənmiş fənndə qalır.")
            % {"n": kept_total}
        )
    return info


def _tables(plan) -> list:
    codes = {item["id"]: item["code"] for item in plan["sources"]}
    tables = []
    for relation in RELATIONS:
        if relation.strategy == M2M:
            rows = defaultdict(int)
            for entry in plan["m2m"]["move"] + plan["m2m"]["drop"]:
                rows[entry["from"]] += 1
            by_source = dict(rows)
        else:
            bucket = plan["kept"] if relation.strategy == KEEP else plan["moved"]
            by_source = {sid: len(ids) for sid, ids in bucket.get(relation.key, {}).items()}
        tables.append(
            {
                "key": relation.key,
                "title": str(relation.title),
                "strategy": relation.strategy,
                "count": sum(by_source.values()),
                "by_source": [{"code": codes.get(sid, sid), "count": n} for sid, n in sorted(by_source.items())],
            }
        )
    tables.append(
        {
            "key": "soft_json",
            "title": str(SOFT_JSON_TITLE),
            "strategy": REPOINT,
            "count": len(plan["json_refs"]),
            "by_source": [],
        }
    )
    return tables


def _limited(items) -> list:
    return items[: conflicts_service.LIST_LIMIT]


def preview(
    organization, target_ref, source_refs, *, by_code=False, drop_attendance_only=False, current_only=False
) -> dict:
    """Dry-run: heç nə yazmır. ``drop_attendance_only`` — K3 bayrağı (:mod:`.subject_merge_conflicts`);
    ``current_only`` — keçmiş dövr sətirləri mənbə kartda qalır (:mod:`.subject_merge_scope`)."""
    target, sources = resolve_subjects(organization, target_ref, source_refs, by_code=by_code)
    plan = collect(organization, target, sources, drop_attendance_only=drop_attendance_only, current_only=current_only)
    found = plan["conflicts"]
    tables = _tables(plan)
    return {
        "target": plan["target"],
        "sources": plan["sources"],
        "tables": tables,
        "total": sum(table["count"] for table in tables if table["strategy"] != KEEP),
        "blocking": _limited(found["blocking"]),
        "blocking_total": len(found["blocking"]),
        "resolvable": _limited(found["resolvable"]),
        "resolvable_total": len(found["resolvable"]),
        "warnings": _warnings(target, sources, plan),
        "info": _info(plan),
        "archive_reason": archive_reason_for(target),
        "digest": plan_digest(plan),
        "can_apply": not found["blocking"],
        "current_only": plan["current_only"],
        "left_past": {key: len(ids) for key, ids in plan["past_stay"].items()},
        "moved_counts": counts(plan),
    }


__all__ = [
    "AUDIT_RESOURCE",
    "AUDIT_UNDO_RESOURCE",
    "CHANGES_VERSION",
    "CURRICULUM_KEY",
    "MAX_SOURCES",
    "OFFERING_KEY",
    "MergeError",
    "archive_reason_for",
    "clean_reason",
    "collect",
    "counts",
    "plan_digest",
    "preview",
    "resolve_subjects",
]
