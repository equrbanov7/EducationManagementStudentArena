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
_MARK_BATCH = 2_000

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
    """Bir xananın yazısı üçün lazım olan hər şey — həll bitib.

    ``legacy_pk``…``source_lesson_ref`` YALNIZ provenans daşıyır: toqquşma halında uduzan
    dəyəri sübut qatına yazan J12 (``journal_lesson_recovery``) onları
    ``on_conflict`` hook-u ilə oxuyur.  J4 onları doldurmur (defolt boşdur) və
    heç bir möhür digest-inə girmirlər — yazı davranışı dəyişməz qalır.
    """

    lesson_pk: str
    enrollment_pk: str
    status: str
    score: Decimal | None
    allow_existing: bool = True  # J-V7 arxiv yolunda False: əsas cədvəl udur
    legacy_pk: int = 0
    point_text: str = ""
    row_hash: str = ""
    student_ref: str = ""
    month_id: str = ""
    source_lesson_ref: str = ""


def classify_mark_write(existing, request: MarkWrite) -> str:
    """``get_or_create`` nərdivanının saf forması: xana varsa nə olur?

    ``existing`` ``None``-dursa xana yenidir → ``"written"``.  Varsa: arxiv
    yolunda (``allow_existing=False``) əsas cədvəl udur → ``"superseded"``;
    əks halda eyni dəyər idempotent təkrardır (``"written"``), fərqli dəyər isə
    hesabata düşən ``"conflict"``-dir.  Mövcud xana HEÇ VAXT üstündən yazılmır —
    2 saat trigger-i yalnız ``UPDATE``-i tutur, import xalis INSERT axını qalır.
    """

    if existing is None:
        return "written"
    if not request.allow_existing:
        return "superseded"
    status, score = existing
    return "written" if status == request.status and _same_score(score, request.score) else "conflict"


class LessonMarkWriter:
    """Xanaları dəstə ilə yazan bufer — sətir-başına ``get_or_create`` əvəzinə.

    Niyə (Rehearsal #9): 4.4 milyon xananın hər biri üçün ayrıca
    ``transaction.atomic()`` + ``SELECT`` + ``INSERT`` günlərlə vaxt deməkdir.
    Bufer dəstə başına BİR axtarış sorğusu və BİR ``bulk_create`` işlədir.

    Təsnifat SIRASI dəyişmir: bir dəstə içindəki xanalar mənbə axını sırasında
    təsnif olunur, əvvəlki dəstələrin yazdıqları isə flush-un öz axtarış
    sorğusunda görünür — yəni "əvvəl gələn udur" qaydası (J-V4/J-V7) qorunur.
    Buna görə də ``drive_cells``-in əsas cədvəl → arxiv sərhədində flush ŞƏRTdir.
    """

    __slots__ = ("_batch_rows", "_context", "_ledger", "_on_conflict", "_pending", "created_count")

    def __init__(self, context, ledger, *, batch_rows: int | None = None, on_conflict=None) -> None:
        self._context = context
        self._ledger = ledger
        # Defolt icra vaxtı oxunur ki, test dəstə sərhədini dəyişə bilsin.
        self._batch_rows = max(1, int(_MARK_BATCH if batch_rows is None else batch_rows))
        self._pending: list[tuple[str, bool, MarkWrite]] = []
        # OPSİONAL sübut hook-u: toqquşmada UDUZAN dəyəri kənarda saxlamaq üçün.
        # J4 onu vermir (davranış dəyişmir); J12 verir və uduzanı
        # ``LegacyGradeFact``-a yazır.  Yazı qərarına TƏSİRİ YOXDUR — qalib
        # sətir hər halda olduğu kimi qalır.
        self._on_conflict = on_conflict
        #: HƏQİQƏTƏN yaradılan sətir sayı — idempotent təkrarlar (mövcud xana,
        #: eyni dəyər) buraya DAXİL DEYİL, ona görə hesabat «neçə xana bərpa
        #: olundu» sualına düzgün cavab verir.
        self.created_count = 0

    def enqueue(self, *, uniqid: str, from_archive: bool, request: MarkWrite) -> None:
        self._pending.append((uniqid, from_archive, request))
        if len(self._pending) >= self._batch_rows:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        model = django_apps.get_model("registrar", "LessonMark")
        keys = {(request.lesson_pk, request.enrollment_pk) for _uniqid, _archive, request in batch}
        known = self._existing(model, keys)
        created = []
        with transaction.atomic():
            for uniqid, from_archive, request in batch:
                key = (request.lesson_pk, request.enrollment_pk)
                result = classify_mark_write(known.get(key), request)
                if result == "written" and key not in known:
                    known[key] = (request.status, request.score)
                    created.append(
                        model(
                            organization=self._context.organization,
                            lesson_id=request.lesson_pk,
                            enrollment_id=request.enrollment_pk,
                            status=request.status,
                            score=request.score,
                            # ``entered_by=None`` — import heç kimin adından yazmır.
                            entered_by=None,
                        )
                    )
                if result == "written":
                    self._ledger.count(uniqid, "archive_written" if from_archive else "written")
                    self._ledger.touched_targets.add(request.enrollment_pk)
                elif result == "superseded":
                    self._ledger.count(uniqid, "archive_overlap")
                else:
                    self._ledger.count(uniqid, "conflict")
                    if self._on_conflict is not None:
                        self._on_conflict(uniqid=uniqid, request=request, existing=known.get(key))
            if created:
                model.objects.bulk_create(created)
                self.created_count += len(created)

    def _existing(self, model, keys) -> dict[tuple[str, str], tuple[str, object]]:
        """Dəstənin açarları üçün mövcud xanalar — BİR sorğu, dəqiq süzgəc."""

        rows = model.objects.filter(
            organization=self._context.organization,
            lesson_id__in={lesson_pk for lesson_pk, _enrollment_pk in keys},
            enrollment_id__in={enrollment_pk for _lesson_pk, enrollment_pk in keys},
        ).values_list("lesson_id", "enrollment_id", "status", "score")
        found: dict[tuple[str, str], tuple[str, object]] = {}
        for lesson_id, enrollment_id, status, score in rows.iterator(chunk_size=5_000):
            key = (str(lesson_id), str(enrollment_id))
            if key in keys:
                found[key] = (status, score)
        return found


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


def journal_seal_entry(*, uniqid: str, state: str, offering_pk: str, tally, evidence=(), rule_codes=()):
    """Jurnalın YEKUN möhür qeydi (spec B.6: sətir-başına map YOX) — hələ yazılmır.

    ``evidence`` J-V3 sənəd qeydlərinin sıralı-sabit digest hissəsidir (bax
    ``JournalCellLedger.evidence_part``) — mətn ledger-ə DÜŞMÜR, yalnız qərarın
    kimliyinə qatlanır.  Yazı ``JournalSealer.seal_many`` ilə dəstə-dəstə gedir.
    """

    from .rehearsal_journal_seal import JournalSealEntry, tally_parts

    digest = MARK_SEALER.derivation_hash(seal_key=uniqid, outcome_token=state, parts=(*tally_parts(tally), *evidence))
    label = COURSE_OFFERING_MODEL_LABEL if state == "migrated" else ""
    entry = JournalSealEntry(
        seal_key=uniqid,
        digest=digest,
        state=state,
        label=label,
        target_pk=offering_pk if label else "",
        rule_codes=tuple(rule_codes),
    )
    return entry, (state, digest, label)
