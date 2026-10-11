"""«Jurnal təmizliyi» — QƏRAR qatı: önizləmə → təsdiq və «Bərpa et» (sahib 2026-10-10).

QAYDALAR (hamısı fail-closed):

* **Heç nə silinmir.** Ayrılmış tələbənin sətri ``suspended`` olur (akademik status sinxronu ilə EYNİ məna:
  jurnal / imtahan siyahısından çıxır, «tərk edilmiş» sayılmır, bərpa onu qaytarır); sətir həm də BOŞDURSA
  ``dropped`` seçilə bilər. Boş fənn ``dropped`` olur (``superseded_by`` boş qalır) və nəticə səthlərindən düşür.
* **Keçirilməyən fənn** (sahib 2026-10-11) boş fənn kimi ``dropped`` olur, amma vahid AÇILIŞDIR: seçim
  açılışın bütün aktiv sətirlərini əhatə etməlidirsə tətbiq olunur (yarımçıq seçim rədd edilir).
* **Önizləmə ilə təsdiq arasında sürüşmə rədd olunur.** Önizləmə hər sətrin sübut snapshot-undan sha256 izi
  qaytarır; tətbiq sətirləri ``select_for_update`` ilə kilidləyib izi YENİDƏN hesablayır — fərq varsa (yeni
  bal yazılıb, status dəyişib, sətir artıq namizəd deyil) heç nə yazılmır.
* **Bir əməl ≤ 500 sətir, bir tranzaksiya**; səbəb ≥ 20 simvol; hər qərar ``JournalHygieneDecision``
  jurnalına (append-only) və ``core.audit``-a (``registrar.journal_hygiene``) yazılır.
* **Səlahiyyət:** superadmin və ya təşkilat miqyaslı ``journal.correct`` (RİM rəhbəri). Menyu qapısı ayrıca
  accounts-dadır; bu qat onu təkrar yoxlayır.
* **«Bərpa et»** yalnız bu jurnaldakı qərarı geri qaytarır: status əvvəlki dəyərə dönür (qeydiyyatın statusu
  o vaxtdan dəyişməyibsə və tələbə həmin fənn üzrə başqa jurnalda aktiv deyilsə).

Yan təsirlər (bilərəkdən): ``dropped`` sətir həmin qrupa sonrakı köçürməni bloklayır (``transfer``-in tarixçə
qaydası) — «Bərpa et» onu açır; sorğu hədəfləri yenidən hesablanmır; LMS üzvlüyü silinmir (mövcud dondurma
axını kimi), bərpada isə çatışmayan üzvlük əlavə olunur.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from core import audit as audit_service
from core.constants import AuditAction

from . import journal_hygiene as hygiene
from . import journal_hygiene_rows as rows_service
from .models import HYGIENE_REASON_MIN_LENGTH, Enrollment, JournalHygieneDecision

_CTX = "registrar.journal_hygiene"
AUDIT_RESOURCE = "registrar.journal_hygiene"
MAX_REASON_LENGTH = 2000
TARGET_SUSPEND = "suspend"
TARGET_DROP = "drop"
TARGETS = (TARGET_SUSPEND, TARGET_DROP)


class HygieneError(Exception):
    """İstifadəçiyə göstərilə bilən xəta (``code`` + mesaj + HTTP statusu + opsional təfərrüat)."""

    def __init__(self, code, message, status=400, details=None):
        super().__init__(code, message, status, details)
        self.code = code
        self.message = str(message)
        self.status = status
        self.details = details or []


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def can_apply(user, organization) -> bool:
    """Superadmin və ya təşkilat miqyaslı ``journal.correct`` (sahib/RİM rəhbəri ``*`` ilə daxil)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _is_superadmin(user):
        return True
    if organization is None:
        return False
    from .corrections import CORRECT_PERMISSION

    org_unit = django_apps.get_model("organizations", "OrgUnit")
    return org_unit.user_permission_scope(user, organization, CORRECT_PERMISSION).is_org_wide


