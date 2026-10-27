"""``syllabi_backfill`` — cari semestr jurnalı olan müəllimin köhnə sillabusu (sahib 2026-10-27, OPT-IN faza).

Sahib: «Köhnə sistemdə jurnalı olan müəllimlərin sillabusu burda görünmür — mövcud olanlara dəymədən köhnələri
gətir.» ``syllabi`` fazası sillabusu AÇILIŞA bağlayır və müəllifi açılışın müəllimi edir — birləşmiş jurnalların
(bir açılışa bir neçə köhnə jurnal) digər müəllimləri öz sillabusunu itirib; cutover-in ``syllabus_migration``
fazası isə prod-da heç işləməyib.

Paket ``legacy_delta_extract --teacher-syllabi`` ilə qurulur (``snapshot.phases = ["syllabi_backfill"]``, adi
fazalarla birgə RƏDD olunur). Hər (köhnə müəllim, fənn) cütü üçün — cari semestr jurnallarından:

* müəllim — delta ``TeacherMapper`` (ledger → ad tutuşdurması), ``create=False``: hesab YARADILMIR, tapılmayan
  sayılıb keçilir (``teacher_unresolved``);
* fənn — ``Catalog.subject_for`` (``subject_unresolved``);
* müəllimin bu fəndə İSTƏNİLƏN aktiv sillabusu varsa (müəllif və ya açılış müəllimi kimi) — TOXUNULMUR
  (``skipped_existing``); eyni açarlı PASSİV baza dosye də toxunulmaz qalır (``skipped_inactive_base``);
* mənbə — jurnalın öz ``sillabus_id``-si (eyni fənn, boş deyil), yoxsa həmin müəllim + fənnin ƏN YENİ aktiv,
  boş olmayan köhnə sillabusu (``empty`` / ``no_syllabus``);
* hədəf — semestrsiz «baza sillabus» (``import_migrated_version``, ``approval_source=migration``, müəllif =
  köhnə müəllim). Jurnal onu ``syllabus_for_offering``-in 3-cü pilləsi ilə (fənn + açılışın müəllimi) tapır.

Məzmun ``syllabi`` fazasının ÖZ çeviricisi ilədir (``document_for`` + ``build_section_data``). İdempotentdir:
ikinci qaçış ``skipped_existing`` verir, 0 yazı.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Q
from django.utils import timezone

from ..rehearsal_syllabus_targets import build_section_data
from .history import HistoryPhaseMismatch
from .people import TeacherMapper
from .syllabi import NOTE, _chair_for, _same_subject, document_for

PHASE = "syllabi_backfill"
#: Hesabatda HƏMİŞƏ görünən saylar (0 da) — prod-data-ops xülasəsi ``syllabi_backfill.<açar> <say>`` sətirləridir.
COUNTER_KEYS = (
    "pairs",
    "created",
    "skipped_existing",
    "skipped_inactive_base",
    "teacher_unresolved",
    "subject_unresolved",
    "empty",
    "no_syllabus",
    "duplicate_pair",
)


class TeacherSyllabiPhaseMismatch(HistoryPhaseMismatch):
    """``--teacher-syllabi`` paketi yalnız ``syllabi_backfill`` ilə işlədilir (jurnal bölməsi qismən/boşdur)."""


def check_phases(bundle: dict, phases) -> None:
    if (bundle.get("snapshot") or {}).get("teacher_syllabi") and set(phases) - {PHASE}:
        raise TeacherSyllabiPhaseMismatch("legacy_delta_teacher_syllabi_bundle_phase_mismatch")


def _flag(value) -> bool:
    return str(value or "0").strip() not in ("", "0")


def is_empty(row: dict) -> bool:
    """Həftəlik mövzusu da, peyk bölməsi də olmayan köhnə sillabus."""

    return not row.get("week") and not any((row.get("sections") or {}).values())


def journal_pairs(journals) -> dict:
    """``(legacy teacher_id, legacy lesson_id)`` → həmin cütün jurnalları (saxta / «sonra sil» atılır)."""

    pairs: dict = defaultdict(list)
    for row in journals:
        if _flag(row.get("fake")) or _flag(row.get("sonra_sil")):
            continue
        if row.get("teacher_id") and row.get("lesson_id"):
            pairs[(row["teacher_id"], row["lesson_id"])].append(row)
    return pairs


def choose_source(run, journals, teacher_id, lesson_id, by_id: dict, by_teacher: dict):
    """``(legacy sillabus | None, səbəb)`` — jurnalın öz sillabusu, yoxsa müəllim + fənnin ən yenisi."""

    seen_empty = False
    own = []
    for journal in journals:
        legacy = by_id.get(journal.get("sillabus_id"))
        if legacy is None or not _same_subject(run, legacy.get("lesson_id"), lesson_id):
            continue
        if is_empty(legacy):
            seen_empty = True
            continue
        own.append(legacy)
    if own:
        return max(own, key=lambda row: (bool(row.get("active")), int(row["id"]))), "journal"
    fallback = []
    for legacy in by_teacher.get(teacher_id, ()):
        if not legacy.get("active") or not _same_subject(run, legacy.get("lesson_id"), lesson_id):
            continue
        if is_empty(legacy):
            seen_empty = True
            continue
        fallback.append(legacy)
    if fallback:
        return max(fallback, key=lambda row: int(row["id"])), "teacher_subject"
    return None, "empty" if seen_empty else "no_syllabus"


def backfill_teacher_syllabi(run) -> None:
    from apps.syllabus.public import import_migrated_version

    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    for key in COUNTER_KEYS:
        run.counters.setdefault(f"{PHASE}.{key}", 0)
    teachers = TeacherMapper(run, {row["id"]: row for row in run.bundle["workers"]}, create=False)
    by_id = {row["id"]: row for row in run.bundle["syllabi"]}
    by_teacher: dict = defaultdict(list)
    for row in run.bundle["syllabi"]:
        by_teacher[row.get("teacher_id")].append(row)
    stamp = timezone.now()
    note = NOTE.format(tag=run.tag)
    done: set = set()
    pairs = journal_pairs(run.bundle["journals"])
    run.count(f"{PHASE}.pairs", len(pairs))
    for (teacher_id, lesson_id), journals in sorted(pairs.items()):
        subject_row = run.legacy_subjects.get(lesson_id)
        subject = run.catalog.subject_for(subject_row)[0] if subject_row else None
        if subject is None:
            run.count(f"{PHASE}.subject_unresolved")
            continue
        author, _outcome = teachers.resolve(teacher_id)
        if author is None:
            run.count(f"{PHASE}.teacher_unresolved")
            continue
        if (author.pk, subject.pk) in done:
            run.count(f"{PHASE}.duplicate_pair")
            continue
        mine = Syllabus.objects.filter(organization=run.organization, subject=subject)
        if mine.filter(is_active=True).filter(Q(author=author) | Q(offering__instructor=author)).exists():
            run.count(f"{PHASE}.skipped_existing")
            continue
        if mine.filter(author=author, offering__isnull=True, period__isnull=True).exists():
            # ``import_migrated_version`` get_or_create ilə PASSİV dosyeyə versiya əlavə edərdi — mövcud sətrə dəymirik.
            run.count(f"{PHASE}.skipped_inactive_base")
            continue
        legacy, reason = choose_source(run, journals, teacher_id, lesson_id, by_id, by_teacher)
        if legacy is None:
            run.count(f"{PHASE}.{reason}")
            continue
        section_data, _codes = build_section_data(document_for(legacy))
        _syllabus, version = import_migrated_version(
            organization=run.organization,
            subject=subject,
            approved_at=stamp,
            chair_unit=_chair_for(subject, author, run.organization),
            author=author,
            section_data=section_data,
            note=note,
        )
        done.add((author.pk, subject.pk))  # eyni hədəfə düşən ikinci legacy cüt (dublikat fənn / müəllim) yazmır
        run.created("syllabus_versions", version.pk)
        run.count(f"{PHASE}.created")
        run.count(f"{PHASE}.source_{reason}")


__all__ = [
    "COUNTER_KEYS",
    "PHASE",
    "TeacherSyllabiPhaseMismatch",
    "backfill_teacher_syllabi",
    "check_phases",
    "choose_source",
    "is_empty",
    "journal_pairs",
]
