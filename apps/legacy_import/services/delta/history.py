"""TARİXİ semestrlər (legacy 1–13): cutover-in buraxdığı xanaların bərpası — opt-in ``history`` / ``history_topics``.

Sahib (2026-10-25): «Köçürülməmiş heç bir data problem yaratmasın, köhnə datadan nəyisə bərpa olunası bir şey
varsa et.» Audit: tarixi semestrlərdə 147 435 real xana-gün gəlməyib — HAMISI qeydiyyat yoxluğundandır.
Paket: ``legacy_delta_extract --history-semester 1-13`` (``history_extract``), tətbiq: bu modul.

``history`` fazası (yalnız AÇIQ seçiləndə: paketin ``snapshot.phases``-i və ya ``--phase history``)
--------------------------------------------------------------------------------------------------------
1. **Hesablar** (``history_accounts``) — boşluq tələbələri tutuşdurulur; hesabı OLMAYAN (cutover-in e-poçt səbəbli
   100 nəfəri və s.) hazırda oxuyursa delta yolu ilə, keçmiş tələbədirsə ``alumni`` arxivi ilə (giriş bağlı) yaranır.
2. **Qeydiyyat** (``history_plan``) — ``repair_enrollments_select`` qaydaları: mövcud → əkiz → real məzmun →
   dilim (K9 / siyahıdankənar) və ya qrup sübutu (karantin). Bağlı (təhvil verilmiş) jurnala YALNIZ ƏLAVƏ olunur —
   mövcud xana/bal dəyişmir, ona görə ``journal_unlock`` LAZIM DEYİL (``trg_journal_mark_guard`` yalnız UPDATE-dədir).
3. **Xanalar + yekun** — delta-nın ÖZ kodu (``lessons.build_lessons_and_marks``, ``finals.apply_finals`` → J6
   ``write_exam_score`` / ``write_resit_score``) :class:`HistoryView` adapteri ilə: mənbə paketdən, yazı icazəsi
   yalnız bu fazanın hədəf açılışlarına (bağlı olsalar da). Semestr-semestr işlənir (yaddaş). Yalnız BOŞ doldurulur.

``history_topics`` fazası — tarixi dərslərin BOŞ mövzu/otağı (``topics.apply_topics`` eyni qayda ilə) ledger
açılışlarında, bağlı jurnallarda da (metadata — bal deyil; ayrıca bayraq olaraq ayrıca faza).

Audit: delta batch sətri (``legacy_import.delta_batch``) — saylar + yaradılmış yazılış/açılış/hesab id-ləri (geri
qaytarmaq üçün). Ad yalnız ``--names-out``-a.
"""

from __future__ import annotations

from collections import defaultdict

from .extract import parse_id_list
from .history_accounts import HistoryAccounts
from .history_plan import HistoryPlanner, TargetState, ledger_slices, pair_flags

HISTORY_PHASES = ("history", "history_topics")


class HistoryPhaseMismatch(ValueError):
    """Tarixi paket adi delta fazaları ilə işlədilə bilməz (onlar boşluq tələbələri üçün hesab yaradardı)."""


class HistoryView:
    """``DeltaRun``-un tarixi görünüşü: mənbə ``history`` bölməsi, yazı yalnız ``writable`` açılışlara, saylar ``history.``."""

    def __init__(self, run, *, points=(), lesson_dates=(), excuse_windows=(), lesson_topics=(), writable=()):
        self._run = run
        self.bundle = {
            "points": list(points),
            "lesson_dates": list(lesson_dates),
            "excuse_windows": list(excuse_windows),
            "lesson_topics": list(lesson_topics),
        }
        self._writable = set(writable)

    def __getattr__(self, name):
        return getattr(self._run, name)

    def count(self, key: str, amount: int = 1) -> None:
        self._run.count(f"history.{key}", amount)

    def touched(self, kind: str, pk, fields) -> None:
        self.count(f"touched.{kind}")

    def bulk_create(self, model, objects, kind: str) -> None:
        self._run.bulk_create(model, objects, f"history_{kind}")

    def writable_offerings(self, offering_ids) -> set:
        return {pk for pk in offering_ids if pk in self._writable}

    def ledger_enrollments(self, keys) -> dict:
        return {}  # paketdə yalnız ledger-də OLMAYAN cütlər var

    def excuse_index(self):
        from .apply import DeltaRun

        return DeltaRun.excuse_index(self)


def _section(run) -> dict:
    return run.bundle.get("history") or {}


def _activity(run, journals: dict, flags: dict) -> dict:
    """legacy tələbə → «2025/2026 Yaz» kimi dövr adları (siyahı + xana) — E2/E3 sübutu üçün.

    Paket ``activity`` daşıyırsa (extract bütün jurnallardan qurur) o istifadə olunur; yoxsa paketin öz jurnallarından.
    """

    packed = _section(run).get("activity")
    if packed:
        return {int(student): set(labels) for student, labels in packed.items()}
    labels = {row["id"]: str(row.get("name") or "") for row in run.bundle["periods"]}
    activity: dict = defaultdict(set)
    for journal in journals.values():
        label = labels.get(journal["semestr"], "")
        for student in parse_id_list(journal.get("students_id")):
            activity[student].add(label)
    for uniqid, student in flags:
        if uniqid in journals:
            activity[student].add(labels.get(journals[uniqid]["semestr"], ""))
    return activity