def _require(user, organization):
    if not can_apply(user, organization):
        raise HygieneError(
            "permission_denied",
            pgettext(_CTX, "Jurnal təmizliyi üçün səlahiyyətiniz yoxdur (journal.correct)."),
            status=403,
        )


def _clean_ids(raw) -> list:
    values = raw if isinstance(raw, (list, tuple)) else []
    ids, seen = [], set()
    for value in values:
        parsed = hygiene.parse_uuid(value)
        if parsed is not None and parsed not in seen:
            seen.add(parsed)
            ids.append(parsed)
    if not ids:
        raise HygieneError("empty_selection", pgettext(_CTX, "Heç bir sətir seçilməyib."))
    if len(ids) > rows_service.MAX_BATCH:
        raise HygieneError(
            "batch_too_large",
            pgettext(_CTX, "Bir əməldə ən çox %(n)d sətir emal olunur.") % {"n": rows_service.MAX_BATCH},
        )
    return ids


def clean_reason(raw) -> str:
    reason = " ".join(str(raw or "").split())
    if len(reason) < HYGIENE_REASON_MIN_LENGTH:
        raise HygieneError(
            "reason_too_short",
            pgettext(_CTX, "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil."),
        )
    return reason[:MAX_REASON_LENGTH]


def target_status(category: str, target: str) -> str:
    """Kateqoriya + hədəf → yeni status; boş / keçirilməyən fənn yalnız ``dropped`` ola bilər."""
    if category == hygiene.LEFT and target == TARGET_SUSPEND:
        return Enrollment.Status.SUSPENDED
    if category in hygiene.CATEGORIES and target == TARGET_DROP:
        return Enrollment.Status.DROPPED
    raise HygieneError("invalid_target", pgettext(_CTX, "Bu kateqoriya üçün naməlum əməliyyat."))


# ── Sübut snapshot-u və izi ──────────────────────────────────────────────────


def _digest(payload) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def row_evidence(row: dict, category: str, counts: dict) -> dict:
    """Qərar anındakı sübut — jurnala yazılır, iz (digest) ondan hesablanır."""
    return {
        "enrollment": row["id"],
        "category": category,
        "status": row["status"],
        "reason": row["reason"],
        "tags": sorted(tag["code"] for tag in row["tags"]),
        "strong": bool(row["strong"]),
        "absence_hours": int(row.get("absence_hours") or 0),
        "counts": dict(sorted((counts or {}).items())),
    }


def snapshot(organization, category: str, ids) -> dict:
    """``{id: sətir}`` — YALNIZ hazırda namizəd olan sətirlər, sübut sayları ilə."""
    queryset = hygiene.candidates(organization, category).filter(pk__in=list(ids))
    rows = rows_service.rows_for(queryset, category)
    counts = rows_service.evidence_counts([row["id"] for row in rows])
    for row in rows:
        row["evidence"] = row_evidence(row, category, counts.get(row["id"]))
    return {row["id"]: row for row in rows}


def batch_digest(rows: dict, to_status: str) -> str:
    return _digest({"to": to_status, "rows": sorted((key, _digest(row["evidence"])) for key, row in rows.items())})


# ── Önizləmə ─────────────────────────────────────────────────────────────────


def _partial(organization, category, rows) -> list:
    """Keçirilməyən fənn vahid AÇILIŞDIR: seçim açılışın bütün aktiv sətirlərini əhatə etməlidir."""
    if category != hygiene.NOT_HELD or not rows:
        return []
    return hygiene.not_held.partial_offerings(organization, rows.values())


def _journal_summary(rows) -> list:
    journals = {}
    for row in rows:
        item = journals.setdefault(
            row["offering_id"], {"subject": row["subject"], "group": row["group"], "period": row["period"], "rows": 0}
        )
        item["rows"] += 1
    return sorted(journals.values(), key=lambda item: (-item["rows"], item["subject"]))


