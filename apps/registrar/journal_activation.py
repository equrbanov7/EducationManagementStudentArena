"""«Dərsi aktivləşdir» — cədvəl slotundan BİR kliklə dərs sütunu (UNEC müqayisəsi P1-1, 2026-09-25).

UNEC-də dərs sütunları cədvəldən gəlir, müəllim dərs saatında «Aktivləşdir» basır.
Bizdə «+ Yeni dərs» modalı 5–6 sahə istəyirdi (tarix, növ, saat, otaq, mövzu…).
Bu modul:

* :func:`strip_context` — jurnalın «Qiymətləndirmə» tabının üstündəki «Bu günün
  cədvəl dərsləri» zolağı: açılışın BU GÜNKÜ slotları (həftə günü + üst/alt paritet +
  dövr sərhədi — ``dashboard_data.lessons_on`` ilə EYNİ qayda; parklanmış və silinmiş
  slotlar xaric), saat · növ · otaq · müəllim və sillabusdakı NÖVBƏTİ keçilməmiş mövzu.
  Artıq açılmış slot «Aktivləşdirilib ✓» + sütuna keçid göstərir. Müəllim (2026-09-25):
  slotun ÖZ müəllimi (``ScheduleSlot.instructor``) → bu növün son müəllimi → jurnal sahibi
  (:func:`slot_teacher`); aktivləşdirmə dərsə məhz onu yazır.
* :func:`activate_slot` (POST) — dərsi ``gradebook_lessons.create_lesson(slot=…)`` ilə
  yaradır; MÖVCUD qaydaların hamısı qüvvədədir: tarix = bu gün, fənnin saat həddi,
  sillabus qapısı, dublikat (eyni gün + eyni saat), jurnal kilidi / yekunlaşma.
* :func:`check_manual_lesson` — «+ Yeni dərs» modalının ORTAQ qaydası: saat həddi +
  cədvəli OLAN açılışda heç bir slota uyğun gəlməyən dərs üçün SƏBƏB məcburidir
  (``Lesson.off_schedule_reason``; «Keçilmiş dərslər»də «cədvəldən kənar» işarəsi).
  Cədvəli ümumiyyətlə olmayan açılışda heç nə dəyişmir (müqayisə ediləcək cədvəl yoxdur).

BAYRAQ (sahib 2026-10-10): «Aktivləşdir» RİM «Sistem tənzimləmələri»ndən açılıb-söndürülür
(``core.academic_rules.lesson_activation_enabled``, defolt SÖNDÜRÜLÜ). Söndürülüdə POST 404-dür və
zolaq jurnalda GÖSTƏRİLMİR (sahib 2026-10-14); dərs «Yeni dərs» ilə açılır — modal bu günün slotundan
dolu açılır (``journal_lesson_prefill``). Yandırılanda davranış əvvəlki kimidir (zolaq + «Aktivləşdir»).

Sorğu profili (grid tabı): slotlar 1 + açılışın dərs faktları 1 (mövzu əhatəsi, bu günün
dərsləri, növ üzrə son müəllim — hamısı bir sorğudan). Slot siyahısı və dərs sətirləri
offering obyektində memolanır — modal üçün slot naxışı və «Yeni dərs» doldurması əlavə
sorğu etmir.
"""

from __future__ import annotations

import datetime as _dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, pgettext
from django.views.decorators.http import require_POST

from core import academic_rules

from . import dashboard_data, journal_topics, lesson_rooms
from .journal_access import is_direct_editor, offering_or_404

_CTX = "registrar.journal_activation"
_SLOTS_ATTR = "_ems_activation_slots"
_LESSONS_ATTR = "_ems_activation_lessons"

#: Cədvəldən kənar dərsin səbəbi üçün minimum mətn (boşluqsuz «x» kimi səbəb qəbul olunmur).
REASON_MIN_LENGTH = 3
#: Slotun müddətindən hesablanan akademik saatın tavanı (1 akademik saat = 45 dəqiqə).
MAX_SLOT_HOURS = 4


