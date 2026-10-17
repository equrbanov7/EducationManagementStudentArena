"""«Yeni dərs» modalı ƏVVƏLCƏDƏN DOLU açılır (sahib 2026-10-10: jurnaldakı «Aktivləşdir»-i yığışdır —
müəllim «Yeni dərs» basır, forma cədvələ və son dərsə görə hazır gəlir).

:func:`modal_context` — ``journal_detail`` GET-i üçün ``lesson_prefill`` (yalnız «Yeni dərs» açıla bilən
səhifədə — ``can_edit``). Şablon onu ``{{ lesson_prefill|json_script:"jdLessonPrefill" }}`` ilə verir,
sahələri ``journal_lesson_prefill.js`` doldurur. Qayda:

1. BU GÜNÜN açılmamış cədvəl dərsi (başlanğıc saatında hələ dərs yoxdur), seçim sırası: hazırda gedən →
   :data:`~apps.registrar.journal_list_schedule.GRACE` (30 dəq.) içində bitən → növbəti → ən son keçmiş.
   Slotdan: tip, dərs saatı (təşkilatın öz zəng saatı da ola bilər), akademik saat, otaq (reyestrdə
   tapılmasa — otaq yaddaşı), müəllim (slotun öz müəllimi → bu tipin son müəllimi → jurnal sahibi) və
   sillabusdakı növbəti keçilməmiş mövzu; ``source="slot"`` + ``slot_id``.
2. Slot yoxdursa: tip = cədvəl kilidi → son dərsin tipi → tədris planında ən çox QALAN saatı olan tip;
   akademik saat və müəllim həmin tipin son dərsindən, otaq yaddaşdan (tip + həftə günü, sonra tip);
   dərs saatı son dərsdən YALNIZ açılışın cədvəli ümumiyyətlə yoxdursa (cədvəl varsa saatı müəllim seçir —
   cədvəldən kənar dərs səbəb tələb edir).

Hər tip üçün mövzu / müəllim / akademik saat xəritələri (``*_by_kind``) də verilir — müəllim tipi
dəyişəndə JS həmin tipin dəyərlərinə keçir. Zolaqdakı hər açılmamış slotun dəyərləri ``slots``-dadır
(slot kartındakı «Yeni dərs» modalı məhz həmin slotdan açır).

:func:`posted_slot` — POST: modal slotdan doldurulubsa gizli ``slot_id`` gəlir. Slot bu açılışın olmalı və
seçilmiş tarixdə keçirilməlidir (əks halda xəta); saat və tip slotla EYNİDİRSƏ dərs ``create_lesson(slot=…)``
qaydası ilə açılır — slotun saatı standart olmasa da qəbul olunur, «cədvəldən kənar» səbəbi tələb olunmur.
Müəllim saatı və ya tipi dəyişibsə əl ilə dərs qaydaları işləyir.

:func:`own_lesson_time` — redaktə POST-u: slotdan açılmış dərsin öz (standart olmayan) saatı geri gəlibsə
saxlanılır (əvvəl redaktə onu silirdi).

Sorğu profili: dərs sətirləri ``journal_activation.lesson_rows(memo=True)`` — grid tabında zolaqla
PAYLAŞILIR (0 əlavə), başqa tablarda 1; slot otaqlarının reyestr axtarışı ≤ 1; otaq yaddaşı və mövzu
sətirləri səhifə kontekstindəndir. Tədris planı yalnız açılışın heç bir dərsi və tip kilidi olmayanda oxunur.
"""

from __future__ import annotations

import datetime as _dt

from django.utils import timezone

from . import dashboard_data, journal_activation, lesson_rooms, schedule
from .journal_list_schedule import GRACE

#: Jurnal dərs tipləri (``LessonKind``) — modalın tip seçimi ilə eyni sıra.
KINDS = ("lecture", "seminar", "lab")


def modal_context(offering, context, *, now=None) -> dict:
    """``journal_detail`` kontekstinə ``lesson_prefill`` və BÜTÜN dərslərə görə «keçirilib» işarəli mövzular."""
    if not context.get("can_edit"):
        return {}
    lessons = journal_activation.lesson_rows(offering, memo=True)
    extra = {"lesson_prefill": build(offering, context, now=now)}
    if context.get("topic_choices_meta"):
        extra["topic_choices_meta"] = topics_covered_by(context["topic_choices_meta"], lessons)
    return extra


