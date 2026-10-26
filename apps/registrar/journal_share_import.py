"""Köhnə sistemin jurnal bölgüsünü ``JournalShare`` sətirlərinə yazır — ``apply_journal_shares`` əmrinin nüvəsi.

Sahib 2026-10-26: «nə tələbə artıq şey görsün, nə də müəllimin jurnalı itsin — köhnə sistemin jurnal datasından
götür». Fayl (``journal-shares/1``) köhnə sistemin hər müəllim jurnalından qurulur: hansı açılış, hansı müəllim,
hansı dərs növləri, hansı tələbələr. Burada yalnız YOXLAMA + YAZI var; stdout-a heç bir ad/id çıxmır (yalnız saylar).

Qaydalar:

* dövr cari olmalıdır; açılış həmin dövrdə və aktiv; müəllimin aktiv ``grade.input`` üzvlüyü (yoxsa ``teacher_inactive``);
* tələbələr açılışa aid və ``enrolled`` olmalıdır (etibarlı alt çoxluq saxlanılır; heç biri qalmırsa pay atlanır);
  açılışın BÜTÜN aktiv tələbələri → boş (hamısı) saxlanılır;
* növlər ``LessonKind`` dəyərlərinə çevrilir; açılışın dərslərindəki bütün növləri örtürsə → boş (hamısı);
* (açılış, müəllim) üzrə upsert, ``source=legacy``; ƏL İLƏ yaradılmış pay HEÇ VAXT üzərinə yazılmır;
* ``drop_enrollments`` — hələ ``enrolled`` və heç bir datası olmayan qeydiyyat «Jurnal təmizliyi» qərarı ilə
  ``dropped`` olur (kateqoriya ``empty_subject``, səbəb kodu ``language_level`` — tarixçədən geri qaytarılır);
  datası olan saxlanılır (``drop_kept_has_data``).
"""

from __future__ import annotations

import json
import secrets
from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.http_ids import parse_uuid

from .models import CourseOffering, Enrollment, JournalShare, JournalShareSource, Lesson, LessonKind

FORMAT = "journal-shares/1"
DROP_REASON_CODE = "language_level"
DROP_REASON = (
    "Xarici dil səviyyə jurnalı: köhnə sistemdə tələbə bu səviyyənin jurnalında olmayıb, "
    "yeni jurnalda da heç bir datası yoxdur (apply_journal_shares)."
)
#: Fayldakı növ adları → ``LessonKind``.
KIND_ALIASES = {
    "lecture": LessonKind.LECTURE,
    "seminar": LessonKind.SEMINAR,
    "lab": LessonKind.LAB,
    "laboratory": LessonKind.LAB,
}
SHOWN = (
    "shares_in_file",
    "shares_created",
    "shares_updated",
    "shares_unchanged",
    "manual_kept",
    "owner_shares",
    "teacher_shares",
    "owner_flag_mismatch",
    "offering_missing",
    "teacher_missing",
    "teacher_inactive",
    "kind_unknown",
    "kinds_all",
    "enrollments_all",
    "enrollments_invalid",
    "no_valid_enrollments",
    "drops_in_file",
    "drops_applied",
    "drop_kept_has_data",
    "drop_not_enrolled",
)


class ShareFileError(Exception):
    """Fayl oxunmadı / format səhvdir (kod — stdout-a yalnız bu çıxır)."""


def new_batch() -> str:
    return f"shares-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ShareFileError("file_unreadable") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ShareFileError("bad_format")
    if not isinstance(data.get("shares"), list) or not isinstance(data.get("drop_enrollments", []), list):
        raise ShareFileError("bad_format")
    return data


def current_period(organization, period_id):
    period_model = django_apps.get_model("organizations", "AcademicPeriod")
    period_uuid = parse_uuid(period_id)
    period = period_model.objects.filter(organization=organization, pk=period_uuid).first() if period_uuid else None
    if period is None:
        raise ShareFileError("period_not_found")
    if not period.is_current:
        raise ShareFileError("period_not_current")
    return period


def _ids(values) -> list:
    return [str(value) for value in values or [] if value]


