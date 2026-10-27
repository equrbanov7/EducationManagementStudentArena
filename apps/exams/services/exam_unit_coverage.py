"""Qrup imtahanın fənnini keçmir — xəbərdarlıq + məcburi əlavə səbəbi (sahib 2026-10-27).

Sahib: «Qrup seçərkən əgər o qrupdan bir nəfər belə o fənni keçmirsə — tələbələrdən biri belə həmin fənnin
jurnalında yoxdursa — modal mesaj gəlsin ki, bu qrupun bu fənni yoxdur; məcburi olaraq etmək seçimi də olsun,
bununla bağlı səbəb yazaraq.» Prod halı: «236 QM» qrupu «Azərbaycan tarixi» midterminə səhvən əlavə olunmuşdu.

Qayda (server avtoritetdir — API birbaşa çağırılsa da):

* yalnız imtahanın **fənni** var və kateqoriya balı jurnala yazır (``exam_journal_coverage.JOURNAL_CATEGORIES``
  — final / midterm);
* qrupun (alt qruplar daxil, giriş siyasəti kimi) ən azı bir aktiv tələbəsi fənnin cari dövr jurnalında
  ``enrolled`` deyilsə qrup «əhatəsiz»dir (registrar ``exam_journal_link.group_subject_coverage``);
* YENİ əlavə olunan əhatəsiz qrup yalnız açıq «məcburi əlavə» + ən azı :data:`REASON_MIN_LENGTH` simvolluq
  səbəblə qəbul olunur (POST ``forced_units`` — JSON ``{qrup_id: səbəb}``; və ya qrup id-ləri siyahısı +
  ``forced_unit_reason_<id>`` / ümumi ``forced_units_reason``). İmtahanda artıq olan qruplar yoxlanmır (köhnə
  imtahanların redaktəsi bloklanmır).

Qəbul olunan məcburi əlavə ``AuditLog``-a yazılır (``resource_type =`` :data:`AUDIT_RESOURCE` — kim, imtahan,
qrup, əhatəsiz tələbə sayı, səbəb) və imtahan səhifəsinin tarixçəsində görünür (:func:`history`).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from django.utils.translation import pgettext

logger = logging.getLogger(__name__)

#: Səbəbin minimum / maksimum uzunluğu (boşluqlar normallaşdırıldıqdan sonra).
REASON_MIN_LENGTH = 10
REASON_MAX_LENGTH = 1000
#: POST sahələri (ExamForm-un sahəsi deyil — ``allowed_units`` kimi view yoxlayır).
FORCED_FIELD = "forced_units"
REASON_FIELD_PREFIX = "forced_unit_reason_"
COMMON_REASON_FIELD = "forced_units_reason"
#: Xəbərdarlıqda göstərilən tələbə adlarının sayı.
SAMPLE_SIZE = 5
#: Audit sətri (``AuditLog.resource_type``; ``resource_id`` — imtahanın pk-si).
AUDIT_RESOURCE = "exam_unit_forced"

_CTX = "exams.unit_coverage"


def applies(subject_id, category) -> bool:
    """Yoxlama yalnız fənnli və balı jurnala yazılan (final / midterm) imtahanda."""
    from apps.exams.services.exam_journal_coverage import writes_to_journal

    return bool(subject_id) and writes_to_journal(category)


def unit_label(unit) -> str:
    parent = getattr(unit, "parent", None)
    if parent is not None and getattr(parent, "name", ""):
        return f"{unit.name} — {parent.name}"
    return str(getattr(unit, "name", "") or unit)


@dataclass
class GroupCoverage:
    """Bir reyestr qrupunun fənn jurnalı əhatəsi."""

    unit_id: str
    name: str
    total: int
    uncovered: int
    has_journal: bool
    uncovered_ids: list = field(default_factory=list)
    names: list = field(default_factory=list)

    @property
    def is_uncovered(self) -> bool:
        return self.uncovered > 0

    def as_json(self) -> dict:
        return {
            "id": self.unit_id,
            "name": self.name,
            "total": self.total,
            "uncovered": self.uncovered,
            "has_journal": self.has_journal,
            "names": list(self.names),
            "more": max(self.uncovered - len(self.names), 0),
        }


def _sample_names(student_ids) -> dict:
    """``{student_id: «Ad Soyad Ata adı»}`` — soyad / ad sırası ilə (BİR sorğu)."""
    if not student_ids:
        return {}
    from django.contrib.auth import get_user_model

    from core.person_names import user_display_name_with_patronymic

    users = (
        get_user_model()
        .objects.filter(pk__in=list(student_ids))
        .select_related("profile")
        .order_by("last_name", "first_name", "pk")
    )
    return {user.pk: user_display_name_with_patronymic(user) for user in users}


def coverage(organization, subject_id, units, *, sample=SAMPLE_SIZE) -> list:
    """Seçilmiş reyestr qrupları (``OrgUnit``) → :class:`GroupCoverage` siyahısı (qrup sırası saxlanır)."""
    units = list(units or ())
    if organization is None or not subject_id or not units:
        return []
    from apps.registrar.public import exam_journal_link

    raw = exam_journal_link.group_subject_coverage(organization, subject_id, [unit.pk for unit in units])
    picked = set()
    for row in raw.values():
        picked.update(row["uncovered"])
    names = _sample_names(picked) if sample else {}
    order = list(names)
    out = []
    for unit in units:
        row = raw.get(unit.pk) or {"students": [], "uncovered": [], "has_journal": False}
        uncovered = set(row["uncovered"])
        ordered = [sid for sid in order if sid in uncovered]
        out.append(
            GroupCoverage(
                unit_id=str(unit.pk),
                name=unit_label(unit),
                total=len(row["students"]),
                uncovered=len(uncovered),
                has_journal=bool(row["has_journal"]),
                uncovered_ids=sorted(uncovered),
                names=[names[sid] for sid in ordered[:sample]],
            )
        )
    return out


def _normalize_reason(value) -> str:
    return " ".join(str(value or "").split())[:REASON_MAX_LENGTH]


def parse_forced(data) -> dict:
    """POST-dan məcburi əlavələr → ``{qrup_id (str): səbəb}`` (səbəb boş ola bilər — yoxlama sonra)."""
    raw = str(data.get(FORCED_FIELD) or "").strip() if hasattr(data, "get") else ""
    forced: dict = {}
    if raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = raw.split(",")
        if isinstance(parsed, dict):
            forced = {str(key).strip(): _normalize_reason(value) for key, value in parsed.items()}
        elif isinstance(parsed, list):
            forced = {str(key).strip(): "" for key in parsed}
    common = _normalize_reason(data.get(COMMON_REASON_FIELD)) if hasattr(data, "get") else ""
    for key in list(forced):
        if not key:
            forced.pop(key)
            continue
        if not forced[key]:
            forced[key] = _normalize_reason(data.get(f"{REASON_FIELD_PREFIX}{key}")) or common
    return forced


@dataclass
class Check:
    """Saxlamadan əvvəlki qərar: qəbul olunan məcburi əlavələr və bloklanan qruplar."""

    accepted: list = field(default_factory=list)  # [(GroupCoverage, səbəb)]
    blocked: list = field(default_factory=list)  # [GroupCoverage]
    error: str = ""

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocked)


def check_new_units(organization, *, subject_id, category, new_units, data) -> Check:
    """YENİ əlavə olunan qrupları yoxla → :class:`Check`. Tətbiq olunmursa / yeni qrup yoxdursa boş."""
    result = Check()
    if not new_units or not applies(subject_id, category):
        return result
    forced = parse_forced(data)
    short = False
    for row in coverage(organization, subject_id, new_units):
        if not row.is_uncovered:
            continue
        reason = forced.get(row.unit_id)
        if reason and len(reason) >= REASON_MIN_LENGTH:
            result.accepted.append((row, reason))
            continue
        short = short or row.unit_id in forced
        result.blocked.append(row)
    if result.blocked:
        result.error = (
            pgettext(_CTX, "Səbəb ən azı %(min)d simvol olmalıdır.") % {"min": REASON_MIN_LENGTH}
            if short
            else pgettext(
                _CTX,
                "Seçilmiş qrupların bəzi tələbələri bu fənnin cari semestr jurnalında yoxdur. "
                "Qrupu çıxarın və ya səbəb yazaraq məcburi əlavə edin.",
            )
        )
    return result


def record_forced(exam, accepted, *, user, subject_label="", request=None) -> list:
    """Qəbul olunan məcburi əlavələri audit et (imtahanın saxlanması ilə EYNİ tranzaksiyada) → ``AuditLog``-lar."""
    from apps.audit.public import log_action
    from core.constants import AuditAction

    logs = []
    for row, reason in accepted or ():
        logs.append(
            log_action(
                action=AuditAction.UPDATE,
                user=user,
                organization=exam.organization,
                obj=exam,
                new_values={"unit_id": row.unit_id, "unit": row.name},
                changes={
                    "unit_id": row.unit_id,
                    "unit": row.name,
                    "subject_id": str(exam.subject_id or ""),
                    "subject": subject_label,
                    "students": row.total,
                    "uncovered": row.uncovered,
                    "has_journal": row.has_journal,
                },
                reason=reason,
                request=request,
                resource_type=AUDIT_RESOURCE,
                resource_id=str(exam.pk),
                resource_repr=str(getattr(exam, "title", ""))[:500],
            )
        )
    return logs


def history(exam, rows=None) -> list:
    """İmtahan səhifəsi üçün məcburi əlavə olunmuş qruplar (yenidən köhnəyə) — siyahı dict-lər.

    ``rows`` — əvvəlcədən çəkilmiş ``exam_subject_change.audit_rows`` (səhifədə əlavə sorğu olmasın)."""
    if not getattr(exam, "pk", None):
        return []
    if rows is None:
        from apps.exams.services.exam_subject_change import audit_rows

        rows = audit_rows(exam, (AUDIT_RESOURCE,))
    rows = [row for row in rows if row.resource_type == AUDIT_RESOURCE]
    out = []
    for row in rows:
        changes = row.changes if isinstance(row.changes, dict) else {}
        out.append(
            {
                "at": row.created_at,
                "user": (row.user.get_full_name() or row.user.username) if row.user else "—",
                "unit": changes.get("unit") or "—",
                "subject": changes.get("subject") or "—",
                "students": int(changes.get("students") or 0),
                "uncovered": int(changes.get("uncovered") or 0),
                "reason": row.reason,
            }
        )
    return out


__all__ = [
    "AUDIT_RESOURCE",
    "COMMON_REASON_FIELD",
    "FORCED_FIELD",
    "REASON_FIELD_PREFIX",
    "REASON_MIN_LENGTH",
    "Check",
    "GroupCoverage",
    "applies",
    "check_new_units",
    "coverage",
    "history",
    "parse_forced",
    "record_forced",
    "unit_label",
]