def build(offering, context, *, now=None) -> dict:
    """Modalın defoltları (bax modul sənədi). ``now`` — test üçün (defolt: indiki yerli vaxt)."""
    now = timezone.localtime(now) if now is not None else timezone.localtime()
    today = now.date()
    lessons = journal_activation.lesson_rows(offering, memo=True)
    covered, last_instructor, todays = journal_activation.lesson_facts(offering, today, memo=True)
    topic_rows = context.get("topic_choices_meta") or []
    memory = context.get("lesson_room_memory") or {}
    # «Son dərs» — bu günə qədər keçirilənlərdən (irəli tarixli planlanmış dərs defolt olmasın).
    held = [lesson for lesson in lessons if lesson.date <= today] or lessons
    last_by_kind: dict = {}
    for lesson in held:
        last_by_kind.setdefault(lesson.kind, lesson)
    owner = str(offering.instructor_id or "")
    # Jurnal sahibindən BAŞQA müəllimlərin adı (artıq yüklənib — sorğu yoxdur): slotun öz müəllimi seçicinin
    # namizəd siyahısında olmaya bilər (bölünmüş tədris), çip adı buradan gəlir.
    labels: dict = {}

    def teacher_id(user) -> str:
        if user is None:
            return owner
        if str(user.pk) != owner:
            labels[str(user.pk)] = (user.get_full_name() or "").strip() or user.username
        return str(user.pk)

    for lesson in lessons:  # redaktə modalının çipi də (slot müəllimi ilə açılmış dərs) — sorğusuz
        if lesson.instructor_id:
            teacher_id(lesson.instructor)
    data = {
        "date": today.isoformat(),
        "parity": str(dashboard_data.week_parity(offering.period, today)),
        "topic_by_kind": {kind: journal_activation.next_topic(topic_rows, covered, kind) for kind in KINDS},
        "instructor_by_kind": {kind: teacher_id(last_instructor.get(kind)) for kind in KINDS},
        "hours_by_kind": {kind: _hours(last_by_kind.get(kind)) for kind in KINDS},
        "instructor_labels": labels,
        "slots": {},
    }
    candidates = open_slots(offering, today, todays)
    rooms = _slot_rooms(offering, candidates)
    for slot in candidates:
        kind = journal_activation.slot_kind(slot)
        data["slots"][str(slot.pk)] = {
            "kind": kind,
            "time": journal_activation.slot_time_key(slot),
            "hours": journal_activation.slot_hours(slot),
            "room": rooms.get((slot.room or "").strip()) or _memory_room(memory, kind, today),
            # ``journal_activation.slot_teacher`` qaydası: slotun öz müəllimi → bu tipin son müəllimi → jurnal sahibi.
            "instructor": teacher_id(slot.instructor if slot.instructor_id else last_instructor.get(slot.kind)),
            "topic": data["topic_by_kind"].get(kind, ""),
            "label": f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M} · {slot.get_kind_display()}",
            "source": "slot",
            "slot_id": str(slot.pk),
        }
    picked = pick_slot(candidates, now)
    if picked is not None:
        data.update(data["slots"][str(picked.pk)])
    else:
        data.update(_fallback(offering, context, data, held, last_by_kind, memory, today))
    return data


def open_slots(offering, today, todays_lessons) -> list:
    """Bu günün cədvəl slotları, başlanğıc saatında hələ dərs açılmayanlar (zolaqdakı «açılmayıb» qaydası)."""
    taken = {lesson.start_time for lesson in todays_lessons if lesson.start_time is not None}
    return [slot for slot in journal_activation.slots_on(offering, today) if slot.start_time not in taken]


def pick_slot(slots, now):
    """«Yeni dərs» üçün slot: hazırda gedən → GRACE içində bitən → növbəti → ən son keçmiş (yoxdursa ``None``)."""
    if not slots:
        return None
    day, clock = now.date(), now.time()
    running = [slot for slot in slots if slot.start_time <= clock < slot.end_time]
    if running:
        return running[0]
    current = _dt.datetime.combine(day, clock)
    ended = [slot for slot in slots if slot.end_time <= clock]
    recent = [slot for slot in ended if _dt.datetime.combine(day, slot.end_time) + GRACE > current]
    if recent:
        return max(recent, key=lambda slot: slot.end_time)
    upcoming = [slot for slot in slots if slot.start_time > clock]
    if upcoming:
        return min(upcoming, key=lambda slot: slot.start_time)
    return max(ended, key=lambda slot: slot.end_time) if ended else None


