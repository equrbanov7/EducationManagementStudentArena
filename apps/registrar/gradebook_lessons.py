"""Dərs (Lesson) CRUD — gradebook-un davamı.

``gradebook.py`` modul-ölçü büdcəsinə görə bölünüb (``gradebook_components.py``
ilə eyni nümunə): dərs sütununun yaradılması / redaktəsi / silinməsi buradadır.
Bütün ictimai adlar ``gradebook``-dan re-eksport olunur — çağıranlar üçün API
dəyişməyib.

Otaq (``room``) sahəsi opsionaldır: köhnə dərslərdə yoxdur, boş qala bilər.
Redaktədə ``None`` MƏNALI dəyərdir ("otağı təmizlə"), ona görə "verilməyib"
halı ``UNSET`` sentineli ilə ayrılır.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar import grade_audit
from apps.registrar.models import CourseOffering, Lesson, LessonKind, LessonMark

from .gradebook import (  # noqa: F401
    DEFAULT_LESSON_HOURS,
    LESSON_SCORE_MAX,
    UNSET,
    LessonRuleError,
    can_edit_lesson,
    ensure_assessment_scheme,
    journal_is_locked,
    recompute_absence_hours,
)

_CTX = "registrar.journal_lessons"

# ── Lesson (dərs) CRUD ───────────────────────────────────────────────────────


def _coerce_date(value):
    import datetime

    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


#: `Lesson.topic` CharField(255) — ORM uzunluğu yoxlamır, uzun mövzu DB `DataError`
#: (500) verirdi (QA 2026-09-05 JOURNAL-TEACHER-01). Həm yaratma, həm yeniləmə yolu
#: buradan keçir.
MAX_TOPIC_LENGTH = Lesson._meta.get_field("topic").max_length or 255


def parse_lesson_score(raw):
    """Xana balı — düzgün deyilsə ``None`` (SƏSSİZ 0 YAZILMIR).

    QA 2026-09-05 (P3-10): `'abc'` → 0, `-3` → 0, `11` → 10, `7.5` → 7.50 kimi
    səssiz çevrilirdi; yazı səhvi tələbəyə SIFIR bal yazırdı. Bal tam ədəddir
    (bax akademik qayda: bütöv qiymətlər) və 0..``LESSON_SCORE_MAX`` aralığındadır;
    kənar dəyər YAZILMIR — çağıran tərəf istifadəçiyə xəbər verir.
    """
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, TypeError, ValueError, AttributeError):
        return None
    if value != value.to_integral_value():
        return None
    if value < 0 or value > LESSON_SCORE_MAX:
        return None
    return value.to_integral_value()


def clean_topic(topic) -> str:
    text = topic.strip() if isinstance(topic, str) else ""
    if len(text) > MAX_TOPIC_LENGTH:
        raise LessonRuleError(f"Dərs mövzusu ən çox {MAX_TOPIC_LENGTH} simvol ola bilər ({len(text)} göndərildi).")
    return text


#: Dövr bitibsə üst hədd: bu gündən bir tədris ili irəli (sağlamlıq qapısı).
MAX_FUTURE_LESSON_DAYS = 365


def ensure_date_within_period(offering, parsed) -> None:
    """Dərs tarixinin ÜST həddi (QA 2026-09-05 P2-11).

    Əvvəl yalnız keçmiş tarix yoxlanılırdı — 2099-cu ilə dərs açmaq mümkün idi
    və başlıqdakı «keçirilmiş saat» hesabı pozulurdu.

    * Dövr HƏLƏ BİTMƏYİBSƏ üst hədd dövrün ``end_date``-idir.
    * Dövr artıq bitibsə (köhnə jurnala sonradan qeyd aparmaq normal axındır —
      semestr kilidləri onsuz da ayrıca işləyir) hədd bu gündən bir il irəlidir.

    RİM/superuser override-i (``allow_past``) bu qapını da keçir.
    """
    # `end_date` obyektdə hələ sətir ola bilər (yeni yaradılmış, refresh olunmamış dövr).
    end_date = _coerce_date(getattr(getattr(offering, "period", None), "end_date", None))
    today = timezone.localdate()
    if end_date and end_date >= today:
        if parsed > end_date:
            raise LessonRuleError(f"Dərs tarixi dövrün sonundan ({end_date:%d.%m.%Y}) sonra ola bilməz.")
        return
    if parsed > today + timedelta(days=MAX_FUTURE_LESSON_DAYS):
        raise LessonRuleError("Dərs tarixi bir ildən artıq irəlidə ola bilməz.")


@transaction.atomic
def create_lesson(
    *,
    offering,
    date,
    kind=LessonKind.LECTURE,
    topic="",
    hours=None,
    start_time=None,
    end_time=None,
    created_by=None,
    instructor=None,
    room=None,
    allow_past=False,
    slot=None,
    off_schedule_reason="",
):
    """Add a held session. ``instructor`` bu dərsin müəllimi (boşdursa açılışınkı);
    ``room`` dərsin otağı (opsional — köhnə dərslərdə yoxdur);
    ``allow_past`` İKT rəhbəri/seed üçün keçmiş tarixi keçir.

    ``slot`` — cədvəldən «Aktivləşdir» yolu (UNEC P1-1, bax ``journal_activation``): saat və
    növ HƏMİŞƏ slotdan, otaq / müəllim / akademik saat açıq verilməyibsə slotdan köçürülür;
    slot bu açılışın olmalı və həmin TARİXDƏ keçirilməlidir. Qalan bütün qaydalar (kilid,
    sillabus qapısı, keçmiş tarix, dövr sərhədi, dublikat) dəyişmədən tətbiq olunur.
    ``off_schedule_reason`` — cədvəldən kənar dərsin səbəbi; yazılırsa audit izinə də düşür."""
    if journal_is_locked(offering):
        raise LessonRuleError("Jurnal kilidlidir — dərs əlavə etmək olmaz.")
    # README §8/2 — «jurnal təsdiqlənmiş sillabus olmadan bloklanır».  Qayda
    # ORG SİYASƏTİDİR və default SÖNDÜRÜLÜDÜR (köçürülmüş data qorunur);
    # açıq olduqda `SyllabusGateError` (səbəb kodu ilə) atılır.
    from apps.registrar import journal_policy

    journal_policy.ensure_lesson_allowed(offering)
    parsed = _coerce_date(date)
    if parsed is None:
        raise LessonRuleError("Dərs tarixi düzgün deyil.")
    if not allow_past and parsed < timezone.localdate():
        raise LessonRuleError("Keçmiş tarixə dərs əlavə etmək olmaz.")
    if not allow_past:
        ensure_date_within_period(offering, parsed)
    if slot is not None:
        from apps.registrar import journal_activation

        fields = journal_activation.slot_lesson_fields(
            offering, slot, parsed, last_instructor={} if instructor is not None else None
        )
        kind, start_time, end_time = fields["kind"], fields["start_time"], fields["end_time"]
        room = room if room is not None else fields["room"]
        instructor = instructor or fields["instructor"]
        hours = hours or fields["hours"]
    new_hours = hours or DEFAULT_LESSON_HOURS
    # L-3 (2026-09-25): «yoxla → yarat» yarışı — iki redaktor (müəllim + İKT) eyni slotu eyni anda
    # aktivləşdirəndə dublikat sütun yaranırdı. Açılış sətri kilidlənir: EYNİ açılışa dərs yaratma
    # seriyalaşır, dublikat yoxlaması kilid altında gedir (başqa açılışlar gözləmir).
    CourseOffering.objects.select_for_update().filter(pk=offering.pk).values_list("pk", flat=True).first()
    if start_time and Lesson.objects.filter(offering=offering, date=parsed, start_time=start_time).exists():
        raise LessonRuleError("Eyni gündə eyni dərs saatına artıq dərs var — üst-üstə düşür.")
    ensure_assessment_scheme(offering=offering)
    lesson = Lesson.objects.create(
        organization=offering.organization,
        offering=offering,
        date=parsed,
        kind=kind,
        topic=clean_topic(topic),
        hours=new_hours,
        start_time=start_time,
        end_time=end_time,
        created_by=created_by,
        instructor=instructor or offering.instructor,
        room=room,
        off_schedule_reason=(off_schedule_reason or "").strip()[:255],
    )
    if lesson.off_schedule_reason:
        # «Dəyişiklik tarixçəsi» panelində və audit hesabatlarında görünsün (kim, nə vaxt, niyə).
        grade_audit.log_grade_changes(
            offering=offering,
            by_user=created_by,
            kind="mark",
            changes=[
                {
                    "student": "—",
                    "item": f"{lesson.date} · {lesson.get_kind_display()}",
                    "old": "—",
                    "new": f"cədvəldən kənar dərs açıldı — {lesson.off_schedule_reason}",
                }
            ],
        )
    return lesson


@transaction.atomic
def update_lesson(
    *,
    lesson,
    date=None,
    kind=None,
    topic=None,
    hours=None,
    start_time=None,
    end_time=None,
    instructor=None,
    room=UNSET,
    allow_past=False,
    allow_locked=False,
    by_user=None,
    audit=True,
) -> bool:
    """Səhv açılmış dərsi düzəlt (2 saat içində). ``allow_locked``/``allow_past``
    pəncərəni + keçmiş-tarixi keçir (İKT/superuser); yayımlanmış jurnal yenə kilidli.

    Audit 2026-09-28 J-02: ``create_lesson`` ilə EYNİ qaydalar — saat 1..``MAX_SLOT_HOURS``
    və fənnin saat həddi (``hours_cap_error``), eyni gün + eyni başlanğıc saatında ikinci
    dərs yoxdur (açılış sətri kilidi altında); tarix/saat/növ dəyişikliyi qiymət audit
    izinə yazılır (``by_user``; öz auditini yazan sənədli düzəliş yolları ``audit=False``
    ötürür). Əvvəl ``hours=0`` qayıb saatını silir, dublikat slot
    yaranır və heç bir iz qalmırdı."""
    if journal_is_locked(lesson.offering) or (not can_edit_lesson(lesson) and not allow_locked):
        return False
    offering = lesson.offering
    # «yoxla → yaz» yarışı: create_lesson ilə eyni kilid (açılış sətri) — dublikat yoxlaması seriyalaşır.
    CourseOffering.objects.select_for_update().filter(pk=offering.pk).values_list("pk", flat=True).first()
    before = {"date": lesson.date, "hours": lesson.hours, "kind": lesson.kind}
    fields = []
    if date is not None:
        parsed = _coerce_date(date)
        if parsed is None:
            raise LessonRuleError("Dərs tarixi düzgün deyil.")
        if parsed < timezone.localdate() and not allow_past:
            raise LessonRuleError("Dərs tarixi bu gündən əvvəl ola bilməz.")
        if not allow_past:
            ensure_date_within_period(lesson.offering, parsed)
        lesson.date = parsed
        fields.append("date")
    if kind is not None and kind in dict(LessonKind.choices):
        lesson.kind = kind
        fields.append("kind")
    if topic is not None:
        lesson.topic = clean_topic(topic)
        fields.append("topic")
    if hours is not None:
        lesson.hours = _validated_hours(offering, lesson, hours)
        fields.append("hours")
    if start_time is not None:
        lesson.start_time = start_time or None
        fields.append("start_time")
    if end_time is not None:
        lesson.end_time = end_time or None
        fields.append("end_time")
    if instructor is not None:
        lesson.instructor = instructor
        fields.append("instructor")
    # Otaq TƏMİZLƏNƏ də bilər (None = "otaq seçilməyib"), ona görə "verilməyib"
    # halı ayrıca sentinel ilə fərqləndirilir — None-u "dəyişmə" saymırıq.
    if room is not UNSET:
        lesson.room = room
        fields.append("room")
    if lesson.start_time and ({"date", "start_time"} & set(fields)):
        clash = Lesson.objects.filter(offering=offering, date=lesson.date, start_time=lesson.start_time)
        if clash.exclude(pk=lesson.pk).exists():
            raise LessonRuleError("Eyni gündə eyni dərs saatına artıq dərs var — üst-üstə düşür.")
    if fields:
        lesson.save(update_fields=fields)
        if "hours" in fields and before["hours"] != lesson.hours:
            # Saat dəyişibsə qayıb saatı (25 % buraxılış həddi) bu dərsin işarələri üzrə yenidən hesablanır.
            for mark in LessonMark.objects.filter(lesson=lesson).select_related("enrollment"):
                recompute_absence_hours(enrollment=mark.enrollment)
        if audit:
            _audit_lesson_update(offering, lesson, before, by_user)
    return True


def _validated_hours(offering, lesson, hours) -> int:
    """J-02: dərs saatı 1..``MAX_SLOT_HOURS`` tam ədəddir və fənnin saat həddini keçmir."""
    from apps.registrar.journal_activation import MAX_SLOT_HOURS, hours_cap_error

    try:
        value = int(hours)
    except (TypeError, ValueError):
        raise LessonRuleError(pgettext(_CTX, "Dərs saatı müsbət tam ədəd olmalıdır."))
    if value == lesson.hours:
        return value  # dəyişməyib (köhnə dərsin saatı tavandan böyük olsa belə toxunulmur)
    if value < 1 or value > MAX_SLOT_HOURS:
        raise LessonRuleError(pgettext(_CTX, "Dərs saatı 1 ilə %(max)s arasında olmalıdır.") % {"max": MAX_SLOT_HOURS})
    extra = value - int(lesson.hours or 0)
    if extra > 0:
        error = hours_cap_error(offering, extra)
        if error:
            raise LessonRuleError(error)
    return value


def _audit_lesson_update(offering, lesson, before, by_user):
    """J-02: tarix / saat / növ dəyişikliyi «Dəyişiklik tarixçəsi»nə düşür (qayıb həddinə təsir edir)."""
    labels = dict(LessonKind.choices)
    after = {"date": lesson.date, "hours": lesson.hours, "kind": lesson.kind}
    item = f"{lesson.date} · {lesson.get_kind_display()}"
    changes = []
    for field, label in (("date", "tarix"), ("hours", "saat"), ("kind", "növ")):
        old, new = before[field], after[field]
        if old == new:
            continue
        if field == "kind":
            old, new = labels.get(old, old), labels.get(new, new)
        changes.append({"student": "—", "item": f"{item} · dərs {label}", "old": str(old), "new": str(new)})
    if changes:
        grade_audit.log_grade_changes(offering=offering, by_user=by_user, kind="mark", changes=changes)


@transaction.atomic
def delete_lesson(*, lesson, by_user=None, allow_locked=False) -> bool:
    """Səhv açılmış dərsi sil (2 saat içində; ``allow_locked`` İKT/superuser üçün keçir).
    İşarələr kaskadla silinir; əməliyyat audit tarixçəsinə düşür."""
    if journal_is_locked(lesson.offering) or (not can_edit_lesson(lesson) and not allow_locked):
        return False
    offering = lesson.offering
    label = f"{lesson.date} · {lesson.get_kind_display()}"
    touched = [m.enrollment for m in LessonMark.objects.filter(lesson=lesson).select_related("enrollment")]
    lesson.delete()
    for enrollment in touched:
        recompute_absence_hours(enrollment=enrollment)
    grade_audit.log_grade_changes(
        offering=offering,
        by_user=by_user,
        kind="mark",
        changes=[{"student": "—", "item": label, "old": "dərs sütunu", "new": "silindi"}],
    )
    return True


# Köhnə ad — mövcud çağırışlar üçün (yalnız tarix dəyişən variant).
def update_lesson_date(*, lesson, date) -> bool:
    try:
        return update_lesson(lesson=lesson, date=date)
    except LessonRuleError:
        return False