def preview(*, organization, actor, category, enrollment_ids, target) -> dict:
    """Seçimin təsiri: neçə sətir/jurnal/tələbə, sübut, bloklananlar və tətbiq üçün iz."""
    _require(actor, organization)
    ids = _clean_ids(enrollment_ids)
    to_status = target_status(category, target)
    rows = snapshot(organization, category, ids)
    missing = len(ids) - len(rows)
    with_evidence = [row for row in rows.values() if row["has_evidence"]]
    blocked = []
    if category == hygiene.LEFT and to_status == Enrollment.Status.DROPPED:
        blocked = [{"id": row["id"], "student": row["student"], "subject": row["subject"]} for row in with_evidence]
    partial = _partial(organization, category, rows)
    totals = Counter()
    for row in rows.values():
        totals.update(row["evidence"]["counts"])
    journals = _journal_summary(rows.values())
    return {
        "category": category,
        "target": target,
        "to_status": to_status,
        "to_label": rows_service.status_label(to_status),
        "requested": len(ids),
        "rows": len(rows),
        "missing": missing,
        "journals": len(journals),
        "journal_list": journals[:12],
        "students": len({row["student_id"] for row in rows.values()}),
        "with_evidence": len(with_evidence),
        "evidence_totals": dict(sorted(totals.items())),
        "blocked": blocked[:50],
        "blocked_total": len(blocked),
        "partial_total": len(partial),
        "digest": batch_digest(rows, to_status),
        "can_apply": bool(rows) and not missing and not blocked and not partial,
    }


# ── Tətbiq ───────────────────────────────────────────────────────────────────


def _actor_name(actor) -> str:
    if actor is None or not getattr(actor, "pk", None):
        return pgettext(_CTX, "Sistem")
    return ((actor.get_full_name() or "").strip() or actor.get_username())[:200]


def record_decisions(*, organization, category, rows, to_status, reason, actor=None, request=None) -> dict:
    """Status yazısı + qərar jurnalı + audit — ÇAĞIRANIN tranzaksiyasında (önləmə axınları da işlədir).

    ``rows`` — :func:`snapshot` formasında sətirlər (``id``, ``status``, ``reason``, ``evidence``).
    Status yazısı mənbə statusu ilə şərtlidir; sayı tutmasa (paralel dəyişiklik) xəta atılır və bütün
    tranzaksiya geri qaytarılır.
    """
    rows = list(rows)
    if not rows:
        return {"batch": "", "changed": 0, "to_status": to_status, "decision_ids": []}
    batch = uuid.uuid4()
    now = timezone.now()
    by_status = {}
    for row in rows:
        by_status.setdefault(row["status"], []).append(row["id"])
    changed = 0
    for from_status, ids in by_status.items():
        changed += Enrollment.objects.filter(organization=organization, pk__in=ids, status=from_status).update(
            status=to_status, updated_at=now
        )
    if changed != len(rows):
        raise HygieneError(
            "drift", pgettext(_CTX, "Seçilmiş sətirlər bu arada dəyişib — siyahını yeniləyin."), status=409
        )
    actor = actor if getattr(actor, "pk", None) else None
    decisions = JournalHygieneDecision.objects.bulk_create(
        [
            JournalHygieneDecision(
                organization=organization,
                enrollment_id=row["id"],
                batch=batch,
                category=category,
                reason_code=row["reason"],
                from_status=row["status"],
                to_status=to_status,
                evidence=row["evidence"],
                evidence_digest=_digest(row["evidence"]),
                reason=reason,
                decided_by=actor,
                decided_by_name=_actor_name(actor),
            )
            for row in rows
        ],
        batch_size=rows_service.MAX_BATCH,
    )
    decision_ids = [str(item.pk) for item in decisions]
    audit_service.log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(batch),
        resource_repr=f"{category} · {len(rows)}",
        old_values={"status": sorted(by_status)},
        new_values={"status": to_status},
        changes={
            "batch": str(batch),
            "category": category,
            "enrollment_ids": [str(row["id"]) for row in rows],
            "decision_ids": decision_ids,
            "reasons": dict(Counter(row["reason"] for row in rows)),
        },
        reason=reason,
    )
    return {"batch": str(batch), "changed": changed, "to_status": to_status, "decision_ids": decision_ids}