class _Context:
    """Fayldakı açılışların bir dəfəlik oxunuşu (açılış, aktiv tələbələr, dərs növləri, mövcud paylar)."""

    def __init__(self, organization, period, offering_ids):
        self.offerings = {
            str(offering.pk): offering
            for offering in CourseOffering.objects.filter(
                organization=organization, period=period, pk__in=offering_ids
            ).only("id", "is_active", "instructor_id", "organization_id")
        }
        self.enrolled = defaultdict(set)
        for offering_id, enrollment_id in Enrollment.objects.filter(
            offering_id__in=list(self.offerings), status=Enrollment.Status.ENROLLED
        ).values_list("offering_id", "pk"):
            self.enrolled[str(offering_id)].add(str(enrollment_id))
        self.kinds = defaultdict(set)
        for offering_id, kind in (
            Lesson.objects.filter(offering_id__in=list(self.offerings)).values_list("offering_id", "kind").distinct()
        ):
            self.kinds[str(offering_id)].add(kind)
        self.existing = {
            (str(share.offering_id), share.teacher_id): share
            for share in JournalShare.objects.filter(offering_id__in=list(self.offerings), is_active=True)
        }


def _teacher_verdicts(organization, teacher_ids) -> tuple[dict, dict]:
    """``({id: "ok" | "teacher_missing" | "teacher_inactive"}, {id: user})`` — bir müəllim bir dəfə yoxlanır."""
    from .integrity import is_authorized_instructor

    users = {user.pk: user for user in get_user_model().objects.filter(pk__in=teacher_ids)}
    verdicts = {}
    for teacher_id in teacher_ids:
        user = users.get(teacher_id)
        if user is None:
            verdicts[teacher_id] = "teacher_missing"
        elif not user.is_active or not is_authorized_instructor(organization=organization, instructor=user):
            verdicts[teacher_id] = "teacher_inactive"
        else:
            verdicts[teacher_id] = "ok"
    return verdicts, users


def _kinds(raw, present: set, counts: Counter) -> list:
    kinds = []
    for name in raw or []:
        kind = KIND_ALIASES.get(str(name).strip().lower())
        if kind is None:
            counts["kind_unknown"] += 1
        elif kind not in kinds:
            kinds.append(str(kind))
    if not kinds or (present and set(kinds) >= present):
        counts["kinds_all"] += 1
        return []
    return sorted(kinds)


def _enrollments(raw, enrolled: set, counts: Counter):
    given = set(_ids(raw))
    if not given:
        counts["enrollments_all"] += 1
        return []
    valid = given & enrolled
    counts["enrollments_invalid"] += len(given - valid)
    if not valid:
        return None
    if valid == enrolled:
        counts["enrollments_all"] += 1
        return []
    return sorted(valid)


def _upsert(offering, teacher, kinds, enrollment_ids, *, organization, actor, batch, context, counts):
    share = context.existing.get((str(offering.pk), teacher.pk))
    if share is not None and share.source != JournalShareSource.LEGACY:
        counts["manual_kept"] += 1
        return
    if share is None:
        share = JournalShare.objects.create(
            organization=organization,
            offering=offering,
            teacher=teacher,
            kinds=kinds,
            source=JournalShareSource.LEGACY,
            batch=batch,
            created_by=actor,
        )
        share.enrollments.set(enrollment_ids)
        context.existing[(str(offering.pk), teacher.pk)] = share
        counts["shares_created"] += 1
        return
    current = {str(pk) for pk in share.enrollments.values_list("pk", flat=True)}
    if sorted(share.kinds or []) == kinds and current == set(enrollment_ids):
        counts["shares_unchanged"] += 1
        return
    share.kinds = kinds
    share.batch = batch
    share.save(update_fields=["kinds", "batch", "updated_at"])
    share.enrollments.set(enrollment_ids)
    counts["shares_updated"] += 1


