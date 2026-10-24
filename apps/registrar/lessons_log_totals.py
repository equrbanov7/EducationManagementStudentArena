"""Ekran 21 «Keçilmiş dərslər» — dövr üzrə KPI aqreqatı (`range_totals`).

Perf auditi 2026-09-13 F-13: `lessons_log.range_totals` dövrün BÜTÜN dərslərini
(rektorda 35 159 sətir) `values_list` ilə Python-a çəkib `note_state` ilə
təsnif edirdi (141 ms + döngü), xana aqreqatı (509 833 qeyd, 513 ms) isə hər
açılışda təkrarlanırdı — səhifə 1 038 ms. İndi «boş» / «gec» təsnifatı SQL-dədir
(`note_state` ilə EYNİ qayda) və nəticə sorğu-hash açarı ilə 300 s keşlənir.

Ayrıca modul: `lessons_log.py` modul-ölçü qapısında dondurulub (634 sətir) —
yeni kod ora əlavə edilmir; `lessons_log` bu adları geri-uyğunluq üçün
re-export edir (`service.range_totals` çağıranları dəyişmir).

KÖÇÜRMƏ (2026-10-24, sahib: «demək olar hər dərs “Gec yazılıb” görünür»)
-----------------------------------------------------------------------
Köhnə sistemdən köçürülən jurnalın xanası hədəfdə İDXAL ANINDA yaranır
(``LessonMark.created_at`` = köçürmə vaxtı, dərs tarixindən aylar sonra) — yəni
«ilk xana 48 saatdan gec» qaydası köçürülmüş HƏR dərsi «gec» sayırdı. Qayda
yalnız YENİ SİSTEMDƏ yazılmış xanaya tətbiq olunur:

* **Köçürülmüş dərs** (:func:`imported_lesson_q`) — ``Lesson.created_by`` BOŞDUR.
  Üç idxal yazıçısının hamısı (cutover J3 ``journal_lessons``, J12 bərpası
  ``is_legacy_synthesised``, ``legacy_delta_apply``) dərsi ``created_by=None`` ilə
  yazır («import heç kimin adından yazmır»); yeni sistemin YEGANƏ yaratma yolu
  ``gradebook_lessons.create_lesson`` isə hər çağırışda aktoru verir (jurnal
  POST-u, «Aktivləşdir», backfill — ``--actor`` məcburidir). Delta-nın özü də
  eyni ayrımı işlədir (``LessonBook``: müəllimin dərsi = ``created_by`` dolu).
  Belə dərs HEÇ VAXT «gec» deyil (boşdursa yenə «boş»dur).
* **Köçürülmüş xana** — ``entered_by`` BOŞ və rəsmi düzəlişin yaratdığı xana
  DEYİL (:func:`new_system_mark_q` / :func:`lesson_new_system_mark_q`). Delta
  köhnə sistemin xanasını müəllimin yeni sistemdə açdığı dərsə də yaza bilər;
  həmin xana gecikmə hesabına girmir. Rəsmi düzəliş (``JournalCorrection.created_mark``) boş xananı
  ``entered_by``-sız yaradır — o, YENİ sistemin yazısıdır və sayılır.

Hər iki şərt eyni aqreqat sorğunun içindədir (əlavə sorğu yoxdur).
"""

from __future__ import annotations

import datetime as _dt
import hashlib

from django.core.cache import cache
from django.db.models import Count, DateField, Exists, ExpressionWrapper, F, Min, OuterRef, Q, Sum, Value
from django.db.models.functions import TruncDate

from apps.registrar.models import AttendanceStatus, JournalCorrection, LessonMark

#: «Gec yazılıb» həddi — dizayn: «dərsdən 48 saat sonra».
LATE_AFTER_HOURS = 48

#: `range_totals` keşinin müddəti (saniyə) — `analytics_cache` ilə eyni siyasət:
#: hesabat səthidir, bir neçə dəqiqəlik köhnəlmə qəbul olunur.
TOTALS_CACHE_TTL = 300


def imported_lesson_q(prefix: str = "") -> Q:
    """Köhnə sistemdən köçürülmüş dərs — ``created_by`` boşdur (modul sənədi)."""
    return Q(**{f"{prefix}created_by__isnull": True})


def is_imported_lesson(lesson) -> bool:
    """:func:`imported_lesson_q`-nin obyekt forması (səhifə sətirləri üçün)."""
    return getattr(lesson, "created_by_id", None) is None


def new_system_mark_q() -> Q:
    """``LessonMark`` sorğusunun öz sətri üçün: yeni sistemdə yazılmış xana.

    Aktoru var (``entered_by``) VƏ YA onu rəsmi düzəliş yaradıb — düzəliş şərti
    ``Exists``-dir (JOIN yox), ona görə say aqreqatları təkrarlanmır.
    """
    created_by_correction = JournalCorrection.objects.filter(lesson_mark_id=OuterRef("id"), created_mark=True)
    return Q(entered_by__isnull=False) | Q(Exists(created_by_correction))