def apply_history(run) -> None:
    from .finals import apply_finals
    from .lessons import build_lessons_and_marks
    from .people import _display

    section = _section(run)
    journals = {row["uniqid"]: row for row in section.get("journals") or []}
    points = [row for row in section.get("points") or [] if row["journal_uniqid"] in journals]
    if not points:
        run.count("history.empty_section")
        return
    flags = pair_flags(points)
    run.count("history.pairs", len(flags))
    accounts = HistoryAccounts(run, section, activity=_activity(run, journals, flags))
    users = accounts.resolve_all({student for _uniqid, student in flags})
    slices = ledger_slices(run, journals)
    semesters = sorted({journal["semestr"] for journal in journals.values()})
    period_ids = [period.pk for period in (run.period_of(semestr) for semestr in semesters) if period is not None]
    state = TargetState(run.organization, users.values(), period_ids)
    planner = HistoryPlanner(run, state=state, slices=slices)
    rows = {row["id"]: row for row in run.bundle["students"]}

    # Sıra deterministikdir və təkrar qaçışla EYNİ qərarı verir: əvvəl real məzmunlu cütlər (yazılış aça bilənlər),
    # sonra yalnız «qb» olanlar (onlar yalnız artıq açılmış yazılışa düşə bilər); hər qrupda ledger dilimli jurnallar
    # karantindən əvvəl (karantinin qrup sübutu dilimli bərpanı da görür).
    def order(pair):
        content = flags[pair]["real"] or flags[pair]["final"]
        return (not content, pair[0] not in slices, pair)

    for uniqid, legacy_id in sorted(flags, key=order):
        user_id = users.get(legacy_id)
        if user_id is None:
            planner.skip("student_unresolved")
            continue
        display = _display(rows.get(legacy_id) or {})
        planner.decide(uniqid, legacy_id, user_id, journals[uniqid], flags[(uniqid, legacy_id)], display=display)
    planner.flush()
    enrollments = planner.result
    by_semester: dict = defaultdict(list)
    for row in points:
        if (row["journal_uniqid"], row["student_id"]) in enrollments:
            by_semester[journals[row["journal_uniqid"]]["semestr"]].append(row)
    quarantined_ids = {journal["id"]: journal for uniqid, journal in journals.items() if uniqid not in slices}
    for semestr in sorted(by_semester):
        sem_points = by_semester[semestr]
        sem_pairs = {(row["journal_uniqid"], row["student_id"]) for row in sem_points}
        sem_enrollments = {key: enrollments[key] for key in sem_pairs}
        sem_slices = _view_slices(journals, sem_enrollments)
        offering_ids = {enrollment.offering_id for enrollment in sem_enrollments.values()}
        view = HistoryView(
            run,
            points=sem_points,
            lesson_dates=[
                row
                for row in section.get("lesson_dates") or []
                if row["journal_id"] in quarantined_ids and quarantined_ids[row["journal_id"]]["semestr"] == semestr
            ],
            excuse_windows=section.get("excuse_windows") or [],
            writable=offering_ids,
        )
        build_lessons_and_marks(view, sem_slices, sem_enrollments, until=run.until)
        apply_finals(view, sem_enrollments)


def _view_slices(journals: dict, enrollments: dict) -> dict:
    """Adapter dilimləri: jurnalın YALNIZ bu fazanın hədəf açılışları (dərs/xana yükü minimal qalsın)."""

    from .journals import JournalSlices

    used: dict = defaultdict(dict)
    for (uniqid, _student), enrollment in enrollments.items():
        used[uniqid][enrollment.offering_id] = enrollment.offering
    out = {}
    for uniqid, offerings in used.items():
        entry = JournalSlices(journals[uniqid])
        entry.offerings = [offerings[pk] for pk in sorted(offerings, key=str)]
        entry.writable = set(offerings)
        out[uniqid] = entry
    return out


def apply_history_topics(run) -> None:
    """Tarixi dərslərin BOŞ mövzu/otağı — ``topics.apply_topics`` ledger dilimləri ilə, semestr-semestr."""

    from .journals import JournalSlices
    from .topics import apply_topics

    rows = _section(run).get("lesson_topics") or []
    if not rows:
        run.count("history.topics.empty_section")
        return
    journals = {row["journal_uniqid"]: {"uniqid": row["journal_uniqid"], "groups_id": "[]"} for row in rows}
    slices = {}
    for uniqid, found in ledger_slices(run, journals).items():
        entry = JournalSlices(journals[uniqid])
        entry.offerings = [offering for _ref, _unit, offering in found]
        entry.writable = {offering.pk for offering in entry.offerings}
        slices[uniqid] = entry
    by_semester: dict = defaultdict(list)
    for row in rows:
        by_semester[row.get("semestr")].append(row)
    for semestr in sorted(by_semester, key=lambda value: (value is None, value or 0)):
        sem_rows = by_semester[semestr]
        sem_slices = {
            row["journal_uniqid"]: slices[row["journal_uniqid"]] for row in sem_rows if row["journal_uniqid"] in slices
        }
        apply_topics(HistoryView(run, lesson_topics=sem_rows), sem_slices)


__all__ = ["HISTORY_PHASES", "HistoryPhaseMismatch", "HistoryView", "apply_history", "apply_history_topics"]
