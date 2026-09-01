"""Sillabus sənədinin yığılması və DUBLİKAT → VERSİYA nərdivanı.

``rehearsal_syllabus_source`` cədvəlləri ayrı-ayrı oxuyur; bu modul onları bir
sənədə yığır və (fənn, müəllim) cütü üzrə versiya nərdivanına düzür.  Burada da
heç bir hədəf yazısı yoxdur — yalnız saf funksiyalar.

Niyə dublikatlar SİLİNMİR
=========================
Canlı mənbədə 8,248 başlıq cəmi 5,646 fərqli (``lesson_id``, ``teacher_id``)
cütü verir: 4,172 cüt tək, qalanı təkrarlıdır (2 dəfə 945, 3 dəfə 294 … 19 dəfə
1).  Nümunə: ``lesson_id=4, teacher_id=282`` üçün 7 sillabus, hər birində eyni
23 mövzu — köhnə sistem çox güman hər açılış/qrup üçün nüsxə yaradıb, sonra
qrup sütunları sıfırlanıb (``qrup_id`` bu gün 8,248/8,248 sətirdə 0-dır).

Yalnız sonuncunu köçürmək tarixçəni silmək, hamısını bərabər köçürmək isə
siyahını 8,248 sətirlə doldurmaq olardı.  Ona görə təkrarlar VERSİYA olur.

Qatlama və status seçkisi (deterministik, sıradan asılı olmayan)
================================================================
1. Sənədlər ``sillabus.id`` üzrə ARTAN sırada düzülür.
2. Hər sənədin ``content_digest``-i hesablanır — yalnız TƏMİZLƏNMİŞ MƏZMUN
   üzərində (dil, fənn saatı, həftəlik plan, 10 bölmə).  ``sillabus.id``,
   ``uniqid`` və ``active`` bayrağı digest-ə GİRMİR: onlar sənədin kim
   olduğunu deyil, harada durduğunu bildirir.
3. Eyni digest-li sənədlər BİR versiyaya qatlanır; nümayəndə ƏN KİÇİK
   ``id``-dir (orijinal), qatlananların ``id``-ləri ``folded_source_pks``-də
   qalır — yəni heç bir mənbə sətri səssizcə itmir, uzlaşdırmada tam sayılır.
4. Versiya nömrələri saxlanan sənədlərə ``id`` sırasında 1…N verilir.
5. **APPROVED seçkisi:** ən BÖYÜK ``id``-li o versiya seçilir ki, onun özü və
   ya qatlanan qardaşlarından biri ``active=1`` olsun.  Qalan hər versiya
   ``ARCHIVED``-dir.  Heç biri aktiv deyilsə — HEÇ BİRİ APPROVED OLMUR.

   ⚠️ Bu 5-ci qayda sahibin «hamısı təsdiqlənmiş gəlsin» tələbi ilə mənbədəki
   ``active`` bayrağı arasındakı ziddiyyəti uydurmadan həll edir: 714
   qeyri-aktiv başlıq mənbədə AÇIQ şəkildə söndürülüb, onları «təsdiqlənmiş»
   yazmaq mövcud faktı dəyişmək olardı.  Təsdiq özü isə saxta insan imzası ilə
   deyil, ``SyllabusVersion.approval_source = "migration"`` ilə gəlir.

⚠️ Semestr və tarix BURADA DA UYDURULMUR
----------------------------------------
Mənbədə nə semestr, nə yaranma tarixi var (``sillabus``-da tarix sütunu yoxdur,
``sillabus_sem_muh.tarix`` 131,056/131,056 sətirdə boşdur).  Versiya nərdivanı
ona görə yalnız ``sillabus.id`` sırasına söykənir — bu, mənbənin YEGANƏ real
xronologiya siqnalıdır (auto-increment), və o da "tarix" kimi TƏQDİM EDİLMİR.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .rehearsal_contracts import RehearsalContext, canonical_json_digest
from .rehearsal_syllabus_source import (
    AMBIGUOUS_UNIQID,
    ORPHAN_UNIQID,
    SyllabusHeaderRow,
    SyllabusSectionRow,
    SyllabusWeekRow,
    syllabus_header_index,
    syllabus_section_rows,
    syllabus_week_rows,
)
from .syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS

#: ``teacher_id`` heç bir ``workers`` sətrinə düşmür (canlı: 956 başlıq).
#: ⚠️ Sahibin 2026-08-31 qərarı (spec §9): belə sillabus HƏDƏFƏ YAZILMIR.
#: Kod itkini gizlətmir — ledger-də ``state=SKIPPED`` möhürü ilə qalır ki,
#: uzlaşdırmada 8,248 → hədəf fərqi izahsız qalıq verməsin.
INSTRUCTOR_UNRESOLVED = "legacy_syllabus_instructor_unresolved"
#: Versiya qatlandı: məzmun digest-i əvvəlki versiya ilə eynidir.
VERSION_FOLDED = "legacy_syllabus_version_folded"
#: (fənn, müəllim) cütündə heç bir aktiv başlıq yoxdur → APPROVED seçilmir.
NO_ACTIVE_VERSION = "legacy_syllabus_no_active_version"


@dataclass(frozen=True)
class SyllabusDocument:
    """Bir ``sillabus`` başlığı + ona bağlı BÜTÜN bölmə sətirləri."""

    header: SyllabusHeaderRow
    week: tuple[SyllabusWeekRow, ...]
    #: mənbə cədvəli → sətirlər (``SYLLABUS_SECTION_CONTRACTS`` sırasında).
    sections: tuple[tuple[str, tuple[SyllabusSectionRow, ...]], ...]

    @property
    def section_row_count(self) -> int:
        return len(self.week) + sum(len(rows) for _table, rows in self.sections)


@dataclass(frozen=True)
class SyllabusVersion:
    """Nərdivanın bir pilləsi."""

    version_number: int
    document: SyllabusDocument
    content_digest: str
    approved: bool
    #: Bu versiyaya qatlanan DİGƏR ``sillabus.id``-lər (artan sırada).
    folded_source_pks: tuple[int, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class SyllabusVersionLadder:
    """Bir (fənn, müəllim) cütünün bütün versiyaları."""

    lesson_id: int
    teacher_id: int
    versions: tuple[SyllabusVersion, ...]

    @property
    def source_document_count(self) -> int:
        return sum(1 + len(version.folded_source_pks) for version in self.versions)


@dataclass(frozen=True)
class SyllabusSourceSnapshot:
    """Bütün mənbənin bir keçidlik, yaddaşdakı distilləsi."""

    ladders: tuple[SyllabusVersionLadder, ...]
    #: Başlığı olmayan bölmə ``uniqid``-ləri → (cədvəl → sətir sayı).
    orphans: Mapping[str, Mapping[str, int]]
    #: Birdən çox başlıq daşıyan ``uniqid``-lər (fail-closed bağlanmır).
    ambiguous_uniqids: frozenset[str]

    @property
    def issue_codes(self) -> tuple[str, ...]:
        """Bu snapshot-ın hesabata yazdığı bütün qalıq kodları."""

        codes: list[str] = []
        if self.orphans:
            codes.append(ORPHAN_UNIQID)
        if self.ambiguous_uniqids:
            codes.append(AMBIGUOUS_UNIQID)
        return tuple(codes)


def content_digest(document: SyllabusDocument) -> str:
    """Sənədin MƏZMUN barmaq izi — ``id``/``uniqid``/``active`` daxil DEYİL.

    Qatlama qərarı buna baxır, ona görə payload-a yalnız müəllimin YAZDIĞI şey
    girir.  ``lesson_id``/``teacher_id`` də girmir: nərdivan onsuz da məhz o
    cütün içindədir, onları digest-ə qatmaq heç nə ayırmazdı.
    """

    payload = {
        "language": document.header.language,
        "lesson_hours": document.header.lesson_hours,
        "week": [
            {
                "topic": row.topic,
                "note": row.note,
                "hours": [list(pair) for pair in row.hours],
            }
            for row in document.week
        ],
        "sections": {table: [row.text for row in rows] for table, rows in document.sections},
    }
    return canonical_json_digest(payload)


def _elect_versions(
    documents: tuple[SyllabusDocument, ...],
) -> tuple[SyllabusVersion, ...]:
    """Qatla, nömrələ, APPROVED seç — modul başlığındakı 5 qayda."""

    retained: list[SyllabusDocument] = []
    digests: list[str] = []
    folded: dict[str, list[int]] = {}
    active_pks: dict[str, bool] = {}
    position_of: dict[str, int] = {}
    for document in documents:
        digest = content_digest(document)
        if digest in position_of:
            folded[digest].append(document.header.legacy_pk)
            active_pks[digest] = active_pks[digest] or document.header.active
            continue
        position_of[digest] = len(retained)
        retained.append(document)
        digests.append(digest)
        folded[digest] = []
        active_pks[digest] = document.header.active

    approved_index = -1
    for index, digest in enumerate(digests):
        if active_pks[digest]:
            approved_index = index  # ən BÖYÜK id-li aktiv pillə qalib gəlir

    versions: list[SyllabusVersion] = []
    for index, document in enumerate(retained):
        digest = digests[index]
        issues: list[str] = list(document.header.issues)
        if folded[digest]:
            issues.append(VERSION_FOLDED)
        if approved_index < 0:
            issues.append(NO_ACTIVE_VERSION)
        versions.append(
            SyllabusVersion(
                version_number=index + 1,
                document=document,
                content_digest=digest,
                approved=index == approved_index,
                folded_source_pks=tuple(sorted(folded[digest])),
                issues=tuple(issues),
            )
        )
    return tuple(versions)


def build_syllabus_snapshot(context: RehearsalContext) -> SyllabusSourceSnapshot:
    """12 cədvəli oxu, sənədləri yığ, versiya nərdivanlarını qur.

    Cədvəllər BİR-BİR axıdılır (hər biri öz audited bağlantısında), sonra
    ``uniqid`` üzrə birləşdirilir.  Bu, mənbədə yad açar olmadığı üçün yeganə
    mümkün formadır; sıra isə hər axının PK sırasından gəlir, ona görə eyni
    dump iki dəfə oxunanda eyni nəticə çıxır.
    """

    index = syllabus_header_index(context)
    week_by_uniqid = syllabus_week_rows(context)
    sections_by_table = {table: syllabus_section_rows(context, table) for table in SYLLABUS_SECTION_CONTRACTS}

    documents_by_pair: dict[tuple[int, int], list[SyllabusDocument]] = {}
    for legacy_pk in sorted(index.headers):
        header = index.headers[legacy_pk]
        # Ambiqü uniqid körpüdə yoxdur → başlıq bölməsiz qalır (fail-closed).
        linked = index.pk_of_uniqid.get(header.uniqid) == legacy_pk
        document = SyllabusDocument(
            header=header,
            week=week_by_uniqid.get(header.uniqid, ()) if linked else (),
            sections=tuple(
                (table, sections_by_table[table].get(header.uniqid, ()) if linked else ())
                for table in SYLLABUS_SECTION_CONTRACTS
            ),
        )
        documents_by_pair.setdefault((header.lesson_id, header.teacher_id), []).append(document)

    ladders = tuple(
        SyllabusVersionLadder(
            lesson_id=lesson_id,
            teacher_id=teacher_id,
            versions=_elect_versions(tuple(documents)),
        )
        for (lesson_id, teacher_id), documents in sorted(documents_by_pair.items())
    )
    return SyllabusSourceSnapshot(
        ladders=ladders,
        orphans=_orphan_report(index, week_by_uniqid, sections_by_table),
        ambiguous_uniqids=index.ambiguous_uniqids,
    )


def _orphan_report(index, week_by_uniqid, sections_by_table) -> dict[str, dict[str, int]]:
    """Başlığı olmayan ``uniqid``-lər → hansı cədvəldə neçə sətir qaldı.

    Bu sətirlər ATILIR, amma hesabata YAZILIR: çərçivənin qaydası izahsız
    qalığın sıfır olmasıdır, izahlı qalığın isə görünməsidir.
    """

    known = set(index.pk_of_uniqid) | index.ambiguous_uniqids
    orphans: dict[str, dict[str, int]] = {}
    for table, grouped in (("sillabus_sem_muh", week_by_uniqid), *sections_by_table.items()):
        for uniqid, rows in grouped.items():
            if uniqid in known:
                continue
            orphans.setdefault(uniqid, {})[table] = len(rows)
    return orphans


__all__ = [
    "INSTRUCTOR_UNRESOLVED",
    "NO_ACTIVE_VERSION",
    "VERSION_FOLDED",
    "SyllabusDocument",
    "SyllabusSourceSnapshot",
    "SyllabusVersion",
    "SyllabusVersionLadder",
    "build_syllabus_snapshot",
    "content_digest",
]