def lesson_new_system_mark_q() -> Q:
    """:func:`new_system_mark_q`-nin DƏRSDƏN baxan forması (``marks__`` yolu).

    Düzəliş şərti burada LEFT JOIN-dir: bir xananın bir neçə düzəlişi sətri
    təkrarlaya bilər — ``Min`` və «sıfırdırmı» yoxlaması buna həssas deyil.
    Korrelyasiyalı alt-sorğu (dövrdə ~500 k xana) əvəzinə hash join seçilib.
    """
    return Q(marks__entered_by__isnull=False) | Q(marks__corrections__created_mark=True)


def totals_cache_key(lessons_qs) -> str:
    """Dövr KPI-larının keş açarı — sorğunun ÖZÜ (əhatə + tarix aralığı +
    bütün filtrlər parametrlərlə birlikdə) hash-lənir, yəni fərqli əhatəli iki
    aktor heç vaxt eyni açarı paylaşmır (tenant/scope sızması yoxdur)."""
    raw = str(lessons_qs.order_by().values("id").query)
    return "registrar:lessons_log_totals:" + hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def range_totals(lessons_qs) -> dict:
    """Dövr üzrə KPI-lar — İKİ aqreqat sorğu (dərslər + xanalar), 300 s keş.

    Perf auditi 2026-09-13 F-13: əvvəl dövrün BÜTÜN dərsləri (rektorda
    35 159 sətir) `values_list` ilə Python-a çəkilib `note_state` ilə
    təsnif olunurdu (141 ms + döngü), xana aqreqatı (509 833 qeyd, 513 ms)
    isə hər açılışda təkrarlanırdı — səhifə 1 038 ms. İndi «boş» / «gec»
    təsnifatı SQL-dədir (`note_state` ilə EYNİ qayda: ilk xananın YERLİ
    tarixi dərs tarixindən 48 saatdan çox sonradırsa gec) və nəticə
    sorğu-hash açarı ilə keşlənir.
    """
    key = totals_cache_key(lessons_qs)
    cached = cache.get(key)
    if cached is not None:
        return dict(cached)
    totals = _compute_range_totals(lessons_qs)
    cache.set(key, totals, TOTALS_CACHE_TTL)
    return totals


def _compute_range_totals(lessons_qs) -> dict:
    # `note_state`: `(written - lesson_date) > 48 saat`, `written` tam TARİXDİR
    # (`localtime(first_mark).date()`) → fərq ≥ 3 gün ⇔ `written >= date + 3 gün`.
    # `TruncDate` cari saat qurşağında kəsir — `timezone.localtime` ilə eyni.
    # `first_mark` YALNIZ yeni sistemin dərsində yeni sistemin xanasıdır (modul
    # sənədi «KÖÇÜRMƏ»): köçürülmüş dərsdə/xanada NULL qalır → «gec» sayılmır;
    # «boş» isə xana SAYI ilə qərarlaşır (köçürülmüş xana da xanadır).
    late_from = ExpressionWrapper(
        F("date") + Value(_dt.timedelta(hours=LATE_AFTER_HOURS + 24)), output_field=DateField()
    )
    counted = ~imported_lesson_q() & lesson_new_system_mark_q()
    lesson_totals = (
        lessons_qs.order_by()
        .annotate(marks_total=Count("marks__id"), first_mark=Min("marks__created_at", filter=counted))
        .annotate(first_mark_day=TruncDate("first_mark"), late_from=late_from)
        .aggregate(
            lessons=Count("id"),
            hours=Sum("hours"),
            empty=Count("id", filter=Q(marks_total=0)),
            late=Count("id", filter=Q(first_mark__isnull=False, first_mark_day__gte=F("late_from"))),
        )
    )
    total = int(lesson_totals["lessons"] or 0)
    hours = int(lesson_totals["hours"] or 0)
    empty = int(lesson_totals["empty"] or 0)
    late = int(lesson_totals["late"] or 0)

    attendance = LessonMark.objects.filter(lesson__in=lessons_qs.values("id")).aggregate(
        present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
        absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        excused=Count("id", filter=Q(status=AttendanceStatus.EXCUSED)),
        graded=Count("id", filter=Q(score__isnull=False)),
    )
    marked = int(attendance["present"] or 0) + int(attendance["absent"] or 0) + int(attendance["excused"] or 0)
    rate = int(round(int(attendance["present"] or 0) * 100 / marked)) if marked else 0
    return {
        "lessons": total,
        "hours": hours,
        "empty": empty,
        "late": late,
        "present": int(attendance["present"] or 0),
        "absent": int(attendance["absent"] or 0),
        "excused": int(attendance["excused"] or 0),
        "graded": int(attendance["graded"] or 0),
        "attendance_rate": rate,
    }


__all__ = [
    "LATE_AFTER_HOURS",
    "TOTALS_CACHE_TTL",
    "imported_lesson_q",
    "is_imported_lesson",
    "lesson_new_system_mark_q",
    "new_system_mark_q",
    "range_totals",
    "totals_cache_key",
]