def _fallback(offering, context, data, held, last_by_kind, memory, today) -> dict:
    """Bu gün açılmamış slot yoxdur: tip kilidi → son dərsin tipi → tədris planı (bax modul sənədi)."""
    locked = context.get("locked_lesson_kind") or ""
    last = held[0] if held else None
    if locked:
        kind, source = locked, ("last" if last_by_kind.get(locked) else "")
    elif last is not None:
        kind, source = last.kind, "last"
    else:
        kind = _plan_kind(offering, held)
        source = "plan" if kind else ""
    kind = kind if kind in KINDS else KINDS[0]
    reference = last_by_kind.get(kind) or last
    return {
        "kind": kind,
        # Cədvəli olan açılışda saatı müəllim özü seçir (səhv saat «cədvəldən kənar» səbəb istəyir).
        "time": "" if journal_activation.offering_slots(offering) else _standard_time(reference),
        "hours": data["hours_by_kind"][kind],
        "room": _memory_room(memory, kind, today),
        "instructor": data["instructor_by_kind"][kind],
        "topic": data["topic_by_kind"][kind],
        "label": "",
        "source": source,
        "slot_id": "",
    }


def _plan_kind(offering, lessons) -> str:
    """Tədris planında (və ya dərs yükündə) ən çox QALAN saatı olan tip; plan yoxdursa boş."""
    from . import plan_hours

    plan = plan_hours.plan_hours_for_offering(offering)
    if not plan:
        return ""
    used: dict = {}
    for lesson in lessons:
        used[lesson.kind] = used.get(lesson.kind, 0) + int(lesson.hours or 0)
    best = max(KINDS, key=lambda kind: (plan.get(kind, 0) - used.get(kind, 0), -KINDS.index(kind)))
    return best if plan.get(best, 0) - used.get(best, 0) > 0 else ""


def _slot_rooms(offering, slots) -> dict:
    """Slotların sərbəst mətnli otağı → reyestr otağının id-si, BİR sorğu ilə (``lesson_rooms.slot_room_ids``)."""
    return lesson_rooms.slot_room_ids(offering.organization, [slot.room for slot in slots])


def _memory_room(memory, kind, day) -> str:
    """Otaq yaddaşı (``lesson_rooms.remembered_rooms``) — əvvəl «tip|həftə günü», sonra yalnız «tip» (JS ilə eyni)."""
    return memory.get(f"{kind}|{day.isoweekday()}") or memory.get(kind) or ""


def _standard_time(lesson) -> str:
    """Dərsin saatı modalın standart seçimlərindəndirsə ``"HH:MM|HH:MM"``, yoxdursa boş."""
    if lesson is None or lesson.start_time is None or lesson.end_time is None:
        return ""
    pair = (f"{lesson.start_time:%H:%M}", f"{lesson.end_time:%H:%M}")
    return "|".join(pair) if pair in schedule.STANDARD_LESSON_TIMES else ""


def _hours(lesson) -> int:
    """Həmin tipin son dərsinin akademik saatı (modal seçimi 1..4), yoxdursa standart 2."""
    from .gradebook import DEFAULT_LESSON_HOURS

    hours = int(getattr(lesson, "hours", 0) or 0)
    return hours if 1 <= hours <= journal_activation.MAX_SLOT_HOURS else DEFAULT_LESSON_HOURS


def topics_covered_by(rows, lessons) -> list:
    """Mövzu seçimlərinin «✓ keçirilib» işarəsi BÜTÜN dərslərə görə.

    ``journal_topics.lesson_topic_meta`` jurnalın görünən PƏNCƏRƏSİNİN dərslərini alırdı — pəncərədən
    kənarda keçilmiş mövzu «keçirilməyib» görünürdü. İşarənin tarixi keçirilmiş ən son dərsin tarixidir
    (yalnız gələcək dərs varsa — ən yaxın gələcək tarix)."""
    today = timezone.localdate()
    held: dict = {}  # mövzu → bu günə qədər (daxil) keçirilmiş ən son dərsin tarixi
    upcoming: dict = {}  # mövzu → gələcək tarixli ən yaxın dərs
    kinds: dict = {}  # mövzu → KEÇİRİLMİŞ dərs növləri
    for lesson in lessons:
        if not lesson.topic:
            continue
        if lesson.date <= today:
            if lesson.topic not in held or lesson.date > held[lesson.topic]:
                held[lesson.topic] = lesson.date
            kinds.setdefault(lesson.topic, set()).add(lesson.kind)
        elif lesson.topic not in upcoming or lesson.date < upcoming[lesson.topic]:
            upcoming[lesson.topic] = lesson.date
    # «keçirilib» = mövzunun HƏR HANSI dərsi bu gün və ya əvvəl; «planlaşdırılıb» = keçirilməyib, amma gələcək dərs var
    # (QA-1 F13; ``journal_extras.calendar_plan`` ilə eyni qayda). Mühazirəsi keçilmiş, seminarı gələcəkdə olan mövzu keçirilib.
    return [
        {
            **row,
            "covered": row["title"] in held,
            "planned": row["title"] not in held and row["title"] in upcoming,
            "date": held.get(row["title"]) or upcoming.get(row["title"]),
            "covered_kinds": sorted(kinds.get(row["title"], ())),
        }
        for row in rows
    ]