# --------------------------------------------------------------------------- #
# Slotlar
# --------------------------------------------------------------------------- #


def offering_slots(offering) -> list:
    """Açılışın cədvəldə DURAN slotları (parklanmış/silinmiş xaric) — offering üzrə memo, TƏK sorğu.

    Slotun öz müəllimi (``instructor``, bölünmüş tədris) eyni sorğuda LEFT JOIN ilə gəlir."""
    cached = getattr(offering, _SLOTS_ATTR, None)
    if cached is None:
        from .models import ScheduleSlot

        cached = list(
            ScheduleSlot.objects.filter(offering=offering, is_parked=False)
            .select_related("instructor")
            .order_by("weekday", "start_time")
        )
        setattr(offering, _SLOTS_ATTR, cached)
    return cached


def slot_teacher(offering, slot, last_instructor):
    """Dərsin müəllimi: slotun ÖZ müəllimi (cədvəldə təyin olunubsa), sonra bu növün son müəllimi,
    sonra jurnal sahibi (2026-09-25 — bölünmüş tədrisdə seminarı aparan assistent)."""
    if slot.instructor_id:
        return slot.instructor
    return last_instructor.get(slot.kind) or offering.instructor


def slots_on(offering, day) -> list:
    """Verilmiş TARİXDƏ keçirilən slotlar — ana səhifə kartı ilə EYNİ qayda (paritet + dövr)."""
    if day is None:
        return []
    return dashboard_data.lessons_on(offering_slots(offering), day, period=offering.period)


def slot_matches(offering, day, start_time) -> bool:
    return start_time is not None and any(slot.start_time == start_time for slot in slots_on(offering, day))


def offering_slot(offering, slot_id):
    """``slot_id`` bu açılışın cədvəldə DURAN slotudursa onu qaytar (yad / parklanmış / silinmiş → LessonRuleError).

    Axtarış memolanmış :func:`offering_slots` siyahısındadır — yad slot bazadan oxunmur da."""
    from .gradebook import LessonRuleError

    text = str(slot_id or "").strip()
    for slot in offering_slots(offering):
        if str(slot.pk) == text:
            return slot
    raise LessonRuleError(pgettext(_CTX, "Bu cədvəl dərsi bu fənnə aid deyil."))


def check_slot_day(offering, slot, day) -> None:
    """Slot bu açılışındır və ``day`` TARİXİNDƏ keçirilir (həftə günü + üst/alt + dövr), yoxsa LessonRuleError."""
    from .gradebook import LessonRuleError

    if slot.offering_id != offering.pk or slot.is_parked:
        raise LessonRuleError(pgettext(_CTX, "Bu cədvəl dərsi bu fənnə aid deyil."))
    if day is None or not any(item.pk == slot.pk for item in slots_on(offering, day)):
        raise LessonRuleError(
            pgettext(
                _CTX, "Bu cədvəl dərsi %(date)s tarixində keçirilmir (həftə günü və ya üst/alt həftə uyğun deyil)."
            )
            % {"date": day.strftime("%d.%m.%Y") if day else "—"}
        )


