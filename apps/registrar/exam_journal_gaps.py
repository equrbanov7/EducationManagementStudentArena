"""İmtahan qrupunun «jurnalı yoxdur» boşluğunun SƏBƏBİ + yalnız-doldurma düzəlişi (sahib 2026-10-27).

Sahib: «Bu imtahan təyin etdiklərim var … bəzilərini deyir ki jurnalı yoxdur — o qrupların o hissəsini həll et».
Sehrbaz (``exams.services.exam_unit_coverage``) qrupun HƏR aktiv tələbəsinin imtahanın fənni üzrə cari dövr
jurnalında olub-olmadığını yoxlayır (:func:`~apps.registrar.exam_journal_link.group_subject_coverage`). Bu modul
əhatəsiz tələbəni SƏBƏBƏ görə ayırır (hamısı BİR qrup üçün sabit sayda sorğu, YALNIZ OXU):

``roster_gap``           qrupun (ailənin) bu fəndən jurnalı VAR, tələbə isə onun siyahısında deyil — jurnal
                         qrupun tələbələri ilə dolduqdan SONRA qrupa gəlib (köçürmə, alt qrupa yerləşdirmə, legacy
                         delta). DÜZƏLİŞ: :func:`fill_rosters` → ``services.enroll_group_students`` (açılışın
                         yaradılmasındakı EYNİ yol: tarixçə, başqa jurnalda aktiv qeydiyyat, üzvlük qapısı);
``dropped``              tələbənin bu fənn jurnalında ``dropped`` / ``suspended`` sətri var — siyahıdan qəsdən
                         çıxarılıb (səviyyə jurnalı, köçürmə, dondurma); doldurulmur;
``subgroup_unplaced``    jurnal yalnız alt qrup(lar)dadır, tələbə isə ANA qrupda qalıb — yerləşdirmə
                         ``place_parent_group_students`` ilə (jurnal sübutu tələb edir; burada yazılmır);
``other_journal``        jurnal ailənin başqa qrupundadır və tələbə onun üzvü deyil (məs. ana qrupun öz tələbəsi
                         var) — əl ilə qərar;
``task_row``             fənnin bu qrup üçün tədris tapşırığı sətri var, açılışı yoxdur — ``resync_task_offerings``;
``variant_subject``      tələbə ADI OXŞAR başqa fənn kartının jurnalındadır («Azərbaycan tarixi» ↔ «Azərbaycanın
                         tarixi») — ya imtahanı həmin kartla yaradın, ya ``merge_subjects`` / ``merge_twin_offerings``;
``no_journal``           qrupun bu fəndən heç bir izi yoxdur (yük yoxdur) — tədris şöbəsinin qərarı.

Normallaşdırılmış adı EYNİ olan kart (əkiz) burada boşluq DEYİL — onu bağlantı özü həll edir
(:mod:`apps.registrar.exam_journal_scope`).
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass, field

from django.apps import apps as django_apps

from apps.registrar import exam_journal_link, exam_journal_scope
from apps.registrar.models import AcademicStatus, CourseOffering, Enrollment, StudentAcademicRecord, Subject
from apps.registrar.subject_duplicates import normalized_subject_key

ROSTER_GAP = "roster_gap"
DROPPED = "dropped"
SUBGROUP_UNPLACED = "subgroup_unplaced"
OTHER_JOURNAL = "other_journal"
TASK_ROW = "task_row"
VARIANT_SUBJECT = "variant_subject"
NO_JOURNAL = "no_journal"
REASONS = (ROSTER_GAP, DROPPED, SUBGROUP_UNPLACED, OTHER_JOURNAL, TASK_ROW, VARIANT_SUBJECT, NO_JOURNAL)
#: Bu modulun özünün düzəltdiyi səbəb (qalanları — mövcud əmrlər / insan qərarı).
FIXABLE = frozenset({ROSTER_GAP})
#: Oxşar ad həddi (normallaşdırılmış açarda) — rəqəmlər fərqlidirsə («dil-1» ↔ «dil-2») oxşar sayılmır.
VARIANT_RATIO = 0.9

_DIGITS = re.compile(r"\d+")
FILL_REASON = "İmtahan qrupunun jurnal boşluğu: qrupa sonradan gəlmiş tələbə fənnin jurnalına (sahib 2026-10-27)"


@dataclass
class GroupGap:
    """Bir imtahan qrupunun boşluğu: tələbə sayları səbəb üzrə + düzəldiləcək açılışlar."""

    unit_id: object
    students: int = 0
    uncovered: int = 0
    has_journal: bool = False
    reasons: Counter = field(default_factory=Counter)
    fill_offering_ids: set = field(default_factory=set)
    variant_codes: set = field(default_factory=set)

    @property
    def reason(self) -> str:
        """Qrupun əsas səbəbi (ən çox tələbə; bərabərlikdə ``REASONS`` sırası) və ya ``""``."""
        if not self.reasons:
            return ""
        return max(REASONS, key=lambda key: (self.reasons.get(key, 0), -REASONS.index(key)))


def is_variant_name(name: str, other: str) -> bool:
    """Ad oxşardır, amma EYNİ deyil (eyni olan — əkiz, bağlantı həll edir) və rəqəmləri fərqlənmir."""
    left, right = normalized_subject_key(name), normalized_subject_key(other)
    if not left or not right or left == right or _DIGITS.findall(left) != _DIGITS.findall(right):
        return False
    return difflib.SequenceMatcher(None, left, right).ratio() >= VARIANT_RATIO


def _records(organization, group_ids) -> dict:
    out: dict = {}
    for student_id, group_id in StudentAcademicRecord.objects.filter(
        organization=organization, group_id__in=group_ids, is_active=True, status=AcademicStatus.ENROLLED
    ).values_list("student_id", "group_id"):
        out[student_id] = group_id
    return out


def _task_row_groups(organization, period, subject_id, group_ids) -> set:
    """Fənnin bu dövr üçün tapşırıq sətri olan qrupları (iş yükü modulu — tətbiq registrində)."""
    try:
        Row = django_apps.get_model("workload", "TeachingTaskRow")
    except LookupError:
        return set()
    return set(
        Row.objects.filter(organization=organization, period=period, subject_id=subject_id, groups__in=group_ids)
        .exclude(task__status="cancelled")
        .values_list("groups", flat=True)
    )


def _variant_codes(organization, period, subject_id, student_ids) -> dict:
    """``{tələbə: {fənn kodu}}`` — tələbənin cari dövrdə ADI OXŞAR başqa fənn kartının jurnalında olduğu kodlar."""
    if not student_ids:
        return {}
    name = Subject.objects.filter(pk=subject_id).values_list("name", flat=True).first() or ""
    out: dict = {}
    for student_id, code, other in Enrollment.objects.filter(
        organization=organization,
        student_id__in=student_ids,
        offering__period=period,
        status=Enrollment.Status.ENROLLED,
    ).values_list("student_id", "offering__subject__code", "offering__subject__name"):
        if is_variant_name(name, other):
            out.setdefault(student_id, set()).add(code)
    return out


def _journal_reason(unit_id, group_id, by_group, own, linked, populated):
    """Ailədə jurnal VAR, tələbə siyahıda deyil → ``(səbəb, doldurulacaq açılış | None)``."""
    if group_id in by_group:
        return ROSTER_GAP, by_group[group_id]  # öz qrupunun jurnalı — sonradan gəlib
    for gid, offering_id in by_group.items():
        if gid in populated:
            continue
        # Öz tələbəsi olmayan BİRLƏŞİK qrupun jurnalı: alt qrup tələbəsi «alt qrupdan əlavə» düşür
        # (``enroll_group_students`` → ``_rollup_combined_groups``).
        if (gid == unit_id and group_id != unit_id) or (gid in linked - own and group_id == unit_id):
            return ROSTER_GAP, offering_id
    if group_id == unit_id and any(gid in own - {unit_id} for gid in by_group):
        return SUBGROUP_UNPLACED, None  # jurnal alt qruplardadır, tələbə ana qrupda qalıb
    return OTHER_JOURNAL, None


def classify(organization, subject_id, group_ids, *, period=None) -> dict:
    """Reyestr qrupları → ``{qrup_pk: GroupGap}`` (əhatəli qrup da daxil — ``uncovered == 0``)."""
    period = period or exam_journal_link.current_period(organization)
    if organization is None or not subject_id or period is None:
        return {}
    units, own, linked = exam_journal_scope.unit_families(organization, group_ids)
    if not units:
        return {}
    coverage = exam_journal_link.group_subject_coverage(organization, subject_id, [u.pk for u in units], period=period)
    journals = exam_journal_scope.journal_offerings_by_unit(organization, period, subject_id, linked)
    family_ids = set().union(*linked.values())
    record_group = _records(organization, family_ids)
    populated = set(record_group.values())
    uncovered_all = {sid for row in coverage.values() for sid in row["uncovered"]}
    variants = _variant_codes(organization, period, subject_id, uncovered_all)
    task_groups = _task_row_groups(organization, period, subject_id, family_ids)
    journal_ids = {pk for row in journals.values() for kind in ("exact", "twin") for pk, _gid in row[kind]}
    dropped = set(
        Enrollment.objects.filter(
            organization=organization, student_id__in=uncovered_all, offering_id__in=journal_ids
        ).values_list("student_id", flat=True)
    )
    out = {}
    for unit in units:
        row = coverage.get(unit.pk) or {"students": [], "uncovered": [], "has_journal": False}
        gap = GroupGap(
            unit_id=unit.pk,
            students=len(row["students"]),
            uncovered=len(row["uncovered"]),
            has_journal=row["has_journal"],
        )
        found = journals.get(unit.pk) or {"exact": [], "twin": []}
        offerings = found["exact"] or found["twin"]
        by_group = {}
        for pk, gid in offerings:
            by_group.setdefault(gid, pk)
        for student_id in row["uncovered"]:
            group_id = record_group.get(student_id)
            if student_id in dropped:
                gap.reasons[DROPPED] += 1
            elif offerings:
                reason, target = _journal_reason(unit.pk, group_id, by_group, own[unit.pk], linked[unit.pk], populated)
                gap.reasons[reason] += 1
                if target is not None:
                    gap.fill_offering_ids.add(target)
            elif task_groups & linked[unit.pk]:
                gap.reasons[TASK_ROW] += 1
            elif student_id in variants:
                gap.reasons[VARIANT_SUBJECT] += 1
                gap.variant_codes |= variants[student_id]
            else:
                gap.reasons[NO_JOURNAL] += 1
        out[unit.pk] = gap
    return out


def fill_rosters(offering_ids, *, by_user, reason: str = FILL_REASON) -> Counter:
    """``roster_gap`` açılışlarına qrupun çatışmayan tələbələrini yaz (YALNIZ ƏLAVƏ; idempotent) → saylar.

    Bağlı jurnal və siyahıya bağlı dövr (``guest_roster.roster_block_reason``) toxunulmur — sayılır."""
    from apps.registrar import guest_roster, services

    counts: Counter = Counter()
    offerings = list(
        CourseOffering.objects.filter(pk__in=list(offering_ids or ()), is_active=True)
        .select_related("period", "organization")
        .order_by("pk")
    )
    open_offerings = []
    for offering in offerings:
        if guest_roster.roster_block_reason(offering):
            counts["roster_blocked"] += 1
        else:
            open_offerings.append(offering)
    if open_offerings:
        report = services.enroll_group_students(offerings=open_offerings, by_user=by_user, reason=reason)
        counts.update({f"enroll_{key}": int(value) for key, value in report.items() if value})
    counts["offerings"] += len(open_offerings)
    return counts


__all__ = [
    "DROPPED",
    "FIXABLE",
    "NO_JOURNAL",
    "OTHER_JOURNAL",
    "REASONS",
    "ROSTER_GAP",
    "SUBGROUP_UNPLACED",
    "TASK_ROW",
    "VARIANT_SUBJECT",
    "GroupGap",
    "classify",
    "fill_rosters",
    "is_variant_name",
]
