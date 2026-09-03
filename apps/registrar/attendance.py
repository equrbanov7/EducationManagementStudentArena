"""Davamiyyət balı (attendance score /10) — rəsmi "DAVAMİYYƏT BALININ HESABLANMASI"
cədvəlinin kanonik hesablaması.

Rəsmi cədvəl 2-ölçülü lookup kimi çap olunub (sətir = fənnin auditoriya saatı:
10, 15, 20, 25, 30, 45, 60, 75, 90, 105, 120, 135 saat; sütun = q/b sayı 0..16;
xana = 10-luq davamiyyət balı, onluqlu — məs. 2 q/b → 8.65). Amma cədvəlin altında
sadə, xətti və dəqiq qayda dayanır (30-a yaxın xana üzərində yoxlanılıb):

    * bir q/b = 2 akademik saat (standart cüt-saat dərsi; ``gradebook.DEFAULT_LESSON_HOURS``)
    * buraxılmış_saat = 2 × q/b
    * davamiyyət balı = 10 × (1 − buraxılmış_saat / dərs_saatı)
      2 onluğa AŞAĞI yuvarlanır (floor/truncate) — məs. 9.6667 → 9.66, 9.5556 → 9.55.

Tələbə auditoriya saatlarının 25%-**dən çoxunu** (strict ``>``) buraxdıqda fəndən
imtahana BURAXILMIR (cədvəldə qırmızı xanalar) — bu, mövcud
:func:`apps.registrar.services.get_exam_eligibility` barring qaydası ilə eynidir
(120 saat / 15 q/b = tam 25% = 7.50, hələ buraxılır; 16 q/b → buraxılmır).

Real sistem əsl buraxılmış saatı saxlayır (``Enrollment.absence_hours`` —
``Lesson.hours`` cəmi, üzrlü qayıblar çıxılır), ona görə bu funksiya **saat**
əsaslıdır: standart 2-saatlıq dərslər üçün cədvəli eynən yaradır, qeyri-standart
dərs saatları (məs. 1 və ya 4 saatlıq laboratoriya) üçün isə düzgün ümumiləşdirir.

QEYD (cədvəldəki qeyd): Gənclər və İdman Nazirliyinin Kollegiyası tərəfindən
təsdiq edilmiş milli yığma komandaların üzvü olan idmançı-tələbələr üçün 25%
istisnası var. Bu, üzrlü qayıbdan FƏRQLİ mexanizmdir: üzrlü qayıb saatı
``absence_hours``-a heç vaxt daxil olmur (yəni HƏM balı, HƏM həddi dəyişir),
istisna isə saatları olduğu kimi saxlayıb yalnız BURAXILIŞ qərarını ləğv edir —
tələbənin davamiyyət balı yenə də real qayıba görə aşağı düşür.  Ona görə
:func:`attendance_score` ``exempt=`` açarını qəbul edir; mənbəyi
``StudentAcademicRecord.national_athlete_exemption`` sahəsidir və o sahə
köçürmə ilə AVTOMATİK DOLDURULMUR (bax aşağıdakı «TARİXİ DATA» qeydi).

⚠️ TARİXİ DATA (sahib qərarı, 2026-08-31).  Bu düstur **gələcək semestrlər**
üçün kanonikdir.  Köçürülmüş tarixi semestrlərdə köhnə sistemin yazdığı
davamiyyət balı və buraxılış statusu **olduğu kimi qalır** — bu modul tarixi
data üzərində yalnız YOXLAMA (köçürmənin sadiqliyini ölçmək) üçün işlədilir,
dəyər yazmaq üçün YOX.  Tarixi yazılışlara geriyə dönük blok qoyan miqrasiya,
skript və ya komanda yazılmır.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

# Cədvəldəki hər q/b bir cüt-saat (2 akademik saat) dərsə bərabərdir.
HOURS_PER_ABSENCE = 2
# Standart buraxılış həddi — auditoriya saatlarının 25%-i (proqramdan konfiqurasiya
# olunur; bax ``Program.absence_limit_percent`` / ``gradebook.absence_limit_percent_for``).
DEFAULT_ABSENCE_LIMIT_PERCENT = 25
MAX_SCORE = Decimal("10")
_TWO_PLACES = Decimal("0.01")


def _as_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def attendance_score(lesson_hours, absence_hours, *, limit_percent=DEFAULT_ABSENCE_LIMIT_PERCENT, exempt=False):
    """Davamiyyət balını (10-luq) rəsmi cədvələ görə hesablayır.

    :param lesson_hours: fənnin ümumi auditoriya saatı (``CourseOffering.lesson_hours``).
    :param absence_hours: buraxılmış (üzrsüz) saat (``Enrollment.absence_hours``).
    :param limit_percent: buraxılış həddi faizlə (default 25).
    :param exempt: rəsmi idmançı-tələbə istisnası (milli yığma).  ``True`` olduqda
        25% həddi BURAXILIŞ qərarını ləğv etmir — bal yenə real qayıba görə
        hesablanır, sadəcə ``barred`` heç vaxt ``True`` olmur.  Default ``False``:
        heç bir mövcud çağırış bu davranışı görmür.
    :returns: ``(score, barred)`` — ``score`` :class:`~decimal.Decimal` (0..10, 2 onluğa
        aşağı yuvarlanmış) tələbə imtahana buraxılırsa; buraxılmırsa ``score`` ``None``
        və ``barred`` ``True``. Dərs saatı 0/naməlum olduqda tam 10.00 (barred deyil).
    """
    hours = _as_decimal(lesson_hours)
    absent = _as_decimal(absence_hours)
    if hours <= 0:
        # Dərs saatı hələ təyin olunmayıb — cəza yoxdur, tam bal.
        return (MAX_SCORE.quantize(_TWO_PLACES), False)

    allowed = hours * _as_decimal(limit_percent) / Decimal(100)
    if absent > allowed and not exempt:
        # 25% həddi keçilib → imtahana buraxılmır (cədvəldə qırmızı xana).
        return (None, True)

    ratio = (hours - absent) / hours
    score = (MAX_SCORE * ratio).quantize(_TWO_PLACES, rounding=ROUND_DOWN)
    if score < 0:
        score = Decimal("0.00")
    return (score, False)


def attendance_score_from_count(
    lesson_hours, absence_count, *, limit_percent=DEFAULT_ABSENCE_LIMIT_PERCENT, exempt=False
):
    """Cədvəlin sütunu (q/b **sayı**) əsaslı rahatlıq üçün — hər q/b = 2 saat sayır.

    Yalnız əsl buraxılmış saat əlçatan olmayanda istifadə edin; mümkünsə həmişə
    :func:`attendance_score` (real ``absence_hours``) üstündür."""
    absent_hours = _as_decimal(absence_count) * HOURS_PER_ABSENCE
    return attendance_score(lesson_hours, absent_hours, limit_percent=limit_percent, exempt=exempt)