def posted_slot(offering, data, *, date, kind):
    """«Yeni dərs» POST-unda gizli ``slot_id`` → slot (saat/tip slotla eynidirsə), yoxdursa ``None``.

    * Slot bu açılışın deyil, parklanıb/silinib və ya seçilmiş tarixdə keçirilmir → ``LessonRuleError``
      (saxta və ya köhnəlmiş id səssizcə qəbul olunmur).
    * Göndərilən dərs saatı və ya tip slotdan fərqlidirsə → ``None``: əl ilə dərs qaydaları (standart saat,
      cədvəldən kənar səbəb) tətbiq olunur — müəllimin seçimi slotu üstələyir."""
    raw = (data.get("slot_id") or "").strip()
    if not raw:
        return None
    from .gradebook_lessons import _coerce_date

    day = _coerce_date(date)
    if day is None:
        return None  # tarix xətasını create_lesson göstərir
    slot = journal_activation.offering_slot(offering, raw)
    journal_activation.check_slot_day(offering, slot, day)
    if (data.get("lesson_time") or "").strip() != journal_activation.slot_time_key(slot):
        return None
    if kind != journal_activation.slot_kind(slot):
        return None
    return slot


def schedule_slot_for(offering, day, start_time, kind):
    """Seçilmiş TARİXİN cədvəl slotu (həftə günü + üst/alt + dövr): saatı uyğun gələn (eyni tip üstün),
    yoxdursa eyni tipli, o da yoxdursa günün ilk slotu; həmin gün slot yoxdursa ``None``.

    journal_lesson_schedule.js-in ``match`` qaydası ilə EYNİDİR (modal otağı buna görə doldurur)."""
    slots = journal_activation.slots_on(offering, day)
    if not slots:
        return None
    pool = [slot for slot in slots if start_time is not None and slot.start_time == start_time] or slots
    return next((slot for slot in pool if journal_activation.slot_kind(slot) == kind), pool[0])


def posted_room(offering, data, *, date, start_time, kind, slot):
    """«Yeni dərs» POST-unun otağı (sahib 2026-10-17: «otaq nömrəsi cədvəldəki avtomatik gəlsin»).

    * Otaq göndərilibsə — TƏŞKİLAT daxilində həll olunur (``lesson_rooms.resolve_lesson_room``): yad
      təşkilatın / deaktiv / yararsız id-li otaq dərsə BAĞLANMIR (fail-closed) və cədvələ də keçilmir.
    * Boşdursa və dərs slot yolundadırsa (``slot``) — ``create_lesson`` slotun otağını özü köçürür (``None``).
    * Boşdursa və slot yoxdursa — həmin tarix/saatın cədvəl slotunun otağı (:func:`schedule_slot_for`);
      slot yoxdursa və ya otağı reyestrdə tapılmırsa otaqsız."""
    raw = (data.get("lesson_room") or "").strip()
    if raw or slot is not None:
        return lesson_rooms.resolve_lesson_room(offering.organization, raw)
    from .gradebook_lessons import _coerce_date

    day = _coerce_date(date)
    match = schedule_slot_for(offering, day, start_time, kind) if day is not None else None
    return journal_activation.resolve_slot_room(offering, match) if match is not None else None


def own_lesson_time(lesson, raw):
    """Redaktə POST-u: göndərilən saat dərsin ÖZ saatıdırsa ``(start, end)``, yoxdursa ``(None, None)``.

    Cədvəl slotundan açılmış dərsin saatı təşkilatın öz zəng saatı ola bilər (standart siyahıda yoxdur) —
    modal onu müvəqqəti seçim kimi göstərir, ``schedule.parse_time_slot`` isə yalnız standart saatı tanıyır.
    Bu yoxlama olmasa redaktə (məs. yalnız mövzu əlavə etmək) dərsin saatını SİLİRDİ və zolaq slotu yenidən
    «açılmayıb» göstərirdi (dublikat dərs riski)."""
    if lesson.start_time is None or lesson.end_time is None:
        return None, None
    if (raw or "").strip() != f"{lesson.start_time:%H:%M}|{lesson.end_time:%H:%M}":
        return None, None
    return lesson.start_time, lesson.end_time


__all__ = [
    "KINDS",
    "build",
    "modal_context",
    "open_slots",
    "own_lesson_time",
    "pick_slot",
    "posted_room",
    "posted_slot",
    "schedule_slot_for",
    "topics_covered_by",
]
