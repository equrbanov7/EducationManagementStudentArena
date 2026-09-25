"""«Dərsi aktivləşdir» — cədvəl slotundan BİR kliklə dərs sütunu (UNEC müqayisəsi P1-1, 2026-09-25).

UNEC-də dərs sütunları cədvəldən gəlir, müəllim dərs saatında «Aktivləşdir» basır.
Bizdə «+ Yeni dərs» modalı 5–6 sahə istəyirdi (tarix, növ, saat, otaq, mövzu…).
Bu modul:

* :func:`strip_context` — jurnalın «Qiymətləndirmə» tabının üstündəki «Bu günün
  cədvəl dərsləri» zolağı: açılışın BU GÜNKÜ slotları (həftə günü + üst/alt paritet +
  dövr sərhədi — ``dashboard_data.lessons_on`` ilə EYNİ qayda; parklanmış və silinmiş
  slotlar xaric), saat · növ · otaq · müəllim və sillabusdakı NÖVBƏTİ keçilməmiş mövzu.
  Artıq açılmış slot «Aktivləşdirilib ✓» + sütuna keçid göstərir.
* :func:`activate_slot` (POST) — dərsi ``gradebook_lessons.create_lesson(slot=…)`` ilə
  yaradır; MÖVCUD qaydaların hamısı qüvvədədir: tarix = bu gün, fənnin saat həddi,
  sillabus qapısı, dublikat (eyni gün + eyni saat), jurnal kilidi / yekunlaşma.
* :func:`check_manual_lesson` — «+ Yeni dərs» modalının ORTAQ qaydası: saat həddi +
  cədvəli OLAN açılışda heç bir slota uyğun gəlməyən dərs üçün SƏBƏB məcburidir
  (``Lesson.off_schedule_reason``; «Keçilmiş dərslər»də «cədvəldən kənar» işarəsi).
  Cədvəli ümumiyyətlə olmayan açılışda heç nə dəyişmir (müqayisə ediləcək cədvəl yoxdur).

Sorğu profili (grid tabı): slotlar 1 + açılışın dərs faktları 1 (mövzu əhatəsi, bu günün
dərsləri, növ üzrə son müəllim — hamısı bir sorğudan). Slot siyahısı offering obyektində
memolanır — modal üçün slot naxışı əlavə sorğu etmir.
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

from . import dashboard_data
from .journal_access import is_direct_editor, offering_or_404

_CTX = "registrar.journal_activation"
_SLOTS_ATTR = "_ems_activation_slots"

#: Cədvəldən kənar dərsin səbəbi üçün minimum mətn (boşluqsuz «x» kimi səbəb qəbul olunmur).
REASON_MIN_LENGTH = 3
#: Slotun müddətindən hesablanan akademik saatın tavanı (1 akademik saat = 45 dəqiqə).
MAX_SLOT_HOURS = 4


# --------------------------------------------------------------------------- #
# Slotlar
# --------------------------------------------------------------------------- #


def offering_slots(offering) -> list:
    """Açılışın cədvəldə DURAN slotları (parklanmış/silinmiş xaric) — offering üzrə memo, TƏK sorğu."""
    cached = getattr(offering, _SLOTS_ATTR, None)
    if cached is None:
        from .models import ScheduleSlot

        cached = list(ScheduleSlot.objects.filter(offering=offering, is_parked=False).order_by("weekday", "start_time"))
        setattr(offering, _SLOTS_ATTR, cached)
    return cached


def slots_on(offering, day) -> list:
    """Verilmiş TARİXDƏ keçirilən slotlar — ana səhifə kartı ilə EYNİ qayda (paritet + dövr)."""
    if day is None:
        return []
    return dashboard_data.lessons_on(offering_slots(offering), day, period=offering.period)


def slot_matches(offering, day, start_time) -> bool:
    return start_time is not None and any(slot.start_time == start_time for slot in slots_on(offering, day))


def slot_hours(slot) -> int:
    """Slotun müddətindən akademik saat (45 dəq.): 80–90 dəqiqəlik standart cüt = 2 saat."""
    from .gradebook import DEFAULT_LESSON_HOURS

    start = _dt.datetime.combine(_dt.date.min, slot.start_time)
    end = _dt.datetime.combine(_dt.date.min, slot.end_time)
    minutes = int((end - start).total_seconds() // 60)
    if minutes <= 0:
        return DEFAULT_LESSON_HOURS
    return max(1, min(MAX_SLOT_HOURS, round(minutes / 45)))


def slot_pattern(offering) -> list:
    """Dərs modalı üçün slot naxışı (JSON adası) — JS «cədvəldən kənar» sahəsini buna görə açır."""
    return [
        {"weekday": slot.weekday, "week_type": slot.week_type, "start": slot.start_time.strftime("%H:%M")}
        for slot in offering_slots(offering)
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


def _lesson_facts(offering, today):
    """Mövzu əhatəsi (növ üzrə), növ üzrə SON müəllim və bu günün dərsləri — bir sorğudan."""
    lessons = (
        offering.lessons.select_related("instructor")
        .only(
            "topic",
            "kind",
            "date",
            "start_time",
            "created_at",
            "off_schedule_reason",
            "instructor__first_name",
            "instructor__last_name",
            "instructor__username",
        )
        .order_by("-date", "-created_at")
    )
    covered: dict = {}
    last_instructor: dict = {}
    todays = []
    for lesson in lessons:
        if lesson.topic:
            covered.setdefault(lesson.topic, set()).add(lesson.kind)
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
    from .gradebook import LessonRuleError
    from .models import LessonKind

    if slot.offering_id != offering.pk or slot.is_parked:
        raise LessonRuleError(pgettext(_CTX, "Bu cədvəl dərsi bu fənnə aid deyil."))
    if not any(item.pk == slot.pk for item in slots_on(offering, day)):
        raise LessonRuleError(
            pgettext(
                _CTX, "Bu cədvəl dərsi %(date)s tarixində keçirilmir (həftə günü və ya üst/alt həftə uyğun deyil)."
            )
            % {"date": day.strftime("%d.%m.%Y")}
        )
    kind = slot.kind if slot.kind in LessonKind.values else LessonKind.LECTURE
    if last_instructor is None:
        _covered, last_instructor, _todays = _lesson_facts(offering, day)
    return {
        "kind": kind,
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "hours": slot_hours(slot),
        "room": resolve_slot_room(offering, slot),
        # Fənn iki müəllim arasında bölünübsə (mühazirə/seminar) — bu növün son müəllimi.
        "instructor": last_instructor.get(kind) or offering.instructor,
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

    Cədvəli olmayan açılışda heç biri yoxdur — səhifə köhnə kimi qalır."""
    if not offering_slots(offering):
        return {}
    extra = {"lesson_slot_pattern": slot_pattern(offering) if context.get("can_edit") else []}
    if context.get("active_tab") != "grid" or context.get("correction_mode"):
        return extra
    today = timezone.localdate()
    now = timezone.localtime().time()
    todays_slots = slots_on(offering, today)
    covered, last_instructor, todays_lessons = _lesson_facts(offering, today)
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
        teacher = last_instructor.get(slot.kind) or offering.instructor
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
                "lesson_topic": lesson.topic if lesson is not None else "",
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
    """Bu günün cədvəl slotundan dərs sütunu aç (tək klik). Yalnız birbaşa redaktor."""
    offering = offering_or_404(request, offering_id)
    if not is_direct_editor(request.user, offering):
        raise Http404
    from .models import ScheduleSlot

    slot = ScheduleSlot.objects.filter(pk=slot_id, offering=offering, is_parked=False).first()
    if slot is None:
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

    covered, last_instructor, _todays = _lesson_facts(offering, today)
    topic = next_topic(journal_topics.lesson_topic_meta(offering, []), covered, slot.kind)
    try:
        lesson = gradebook.create_lesson(
            offering=offering,
            date=today,
            slot=slot,
            topic=topic,
            created_by=request.user,
            instructor=last_instructor.get(slot.kind) or offering.instructor,
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
    "hours_cap_error",
    "next_topic",
    "offering_slots",
    "resolve_slot_room",
    "slot_hours",
    "slot_lesson_fields",
    "slot_matches",
    "slot_pattern",
    "slots_on",
    "strip_context",
]