def apply(*, organization, actor, category, enrollment_ids, target, reason, expected_digest, request=None) -> dict:
    """Önizlənmiş seçimi tətbiq edir — kilid altında yenidən yoxlayıb (sürüşmə → heç nə yazılmır)."""
    _require(actor, organization)
    ids = _clean_ids(enrollment_ids)
    reason = clean_reason(reason)
    to_status = target_status(category, target)
    if not str(expected_digest or "").strip():
        raise HygieneError("preview_required", pgettext(_CTX, "Əvvəlcə önizləməyə baxın."))
    with transaction.atomic():
        list(
            Enrollment.objects.select_for_update(of=("self",))
            .filter(organization=organization, pk__in=ids)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        rows = snapshot(organization, category, ids)
        if len(rows) != len(ids) or batch_digest(rows, to_status) != str(expected_digest).strip():
            raise HygieneError(
                "drift",
                pgettext(_CTX, "Siyahı önizləmədən sonra dəyişib — yenidən önizləyin."),
                status=409,
            )
        if _partial(organization, category, rows):
            raise HygieneError(
                "partial_offering",
                pgettext(_CTX, "Keçirilməyən fənn bütöv açılış kimi çıxarılır — açılışın bütün sətirlərini seçin."),
                status=409,
            )
        if category == hygiene.LEFT and to_status == Enrollment.Status.DROPPED:
            if any(row["has_evidence"] for row in rows.values()):
                raise HygieneError(
                    "has_evidence", pgettext(_CTX, "Məlumatı olan sətir yalnız dondurula bilər."), status=409
                )
        ordered = [rows[str(pk)] for pk in sorted(ids)]
        return record_decisions(
            organization=organization,
            category=category,
            rows=ordered,
            to_status=to_status,
            reason=reason,
            actor=actor,
            request=request,
        )


# ── Bərpa ────────────────────────────────────────────────────────────────────


def _restore_course_members(enrollments) -> int:
    """Bərpa olunan ``enrolled`` sətirlərin LMS üzvlüyü (çatışmayan varsa) — iki sorğu, idempotent."""
    pairs = {(item.offering.course_id, item.student_id) for item in enrollments if item.offering.course_id}
    if not pairs:
        return 0
    membership = django_apps.get_model("courses", "CourseMembership")
    created = membership.objects.bulk_create(
        [membership(course_id=course, user_id=user, role="student") for course, user in sorted(pairs)],
        ignore_conflicts=True,
    )
    return len(created)


def active_elsewhere(organization, enrollments) -> set:
    """Bərpa ``enrolled``-a qaytarırsa: tələbə həmin fənn + dövr üzrə BAŞQA jurnalda aktivdirmi."""
    if not enrollments:
        return set()
    keys = {(item.student_id, item.offering.subject_id, item.offering.period_id) for item in enrollments}
    rows = (
        Enrollment.objects.filter(
            organization=organization,
            status=Enrollment.Status.ENROLLED,
            student_id__in={key[0] for key in keys},
            offering__subject_id__in={key[1] for key in keys},
            offering__period_id__in={key[2] for key in keys},
        )
        .exclude(pk__in=[item.pk for item in enrollments])
        .values_list("student_id", "offering__subject_id", "offering__period_id")
    )
    return {key for key in rows if key in keys}


def revert(*, organization, actor, decision_ids, reason, request=None) -> dict:
    """Seçilmiş qərarları geri qaytarır (hamısı və ya heç biri)."""
    _require(actor, organization)
    ids = _clean_ids(decision_ids)
    reason = clean_reason(reason)
    with transaction.atomic():
        decisions = list(
            JournalHygieneDecision.objects.select_for_update(of=("self",))
            .filter(organization=organization, pk__in=ids)
            .order_by("pk")
        )
        if len(decisions) != len(ids) or any(item.reverted_at for item in decisions):
            raise HygieneError(
                "not_revertable", pgettext(_CTX, "Qərar tapılmadı və ya artıq geri qaytarılıb."), status=409
            )
        enrollments = {
            item.pk: item
            for item in Enrollment.objects.select_for_update(of=("self",))
            .filter(organization=organization, pk__in={item.enrollment_id for item in decisions})
            .select_related("offering")
        }
        restoring = [
            enrollments[item.enrollment_id] for item in decisions if item.from_status == Enrollment.Status.ENROLLED
        ]
        clashes = active_elsewhere(organization, restoring)
        blocked = []
        for item in decisions:
            enrollment = enrollments[item.enrollment_id]
            key = (enrollment.student_id, enrollment.offering.subject_id, enrollment.offering.period_id)
            if enrollment.status != item.to_status:
                blocked.append({"id": str(item.pk), "code": "status_changed"})
            elif item.from_status == Enrollment.Status.ENROLLED and key in clashes:
                blocked.append({"id": str(item.pk), "code": "active_elsewhere"})
        if blocked:
            raise HygieneError(
                "revert_blocked",
                pgettext(
                    _CTX,
                    "Bəzi qərarlar geri qaytarıla bilmir: qeydiyyatın statusu o vaxtdan dəyişib "
                    "və ya tələbə həmin fənn üzrə başqa jurnalda aktivdir.",
                ),
                status=409,
                details=blocked,
            )
        return revert_locked(
            organization=organization,
            decisions=decisions,
            enrollments=enrollments,
            reason=reason,
            actor=actor,
            request=request,
        )


def revert_locked(*, organization, decisions, enrollments, reason, actor=None, request=None) -> dict:
    """KİLİDLƏNMİŞ və yoxlanmış qərarları geri qaytarır: status + qərar jurnalı + audit + LMS üzvlüyü.

    Çağıranın tranzaksiyasında işləyir; ``enrollments`` — ``{pk: Enrollment}`` (``offering`` ilə).
    «Bərpa et» və sistem axınları (seçmə fənnin yenidən seçilməsi) eyni yolu işlədir.
    """
    now = timezone.now()
    actor = actor if getattr(actor, "pk", None) else None
    transitions = {}
    for item in decisions:
        transitions.setdefault((item.to_status, item.from_status), []).append(item.enrollment_id)
    for (current, previous), enrollment_ids in transitions.items():
        Enrollment.objects.filter(pk__in=enrollment_ids, status=current).update(status=previous, updated_at=now)
    JournalHygieneDecision.objects.filter(pk__in=[item.pk for item in decisions], reverted_at__isnull=True).update(
        reverted_at=now, reverted_by=actor, reverted_by_name=_actor_name(actor), revert_reason=reason, updated_at=now
    )
    audit_service.log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(decisions[0].batch),
        resource_repr=f"revert · {len(decisions)}",
        old_values={"status": sorted({item.to_status for item in decisions})},
        new_values={"status": sorted({item.from_status for item in decisions})},
        changes={
            "reverted_decisions": [str(item.pk) for item in decisions],
            "enrollment_ids": [str(item.enrollment_id) for item in decisions],
        },
        reason=reason,
    )
    restoring = [
        enrollments[item.enrollment_id] for item in decisions if item.from_status == Enrollment.Status.ENROLLED
    ]
    return {"reverted": len(decisions), "course_members": _restore_course_members(restoring)}


__all__ = [
    "AUDIT_RESOURCE",
    "HygieneError",
    "TARGETS",
    "TARGET_DROP",
    "TARGET_SUSPEND",
    "active_elsewhere",
    "apply",
    "batch_digest",
    "can_apply",
    "clean_reason",
    "preview",
    "record_decisions",
    "revert",
    "revert_locked",
    "row_evidence",
    "snapshot",
    "target_status",
]
