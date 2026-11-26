"""«Tələbəni bərpa et» — jurnaldan çıxarılmış tələbənin jurnala QAYTARILMASI (sahib 2026-11-15).

Sahib: «kimsə səhvən jurnaldan uzaqlaşdırılıb, sonra necə bərpa edim bilmirəm».

YENİ ÇIXARMA / BƏRPA MEXANİZMİ İCAD OLUNMUR — bu modul jurnal səhifəsində BİR siyahı və BİR «Bərpa et» verir,
əməlin özü isə mövcud yollara ötürülür (köhnə qeydiyyat aktivləşir, bal / davamiyyət xanaları yerində qalır —
yeni ``Enrollment`` yaradılmır):

* **«Fəndən azad»** (``subject_exempt`` qərarı) → :func:`subject_exempt.restore_student`;
* **«Jurnal təmizliyi»** qərarı (ayrılmış tələbə «dondur» / boş fənn / keçirilməyən fənn / sistem
  önləmələri, ``from_status=enrolled``) → :func:`journal_hygiene_actions.revert_locked` — yalnız RİM rəhbəri /
  superadmin (həmin qərarları verən açar, ``journal.correct`` org-wide);
* **alt qrupdan əlavənin «Çıxar»-ı** → :func:`guest_roster.add_guest_student` (mövcud ``dropped`` sətir yenidən
  ``enrolled`` olur) + kredit / tutum qapısı və yerləşdirmə tarixçəsi, «Alt qrupdan tələbə əlavə et» ilə EYNİ.

Bərpa olunmayanlar siyahıda SƏBƏBLƏ görünür (düymə yoxdur): akademik status (məzuniyyət / xaric / məzun —
bərpa əmri ilə qayıdır), rəsmi qrup köçürməsi (``superseded_by`` — qrup yazısı yalnız köçürmə servisi ilə),
xarici nəticənin tanınması, sistemin başqa yolla çıxardığı sətir.

QAPILAR (fail-closed, server tərəfdə): siyahı dəyişikliyi qapısı (:func:`guest_roster.roster_block_reason` —
bağlı jurnal / keçmiş dövr), növə görə açar, «tələbə həmin fənn üzrə başqa jurnalda aktivdir» (aydın xəta,
hansı qrupun jurnalı), qeydiyyatın statusu qərardan sonra dəyişibsə rədd. Hər bərpa jurnalın «Dəyişiklik
tarixçəsi»nə ``roster-restore`` sətri yazır (:func:`journal_removal.record_restore`); qeyd istəyə bağlıdır.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from . import guest_roster
from . import journal_hygiene as hygiene
from . import journal_hygiene_actions as actions
from . import journal_inactive_freeze, journal_removal, subject_exempt
from .journal_names import journal_student_name
from .models import (
    AcademicStatus,
    Enrollment,
    HygieneCategory,
    JournalHygieneDecision,
    JournalRemoval,
    RemovalAction,
)

_CTX = "registrar.roster_restore"

#: Bir siyahıda ən çox sətir (yeni → köhnə).
MAX_ROWS = 300

KIND_EXEMPT = "exempt"
KIND_HYGIENE = "hygiene"
KIND_GUEST = "guest"
#: 08.11 «aktivliyi olmayan tələbə» dondurulması (sahib 2026-11-26) — hesab + bütün fənlər birlikdə qayıdır.
KIND_INACTIVE = "inactive_freeze"

#: Jurnal tarixçəsindəki «əməl» kodu (``JournalRemoval`` sətri deyil — yalnız audit izi).
HISTORY_ACTION_HYGIENE = journal_removal.HISTORY_ACTION_HYGIENE


class RestoreError(Exception):
    """İstifadəçiyə göstərilə bilən xəta (``code`` + mesaj + HTTP statusu)."""

    def __init__(self, code, message, status=400):
        super().__init__(code, message, status)
        self.code = code
        self.message = str(message)
        self.status = status


# ── Səlahiyyət ───────────────────────────────────────────────────────────────


def can_view(user, offering) -> bool:
    """Siyahını görən: çıxara bilən hər kəs (``journal.correct`` org-wide və ya əhatəli ``journal.roster``)."""
    return subject_exempt.can_exempt(user, offering)


def _kind_allowed(user, offering, kind) -> bool:
    if kind == KIND_EXEMPT:
        return subject_exempt.can_exempt(user, offering)
    if kind == KIND_GUEST:
        return guest_roster.can_manage_offering_roster(user, offering)
    if kind in (KIND_HYGIENE, KIND_INACTIVE):
        return actions.can_apply(user, offering.organization)
    return False


def block_reason(offering) -> str:
    """Bərpa qadağandırsa səbəb (alt qrup / «Fəndən azad» ilə EYNİ qapı), açıqdırsa boş sətir."""
    return guest_roster.roster_block_reason(offering)


# ── Təsnifat ─────────────────────────────────────────────────────────────────


def _removed_queryset(offering):
    return Enrollment.objects.filter(
        organization=offering.organization,
        offering=offering,
        status__in=(Enrollment.Status.DROPPED, Enrollment.Status.SUSPENDED),
    )


def removed_count(offering) -> int:
    """Düymənin sayğacı — bir COUNT sorğusu."""
    return _removed_queryset(offering).count()


def _active_decisions(enrollment_ids) -> dict:
    """``{enrollment_id: ən son qüvvədə olan qərar}`` — bir sorğu."""
    rows = (
        JournalHygieneDecision.objects.filter(enrollment_id__in=list(enrollment_ids), reverted_at__isnull=True)
        .order_by("enrollment_id", "-created_at")
        .only(
            "id",
            "enrollment_id",
            "category",
            "reason_code",
            "from_status",
            "to_status",
            "reason",
            "decided_by_name",
            "created_at",
        )
    )
    found: dict = {}
    for row in rows:
        found.setdefault(row.enrollment_id, row)
    return found


def _latest_removals(enrollment_ids) -> dict:
    """``{enrollment_id: ən son JournalRemoval}`` — «niyə» sualının cavabı (bir sorğu)."""
    rows = JournalRemoval.objects.filter(enrollment_id__in=list(enrollment_ids)).order_by(
        "enrollment_id", "-created_at"
    )
    found: dict = {}
    for row in rows:
        found.setdefault(row.enrollment_id, row)
    return found


def classify(enrollment, decision=None, *, inactive=False) -> dict:
    """``{"kind", "info"}`` — ``kind`` bərpa yoludur (boş → bərpa olunmur, ``info`` səbəbi deyir)."""
    status = enrollment.status
    if decision is not None and decision.to_status == status:
        if decision.category == subject_exempt.EXEMPT:
            if decision.reason_code == subject_exempt.RECOGNITION_REASON_CODE:
                return {
                    "kind": "",
                    "info": pgettext(
                        _CTX, "Xarici nəticə tanınıb — «Xarici nəticələrin tanınması» bölməsində ləğv olunur."
                    ),
                }
            return {"kind": KIND_EXEMPT, "info": ""}
        if decision.from_status == Enrollment.Status.ENROLLED:
            return {"kind": KIND_HYGIENE, "info": ""}
        return {"kind": "", "info": pgettext(_CTX, "Əvvəl də jurnalda aktiv deyildi — bərpa onu qaytarmır.")}
    if status == Enrollment.Status.DROPPED and enrollment.superseded_by_id:
        return {
            "kind": "",
            "info": pgettext(
                _CTX, "Rəsmi qrup köçürməsi ilə başqa jurnala keçib — qrup yalnız köçürmə əmri ilə dəyişir."
            ),
        }
    if status == Enrollment.Status.DROPPED and enrollment.source_group_id:
        return {"kind": KIND_GUEST, "info": ""}
    if status == Enrollment.Status.SUSPENDED and inactive:
        return {"kind": KIND_INACTIVE, "info": ""}
    if status == Enrollment.Status.SUSPENDED:
        return {
            "kind": "",
            "info": pgettext(
                _CTX,
                "Akademik statusa görə dondurulub (məzuniyyət / xaric / məzun) — qrup reyestrində «Bərpa et» "
                "əmri ilə qayıdır.",
            ),
        }
    return {"kind": "", "info": pgettext(_CTX, "Sistem tərəfindən çıxarılıb — bu pəncərədən bərpa olunmur.")}


def _elsewhere_map(offering, enrollments) -> dict:
    """``{student_id: başqa aktiv jurnalın qrupu}`` — həmin fənn + dövr üzrə (bir sorğu)."""
    student_ids = {item.student_id for item in enrollments}
    if not student_ids:
        return {}
    rows = (
        Enrollment.objects.filter(
            organization=offering.organization,
            status=Enrollment.Status.ENROLLED,
            student_id__in=student_ids,
            offering__subject_id=offering.subject_id,
            offering__period_id=offering.period_id,
        )
        .exclude(offering_id=offering.pk)
        .values_list("student_id", "offering__group__name")
    )
    found: dict = {}
    for student_id, group_name in rows:
        found.setdefault(student_id, group_name or "—")
    return found


def elsewhere_message(kind, group_name) -> str:
    """«Başqa jurnalda aktivdir» — nə etməli olduğunu deyən mətn."""
    if kind == KIND_GUEST:
        return pgettext(
            _CTX,
            "Tələbə bu fənn üzrə «%(group)s» qrupunun jurnalında aktivdir. Bu jurnala qaytarmaq üçün «Alt qrupdan "
            "tələbə əlavə et» pəncərəsində «öz jurnalından azad et» seçin.",
        ) % {"group": group_name}
    return pgettext(
        _CTX,
        "Tələbə bu fənn üzrə «%(group)s» qrupunun jurnalında aktivdir — əvvəlcə oradan çıxarın, sonra bərpa edin.",
    ) % {"group": group_name}


def _status_label(enrollment) -> str:
    if enrollment.status == Enrollment.Status.SUSPENDED:
        return pgettext(_CTX, "Dondurulub")
    return pgettext(_CTX, "Çıxarılıb")


def _academic_label(record) -> str:
    if record is None:
        return ""
    try:
        return str(AcademicStatus(record.status).label)
    except ValueError:
        return str(record.status or "")


def _decision_label(decision) -> str:
    """«Ayrılmış tələbə — Xaric olunub» (qərar kateqoriyası + səbəb kodu, aktiv dildə)."""
    try:
        category = str(HygieneCategory(decision.category).label)
    except ValueError:
        category = str(decision.category or "")
    code = str(decision.reason_code or "")
    detail = hygiene.label(code) if code in hygiene.LABELS else ""
    return " — ".join(part for part in (category, detail) if part)


def rows(user, offering) -> list:
    """Bu jurnaldan çıxarılmış / dondurulmuş tələbələr (yeni → köhnə) — modalın siyahısı.

    Sorğu sayı sətir sayından asılı deyil: qeydiyyatlar + qərarlar + səbəblər + başqa jurnal + cari qrup.
    """
    from .models import StudentAcademicRecord

    enrollments = list(
        _removed_queryset(offering)
        .select_related("student__profile", "source_group")
        .order_by("-updated_at", "pk")[:MAX_ROWS]
    )
    if not enrollments:
        return []
    ids = [item.pk for item in enrollments]
    decisions = _active_decisions(ids)
    removals = _latest_removals(ids)
    elsewhere = _elsewhere_map(offering, enrollments)
    records: dict = {}
    for record in (
        StudentAcademicRecord.objects.filter(
            organization=offering.organization, student_id__in={item.student_id for item in enrollments}
        )
        .select_related("group")
        .order_by("student_id", "-is_active", "-created_at")
    ):
        records.setdefault(record.student_id, record)
    blocked = block_reason(offering)
    inactive = journal_inactive_freeze.frozen_enrollment_ids(
        offering.organization,
        {item.student_id for item in enrollments if item.status == Enrollment.Status.SUSPENDED},
    )
    result = []
    for enrollment in enrollments:
        decision = decisions.get(enrollment.pk)
        removal = removals.get(enrollment.pk)
        state = classify(enrollment, decision, inactive=str(enrollment.pk) in inactive)
        kind = state["kind"]
        record = records.get(enrollment.student_id)
        message = state["info"]
        if kind and enrollment.student_id in elsewhere:
            message = elsewhere_message(kind, elsewhere[enrollment.student_id])
        elif kind and not _kind_allowed(user, offering, kind):
            message = pgettext(_CTX, "Bu qərarı yalnız RİM geri qaytara bilər.")
        if removal is not None and decision is not None and decision.created_at > removal.created_at:
            removal = None  # köhnə dövrün səbəbi — son çıxarılma qərarla (səbəb sətri olmadan) edilib
        if removal is not None:
            when, by = removal.created_at, removal.actor_name
            why = journal_removal.reason_label(removal.reason)
            note = removal.note
        elif decision is not None:
            when, by, why, note = (
                decision.created_at,
                decision.decided_by_name,
                _decision_label(decision),
                decision.reason,
            )
        else:
            when, by, why, note = enrollment.updated_at, "", "", ""
        if kind == KIND_INACTIVE:
            by = pgettext(_CTX, "Sistem (08.11 aktivlik yoxlaması)")
            why = pgettext(
                _CTX,
                "Heç bir fəndə i/e, bal və midterm olmadığı üçün dondurulub. «Bərpa et» hesabı açır və tələbəni "
                "dondurulduğu bütün fənlərin jurnallarına qaytarır.",
            )
        elif enrollment.status == Enrollment.Status.SUSPENDED and decision is None and record is not None:
            why = why or _academic_label(record)
        result.append(
            {
                "enrollment": str(enrollment.pk),
                "name": journal_student_name(enrollment.student),
                "group": getattr(getattr(record, "group", None), "name", "") or "",
                "source_group": getattr(enrollment.source_group, "name", "") or "",
                "status": enrollment.status,
                "status_label": _status_label(enrollment),
                "when": timezone.localtime(when).strftime("%d.%m.%Y %H:%M") if when else "",
                "by": by or "",
                "reason": why,
                "note": note or "",
                "kind": kind,
                "restorable": bool(kind) and not message and not blocked,
                "message": message,
            }
        )
    return result


# ── Bərpa ────────────────────────────────────────────────────────────────────


def clean_note(raw) -> str:
    return journal_removal.clean_note(raw)


def _default_note() -> str:
    return pgettext(_CTX, "Jurnala bərpa edildi")


def _lock_enrollment(offering, enrollment_id):
    enrollment = (
        Enrollment.objects.select_for_update(of=("self",))
        .select_related("offering", "student")
        .filter(organization=offering.organization, offering=offering, pk=enrollment_id)
        .first()
    )
    if enrollment is None:
        raise RestoreError("not_found", pgettext(_CTX, "Qeydiyyat tapılmadı."), status=404)
    if enrollment.status == Enrollment.Status.ENROLLED:
        raise RestoreError("already_enrolled", pgettext(_CTX, "Tələbə artıq jurnaldadır."), status=409)
    return enrollment


def _assert_not_elsewhere(offering, enrollment, kind):
    elsewhere = _elsewhere_map(offering, [enrollment])
    if enrollment.student_id in elsewhere:
        raise RestoreError("active_elsewhere", elsewhere_message(kind, elsewhere[enrollment.student_id]), status=409)


def _restore_hygiene(*, offering, enrollment, decision, actor, note, request):
    decision = JournalHygieneDecision.objects.select_for_update(of=("self",)).get(pk=decision.pk)
    if decision.reverted_at is not None:
        raise RestoreError("not_revertable", pgettext(_CTX, "Qərar artıq geri qaytarılıb."), status=409)
    actions.revert_locked(
        organization=offering.organization,
        decisions=[decision],
        enrollments={enrollment.pk: enrollment},
        reason=note or _default_note(),
        actor=actor,
        request=request,
    )
    journal_removal.record_restore(
        enrollment=enrollment, actor=actor, note=note, request=request, action=HISTORY_ACTION_HYGIENE
    )


def _restore_guest(*, offering, enrollment, actor, note, request):
    from . import subgroup_placement

    # Tələbə hələ də o qrupdadırsa provenans məhz ondan götürülür; qrupu dəyişibsə servis cari qeydi oxuyur və
    # «mənbə qrupu fərqlidir» xətasını özü verir (qrup yazısı yalnız köçürmə servisi ilə — burada heç nə yazılmır).
    same_group = guest_roster._record_for(
        offering=offering, student=enrollment.student, source_group=enrollment.source_group
    )
    source_group = enrollment.source_group if same_group is not None else None
    try:
        plan = subgroup_placement.journal_modal_check(student=enrollment.student, offering=offering)
        restored = guest_roster.add_guest_student(
            offering=offering,
            student=enrollment.student,
            by_user=actor,
            source_group=source_group,
            reason=note or _default_note(),
        )
    except subgroup_placement.SubgroupPlacementError as exc:
        raise RestoreError(exc.code, exc.message, status=409)
    except ValidationError as exc:
        raise RestoreError("guest_blocked", "; ".join(exc.messages), status=409)
    document = guest_roster.guest_document_map([restored.pk]).get(restored.pk)
    subgroup_placement.record_journal_placement(
        plan=plan,
        enrollment=restored,
        document=document[0] if document else None,
        actor=actor,
        reason=note or _default_note(),
        request=request,
    )
    journal_removal.record_restore(
        enrollment=restored, actor=actor, note=note, request=request, action=RemovalAction.GUEST_REMOVE.value
    )


def restore(*, offering, enrollment_id, actor, note="", request=None) -> dict:
    """Çıxarılmış tələbəni bu jurnala qaytarır (köhnə qeydiyyat aktivləşir; bir tranzaksiya).

    Növü klientdən GÖTÜRÜLMÜR — server qeydiyyatın vəziyyətindən təyin edir (:func:`classify`)."""
    blocked = block_reason(offering)
    if blocked:
        raise RestoreError("roster_closed", blocked, status=409)
    note = clean_note(note)
    with transaction.atomic():
        enrollment = _lock_enrollment(offering, enrollment_id)
        decision = _active_decisions([enrollment.pk]).get(enrollment.pk)
        frozen = journal_inactive_freeze.frozen_enrollment_ids(offering.organization, {enrollment.student_id})
        state = classify(enrollment, decision, inactive=str(enrollment.pk) in frozen)
        kind = state["kind"]
        if not kind:
            raise RestoreError("not_restorable", state["info"], status=409)
        if not _kind_allowed(actor, offering, kind):
            raise RestoreError(
                "permission_denied", pgettext(_CTX, "Bu qərarı yalnız RİM geri qaytara bilər."), status=403
            )
        _assert_not_elsewhere(offering, enrollment, kind)
        if kind == KIND_EXEMPT:
            try:
                subject_exempt.restore_student(
                    offering=offering,
                    decision_id=decision.pk,
                    actor=actor,
                    reason=note or _default_note(),
                    request=request,
                )
            except subject_exempt.HygieneError as exc:
                raise RestoreError(exc.code, exc.message, status=exc.status)
        elif kind == KIND_INACTIVE:
            journal_inactive_freeze.undo_student(
                organization=offering.organization, actor=actor, student_id=enrollment.student_id
            )
            enrollment.refresh_from_db(fields=["status"])
            if enrollment.status != Enrollment.Status.ENROLLED:
                raise RestoreError("not_restorable", pgettext(_CTX, "Tələbə bərpa olunmadı."), status=409)
            journal_removal.record_restore(
                enrollment=enrollment,
                actor=actor,
                note=note,
                request=request,
                action=journal_removal.HISTORY_ACTION_INACTIVE,
            )
        elif kind == KIND_HYGIENE:
            _restore_hygiene(
                offering=offering, enrollment=enrollment, decision=decision, actor=actor, note=note, request=request
            )
        else:
            _restore_guest(offering=offering, enrollment=enrollment, actor=actor, note=note, request=request)
    return {"enrollment": str(enrollment.pk), "kind": kind}


__all__ = [
    "KIND_EXEMPT",
    "KIND_GUEST",
    "KIND_HYGIENE",
    "KIND_INACTIVE",
    "MAX_ROWS",
    "RestoreError",
    "block_reason",
    "can_view",
    "classify",
    "elsewhere_message",
    "removed_count",
    "restore",
    "rows",
]
