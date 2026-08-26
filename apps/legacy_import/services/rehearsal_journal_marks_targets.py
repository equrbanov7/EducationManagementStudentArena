"""Target side of ``journal_marks`` (J4): LessonMark yazısı və jurnal möhürü.

``gradebook.save_marks`` semantikası qəsdən BURADA güzgülənir, İMPORT EDİLMİR.
Səbəblər (hamısı raportda təkrarlanır):

1. **Modul sərhədi** — ``apps.registrar.gradebook`` importu qrafa yeni
   ``legacy_import → registrar`` tili açardı; J1 (``ensure_assessment_scheme``)
   və J3 (``create_lesson``) eyni qərarı verib.
2. **EXCUSED ifadə oluna bilmir** — ``save_marks`` ``present``/``absent``
   xaricindəki hər statusu SƏSSİZCƏ ``present``-ə çevirir, J-V3 isə üzürlü
   qaibi (``excusable=1`` / ``allowed_qb``) tələb edir.
3. **Bal itkisi** — ``save_marks`` balı yalnız ``kind in (seminar, lab)`` dərsdə
   saxlayır; J3 hər dərsi ``lecture`` yaradır (spec J3 defoltu), yəni servis
   yolu 250,588 rəqəmli balın HAMISINI atardı — J-V2 "data təhrif edilmir"
   qaydasının birbaşa pozulması.
4. **Yan təsirlər** — servis hər çağırışda audit sətri yazır, bildiriş
   növbələyir və qayıb saatlarını sətir-sətir yenidən hesablayır; 4.6 milyon
   xanada bu import deyil, hadisə fırtınasıdır.

Qorunan invariantlar (servis qatı ilə eyni):
* xana açarı ``(lesson, enrollment)`` unikaldır → həmişə ``get_or_create``,
  heç vaxt çılpaq ``create``;
* mövcud xana ÜSTÜNDƏN YAZILMIR — 2 saat trigger-i yalnız ``UPDATE``-i tutur,
  ona görə import xalis ``INSERT`` axını qalır (J-V10) və fərqli dəyər daşıyan
  mövcud xana ``legacy_journal_mark_target_conflict`` ilə hesabata düşür;
* ``entered_by=None`` — import heç kimin adından yazmır;
* ``Enrollment.absence_hours`` faza sonunda TOPLU şəkildə yenidən hesablanır
  (``gradebook.recompute_absence_hours`` güzgüsü, sətir-sətir sorğu olmadan).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Sum

from apps.legacy_import.models import LegacyMigrationIssue

from .field_contracts import JOURNAL_POINT_FIELDS
from .rehearsal_authorizer import COURSE_OFFERING_MODEL_LABEL
from .rehearsal_journal_points_source import POINT_SOURCE_TABLE
from .rehearsal_journal_seal import JournalSealer

MARKS_ENTITY_TYPE = "journal_marks"
PRESENT_STATUS = "present"
ABSENT_STATUS = "absent"
EXCUSED_STATUS = "excused"
_ABSENCE_CHUNK = 2_000

_SEVERITY = LegacyMigrationIssue.Severity

# E-13: heç nə ERROR deyil — ilk jurnal rehearsal-ı tam histoqram verməlidir.
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                # J-V2: rəqəm 0-10 diapazonundan kənardır (şkala çevrilmir).
                "legacy_journal_mark_score_out_of_range",
                # J-V13: təqvim xanasında tanınmayan kod (nə ie, nə qb, nə rəqəm).
                "legacy_journal_mark_point_unknown",
                # Tələbə J2-də, dərs isə J3-də həll olunmayıb.
                "legacy_journal_mark_enrollment_unresolved",
                "legacy_journal_mark_lesson_unresolved",
                # Xana artıq FƏRQLİ dəyərlə mövcuddur — üstündən yazılmır.
                "legacy_journal_mark_target_conflict",
            ),
            _SEVERITY.WARNING,
        ),
        **dict.fromkeys(
            (
                # Jurnal J1-də MIGRATED deyil (V6 süzgəci və ya karantin).
                "legacy_journal_mark_orphan",
                # J-V4 dedup uduzanı.
                "legacy_journal_mark_duplicate",
                # J-V1(F): boş '' xana = heç nə yazılmayıb → mark yaradılmır.
                "legacy_journal_mark_empty",
                # J-V3: üzürlü qaib tətbiq olundu.
                "legacy_journal_mark_excused",
                # J-V5: ``lab=1`` xanası var — J3 dərsi ``lecture`` yaradıb,
                # ona görə bu yalnız qeyddir (davranışa təsiri yoxdur).
                "legacy_journal_mark_lab_cell",
                # J-V7: arxiv sətri overlap pəncərəsindədir → əsas cədvəl udur.
                "legacy_journal_archive_overlap",
            ),
            _SEVERITY.INFO,
        ),
    }
)

MARK_SEALER = JournalSealer(
    entity_type=MARKS_ENTITY_TYPE,
    source_table=POINT_SOURCE_TABLE,
    derivation_prefix=b"legacy-rehearsal-journal-marks-derivation-v1\x00",
    contract_fingerprint=JOURNAL_POINT_FIELDS.fingerprint,
    issue_severity=ISSUE_SEVERITY,
)


@dataclass(frozen=True)
class MarkWrite:
    """Bir xananın yazısı üçün lazım olan hər şey — həll bitib."""

    lesson_pk: str
    enrollment_pk: str
    status: str
    score: Decimal | None
    allow_existing: bool = True  # J-V7 arxiv yolunda False: əsas cədvəl udur


def write_lesson_mark(context, *, request: MarkWrite) -> str:
    """Xananı yaz; nəticə ``"written"`` / ``"conflict"`` / ``"superseded"``.

    ``superseded`` yalnız arxiv yoludur: xana artıq əsas cədvəldən gəlib.
    """

    model = django_apps.get_model("registrar", "LessonMark")
    with transaction.atomic():
        mark, created = model.objects.get_or_create(
            organization=context.organization,
            lesson_id=request.lesson_pk,
            enrollment_id=request.enrollment_pk,
            defaults={"status": request.status, "score": request.score, "entered_by": None},
        )
        if created:
            return "written"
        if not request.allow_existing:
            return "superseded"
        same = mark.status == request.status and _same_score(mark.score, request.score)
        # Mövcud xana ÜSTÜNDƏN YAZILMIR: eyni dəyər idempotent təkrardır,
        # fərqli dəyər isə hesabata düşən toqquşmadır (2h trigger qorunur).
        return "written" if same else "conflict"


def _same_score(stored, incoming) -> bool:
    if stored is None or incoming is None:
        return stored is None and incoming is None
    return Decimal(stored) == Decimal(incoming)


def recompute_absence_hours(context, enrollment_pks) -> int:
    """``gradebook.recompute_absence_hours`` güzgüsü — toplu, sətir-sətir yox.

    Qayıb saatı YALNIZ ``absent`` sətirlərdən yığılır: ``excused`` (J-V3)
    qayıb limitinə daxil deyil, elə modelin öz qaydasıdır.
    """

    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    mark_model = django_apps.get_model("registrar", "LessonMark")
    keys = sorted(enrollment_pks)
    updated = 0
    for start in range(0, len(keys), _ABSENCE_CHUNK):
        chunk = keys[start : start + _ABSENCE_CHUNK]
        hours = {
            str(row["enrollment_id"]): int(row["total"] or 0)
            for row in mark_model.objects.filter(enrollment_id__in=chunk, status=ABSENT_STATUS)
            .values("enrollment_id")
            .annotate(total=Sum("lesson__hours"))
        }
        pending = []
        for enrollment in enrollment_model.objects.filter(pk__in=chunk).only("id", "absence_hours"):
            target = hours.get(str(enrollment.pk), 0)
            if enrollment.absence_hours != target:
                enrollment.absence_hours = target
                pending.append(enrollment)
        if pending:
            enrollment_model.objects.bulk_update(pending, ["absence_hours"])
            updated += len(pending)
    return updated


def seal_journal(
    context, *, uniqid: str, state: str, offering_pk: str, tally, evidence=(), rule_codes=(), issue_counts=None
):
    """Jurnalın YEKUN möhürü + issue-ları (spec B.6: sətir-başına map YOX).

    ``evidence`` J-V3 sənəd qeydlərinin sıralı-sabit digest hissəsidir (bax
    ``JournalCellLedger.evidence_part``) — mətn ledger-ə DÜŞMÜR, yalnız qərarın
    kimliyinə qatlanır.
    """

    from .rehearsal_journal_seal import tally_parts

    digest = MARK_SEALER.derivation_hash(seal_key=uniqid, outcome_token=state, parts=(*tally_parts(tally), *evidence))
    label = COURSE_OFFERING_MODEL_LABEL if state == "migrated" else ""
    entity_map = MARK_SEALER.seal(
        context,
        seal_key=uniqid,
        digest=digest,
        state=state,
        label=label,
        target_pk=offering_pk if label else "",
    )
    MARK_SEALER.write_issues(
        context,
        seal_key=uniqid,
        digest=digest,
        entity_map=entity_map,
        rule_codes=rule_codes,
        issue_counts=issue_counts,
    )
    return state, digest, label
