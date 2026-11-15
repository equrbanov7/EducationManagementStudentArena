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
    exam_groups = [gid for gid in exam_group_ids or () if gid]
    if exam_groups:
        by_unit = ctx.family_offerings(subject_id, exam_groups)
        target, count = _single([row for rows_ in by_unit.values() for row in rows_])
        if count == 1:
            return StudentGap(OTHER_GROUP_JOURNAL, target)
        if count > 1:
            return StudentGap(OTHER_GROUP_AMBIGUOUS)
    from apps.registrar.exam_journal_gaps import _variant_codes

    if _variant_codes(ctx.organization, ctx.period, subject_id, [student_id]):
        return StudentGap(VARIANT_SUBJECT)
    return StudentGap(NO_JOURNAL)


__all__ = [
    "PLACEABLE",
    "STUDENT_REASONS",
    "StudentGap",
    "classify_student",
    "context",
]