def apply_shares(organization, data, *, actor, batch) -> Counter:
    """Faylın paylarını yaz (çağıranın tranzaksiyasında). Saylar qaytarılır."""
    counts: Counter = Counter()
    period = current_period(organization, data.get("period"))
    items = [item for item in data["shares"] if isinstance(item, dict)]
    counts["shares_in_file"] = len(data["shares"])
    # Çıxarışlar ƏVVƏL: «bütün aktiv tələbələr → boş» qərarı son siyahıya görə verilsin (ikinci işə salınış eyni).
    counts.update(apply_drops(organization, period, _ids(data.get("drop_enrollments")), actor=actor))
    context = _Context(organization, period, sorted({str(item.get("offering")) for item in items}))
    teacher_ids = sorted({item.get("teacher") for item in items if isinstance(item.get("teacher"), int)})
    verdicts, users = _teacher_verdicts(organization, teacher_ids)
    for item in items:
        offering = context.offerings.get(str(item.get("offering")))
        if offering is None or not offering.is_active:
            counts["offering_missing"] += 1
            continue
        verdict = verdicts.get(item.get("teacher"), "teacher_missing")
        if verdict != "ok":
            counts[verdict] += 1
            continue
        teacher = users[item["teacher"]]
        is_owner = offering.instructor_id == teacher.pk
        counts["owner_shares" if is_owner else "teacher_shares"] += 1
        if bool(item.get("is_owner")) != is_owner:
            counts["owner_flag_mismatch"] += 1
        kinds = _kinds(item.get("kinds"), context.kinds[str(offering.pk)], counts)
        enrollment_ids = _enrollments(item.get("enrollments"), context.enrolled[str(offering.pk)], counts)
        if enrollment_ids is None:
            counts["no_valid_enrollments"] += 1
            continue
        _upsert(
            offering,
            teacher,
            kinds,
            enrollment_ids,
            organization=organization,
            actor=actor,
            batch=batch,
            context=context,
            counts=counts,
        )
    return counts


def apply_drops(organization, period, enrollment_ids, *, actor) -> Counter:
    """Datası olmayan səviyyə-artığı qeydiyyatları «Jurnal təmizliyi» qərarı ilə ``dropped`` et."""
    from . import journal_hygiene as hygiene
    from . import journal_hygiene_actions as actions
    from . import journal_hygiene_rows as rows_service

    counts: Counter = Counter({"drops_in_file": len(enrollment_ids)})
    valid = []
    for raw in enrollment_ids:
        parsed = parse_uuid(raw)
        if parsed is None:
            counts["drop_not_enrolled"] += 1
        else:
            valid.append(str(parsed))
    enrolled = Enrollment.objects.filter(
        organization=organization, offering__period=period, pk__in=valid, status=Enrollment.Status.ENROLLED
    )
    enrolled_ids = {str(pk) for pk in enrolled.values_list("pk", flat=True)}
    counts["drop_not_enrolled"] += len(set(valid) - enrolled_ids)
    empty = list(
        enrolled.filter(absence_hours=0)
        .filter(*hygiene.no_evidence_filters())
        .select_for_update(of=("self",))
        .order_by("pk")
        .values_list("pk", "status")
    )
    counts["drop_kept_has_data"] = len(enrolled_ids) - len(empty)
    if not empty:
        return counts
    evidence = rows_service.evidence_counts([pk for pk, _status in empty])
    rows = []
    for pk, status in empty:
        row = {"id": str(pk), "status": status, "reason": DROP_REASON_CODE, "strong": False, "absence_hours": 0}
        row["tags"] = [{"code": DROP_REASON_CODE}]
        row["evidence"] = actions.row_evidence(row, hygiene.EMPTY, evidence.get(str(pk)))
        rows.append(row)
    for start in range(0, len(rows), rows_service.MAX_BATCH):
        result = actions.record_decisions(
            organization=organization,
            category=hygiene.EMPTY,
            rows=rows[start : start + rows_service.MAX_BATCH],
            to_status=Enrollment.Status.DROPPED,
            reason=DROP_REASON,
            actor=actor,
        )
        counts["drops_applied"] += int(result["changed"])
    return counts


def undo_batch(organization, batch: str) -> Counter:
    """Paketin aktiv paylarını söndür (qeydiyyat çıxarışları «Jurnal təmizliyi» tarixçəsindən geri qaytarılır)."""
    changed = JournalShare.objects.filter(organization=organization, batch=batch, is_active=True).update(
        is_active=False, updated_at=timezone.now()
    )
    return Counter({"shares_deactivated": changed})
