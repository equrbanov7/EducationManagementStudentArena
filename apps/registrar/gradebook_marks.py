"""Jurnal xanası (``LessonMark``) yazısı + qayıb sayğacı — ``gradebook``-un davamı.

``gradebook.py`` modul-ölçü büdcəsinə görə bölünüb (``gradebook_components`` /
``gradebook_lessons`` ilə eyni nümunə). Bütün ictimai adlar ``gradebook``-dan
re-eksport olunur — çağıranlar üçün API dəyişməyib.

TUTUM 2026-10-06 — yazı redaktə olunan xanalara MÜTƏNASİBDİR
──────────────────────────────────────────────────────────
Əvvəl hər grid yazısı (müəllim bir dərs günündə bir neçə xananı dəyişir)
açılışın BÜTÜN dərslərini və BÜTÜN işarələrini yükləyir, xananı xana-xana
yazır (mövcud xanaya 2 sorğu: kimlik SELECT + UPDATE) və hər toxunulmuş
qeydiyyat üçün qayıb saatını ayrıca hesablayırdı (2 sorğu). 25 xanalıq yazı
97 sorğu idi, 40 dərslik kursda 1 140 xana sətri yüklənirdi. İndi:

* oxu HƏDƏFLİDİR — yalnız göndərilən dərslər / qeydiyyatlar / xanalar
  (açılışa aidlik eyni süzgəclə qalır: başqa açılışın id-si heç vaxt tapılmır);
* yazı TOPLUDUR — yeni xanalar bir ``INSERT``, dəyişənlər bir ``UPDATE``;
  dəyişməyən (grid-in geri göndərdiyi) xana yenidən yazılmır;
* qayıb sayğacı TOPLUDUR (:func:`recompute_absence_hours_many`) — yalnız
  toxunulmuş qeydiyyatlar, bir aqreqat + bir ``UPDATE``.

Qaydalar dəyişməyib: kilidli jurnal, açılış ``FOR UPDATE`` kilidi (yarış),
rəsmi düzəlişli xana kilidi, xana pəncərəsi (DB trigger də qoruyur), yeni
işarə yalnız dərs günündə, bal yalnız seminar/lab-da (0..10, səhv dəyər
yazılmır), audit sətri, bildirişlər (``on_commit``), qayıb həddi keçidləri.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.registrar import grade_audit
from apps.registrar.models import AttendanceStatus, Enrollment, Lesson, LessonMark

#: Toplu INSERT/UPDATE partiyası — 555 tələbəli açılışda «hamısını göstər»
#: rejimində bir neçə min xana da bir neçə sorğuda gedir.
_BULK_BATCH = 500
_MARK_UPDATE_FIELDS = ["status", "score", "entered_by", "updated_at"]


def _as_uuid(value):
    """Grid açarı → UUID; yararsız / boş dəyər ``None`` (əvvəlki ``str`` müqayisəsi ilə eyni sərtlik)."""
    if isinstance(value, uuid.UUID):
        return value
    if value is None:
        return None
    text = str(value)
    try:
        parsed = uuid.UUID(text)
    except (TypeError, ValueError, AttributeError):
        return None
    return parsed if str(parsed) == text else None


def _requested_cells(entries) -> dict:
    """``{(lesson_id, enrollment_id): entry}`` — eyni xana iki dəfə gəlsə sonuncusu qalır.

    Əvvəl təkrar xana ikinci ``INSERT``-də ``uniq_lesson_enrollment_mark``-a
    çırpılıb bütün partiyanı 500 ilə çökdürürdü.
    """
    cells: dict = {}
    for entry in entries or []:
        lesson_id = _as_uuid(entry.get("lesson_id"))
        enrollment_id = _as_uuid(entry.get("enrollment_id"))
        if lesson_id is None or enrollment_id is None:
            continue
        cells[(lesson_id, enrollment_id)] = entry
    return cells


def _load_targets(offering, cells):
    """Yalnız göndərilən xanaların dərsləri / qeydiyyatları / mövcud işarələri (3 hədəfli sorğu)."""
    lesson_ids = {key[0] for key in cells}
    enrollment_ids = {key[1] for key in cells}
    # Açılışa aidlik eyni süzgəcdədir — başqa açılışın / təşkilatın id-si tapılmır.
    lessons = {lesson.id: lesson for lesson in Lesson.objects.filter(offering=offering, id__in=lesson_ids)}
    enrollments = {
        enrollment.id: enrollment
        for enrollment in Enrollment.objects.filter(
            offering=offering, status=Enrollment.Status.ENROLLED, id__in=enrollment_ids
        ).select_related("student")
    }
    existing = {}
    if lessons and enrollments:
        existing = {
            (mark.lesson_id, mark.enrollment_id): mark
            for mark in LessonMark.objects.filter(lesson_id__in=list(lessons), enrollment_id__in=list(enrollments))
        }
    return lessons, enrollments, existing


def _corrected_mark_ids(existing) -> set:
    """Rəsmi (sənədli) düzəliş almış xanalar — müəllim DƏYİŞƏ BİLMƏZ (yalnız yeni rəsmi düzəliş)."""
    if not existing:
        return set()
    from .models import JournalCorrection

    return set(
        JournalCorrection.objects.filter(
            lesson_mark_id__in=[mark.pk for mark in existing.values()], reversal__isnull=True
        ).values_list("lesson_mark_id", flat=True)
    )


@transaction.atomic
def save_marks(*, offering, entries, by_user=None, enforce_day=True, report=False, request=None):
    """Persist attendance/score cells for an offering (bulk, from the grid).

    ``entries``: iterable of ``{"lesson_id", "enrollment_id", "status", "score"}``.
    Each cell is validated against the offering's own lessons/enrollments
    (cross-offering/tenant injection rejected), honours the per-mark edit window
    (locked cells are skipped) and the lesson type (lecture cells never store a
    score). Blocked entirely when the journal is locked. Returns cells written.
    ``enforce_day=False`` YALNIZ seed/test üçündür — HTTP qatı heç vaxt ötürmür.
    ``report=True`` → ``{"written", "rejected"}`` (yazılmayan xanaların sayı ilə;
    çağıran istifadəçiyə xəbərdarlıq göstərir — bax P3-10).
    """
    from apps.registrar import gradebook
    from apps.registrar import journal_notifications as jn
    from apps.registrar.gradebook_lessons import parse_lesson_score

    if gradebook.journal_is_locked(offering):
        return {"written": 0, "rejected": 0} if report else 0

    # Codex audit §14 (2026-09-13): «oxu → yaz» naxışı. Açılış sətri `FOR UPDATE`
    # ilə kilidlənir — eyni açılışın yazıları tranzaksiya səviyyəsində ardıcıllaşır
    # (kilid sırası: açılış → qeydiyyat → xana; bax `correction_target_locks`).
    type(offering).objects.select_for_update().filter(pk=offering.pk).exists()

    cells = _requested_cells(entries)
    lessons, enrollments, existing = _load_targets(offering, cells) if cells else ({}, {}, {})
    corrected_ids = _corrected_mark_ids(existing)

    written = 0
    rejected = 0
    touched: dict = {}
    prior_hours: dict = {}  # bildiriş keçidləri üçün yazıdan ƏVVƏLKİ qayıb saatları
    audit_changes = []
    notify_events = []
    to_create = []
    to_update = []
    now = timezone.now()
    today = timezone.localdate()
    by_user_id = getattr(by_user, "pk", None)
    for (lesson_id, enrollment_id), entry in cells.items():
        lesson = lessons.get(lesson_id)
        enrollment = enrollments.get(enrollment_id)
        if lesson is None or enrollment is None:
            continue
        mark = existing.get((lesson.id, enrollment.id))
        if mark is not None and mark.pk in corrected_ids:
            continue  # rəsmi düzəlişli xana — müəllim üçün kilidli
        if not gradebook.can_edit_mark(mark, now=now):
            continue  # locked — no back-dated tampering
        if enforce_day and mark is None and lesson.date != today:
            continue  # YENİ işarə yalnız dərsin öz günündə yazılır

        status = entry.get("status")
        if status not in (AttendanceStatus.PRESENT, AttendanceStatus.ABSENT):
            status = AttendanceStatus.PRESENT
        score = None
        if (
            status != AttendanceStatus.ABSENT
            and gradebook.lesson_allows_score(lesson)
            and entry.get("score") not in (None, "")
        ):
            # Seminar/lab balı: tam ədəd, 0..10. Qayıb tələbəyə bal yazılmır —
            # «q/b + 8 bal» xanası mümkün idi (QA 2026-09-05 JOURNAL-TEACHER-09).
            score = parse_lesson_score(entry.get("score"))
            if score is None:
                # Səhv dəyər SƏSSİZ 0-a çevrilmir — xana toxunulmadan qalır (P3-10).
                rejected += 1
                continue

        old_status = mark.status if mark is not None else None
        old_score = mark.score if mark is not None else None
        old = grade_audit.mark_repr(old_status, old_score) if mark is not None else None
        new = grade_audit.mark_repr(status, score)
        if mark is None:
            to_create.append(
                LessonMark(
                    organization_id=offering.organization_id,
                    lesson=lesson,
                    enrollment=enrollment,
                    status=status,
                    score=score,
                    entered_by=by_user,
                )
            )
        elif mark.status != status or mark.score != score or mark.entered_by_id != by_user_id:
            # Dəyişməyən xana (grid hər yazıla bilən xananı geri göndərir) yenidən yazılmır.
            mark.status = status
            mark.score = score
            mark.entered_by = by_user
            mark.updated_at = now  # bulk_update `auto_now`-u özü yeniləmir
            to_update.append(mark)
        if old != new:
            audit_changes.append(
                {
                    "student": grade_audit.student_label(enrollment),
                    "item": f"{lesson.date} · {lesson.get_kind_display()}",
                    "old": old or "—",
                    "new": new,
                }
            )
            # Tələbə bildirişləri: q/b qeydi və yeni/dəyişmiş bal.
            if status == AttendanceStatus.ABSENT and old_status != AttendanceStatus.ABSENT:
                notify_events.append({"enrollment": enrollment, "kind": jn.EVENT_ABSENT})
            if score is not None and score != old_score:
                notify_events.append({"enrollment": enrollment, "kind": jn.EVENT_SCORE, "score": score})
        if enrollment.id not in touched:
            touched[enrollment.id] = enrollment
            prior_hours[enrollment.id] = enrollment.absence_hours
        written += 1

    if to_create:
        LessonMark.objects.bulk_create(to_create, batch_size=_BULK_BATCH)
    if to_update:
        LessonMark.objects.bulk_update(to_update, _MARK_UPDATE_FIELDS, batch_size=_BULK_BATCH)

    # Keep the denormalised Enrollment.absence_hours (used by the "Fənlərim"
    # exam-eligibility badge) in sync with the journal — the single source of truth.
    new_hours = recompute_absence_hours_many(touched.values())
    allowed = None  # açılış həddi YALNIZ sayğac artanda lazımdır (1–2 sorğu)
    for enrollment in touched.values():
        prev = Decimal(prior_hours.get(enrollment.id, 0))
        cur = Decimal(new_hours[enrollment.id])
        if cur <= prev:
            continue
        if allowed is None:
            # Məxrəc açılışın BÜTÜN dərsləridir — `lesson_hours` boşdursa tək SUM aqreqatı.
            allowed = gradebook._allowed_absence_hours(offering, None)
        if allowed <= 0:
            break
        warn_at = allowed * gradebook._WARN_RATIO
        if prev <= allowed < cur:
            notify_events.append({"enrollment": enrollment, "kind": jn.EVENT_BARRED})
        elif prev < warn_at <= cur <= allowed:
            notify_events.append(
                {"enrollment": enrollment, "kind": jn.EVENT_LIMIT_WARNING, "hours": new_hours[enrollment.id]}
            )

    # `request` → audit sətrinə «kim impersonasiya edib» möhürü (sahib qərarı).
    grade_audit.log_grade_changes(
        offering=offering, by_user=by_user, kind="mark", changes=audit_changes, request=request
    )

    if notify_events:
        transaction.on_commit(lambda: jn.send_journal_events(offering=offering, events=notify_events))
    return {"written": written, "rejected": rejected} if report else written


def recompute_absence_hours_many(enrollments) -> dict:
    """``{enrollment_id: saat}`` — bir neçə qeydiyyatın qayıb saatı TOPLU (sətir sayından asılı deyil).

    Sorğular: 1 aqreqat (öz q/b xanaları) + yalnız «alt qrupdan əlavə» sətir varsa
    birləşmə köçürməsi (:func:`guest_merge.carry_over_map`, 2 toplu) + dəyişən
    sayğaclar üçün 1 toplu ``UPDATE``. Qayda :func:`recompute_absence_hours` ilə
    birə-birdir (o, bunu tək sətirlə çağırır).
    """
    from apps.registrar import guest_merge

    enrollments = [enrollment for enrollment in enrollments if enrollment is not None]
    if not enrollments:
        return {}
    own = dict(
        LessonMark.objects.filter(
            enrollment_id__in=[enrollment.pk for enrollment in enrollments], status=AttendanceStatus.ABSENT
        )
        .values("enrollment_id")
        .annotate(total=Sum("lesson__hours"))
        .values_list("enrollment_id", "total")
    )
    # ALT QRUP BİRLƏŞMƏSİ: əvvəlki jurnalda yığılmış qayıb saatı ÜSTƏGƏL (adi sətirlərdə sorğu yoxdur).
    guest_ids = [enrollment.pk for enrollment in enrollments if getattr(enrollment, "source_group_id", None)]
    carried = guest_merge.carry_over_map(guest_ids, with_entry_score=False) if guest_ids else {}

    result: dict = {}
    changed = []
    for enrollment in enrollments:
        summary = carried.get(enrollment.pk)
        hours = int(own.get(enrollment.pk) or 0) + (int(summary["absence_hours"]) if summary else 0)
        result[enrollment.pk] = hours
        if enrollment.absence_hours != hours:
            enrollment.absence_hours = hours
            changed.append(enrollment)
    if changed:
        Enrollment.objects.bulk_update(changed, ["absence_hours"], batch_size=_BULK_BATCH)
    return result


def recompute_absence_hours(*, enrollment):
    """Recompute Enrollment.absence_hours from the student's lesson marks (qb).

    ALT QRUP BİRLƏŞMƏSİ: tələbə öz jurnalından azad edilib bura köçürülübsə,
    əvvəlki jurnalda yığdığı qayıb saatı da ÜSTƏGƏLdir — 25% buraxılış həddi
    dərsə yox, FƏNNƏ + SEMESTRƏ aiddir, birləşmə onu sıfırlamamalıdır
    (bax :mod:`apps.registrar.guest_merge`). Adi sətirlərdə ƏLAVƏ SORĞU OLMUR.
    """
    return recompute_absence_hours_many([enrollment])[enrollment.pk]
