"""Sillabus köçürməsinin HƏDƏF qatı: bölmə xəritəsi + dosye yazıcısı.

``rehearsal_syllabus_source`` mənbəni oxuyur, ``rehearsal_syllabus_documents``
onu sənəd və versiya nərdivanına düzür — bu modul isə nərdivanı
``apps.syllabus`` modelinə yazır və ledger möhürünü qoyur.

Yazı YOLU: ``apps.syllabus.public.import_migrated_version``
=========================================================
Yeni yazı funksiyası YAZILMIR.  Sillabus modulunun öz idxal girişi artıq var və
DB invariantlarını o bilir: ``approval_source="migration"`` (saxta insan
təsdiqi yoxdur, ``approved_by`` NULL qalır), ``change_kind="imported"``,
``locked_at`` = köçürmə anı, 10 bölmə sətri, ``current_version`` /
``approved_version`` göstəricilərinin STATUSDAN həll olunması (arxiv pilləsi
dosyeni «cari» edə bilməz) və tamamlanma faizinin yenidən hesablanması.
Çağırış ``apps.accounts.public.activate_staged_account`` presedenti ilə eyni
formadadır: funksiya-daxili idxal, yəni modul-sərhəd qrafına yeni İMPORT tili
qoyulmur və fasadın öz qapıları yan keçilmir.

Nə YAZILMIR
-----------
Müəllimi həll olunmayan başlıq (canlı: 956) HEÇ YAZILMIR — sahibin 2026-08-31
qərarı (spec §9).  Ledger möhürü qalır (``SKIPPED`` +
``legacy_syllabus_instructor_unresolved``) ki, uzlaşdırma qalığı izahsız
olmasın; ona görə bu modulun yazıcısı ``author_pk``-siz sorğu GÖZLƏMİR və
görsə fail-closed dayanır.

Nə vaxt hansı status
--------------------
Sahibin tələbi «hamısı təsdiqlənmiş gəlsin»dir, mənbədə isə 714 başlıq AÇIQ
şəkildə söndürülüb (``active=0``).  ``rehearsal_syllabus_documents`` bu
ziddiyyəti uydurmadan həll edir: dosyedə ƏN SON aktiv pillə ``APPROVED``,
qalan hər pillə ``ARCHIVED`` olur.  Arxiv pilləsi də ``approval_source``
damğasını daşıyır və ``approved_at``-i doludur — bu, «bu versiya bir vaxt
qüvvədə idi, sonra yenisi ilə əvəzləndi» deməkdir, yəni modelin öz
arxivləmə semantikası (``workflow.archive``) ilə eynidir.

⚠️ Bölmə uyğunlaşdırması: 11 peyk → 10 ``SectionKey``
=====================================================
Dizaynın bölmə kataloqu (``apps.syllabus.constants.SectionKey``) 10 açardır və
onların ikisi (``prev``/``send``) MƏZMUN daşımır.  Spesifikasiyanın §5
cədvəlindəki «qarşılama / giriş» və «imtahan sualları» bölmələri hədəf
kataloqda YOXDUR.  Ona görə:

* ``sillabus_qarsilama_mesaji`` → ``info.welcome``,
* ``sillabus_imtahan_suallari`` → ``assess.exam_questions``,
* ``sillabus_elmi_maraq`` + ``sillabus_certificates`` → ``info.research_interests``
  / ``info.certificates``.

Bu üç ailə ``SyllabusSection.data`` JSON-unda SAXLANILIR, amma bu günün
redaktorunda onları göstərən input YOXDUR — ona görə hər biri öz issue kodu ilə
(``legacy_syllabus_*_unsurfaced``) ledger-də sayılır: data itmir, «görünmür»
faktı isə rəqəmlə görünür.  DÖRDÜNCÜ ailə ``sillabus_yoxlama_formasi`` →
``assess.note``-dur: qiymətləndirmə qaydasının öz mətni (canlı: 8,261 sətir,
4,842-si çoxsətirli) yazılır, redaktorun qiymətləndirmə panelində isə yalnız
bal sürüşdürücüsü var — ``ASSESSMENT_NOTE_UNSURFACED`` məhz bunu sayır.

⚠️ Bu mətn TƏLƏBƏYƏ ÇATIR: ``apps.syllabus.document`` qiymətləndirmə blokunda
``note`` və ``exam_questions`` sahələrini oxuyur.  Əvvəllər blok tətbiqin
DEFOLT rəqəmlərindən qurulurdu və köçürülmüş hər sillabusda mənbədə OLMAYAN
«10 + 10 + 0 + 30 + 50 = 100 bal» sətri görünürdü; indi bal bölgüsü yalnız
DOLDURULANDA yazılır (mənbədə bölgü yoxdur → sətir də yoxdur).  Eyni səbəbdən həftəlik sətirdə ``practical``
saatı və ``qeyd`` mətni əlavə açar kimi qalır (hədəfin ``LESSON_HOUR_KINDS``-i
yalnız lecture/seminar/lab-dır).

Hər qeyddə TƏKRARLANAN struktur faktlar (issue YAZILMIR)
--------------------------------------------------------
Aşağıdakılar mənbənin formasından gəlir və 8,248 qeydin demək olar hamısına
aiddir; onları hər sətir üçün ledger-ə yazmaq 25 000-dən çox eyni sətir
demək olardı, ona görə burada bir dəfə qeyd olunur:

* ``desc.goal`` BOŞ qalır — mənbədə «təsviri VƏ məqsədi» TƏK mətndir, onu ikiyə
  bölmək uydurma olardı;
* ``lit.additional`` BOŞ qalır — ``sillabus_derslikler`` əsas/əlavə ayırmır,
  hamısı ``primary``-yə düşür;
* ``self.option`` BOŞ qalır — mənbədə sərbəst iş variantı (1x10/2x5/10x1) yoxdur;
* ``week.rows[].outcome`` BOŞ qalır — mənbədə mövzu ↔ təlim nəticəsi bağı yoxdur;
* ``info.teacher``/``office_hours`` BOŞ qalır — sillabus cədvəlində müəllim adı
  və qəbul saatı sütunu yoxdur (müəllim ``Syllabus.author``-dadır).

Nəticədə köçürülən versiyaların ``completion_percent``-i 100 OLMUR — bu, doğru
cavabdır: köhnə sillabus bugünkü biznes qaydalarının hamısını ödəmir.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .rehearsal_authorizer import SYLLABUS_VERSION_MODEL_LABEL
from .rehearsal_contracts import LegacyRehearsalEvidenceError
from .rehearsal_journal_seal import JournalSealEntry, JournalSealer
from .rehearsal_syllabus_documents import (
    INSTRUCTOR_UNRESOLVED,
    NO_ACTIVE_VERSION,
    VERSION_FOLDED,
    SyllabusDocument,
)
from .rehearsal_syllabus_source import (
    AMBIGUOUS_UNIQID,
    HOUR_CELL_FRACTIONAL,
    HOUR_CELL_INVALID,
    HOUR_CELL_OUT_OF_RANGE,
    LANGUAGE_UNKNOWN,
    ORPHAN_UNIQID,
)
from .syllabus_migration_contracts import SYLLABUS_HEADER_FIELDS

SYLLABUS_ENTITY_TYPE = "syllabus_document"
SYLLABUS_SOURCE_TABLE = SYLLABUS_HEADER_FIELDS.source_table

# ── Hədəf kataloqunun SABİTLƏRİ ──────────────────────────────────────────────
# Dəyərlər ``apps.syllabus.constants``-dakı ``SectionKey``/``SyllabusStatus``
# ilə HƏRFƏN eynidir; modul-səviyyə idxal QƏSDƏN edilmir (legacy_import → syllabus
# tili yalnız funksiya-daxili yazı çağırışında var), bərabərliyi isə
# ``test_rehearsal_syllabus_targets`` kilidləyir.
SECTION_INFO = "info"
SECTION_DESC = "desc"
SECTION_OUT = "out"
SECTION_WEEK = "week"
SECTION_METHOD = "method"
SECTION_ASSESS = "assess"
SECTION_SELF = "self"
SECTION_LIT = "lit"
SECTION_PREV = "prev"
SECTION_SEND = "send"
SECTION_IDS = (
    SECTION_INFO,
    SECTION_DESC,
    SECTION_OUT,
    SECTION_WEEK,
    SECTION_METHOD,
    SECTION_ASSESS,
    SECTION_SELF,
    SECTION_LIT,
    SECTION_PREV,
    SECTION_SEND,
)
STATUS_APPROVED = "approved"
STATUS_ARCHIVED = "archived"
#: Hədəfin həftəlik cədvəl tavanı (``constants.WEEK_ROWS``).  Mənbədə daha çox
#: sətir ola bilər (nümunə: 23 mövzu) — KƏSİLMİR, yalnız qeyd olunur.
TARGET_WEEK_ROWS = 16
#: Hədəfin auditoriya saatı növləri (``constants.LESSON_HOUR_KINDS``).
TARGET_HOUR_KINDS = ("lecture", "seminar", "lab")

# ── Mənbə peykləri (``rehearsal_syllabus_documents`` sırası ilə) ─────────────
WELCOME_TABLE = "sillabus_qarsilama_mesaji"
DESCRIPTION_TABLE = "sillabus_tesviri_ve_meqsedi"
OUTCOME_TABLE = "sillabus_eldeolunacaq_tecrubeler"
METHOD_TABLE = "sillabus_dersin_islenme_formasi"
ASSESSMENT_TABLE = "sillabus_yoxlama_formasi"
SELF_WORK_TABLE = "sillabus_serbest_is"
EXAM_QUESTION_TABLE = "sillabus_imtahan_suallari"
LITERATURE_TABLE = "sillabus_derslikler"
RESEARCH_TABLE = "sillabus_elmi_maraq"
CERTIFICATE_TABLE = "sillabus_certificates"

# ── Issue taksonomiyası ──────────────────────────────────────────────────────
#: ``lesson_id`` bu run-da MIGRATED fənnə düşmür → sillabus YAZILMIR (karantin).
SUBJECT_UNRESOLVED = "legacy_syllabus_subject_unresolved"
#: İki (fənn, müəllim) cütü EYNİ hədəf dosyesinə düşdü — versiyalar bir
#: nərdivana birləşdirildi.  ⚠️ Müəllimi silinmiş 956 sillabus ARTIQ bu koda
#: səbəb OLMUR: sahibin qərarı ilə onlar heç yazılmır (spec §9), yəni qalan
#: yeganə səbəb kimlik fazasının iki legacy müəllimi bir istifadəçiyə həll
#: etməsidir.
DOSSIER_MERGED = "legacy_syllabus_dossier_merged"
#: Sənədə bir dənə də bölmə sətri bağlanmadı.
SECTIONS_EMPTY = "legacy_syllabus_sections_empty"
#: Boş ``name`` daşıyan peyk sətri siyahıya yazılmadı (mövqe daşımır).
BLANK_ROW_DROPPED = "legacy_syllabus_blank_row_dropped"
#: Mətn kontrakt tavanında kəsildi.
TEXT_TRUNCATED = "legacy_syllabus_text_truncated"
#: Həftəlik sətir sayı hədəfin 16 sətirlik cədvəlini aşır — KƏSİLMİR.
WEEK_ROWS_EXCEED_PLAN = "legacy_syllabus_week_rows_exceed_plan"
#: ``praktiki_saat`` doludur, hədəfin saat növləri isə üçdür — əlavə açarda saxlanıldı.
PRACTICAL_UNSURFACED = "legacy_syllabus_practical_hours_unsurfaced"
#: Qarşılama mesajı ``info.welcome``-a yazıldı; redaktorda hələ göstərilmir.
WELCOME_UNSURFACED = "legacy_syllabus_welcome_unsurfaced"
#: İmtahan sualları ``assess.exam_questions``-a yazıldı; REDAKTORDA input yoxdur.
#: (Oxu sənədi — ``apps.syllabus.document`` — onları tələbəyə göstərir; kod
#: «müəllim redaktə edə bilmir» faktını sayır, «data görünmür» faktını yox.)
EXAM_QUESTIONS_UNSURFACED = "legacy_syllabus_exam_questions_unsurfaced"
#: Qiymətləndirmə qaydasının ÖZ mətni ``assess.note``-a yazıldı; redaktorun
#: qiymətləndirmə panelində bu mətn üçün input YOXDUR (yalnız bal sürüşdürücüsü
#: var).  Oxu sənədi mətni göstərir, amma müəllim onu redaktordan görə/dəyişə
#: bilmir — ona görə itki hesabatda RƏQƏMLƏ görünür.  Canlı mənbədə bu mətn
#: demək olar hər sillabusda var (``sillabus_yoxlama_formasi`` 8,261 sətir),
#: yəni sayğac sıfır olsa, o özü şübhə siqnalıdır.
ASSESSMENT_NOTE_UNSURFACED = "legacy_syllabus_assessment_note_unsurfaced"
#: Elmi maraq / sertifikat ``info``-ya yazıldı; redaktorda göstərilmir.
TEACHER_PROFILE_UNSURFACED = "legacy_syllabus_teacher_profile_unsurfaced"

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity

# E-13 ilə eyni ruh: heç nə ERROR deyil — ilk sillabus köçürməsi tam histoqram
# verməli, bloklamamalıdır.  WARNING = «mənbədə dəyər VAR, hədəfə yazıla
# bilmədi»; INFO = «yazıldı, amma bir şərti qeyd etməyə dəyər».
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                SUBJECT_UNRESOLVED,
                INSTRUCTOR_UNRESOLVED,
                AMBIGUOUS_UNIQID,
                ORPHAN_UNIQID,
                HOUR_CELL_FRACTIONAL,
                HOUR_CELL_INVALID,
                HOUR_CELL_OUT_OF_RANGE,
                TEXT_TRUNCATED,
            ),
            _SEVERITY.WARNING,
        ),
        **dict.fromkeys(
            (
                LANGUAGE_UNKNOWN,
                VERSION_FOLDED,
                NO_ACTIVE_VERSION,
                DOSSIER_MERGED,
                SECTIONS_EMPTY,
                BLANK_ROW_DROPPED,
                WEEK_ROWS_EXCEED_PLAN,
                PRACTICAL_UNSURFACED,
                WELCOME_UNSURFACED,
                EXAM_QUESTIONS_UNSURFACED,
                ASSESSMENT_NOTE_UNSURFACED,
                TEACHER_PROFILE_UNSURFACED,
            ),
            _SEVERITY.INFO,
        ),
    }
)

SYLLABUS_SEALER = JournalSealer(
    entity_type=SYLLABUS_ENTITY_TYPE,
    source_table=SYLLABUS_SOURCE_TABLE,
    # ``v3`` — bax ``rehearsal_syllabus_phase.DERIVED_DIGEST_NAMESPACE`` qeydi.
    derivation_prefix=b"legacy-rehearsal-syllabus-migration-derivation-v3\x00",
    contract_fingerprint=SYLLABUS_HEADER_FIELDS.fingerprint,
    issue_severity=ISSUE_SEVERITY,
)


def _texts(rows) -> tuple[tuple[str, ...], int, bool]:
    """Peyk sətirləri → ``(mətnlər, atılan boş sətir sayı, kəsilibmi)``."""

    texts = tuple(row.text for row in rows if row.text)
    truncated = any(row.truncated for row in rows)
    return texts, len(rows) - len(texts), truncated


def _week_rows(document: SyllabusDocument) -> tuple[list[dict], list[str], bool]:
    """Həftəlik cədvəl — mənbə sırasında, KƏSİLMƏDƏN və PADDİNGSİZ.

    Boş mövzulu sətir ATILMIR: onu atmaq qalan mövzuları bir həftə yuxarı
    sürüşdürərdi.  ``practical`` və ``qeyd`` əlavə açar kimi qalır — hədəfin
    qayda mühərriki onlara baxmır, amma data da itmir.
    """

    rows: list[dict] = []
    codes: list[str] = []
    truncated = False
    practical = False
    for source_row in document.week:
        hours = dict(source_row.hours)
        if hours.get("practical"):
            practical = True
        rows.append(
            {
                "topic": source_row.topic,
                **{kind: int(hours.get(kind, 0)) for kind in TARGET_HOUR_KINDS},
                "outcome": "",
                "practical": int(hours.get("practical", 0)),
                "note": source_row.note,
            }
        )
        codes.extend(source_row.issues)
        truncated = truncated or source_row.truncated
    if practical:
        codes.append(PRACTICAL_UNSURFACED)
    if len(rows) > TARGET_WEEK_ROWS:
        codes.append(WEEK_ROWS_EXCEED_PLAN)
    return rows, codes, truncated


def build_section_data(document: SyllabusDocument) -> tuple[dict, tuple[str, ...]]:
    """Sənəd → ``{section_id: data}`` + bu xəritənin issue kodları.

    Saf funksiya: heç bir DB, heç bir hədəf açarı.  Kodlar TƏKRARSIZ və sabit
    sırada qaytarılır ki, eyni sənəd hər run-da eyni ledger izini versin.
    """

    by_table = dict(document.sections)
    texts: dict[str, tuple[str, ...]] = {}
    codes: list[str] = []
    blanks = 0
    truncated = False
    for table, rows in by_table.items():
        table_texts, table_blanks, table_truncated = _texts(rows)
        texts[table] = table_texts
        blanks += table_blanks
        truncated = truncated or table_truncated

    week_rows, week_codes, week_truncated = _week_rows(document)
    codes.extend(week_codes)
    truncated = truncated or week_truncated

    welcome = "\n\n".join(texts.get(WELCOME_TABLE, ()))
    research = list(texts.get(RESEARCH_TABLE, ()))
    certificates = list(texts.get(CERTIFICATE_TABLE, ()))
    exam_questions = list(texts.get(EXAM_QUESTION_TABLE, ()))
    assessment_note = "\n".join(texts.get(ASSESSMENT_TABLE, ()))
    if welcome:
        codes.append(WELCOME_UNSURFACED)
    if exam_questions:
        codes.append(EXAM_QUESTIONS_UNSURFACED)
    if assessment_note:
        codes.append(ASSESSMENT_NOTE_UNSURFACED)
    if research or certificates:
        codes.append(TEACHER_PROFILE_UNSURFACED)
    if blanks:
        codes.append(BLANK_ROW_DROPPED)
    if truncated:
        codes.append(TEXT_TRUNCATED)
    if not document.section_row_count:
        codes.append(SECTIONS_EMPTY)

    data = {
        SECTION_INFO: {
            "teacher": "",
            "office_hours": "",
            "prerequisites": "",
            "language": document.header.language,
            "lesson_hours": document.header.lesson_hours,
            "welcome": welcome,
            "research_interests": research,
            "certificates": certificates,
        },
        SECTION_DESC: {"description": "\n\n".join(texts.get(DESCRIPTION_TABLE, ())), "goal": ""},
        SECTION_OUT: {"outcomes": list(texts.get(OUTCOME_TABLE, ()))},
        SECTION_WEEK: {"rows": week_rows},
        SECTION_METHOD: {"methods": list(texts.get(METHOD_TABLE, ())), "note": ""},
        # ⚠️ ``midterm``/``project`` 0 qalır — mənbədə bal bölgüsü YOXDUR.
        # Oxu sənədi bu cütü «bölgü doldurulmayıb» kimi oxuyur və uydurma cəm
        # sətri YAZMIR (bax ``apps.syllabus.document._assessment_weights``);
        # tələbənin gördüyü qiymətləndirmə mətni məhz ``note``-dur.
        SECTION_ASSESS: {
            "midterm": 0,
            "project": 0,
            "note": assessment_note,
            "exam_questions": exam_questions,
        },
        SECTION_SELF: {
            "option": "",
            "topics": [{"title": text} for text in texts.get(SELF_WORK_TABLE, ())],
            "archived": [],
        },
        SECTION_LIT: {"primary": list(texts.get(LITERATURE_TABLE, ())), "additional": []},
        SECTION_PREV: {},
        SECTION_SEND: {},
    }
    return data, _ordered_unique(codes)


def _ordered_unique(codes) -> tuple[str, ...]:
    """Kodları TƏKRARSIZ, ilk görünmə sırasında sabitlə."""

    seen: dict[str, None] = {}
    for code in codes:
        seen.setdefault(code, None)
    return tuple(seen)


@dataclass(frozen=True)
class SyllabusWriteRequest:
    """Bir mənbə sənədinin həll olunmuş yazı niyyəti (hədəf açarı YOXDUR)."""

    seal_key: str
    subject_pk: str
    author_pk: str
    minor: int
    status: str
    content_digest: str
    section_data: dict
    folded_source_pks: tuple[int, ...]
    rule_codes: tuple[str, ...]
    #: Digest materialı üçün başlığın distillə olunmuş faktları.
    uniqid: str
    lesson_id: int
    teacher_id: int
    lesson_hours: int
    language: str
    active: bool

    def digest_parts(self) -> tuple[str, ...]:
        """Cross-run sabit qərar izi — heç bir hədəf UUID-si girmir."""

        return (
            f"uniqid={self.uniqid}",
            f"lesson={self.lesson_id}",
            f"teacher={self.teacher_id}",
            f"hours={self.lesson_hours}",
            f"language={self.language}",
            f"active={int(self.active)}",
            f"minor={self.minor}",
            f"status={self.status}",
            f"content={self.content_digest}",
            f"folded={','.join(str(pk) for pk in self.folded_source_pks)}",
        )

    @property
    def note(self) -> str:
        """``decision_reason`` — DAXİLİ iz; şəxsi məlumat DAŞIMIR."""

        return f"myedu:{SYLLABUS_SOURCE_TABLE}:{self.seal_key}"


def resolved_entry(*, seal_key: str, outcome: str, parts, rule_codes, quarantined: bool = False) -> JournalSealEntry:
    """Hədəf yazısı OLMAYAN qərar (yetim, qatlanmış, fənni həll olunmayan)."""

    return JournalSealEntry(
        seal_key=seal_key,
        digest=SYLLABUS_SEALER.derivation_hash(seal_key=seal_key, outcome_token=outcome, parts=tuple(parts)),
        state=_STATE.QUARANTINED if quarantined else _STATE.SKIPPED,
        rule_codes=tuple(rule_codes),
    )


class SyllabusDossierWriter:
    """Bir hədəf dosyesinin bütün versiyalarını BİR tranzaksiyada yazır.

    Niyə dosye-səviyyə tranzaksiya: model «bir dosyedə yalnız bir APPROVED»
    unikal məhdudiyyətini daşıyır, yəni arxivləmə və təsdiq eyni yazı
    ardıcıllığında oturmalıdır.  Nərdivan onsuz da TƏK bir APPROVED pillə
    seçir, ona görə burada UPDATE yoxdur — sadəcə hamısı bir yerdə commit olur
    və yarımçıq dosye qalmır.
    """

    def __init__(self, context) -> None:
        self._context = context
        self._subjects: dict[str, object] = {}
        self._authors: dict[str, object] = {}
        self.issue_counts: Counter[tuple[str, str]] = Counter()
        self.sealed: list[tuple[str, tuple[str, str, str]]] = []
        self.written_versions = 0

    # ── hədəf obyektləri (dəstə daxilində keşlənir) ─────────────────────────

    def _subject(self, subject_pk: str):
        if subject_pk not in self._subjects:
            model = django_apps.get_model("registrar", "Subject")
            self._subjects[subject_pk] = model.objects.get(pk=subject_pk, organization=self._context.organization)
        return self._subjects[subject_pk]

    def _author(self, author_pk: str):
        if not author_pk:
            # Müəllimsiz nərdivan qərar qatında SKIP olunur (spec §9), yəni
            # buraya çatan boş açar kod xətasıdır — uydurma ``author=NULL``
            # yazmaq əvəzinə fail-closed dayanılır.
            raise LegacyRehearsalEvidenceError("legacy_syllabus_author_missing")
        if author_pk not in self._authors:
            model = django_apps.get_model("auth", "User")
            self._authors[author_pk] = model.objects.get(pk=author_pk)
        return self._authors[author_pk]

    # ── yazı ────────────────────────────────────────────────────────────────

    def write(self, requests, *, resolved=()) -> None:
        """Bir dosyenin pillələri + onları müşayiət edən hədəfsiz qərarlar."""

        if not requests and not resolved:
            return
        entries: list[JournalSealEntry] = list(resolved)
        with transaction.atomic():
            for request in requests:
                entries.append(self._write_one(request))
            self._seal(entries)

    def _write_one(self, request: SyllabusWriteRequest) -> JournalSealEntry:
        # Funksiya-daxili idxal: ``apps.accounts.public`` presedenti (V-25).
        from apps.syllabus.public import import_migrated_version

        _syllabus, version = import_migrated_version(
            organization=self._context.organization,
            subject=self._subject(request.subject_pk),
            approved_at=timezone.now(),
            author=self._author(request.author_pk),
            section_data=request.section_data,
            major=1,
            minor=request.minor,
            status=request.status,
            note=request.note,
        )
        self.written_versions += 1
        return JournalSealEntry(
            seal_key=request.seal_key,
            digest=SYLLABUS_SEALER.derivation_hash(
                seal_key=request.seal_key,
                outcome_token="imported",
                parts=request.digest_parts(),
            ),
            state=_STATE.MIGRATED,
            label=SYLLABUS_VERSION_MODEL_LABEL,
            target_pk=str(version.pk),
            rule_codes=request.rule_codes,
        )

    def _seal(self, entries) -> None:
        SYLLABUS_SEALER.seal_many(self._context, entries, issue_counts=self.issue_counts)
        self.sealed.extend((entry.seal_key, (entry.state, entry.digest, entry.label)) for entry in entries)


__all__ = [
    "ASSESSMENT_NOTE_UNSURFACED",
    "ASSESSMENT_TABLE",
    "BLANK_ROW_DROPPED",
    "CERTIFICATE_TABLE",
    "DESCRIPTION_TABLE",
    "DOSSIER_MERGED",
    "EXAM_QUESTIONS_UNSURFACED",
    "EXAM_QUESTION_TABLE",
    "ISSUE_SEVERITY",
    "LITERATURE_TABLE",
    "METHOD_TABLE",
    "OUTCOME_TABLE",
    "PRACTICAL_UNSURFACED",
    "RESEARCH_TABLE",
    "SECTIONS_EMPTY",
    "SECTION_IDS",
    "SELF_WORK_TABLE",
    "STATUS_APPROVED",
    "STATUS_ARCHIVED",
    "SUBJECT_UNRESOLVED",
    "SYLLABUS_ENTITY_TYPE",
    "SYLLABUS_SEALER",
    "SYLLABUS_SOURCE_TABLE",
    "SYLLABUS_VERSION_MODEL_LABEL",
    "TARGET_HOUR_KINDS",
    "TARGET_WEEK_ROWS",
    "TEACHER_PROFILE_UNSURFACED",
    "TEXT_TRUNCATED",
    "WEEK_ROWS_EXCEED_PLAN",
    "WELCOME_TABLE",
    "WELCOME_UNSURFACED",
    "SyllabusDossierWriter",
    "SyllabusWriteRequest",
    "build_section_data",
    "resolved_entry",
]
