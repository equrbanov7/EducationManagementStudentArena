"""İmtahan verib fənnin jurnalında OLMAYAN tələbə — səbəb + yerləşdirmə hədəfi (sahib 2026-11-16).

Sahib: «qiymətləndirilmiş nəticəsi olan hər tələbənin nəticəsi öz səhifəsində görünsün» və «tələbə imtahan
verib, amma o fəndən jurnalı yoxdursa — yoxla, başqa qrupda tələbədirsə deməli o fəndə alt qrupdadır».
:mod:`apps.registrar.exam_journal_gaps` QRUP üzrə sayır (sehrbaz); bu modul CƏHD üzrə — körpünün
``no_enrollment`` verdiyi bir tələbə + fənn cütünü səbəbə görə ayırır (YALNIZ OXU, cüt başına sabit sorğu):

``dropped``              cari dövrdə bu fənnin (əkiz kartın) jurnalında ``dropped`` / ``suspended`` sətri var —
                         siyahıdan qəsdən çıxarılıb (səviyyə, köçürmə, dondurma); avtomatik qaytarılmır;
``kollec``               tələbə Kollec qrupundadır — bu sistemdə yazılmır (sahib 2026-11-10);
``duplicate_account``    eyni ad + soyadlı BAŞQA tələbə hesabının bu fənn jurnalı var — dublikat hesab
                         birləşdirməsi həll edir (burada yazılmır);
``no_record``            tələbənin aktiv akademik qeydi (qrupu) yoxdur;
``roster_gap``           tələbənin ÖZ qrupunun bu fəndən jurnalı var, tələbə siyahıda deyil → öz qrupuna yazılır;
``family_journal``       jurnal qrup AİLƏSİNDƏDİR (alt qrup / ana qrup) və TƏKDİR → «alt qrupdan əlavə» yolu;
``family_ambiguous``     ailədə bir neçə jurnal (məs. iki alt qrup) — hansında oxuduğu sübutsuzdur, yazılmır;
``other_group_journal``  tələbənin qrupu imtahan qruplarının ailəsində deyil, imtahan qrupunun bu fəndən TƏK
                         jurnalı var — sahibin qaydası: «başqa qrupdadırsa o fəndə alt qrupdadır» → əlavə;
``other_group_ambiguous`` imtahan qruplarında bir neçə jurnal — yazılmır;
``variant_subject``      tələbə adı oxşar başqa fənn kartının jurnalındadır (``merge_subjects``);
``no_journal``           heç bir iz yoxdur.

Bu modul YAZMIR. Yerləşdirmə mövcud rəsmi yoldur — :mod:`apps.registrar.exam_taker_placement_2026_11_11`
(sahib 2026-11-11: «jurnalda yoxdursa alt qrup tələbəsidir — sənədsiz əlavə et»; paket + geri qaytarma).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model

from apps.registrar import exam_journal_scope
from apps.registrar.models import AcademicStatus, Enrollment, StudentAcademicRecord

DROPPED = "dropped"
KOLLEC = "kollec"
DUPLICATE_ACCOUNT = "duplicate_account"
NO_RECORD = "no_record"
ROSTER_GAP = "roster_gap"
FAMILY_JOURNAL = "family_journal"
FAMILY_AMBIGUOUS = "family_ambiguous"
OTHER_GROUP_JOURNAL = "other_group_journal"
OTHER_GROUP_AMBIGUOUS = "other_group_ambiguous"
VARIANT_SUBJECT = "variant_subject"
NO_JOURNAL = "no_journal"
STUDENT_REASONS = (
    DROPPED,
    KOLLEC,
    DUPLICATE_ACCOUNT,
    NO_RECORD,
    ROSTER_GAP,
    FAMILY_JOURNAL,
    FAMILY_AMBIGUOUS,
    OTHER_GROUP_JOURNAL,
    OTHER_GROUP_AMBIGUOUS,
    VARIANT_SUBJECT,
    NO_JOURNAL,
)
#: Tək hədəfli (yerləşdirmə ilə düzələn) səbəblər — yerləşdirmə ``exam_taker_placement_2026_11_11``-dədir.
PLACEABLE = frozenset({ROSTER_GAP, FAMILY_JOURNAL, OTHER_GROUP_JOURNAL})


@dataclass(frozen=True)
class StudentGap:
    reason: str
    offering_id: object = None


class _Context:
    """Bir qaçış üçün keş (təşkilat + dövr): Kollec qrupları, əkiz fənlər, qrup ailəsi jurnalları."""

    def __init__(self, organization, period):
        self.organization = organization
        self.period = period
        self._kollec = None
        self._twins: dict = {}
        self._journals: dict = {}

    def kollec_groups(self) -> set:
        if self._kollec is None:
            from apps.registrar.college_journals_hide_2026_11_10 import college_group_ids

            self._kollec = {str(pk) for pk in college_group_ids(self.organization)}
        return self._kollec

    def subject_ids(self, subject_id) -> set:
        if subject_id not in self._twins:
            twins = exam_journal_scope.twin_subject_ids(self.organization, subject_id, self.period)
            self._twins[subject_id] = {subject_id, *twins}
        return self._twins[subject_id]

    def family_offerings(self, subject_id, group_ids) -> dict:
        """``{qrup: [(açılış, qrup)]}`` — qrup ailəsindəki aktiv jurnallar (exact, yoxdursa əkiz)."""
        key = (subject_id, tuple(sorted(str(g) for g in group_ids)))
        if key not in self._journals:
            _units, _own, linked = exam_journal_scope.unit_families(self.organization, group_ids)
            found = exam_journal_scope.journal_offerings_by_unit(self.organization, self.period, subject_id, linked)
            self._journals[key] = {unit: row["exact"] or row["twin"] for unit, row in found.items()}
        return self._journals[key]


def context(organization, period) -> _Context:
    return _Context(organization, period)


def _record(organization, student_id):
    return (
        StudentAcademicRecord.objects.filter(
            organization=organization, student_id=student_id, is_active=True, status=AcademicStatus.ENROLLED
        )
        .exclude(group__isnull=True)
        .order_by("-created_at")
        .only("id", "group_id", "student_id")
        .first()
    )


def _has_duplicate_account(ctx, student_id, subject_ids) -> bool:
    user = get_user_model().objects.filter(pk=student_id).only("first_name", "last_name").first()
    first, last = (getattr(user, "first_name", "") or "").strip(), (getattr(user, "last_name", "") or "").strip()
    if not first or not last:
        return False
    return (
        Enrollment.objects.filter(
            organization=ctx.organization,
            offering__period=ctx.period,
            offering__subject_id__in=subject_ids,
            status=Enrollment.Status.ENROLLED,
            student__first_name__iexact=first,
            student__last_name__iexact=last,
        )
        .exclude(student_id=student_id)
        .exists()
    )


def _single(rows) -> tuple:
    ids = {pk for pk, _gid in rows}
    return (next(iter(ids)), 1) if len(ids) == 1 else (None, len(ids))


def classify_student(ctx, *, student_id, subject_id, exam_group_ids=()) -> StudentGap:
    """Körpünün ``no_enrollment`` cütü → :class:`StudentGap` (səbəb + yerləşdirmə hədəfi)."""
    subject_ids = ctx.subject_ids(subject_id)
    rows = Enrollment.objects.filter(
        organization=ctx.organization,
        student_id=student_id,
        offering__period=ctx.period,
        offering__subject_id__in=subject_ids,
    )
    if rows.filter(status=Enrollment.Status.ENROLLED).exists():
        return StudentGap(NO_JOURNAL)  # körpü yenə də tapmadı (keçmiş dövr / əkiz qaydası) — insan baxışı
    record = _record(ctx.organization, student_id)
    group_id = str(record.group_id) if record is not None else None
    if group_id and group_id in ctx.kollec_groups():
        return StudentGap(KOLLEC)
    if rows.exists():
        return StudentGap(DROPPED)
    if _has_duplicate_account(ctx, student_id, subject_ids):
        return StudentGap(DUPLICATE_ACCOUNT)
    if record is None:
        return StudentGap(NO_RECORD)
    family = ctx.family_offerings(subject_id, [record.group_id]).get(record.group_id) or []
    own = [row for row in family if str(row[1]) == group_id]
    if own:
        return StudentGap(ROSTER_GAP, own[0][0])
    if family:
        target, count = _single(family)
        return StudentGap(FAMILY_JOURNAL, target) if count == 1 else StudentGap(FAMILY_AMBIGUOUS)
    from apps.registrar.exam_journal_gaps import _variant_codes

    if _variant_codes(ctx.organization, ctx.period, subject_id, [student_id]):
        return StudentGap(VARIANT_SUBJECT)  # öz qrupunda fənn ADI OXŞAR başqa kartdadır — yerləşdirmədən əvvəl
    exam_groups = [gid for gid in exam_group_ids or () if gid]
    if exam_groups:
        by_unit = ctx.family_offerings(subject_id, exam_groups)
        target, count = _single([row for rows_ in by_unit.values() for row in rows_])
        if count == 1:
            return StudentGap(OTHER_GROUP_JOURNAL, target)
        if count > 1:
            return StudentGap(OTHER_GROUP_AMBIGUOUS)
    return StudentGap(NO_JOURNAL)


def _unit_names(ids) -> list:
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return sorted(OrgUnit.objects.filter(pk__in=list(ids)).values_list("name", flat=True))


def describe(ctx, gap: StudentGap, *, student_id, subject_id, exam_group_ids=()) -> tuple:
    """Hesabat üçün ŞƏXSSİZ izah → ``(fənn kodu, tələbənin qrupu, ipucu)`` (qrup adı + kodlar, ad yoxdur)."""
    from apps.registrar.models import Subject

    code = Subject.objects.filter(pk=subject_id).values_list("code", flat=True).first() or "-"
    record = _record(ctx.organization, student_id)
    group = _unit_names([record.group_id])[0] if record is not None and record.group_id else "-"
    hint = "-"
    if gap.reason == DROPPED:
        row = (
            Enrollment.objects.filter(
                organization=ctx.organization,
                student_id=student_id,
                offering__period=ctx.period,
                offering__subject_id__in=ctx.subject_ids(subject_id),
            )
            .exclude(status=Enrollment.Status.ENROLLED)
            .select_related("offering__group")
            .order_by("-updated_at")
            .first()
        )
        if row is not None:
            journal = getattr(row.offering.group, "name", "-")
            hint = f"{row.status}{'+superseded' if row.superseded_by_id else ''} journal={journal}"
    elif gap.reason in (OTHER_GROUP_JOURNAL, OTHER_GROUP_AMBIGUOUS, NO_JOURNAL):
        in_exam = record is not None and str(record.group_id) in {str(g) for g in exam_group_ids or ()}
        by_unit = ctx.family_offerings(subject_id, [g for g in exam_group_ids or () if g]) if exam_group_ids else {}
        journal_groups = {gid for rows in by_unit.values() for _pk, gid in rows}
        names = _unit_names(journal_groups)
        hint = f"own_group_in_exam={int(in_exam)} journals={len(journal_groups)} [{', '.join(names[:4])}]"
    elif gap.reason == VARIANT_SUBJECT:
        from apps.registrar.exam_journal_gaps import _variant_codes

        hint = ",".join(
            sorted(_variant_codes(ctx.organization, ctx.period, subject_id, [student_id]).get(student_id, ()))
        )
    return code, group, hint


RESTORE_NOTE = (
    "Sahib 2026-11-16: tələbənin bu fəndən midterm nəticəsi var — deməli fənni oxuyur; jurnala qaytarıldı "
    "(nəticə jurnalda görünsün)."
)


def restore_dropped(ctx, *, student_id, subject_id, actor) -> tuple:
    """``dropped`` hal: fənnin cari jurnalındakı çıxarılmış sətri jurnal səhifəsinin «Bərpa et» yolu ilə qaytar.

    → ``(kod, Enrollment | None)``; kod: ``restored`` / ``restore_<səbəb>`` (``journal_roster_restore.RestoreError``).
    """
    from apps.registrar import journal_roster_restore as roster_restore

    rows = list(
        Enrollment.objects.filter(
            organization=ctx.organization,
            student_id=student_id,
            offering__period=ctx.period,
            offering__is_active=True,
            offering__subject_id__in=ctx.subject_ids(subject_id),
        )
        .exclude(status=Enrollment.Status.ENROLLED)
        .select_related("offering", "offering__period")
        .order_by("-updated_at")
    )
    if not rows:
        return "restore_no_row", None
    if len({row.offering_id for row in rows}) > 1:
        return "restore_ambiguous", None
    row = rows[0]
    try:
        roster_restore.restore(offering=row.offering, enrollment_id=row.pk, actor=actor, note=RESTORE_NOTE)
    except roster_restore.RestoreError as exc:
        code = "".join(ch if ch.isalnum() else "_" for ch in str(exc.code).lower())
        if code != "not_restorable":
            return f"restore_{code}", None
        return _reactivate_system_drop(ctx, row, actor=actor)
    row.refresh_from_db()
    return ("restored", row) if row.status == Enrollment.Status.ENROLLED else ("restore_not_enrolled", None)


def _reactivate_system_drop(ctx, row, *, actor) -> tuple:
    """«Sistem tərəfindən çıxarılıb» sətri (qərarsız ``dropped``): sahib 2026-11-16 — midterm nəticəsi var, fənni oxuyur.

    Yalnız: ``dropped`` (dondurma / ``suspended`` YOX), rəsmi köçürmə izi yoxdur (``superseded_by``), tələbənin aktiv
    qeydi var, jurnalın siyahısı açıqdır, həmin fəndən başqa aktiv jurnalı yoxdur. Tarixçəyə «bərpa» sətri yazılır."""
    from apps.registrar import guest_roster, journal_removal

    if row.status != Enrollment.Status.DROPPED or row.superseded_by_id:
        return "restore_kept_status", None
    if _record(ctx.organization, row.student_id) is None:
        return "restore_no_active_record", None
    if guest_roster.roster_block_reason(row.offering):
        return "restore_roster_closed", None
    elsewhere = Enrollment.objects.filter(
        organization=ctx.organization,
        student_id=row.student_id,
        offering__period=ctx.period,
        offering__subject_id=row.offering.subject_id,
        status=Enrollment.Status.ENROLLED,
    ).exclude(pk=row.pk)
    if elsewhere.exists():
        return "restore_active_elsewhere", None
    row.status = Enrollment.Status.ENROLLED
    row.save(update_fields=["status", "updated_at"])
    journal_removal.record_restore(
        enrollment=row, actor=actor, note=RESTORE_NOTE, action=journal_removal.HISTORY_ACTION_HYGIENE
    )
    return "restored_system_drop", row


#: Birgə imtahan verənlərin ən azı bu qədəri eyni jurnaldadırsa o jurnal seçilir (sahib 2026-11-16).
COTAKER_MIN = 2
COTAKER_SHARE = 0.6


def cotaker_offering(ctx, *, subject_id, candidate_offering_ids, cotaker_ids) -> tuple:
    """Bir neçə uyğun jurnal: tələbə ilə EYNİ imtahanı EYNİ vaxtda verənlərin jurnalı (sahib 2026-11-16:
    «verdiyi saatda hansı qrup imtahan veribsə o qrupdadır») → ``(açılış id | None, kod)``."""
    from collections import Counter

    candidates = {str(pk) for pk in candidate_offering_ids or ()}
    ids = [pk for pk in cotaker_ids or () if pk]
    if not candidates or not ids:
        return None, "cotaker_none"
    counts = Counter(
        str(offering_id)
        for offering_id in Enrollment.objects.filter(
            organization=ctx.organization,
            student_id__in=ids,
            offering_id__in=list(candidates),
            status=Enrollment.Status.ENROLLED,
        ).values_list("offering_id", flat=True)
    )
    if not counts:
        return None, "cotaker_none"
    (top, top_n), *rest = counts.most_common()
    if top_n < COTAKER_MIN or top_n < COTAKER_SHARE * sum(counts.values()) or (rest and rest[0][1] == top_n):
        return None, "cotaker_split"
    return top, "cotaker_match"


def candidate_offering_ids(ctx, *, student_id, subject_id, exam_group_ids=()) -> set:
    """Tələbənin qrup ailəsindəki + imtahan qruplarının bu fəndən aktiv jurnalları (seçim üçün namizədlər)."""
    record = _record(ctx.organization, student_id)
    found = set()
    groups = [g for g in exam_group_ids or () if g]
    if record is not None and record.group_id:
        groups.append(record.group_id)
    if groups:
        for rows in ctx.family_offerings(subject_id, groups).values():
            found |= {str(pk) for pk, _gid in rows}
    return found


__all__ = [
    "PLACEABLE",
    "STUDENT_REASONS",
    "StudentGap",
    "classify_student",
    "candidate_offering_ids",
    "context",
    "cotaker_offering",
    "describe",
    "restore_dropped",
]