def slot_hours(slot) -> int:
    """Slotun müddətindən akademik saat (45 dəq.): 80–90 dəqiqəlik standart cüt = 2 saat."""
    from .gradebook import DEFAULT_LESSON_HOURS

    start = _dt.datetime.combine(_dt.date.min, slot.start_time)
    end = _dt.datetime.combine(_dt.date.min, slot.end_time)
    minutes = int((end - start).total_seconds() // 60)
    if minutes <= 0:
        return DEFAULT_LESSON_HOURS
    return max(1, min(MAX_SLOT_HOURS, round(minutes / 45)))


def slot_kind(slot) -> str:
    """Slotun növü jurnal ``LessonKind`` dəyəri kimi (naməlum → mühazirə)."""
    from .models import LessonKind

    return slot.kind if slot.kind in LessonKind.values else LessonKind.LECTURE


def slot_time_key(slot) -> str:
    """Modalın dərs saatı seçiminin dəyəri — ``"HH:MM|HH:MM"`` (təşkilatın öz zəng saatı da ola bilər)."""
    return f"{slot.start_time:%H:%M}|{slot.end_time:%H:%M}"


def slot_pattern(offering) -> list:
    """Dərs modalı üçün slot naxışı (JSON adası ``#jdSlotPattern``).

    JS «cədvəldən kənar» sahəsini (journal_activation.js) və seçilmiş tarixin cədvəl otağını / saatını
    (journal_lesson_schedule.js, sahib 2026-10-17) buna görə hesablayır: həftə günü + üst/alt + saat + tip
    + otaq. ``room_id`` — slotun mətn otağı reyestrdə TƏK uyğunluqla tapılıbsa (yoxdursa boş, otaq
    yaddaşı işləyir); ``room_label`` — cədvəldə yazıldığı kimi. Otaqlar bir sorğu ilə həll olunur."""
    slots = offering_slots(offering)
    room_ids = lesson_rooms.slot_room_ids(offering.organization, [slot.room for slot in slots])
    return [
        {
            "weekday": slot.weekday,
            "week_type": slot.week_type,
            "start": slot.start_time.strftime("%H:%M"),
            "end": slot.end_time.strftime("%H:%M"),
            "kind": slot_kind(slot),
            "room_id": room_ids.get((slot.room or "").strip(), ""),
            "room_label": (slot.room or "").strip(),
        }
        for slot in slots
    ]


def resolve_slot_room(offering, slot):
    """Slotun sərbəst mətnli otağını (``ScheduleSlot.room``) təşkilatın otaq reyestrində tap.

    Yalnız TƏK dəqiq uyğunluq (ad və ya kod, böyük/kiçik hərf fərqsiz) götürülür; tapılmasa
    və ya bir neçə otaq uyğun gəlsə dərs otaqsız açılır (müəllim 2 saat içində düzəldə bilər)."""
    text = (slot.room or "").strip()
    if not text:
        return None
    rooms = offering.organization.exam_rooms.filter(is_active=True).filter(Q(name__iexact=text) | Q(code__iexact=text))
    matches = list(rooms[:2])
    return matches[0] if len(matches) == 1 else None


# --------------------------------------------------------------------------- #
# Açılışın dərs faktları (TƏK sorğu)
# --------------------------------------------------------------------------- #


def lesson_rows(offering, *, memo: bool = False) -> list:
    """Açılışın BÜTÜN dərsləri (ən yenisi birinci) — mövzu əhatəsi, son müəllim / növ / saat üçün TƏK sorğu.

    ``memo=True`` yalnız jurnal səhifəsinin GET yolu üçündür (zolaq və «Yeni dərs» doldurması eyni
    siyahını paylaşır); yazı yolları (aktivləşdirmə, dərs yaratma) həmişə təzə oxuyur."""
    if memo:
        cached = getattr(offering, _LESSONS_ATTR, None)
        if cached is not None:
            return cached
    rows = list(
        offering.lessons.select_related("instructor")
        .only(
            "topic",
            "syllabus_week",
            "kind",
            "date",
            "hours",
            "start_time",
            "end_time",
            "created_at",
            "off_schedule_reason",
            "instructor__first_name",
            "instructor__last_name",
            "instructor__username",
        )
        .order_by("-date", "-created_at")
    )
    # Mövzusuz, sillabus sətrinə bağlı (köçürülmüş) dərs «keçilib» sayılsın — ``display_topic`` (2026-10-25).
    journal_topics.attach_syllabus_topics(rows, offering=offering)
    if memo:
        setattr(offering, _LESSONS_ATTR, rows)
    return rows


def lesson_facts(offering, today, *, memo: bool = False):
    """Mövzu əhatəsi (növ üzrə), növ üzrə SON müəllim və bu günün dərsləri — bir sorğudan."""
    covered: dict = {}
    last_instructor: dict = {}
    todays = []
    for lesson in lesson_rows(offering, memo=memo):
        if lesson.display_topic:
            covered.setdefault(lesson.display_topic, set()).add(lesson.kind)
        if lesson.instructor_id and lesson.kind not in last_instructor:
            last_instructor[lesson.kind] = lesson.instructor
        if lesson.date == today:
            todays.append(lesson)
    return covered, last_instructor, todays


def next_topic(topic_rows, covered, kind) -> str:
    """Sillabus sırası ilə bu NÖV üçün hələ keçilməmiş İLK mövzu.

    ``topic_rows`` — ``journal_topics.lesson_topic_meta`` sətirləri (``title`` + ``kinds``).
    Növ məlumatı olmayan mənbədə (LMS kursu) mövzu hər hansı növdə keçilibsə «keçilib» sayılır."""
    for row in topic_rows or []:
        kinds = row.get("kinds") or ()
        if kinds and kind not in kinds:
            continue
        done = covered.get(row["title"], set())
        if (kind in done) if kinds else bool(done):
            continue
        return row["title"]
    return ""


def _teacher_name(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def slot_lesson_fields(offering, slot, day, *, last_instructor=None) -> dict:
    """``create_lesson(slot=…)`` üçün slotdan köçürülən sahələr; slot həmin gün keçirilmirsə LessonRuleError."""
    check_slot_day(offering, slot, day)
    kind = slot_kind(slot)
    if last_instructor is None:
        _covered, last_instructor, _todays = lesson_facts(offering, day)
    return {
        "kind": kind,
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "hours": slot_hours(slot),
        # Slotun otağı reyestrdə tapılmasa — müəllimin bu növ + gün üçün əvvəl seçdiyi otaq.
        "room": resolve_slot_room(offering, slot) or lesson_rooms.remembered_room(offering, kind, day),
        # Fənn iki müəllim arasında bölünübsə (mühazirə/seminar): slotun öz müəllimi (cədvəldə
        # təyin olunubsa), yoxdursa bu növün son müəllimi, o da yoxdursa jurnal sahibi.
        "instructor": slot.instructor if slot.instructor_id else (last_instructor.get(kind) or offering.instructor),
    }


# --------------------------------------------------------------------------- #
# «+ Yeni dərs» modalının ortaq qaydası
# --------------------------------------------------------------------------- #


def hours_cap_error(offering, hours) -> str:
    """#6 — fənnin tam saat həddi: planlaşdırılmış + yeni saat toplamı keçməsin (60→62 olmaz)."""
    from . import journal_extras
    from .gradebook import DEFAULT_LESSON_HOURS

    summary = journal_extras.journal_teaching_summary(offering)
    if summary["total"] and summary["scheduled_total"] + (hours or DEFAULT_LESSON_HOURS) > summary["total"]:
        return gettext(
            "Fənnin dərs saatı həddi (%(t)s saat) keçilir — keçirilmiş %(h)s saat, qalan yalnız %(r)s saat."
        ) % {"t": summary["total"], "h": summary["scheduled_total"], "r": summary["remaining"]}
    return ""


def check_manual_lesson(offering, *, date, start_time, hours, raw_reason):
    """Modal ilə açılan dərs üçün ``(səbəb, xəta)``; xəta boş deyilsə dərs AÇILMIR.

    Cədvəli olan açılışda seçilmiş tarix + saat heç bir slota uyğun gəlmirsə dərs
    «cədvəldən kənar»dır və səbəb məcburidir; uyğun gəlirsə (və ya cədvəl yoxdursa)
    göndərilmiş səbəb nəzərə alınmır."""
    error = hours_cap_error(offering, hours)
    if error:
        return "", error
    from .gradebook_lessons import _coerce_date

    day = _coerce_date(date)
    if day is None or not offering_slots(offering) or slot_matches(offering, day, start_time):
        return "", ""
    reason = " ".join((raw_reason or "").split())[:255]
    if len(reason) < REASON_MIN_LENGTH:
        if not academic_rules.lesson_activation_enabled():
            # Sahib 2026-10-10: «Aktivləşdir» söndürülüdə mətn ona yönləndirmir.
            return "", pgettext(
                _CTX,
                "Bu tarix və saatda cədvəldə bu fənnin dərsi yoxdur — cədvəldən kənar dərs üçün səbəbi yazın "
                "(məs. əvəzetmə, kompensasiya dərsi). Cədvəldəki dərs üçün tarixi və saatı cədvələ uyğun seçin.",
            )
        return "", pgettext(
            _CTX,
            "Bu tarix və saatda cədvəldə bu fənnin dərsi yoxdur — cədvəldən kənar dərs üçün səbəbi yazın "
            "(məs. əvəzetmə, kompensasiya dərsi). Cədvəldəki dərs üçün jurnalın üstündəki «Aktivləşdir» düyməsini işlədin.",
        )
    return reason, ""


# --------------------------------------------------------------------------- #
# Jurnal səhifəsinin konteksti
# --------------------------------------------------------------------------- #


def _state(slot, lesson, now) -> str:
    if lesson is not None:
        return "done"
    if slot.start_time <= now < slot.end_time:
        return "now"
    return "past" if slot.end_time <= now else "upcoming"


def strip_context(offering, context) -> dict:
    """``journal_detail`` kontekstinə: ``lesson_slot_pattern`` (modal, hər tab) + ``today_strip`` (grid tabı).

    Cədvəli olmayan açılışda heç biri yoxdur — səhifə köhnə kimi qalır.

    Sahib 2026-10-14: «Bu günün cədvəl dərsləri» zolağı (böyük yaşıl kart) jurnaldan GÖTÜRÜLDÜ — «o
    olmasa da olar». «Aktivləşdir» söndürülüdə (defolt) ``today_strip`` ümumiyyətlə qurulmur (sorğu da
    yoxdur); «Yeni dərs» modalı bu günün slotundan yenə dolu açılır (``journal_lesson_prefill`` öz
    hesabını aparır). Zolaq yalnız RİM «Aktivləşdir»i YANDIRANDA qalır — bir kliklik aktivləşdirmənin
    yeganə girişi odur."""
    if not offering_slots(offering):
        return {}
    extra = {"lesson_slot_pattern": slot_pattern(offering) if context.get("can_edit") else []}
    if context.get("active_tab") != "grid" or context.get("correction_mode"):
        return extra
    activation = academic_rules.lesson_activation_enabled()
    if not activation:
        return extra
    today = timezone.localdate()
    now = timezone.localtime().time()
    todays_slots = slots_on(offering, today)
    covered, last_instructor, todays_lessons = lesson_facts(offering, today, memo=True)
    by_start = {}
    for lesson in todays_lessons:
        if lesson.start_time is not None:
            by_start.setdefault(lesson.start_time, lesson)
    topic_rows = context.get("topic_choices_meta") or []
    items = []
    matched = set()
    for slot in todays_slots:
        lesson = by_start.get(slot.start_time)
        if lesson is not None:
            matched.add(lesson.pk)
        teacher = slot_teacher(offering, slot, last_instructor)
        items.append(
            {
                "slot_id": str(slot.pk),
                "start": slot.start_time,
                "end": slot.end_time,
                "kind": slot.kind,
                "kind_label": slot.get_kind_display(),
                "room": slot.room,
                "teacher": _teacher_name(teacher),
                "topic": next_topic(topic_rows, covered, slot.kind),
                "lesson_id": str(lesson.pk) if lesson is not None else "",
                "lesson_topic": lesson.display_topic if lesson is not None else "",
                "state": _state(slot, lesson, now),
                "activate_url": reverse("registrar:journal_activate_slot", args=[offering.pk, slot.pk]),
            }
        )
    next_day, next_slots = (None, [])
    if not todays_slots:
        next_day, next_slots = dashboard_data.next_lesson_day(
            offering_slots(offering), period=offering.period, today=today
        )
    extra["today_strip"] = {
        "date": today,
        "parity": dashboard_data.week_parity(offering.period, today),
        "items": items,
        "activation": activation,
        "can_activate": bool(context.get("can_edit")),
        "next_day": next_day,
        "next_times": ", ".join(slot.start_time.strftime("%H:%M") for slot in next_slots),
        "extra_lessons": [
            {"id": str(lesson.pk), "start": lesson.start_time, "kind_label": lesson.get_kind_display()}
            for lesson in todays_lessons
            if lesson.pk not in matched
        ],
    }
    return extra


# --------------------------------------------------------------------------- #
# POST — «Aktivləşdir»
# --------------------------------------------------------------------------- #


@login_required
@require_POST
def activate_slot(request, offering_id, slot_id):
    """Bu günün cədvəl slotundan dərs sütunu aç (tək klik). Yalnız birbaşa redaktor.

    RİM tənzimləməsində «Aktivləşdir» söndürülübsə (defolt, sahib 2026-10-10) ünvan YOXDUR (404) —
    dərs «Yeni dərs» modalı ilə açılır."""
    if not academic_rules.lesson_activation_enabled():
        raise Http404
    offering = offering_or_404(request, offering_id)
    if not is_direct_editor(request.user, offering):
        raise Http404
    from .models import ScheduleSlot

    slot = (
        ScheduleSlot.objects.filter(pk=slot_id, offering=offering, is_parked=False).select_related("instructor").first()
    )
    if slot is None:
        raise Http404
    from .journal_share_guard import slot_activation

    slot_allowed, share_teacher = slot_activation(request.user, offering, slot)  # bölünmüş jurnal (2026-10-26)
    if not slot_allowed:
        raise Http404
    back = reverse("registrar:journal_detail", args=[offering.pk])

    from . import gradebook, journal_policy, journal_topics

    gate = journal_policy.syllabus_gate(offering)
    if gate["locked"]:
        # views._handle_add_lesson ilə EYNİ: 403 + səbəb kodu (README §8/2).
        return HttpResponseForbidden(gate["reason_code"], content_type="text/plain; charset=utf-8")
    scheme = getattr(offering, "assessment_scheme", None)
    if scheme is not None and scheme.is_published:
        messages.warning(request, gettext("Jurnal yekunlaşdırılıb — dərs əlavə etmək olmaz."))
        return redirect(back)

    today = timezone.localdate()
    existing = offering.lessons.filter(date=today, start_time=slot.start_time).first()
    if existing is not None:
        messages.info(request, pgettext(_CTX, "Bu cədvəl dərsi bu gün artıq aktivləşdirilib."))
        return redirect(f"{back}#jd-lesson-{existing.pk}")
    error = hours_cap_error(offering, slot_hours(slot))
    if error:
        messages.error(request, error)
        return redirect(back)

    covered, last_instructor, _todays = lesson_facts(offering, today)
    topic = next_topic(journal_topics.lesson_topic_meta(offering, []), covered, slot.kind)
    try:
        lesson = gradebook.create_lesson(
            offering=offering,
            date=today,
            slot=slot,
            topic=topic,
            created_by=request.user,
            instructor=share_teacher or slot_teacher(offering, slot, last_instructor),
        )
    except gradebook.LessonRuleError as exc:
        messages.error(request, str(exc))
        return redirect(back)
    messages.success(
        request,
        pgettext(_CTX, "Dərs aktivləşdirildi: %(time)s · %(kind)s%(topic)s.")
        % {
            "time": f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}",
            "kind": lesson.get_kind_display(),
            "topic": f" — «{topic}»" if topic else "",
        },
    )
    return redirect(f"{back}#jd-lesson-{lesson.pk}")


__all__ = [
    "MAX_SLOT_HOURS",
    "REASON_MIN_LENGTH",
    "activate_slot",
    "check_manual_lesson",
    "check_slot_day",
    "hours_cap_error",
    "lesson_facts",
    "lesson_rows",
    "next_topic",
    "offering_slot",
    "offering_slots",
    "resolve_slot_room",
    "slot_hours",
    "slot_kind",
    "slot_lesson_fields",
    "slot_matches",
    "slot_pattern",
    "slot_teacher",
    "slot_time_key",
    "slots_on",
    "strip_context",
]
