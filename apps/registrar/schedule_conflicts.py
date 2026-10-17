"""Cədvəl konflikt mühərriki + boş hüceyrə tövsiyəsi (SERVER AVTORİTETDİR).

──────────────────────────────────────────────────────────────────────────────
NƏYİ HƏLL EDİR (sahibin tələbi, 2026-09-09)
──────────────────────────────────────────────────────────────────────────────
«Əgər həmin vaxtda müəllimin başqa yerdə dərsi varsa yazsın ki, müəllimin filan
saatda filan qrupa dərsi var və göstərsin» + «proqram tövsiyə versin ki səhər
yaxud günorta növbəsinə uyğun hara boşdursa orada ola bilər».

Köhnə ``schedule.find_conflict`` yalnız BİRİNCİ toqquşan slotu qaytarırdı və
səbəbi sonradan təxmin edirdi (``conflict_reason``). Redaktorun ehtiyacı fərqli:
bir hərəkət eyni anda müəllimi DƏ, otağı DA tuta bilər, və istifadəçi hər ikisini
görməlidir. Ona görə burada BÜTÜN toqquşmalar növü ilə birlikdə qaytarılır və
UI yalnız serverin dediyini göstərir (klient heç nə hesablamır).

QAYDALAR
--------
* vaxt ARALIĞI kəsişməsi (yalnız eyni `start_time` deyil);
* üst/alt həftə: ``ALL`` hər ikisi ilə, ``ODD``/``EVEN`` yalnız özü və ``ALL``
  ilə toqquşur (``odd`` və ``even`` bir-birinə mane olmur);
* PARKLANMIŞ (``is_parked``) və yumşaq silinmiş slotlar heç bir hesabatda
  iştirak etmir — onlar cədvəldə deyil;
* müəllim/otaq yoxlaması TENANT genişliyindədir (başqa fakültənin dərsi də
  müəllimi tutur), qrup yoxlaması isə təbii olaraq qrupun özündədir;
* müəllim = slotun EFFEKTİV müəllimi (2026-09-25): ``ScheduleSlot.instructor``,
  boşdursa jurnal sahibi — seminarı aparan assistentin toqquşması da tutulur
  (``schedule.effective_instructor_id``); id-lər mətn kimi müqayisə olunur
  (JSON-dan gələn ``"12"`` ilə bazadakı ``12`` eyni müəllimdir);
* ``schedule.find_conflict`` ilə EYNİ iki qayda (2026-09-25, 4e0b986d-nin redaktora
  çatmayan hissəsi): (1) ``period_id`` verilibsə yalnız EYNİ semestrin slotları —
  keçən semestrin silinməmiş cədvəli bu semestrin saatını bloklamır (dövr yoxdursa
  köhnə davranış); (2) birləşmiş mühazirə (axın): eyni effektiv müəllim + eyni fənn +
  hər ikisi mühazirə + eyni (və ya boş) otaq, qruplar FƏRQLİ → toqquşma deyil
  (generatorun dərc etdiyi axınlar redaktorda «müəllim toqquşması» görünürdü);
  qrup toqquşması HƏMİŞƏ toqquşmadır (``schedule.is_joint_lecture``);
* PARALEL ALT QRUP (2026-10-14): EYNİ açılışın iki məşğələ/laboratoriya slotu eyni saatda,
  FƏRQLİ effektiv müəllimlərlə — qrup yarıya bölünüb (alt qruplar) paralel oturur; bu, qrup
  toqquşması deyil (müəllim və otaq yoxlaması yenə işləyir). ``offering_id`` verilməyibsə qayda
  işləmir (köhnə davranış);
* ƏHATƏDƏN KƏNAR toqquşma (2026-10-14): ``visible(slot)`` False qaytaran slot (redaktorun
  ``schedule.manage`` əhatəsindən kənar — başqa fakültə/kafedra) MİNİMAL açıqlama ilə qaytarılır:
  yalnız «fənn · qrup» (müəllim adı, otaq, slot id-si YOX) və ``can_force=False`` — onu parklamaq
  olmaz. Qrup toqquşması heç vaxt məcburi keçilmir (``can_force=False``): əvvəlcə həmin dərs
  köçürülməlidir.
"""

from __future__ import annotations

from collections import namedtuple

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import pgettext

from apps.registrar.models import ScheduleSlot, SlotKind, WeekType
from apps.registrar.schedule import effective_instructor, effective_instructor_id, is_joint_lecture, same_id

_CTX = "registrar.schedule_conflicts"

KIND_TEACHER = "teacher"
KIND_GROUP = "group"
KIND_ROOM = "room"

#: Göstəriş sırası — müəllim ən vacibdir (sahibin nümunəsi məhz odur).
KIND_ORDER = (KIND_TEACHER, KIND_GROUP, KIND_ROOM)


def week_types_overlap(a, b) -> bool:
    """Üst və alt həftə bir-birinə mane OLMUR; qalan hər cütlük toqquşur."""
    return not ({a, b} == {WeekType.ODD, WeekType.EVEN})


def time_ranges_overlap(start_a, end_a, start_b, end_b) -> bool:
    return start_a < end_b and start_b < end_a


def _weekday_label(weekday) -> str:
    from apps.registrar import schedule as schedule_service

    for num, label in schedule_service.WEEKDAYS:
        if num == weekday:
            return str(label)
    return str(weekday)


def _week_type_label(week_type) -> str:
    if week_type == WeekType.ODD:
        return pgettext(_CTX, "üst həftə")
    if week_type == WeekType.EVEN:
        return pgettext(_CTX, "alt həftə")
    return pgettext(_CTX, "hər həftə")


def _person_name(user) -> str:
    if user is None:
        return ""
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or str(getattr(user, "username", "") or "")


def _message(kind, slot, *, redacted=False) -> str:
    """İstifadəçiyə göstərilən açıq cümlə (sahibin nümunəsi ilə eyni forma).

    ``redacted`` — əhatədən kənar slot: yalnız «fənn · qrup» açılır."""
    offering = slot.offering
    if redacted:
        short = {
            "subject": getattr(offering.subject, "code", "") or getattr(offering.subject, "name", "") or "",
            "group": getattr(offering.group, "name", "") or pgettext(_CTX, "təyin edilməmiş qrup"),
            "room": slot.room or "",
        }
        if kind == KIND_ROOM:
            return pgettext(_CTX, "%(room)s auditoriyası bu saatda tutulub: %(subject)s · %(group)s.") % short
        return pgettext(_CTX, "Müəllimin bu saatda başqa dərsi var: %(subject)s · %(group)s.") % short
    params = {
        "day": _weekday_label(slot.weekday),
        "time": slot.start_time.strftime("%H:%M"),
        "group": getattr(offering.group, "name", "") or pgettext(_CTX, "təyin edilməmiş qrup"),
        "subject": getattr(offering.subject, "code", "") or getattr(offering.subject, "name", "") or "",
        "teacher": _person_name(effective_instructor(slot)) or pgettext(_CTX, "müəllim təyin edilməyib"),
        "room": slot.room or "",
    }
    if kind == KIND_TEACHER:
        return pgettext(_CTX, "Müəllimin %(day)s %(time)s-da %(group)s qrupunda dərsi var (%(subject)s).") % params
    if kind == KIND_GROUP:
        return pgettext(_CTX, "Qrupun %(day)s %(time)s-da artıq dərsi var (%(subject)s).") % params
    return pgettext(_CTX, "%(room)s auditoriyası %(day)s %(time)s-da %(group)s qrupu tərəfindən tutulub.") % params


def kind_label(kind) -> str:
    """Növ açarının İSTİFADƏÇİ etiketi — UI-da xam «teacher/group/room» görünməsin."""
    if kind == KIND_TEACHER:
        return pgettext(_CTX, "müəllim")
    if kind == KIND_GROUP:
        return pgettext(_CTX, "qrup")
    return pgettext(_CTX, "auditoriya")


def describe(slot, kind, *, in_scope=True) -> dict:
    """Konflikt slotunun JSON müqaviləsi — UI açar adları DƏYİŞMƏZ.

    ``in_scope=False`` — redaktorun əhatəsindən kənar slot: minimal açıqlama (bax modul başlığı)."""
    offering = slot.offering
    can_force = bool(in_scope and kind != KIND_GROUP)
    if not in_scope:
        return {
            "kind": kind,
            "kind_label": kind_label(kind),
            "slot_id": "",
            "message": _message(kind, slot, redacted=True),
            "subject_code": getattr(offering.subject, "code", "") or "",
            "subject_name": getattr(offering.subject, "name", "") or "",
            "group": getattr(offering.group, "name", "") or "",
            "instructor": "",
            "room": slot.room if kind == KIND_ROOM else "",
            "weekday": slot.weekday,
            "weekday_label": _weekday_label(slot.weekday),
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "week_type": slot.week_type,
            "week_type_label": _week_type_label(slot.week_type),
            "in_scope": False,
            "can_force": False,
        }
    return {
        "kind": kind,
        "kind_label": kind_label(kind),
        "slot_id": str(slot.pk),
        "message": _message(kind, slot),
        "subject_code": getattr(offering.subject, "code", "") or "",
        "subject_name": getattr(offering.subject, "name", "") or "",
        "group": getattr(offering.group, "name", "") or "",
        "instructor": _person_name(effective_instructor(slot)),
        "room": slot.room or "",
        "weekday": slot.weekday,
        "weekday_label": _weekday_label(slot.weekday),
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "week_type": slot.week_type,
        "week_type_label": _week_type_label(slot.week_type),
        "in_scope": True,
        "can_force": can_force,
    }


def is_parallel_subgroup(*, offering_id, kind, teacher_id, slot) -> bool:
    """EYNİ açılışın paralel məşğələ/laboratoriyası (alt qruplar), FƏRQLİ müəllimlə — qrup toqquşması deyil."""
    return bool(
        offering_id
        and same_id(offering_id, slot.offering_id)
        and kind
        and kind != SlotKind.LECTURE
        and slot.kind != SlotKind.LECTURE
        and teacher_id
        and not same_id(teacher_id, effective_instructor_id(slot))
    )


def live_slots(organization, *, weekday=None, period_id=None):
    """Cədvəldə HƏQİQƏTƏN duran slotlar (silinməmiş + parklanmamış); ``period_id`` — yalnız o semestr."""
    queryset = ScheduleSlot.objects.filter(organization=organization, is_parked=False)
    if weekday is not None:
        queryset = queryset.filter(weekday=weekday)
    if period_id:
        queryset = queryset.filter(offering__period_id=period_id)
    return queryset.select_related(
        "offering", "offering__subject", "offering__group", "offering__instructor", "instructor"
    )


#: Otaq məşğulluğu üçün yüngül sətir (PERF-1 F-07, 2026-10-17): ``_busy_rooms`` / otaq toqquşması
#: yalnız bu sahələri oxuyur — bütün semestr üçün tam model obyekti qurulmur.
RoomRow = namedtuple("RoomRow", "pk weekday start_time end_time week_type room")


def _sql_pk(field, value):
    """Süzgəc üçün pk dəyəri; yararsız id (``"abc"``) ``None`` — Python müqayisəsi onsuz da tutmur."""
    if not value:
        return None
    try:
        return field.target_field.to_python(value)
    except (ValidationError, TypeError, ValueError):
        return None


def owner_slots(organization, *, period_id=None, group_id=None, instructor_id=None) -> list:
    """Yalnız qrupun VƏ YA (effektiv) müəllimin canlı slotları — tam obyekt (``live_slots`` ilə eyni).

    SQL süzgəci üst-çoxluqdur; dəqiq seçim ``same_id`` ilə Python-da (``detect`` ilə EYNİ müqayisə),
    ona görə nəticə «bütün slotları yüklə + Python-da süz» ilə eynidir, sadəcə semestrin qalanı yüklənmir."""
    group_pk = _sql_pk(ScheduleSlot._meta.get_field("offering").related_model._meta.get_field("group"), group_id)
    teacher_pk = _sql_pk(ScheduleSlot._meta.get_field("instructor"), instructor_id)
    conditions = []
    if group_pk is not None:
        conditions.append(Q(offering__group_id=group_pk))
    if teacher_pk is not None:
        conditions.append(Q(instructor_id=teacher_pk) | Q(instructor__isnull=True, offering__instructor_id=teacher_pk))
    if not conditions:
        return []
    condition = conditions[0] if len(conditions) == 1 else conditions[0] | conditions[1]
    return [
        slot
        for slot in live_slots(organization, period_id=period_id).filter(condition)
        if same_id(group_id, slot.offering.group_id) or same_id(instructor_id, effective_instructor_id(slot))
    ]


def room_rows(organization, *, period_id=None, exclude_ids=()) -> list:
    """Otağı yazılmış canlı slotlar — yüngül :data:`RoomRow` (bir ``values_list`` sorğusu)."""
    excluded = {str(value) for value in (exclude_ids or ()) if value}
    queryset = ScheduleSlot.objects.filter(organization=organization, is_parked=False).exclude(room="")
    if period_id:
        queryset = queryset.filter(offering__period_id=period_id)
    fields = ("pk", "weekday", "start_time", "end_time", "week_type", "room")
    return [RoomRow(*row) for row in queryset.values_list(*fields) if str(row[0]) not in excluded]


def _room_taken(rows, *, weekday, start_time, end_time, week_type, room_norm) -> bool:
    return any(
        row.weekday == weekday
        and time_ranges_overlap(start_time, end_time, row.start_time, row.end_time)
        and week_types_overlap(week_type, row.week_type)
        and room_norm == (row.room or "").strip().lower()
        for row in rows
    )


def detect(
    *,
    organization,
    weekday,
    start_time,
    end_time,
    week_type,
    room="",
    group_id=None,
    instructor_id=None,
    exclude_ids=(),
    candidates=None,
    period_id=None,
    subject_id=None,
    kind=None,
    offering_id=None,
    visible=None,
) -> list[dict]:
    """Bu yerləşdirmənin BÜTÜN toqquşmaları — növ + açıq mətn ilə.

    ``candidates`` verilsə baza sorğusu təkrarlanmır (tövsiyə mühərriki eyni
    slot dəstini onlarla hüceyrə üçün yenidən istifadə edir).

    ``period_id`` — yerləşdirilən açılışın semestri (yalnız o semestrin slotları; boşdursa
    köhnə davranış); ``subject_id`` + ``kind`` — axın qaydası üçün (verilməyibsə qayda
    işləmir, köhnə davranış); ``offering_id`` — paralel alt qrup qaydası üçün; ``visible`` —
    ``callable(slot) -> bool`` (redaktorun əhatəsi; False = minimal açıqlama). Bax modul başlığı.
    """
    excluded = {str(value) for value in (exclude_ids or ()) if value}
    room_norm = (room or "").strip().lower()
    rows = candidates if candidates is not None else live_slots(organization, weekday=weekday, period_id=period_id)

    found: dict = {}
    for slot in rows:
        if slot.weekday != weekday or str(slot.pk) in excluded:
            continue
        if period_id and not same_id(period_id, slot.offering.period_id):
            continue
        if not time_ranges_overlap(start_time, end_time, slot.start_time, slot.end_time):
            continue
        if not week_types_overlap(week_type, slot.week_type):
            continue
        same_group = same_id(group_id, slot.offering.group_id) and not is_parallel_subgroup(
            offering_id=offering_id, kind=kind, teacher_id=instructor_id, slot=slot
        )
        if not same_group and is_joint_lecture(
            kind=kind, subject_id=subject_id, teacher_id=instructor_id, room=room_norm, slot=slot
        ):
            continue
        if same_id(instructor_id, effective_instructor_id(slot)):
            found.setdefault(KIND_TEACHER, slot)
        if same_group:
            found.setdefault(KIND_GROUP, slot)
        if room_norm and room_norm == (slot.room or "").strip().lower():
            found.setdefault(KIND_ROOM, slot)
    return [
        describe(found[key], key, in_scope=visible is None or bool(visible(found[key])))
        for key in KIND_ORDER
        if key in found
    ]


# ── Tövsiyə: hara boşdur ─────────────────────────────────────────────────────


def _day_load(rows, weekday, group_id, instructor_id):
    """Həmin gün qrupun/müəllimin neçə dərsi var (sıxlıq üçün)."""
    total = 0
    for slot in rows:
        if slot.weekday != weekday:
            continue
        if same_id(group_id, slot.offering.group_id) or same_id(instructor_id, effective_instructor_id(slot)):
            total += 1
    return total


def suggest(
    *,
    organization,
    group_id=None,
    instructor_id=None,
    week_type=WeekType.ALL,
    room="",
    shift="",
    exclude_ids=(),
    weekdays=None,
    limit=8,
    period_id=None,
    subject_id=None,
    kind=None,
    offering_id=None,
) -> list[dict]:
    """Həm müəllimin, həm qrupun BOŞ olduğu hüceyrələr — sıralanmış.

    Sahibin tələbi: «proqram tövsiyə versin ki səhər yaxud günorta növbəsinə
    uyğun hara boşdursa orada ola bilər». ``shift`` verilibsə yalnız həmin
    növbənin saatlarına baxılır. ``period_id`` / ``subject_id`` / ``kind`` —
    :func:`detect` ilə eyni (semestr süzgəci + axın qaydası).

    Sıralama (kiçik bal = yaxşı): əvvəlcə HƏMİN GÜN artıq dərsi olan günlər
    (tələbə üçün «bir dərs üçün gəlmək» pisdir), sonra günün erkən saatları.
    """
    from apps.registrar import schedule_grid

    weekdays = weekdays or schedule_grid.TEACHING_WEEKDAYS
    # PERF-1 F-07: tam obyekt yalnız qrupun/müəllimin slotları üçün; qalan slotlar yalnız OTAQ
    # toqquşması verə bilər (axın/paralel qayda müəllim/qrup tələb edir) — onlar yüngül sətirdir.
    rows = owner_slots(organization, period_id=period_id, group_id=group_id, instructor_id=instructor_id)
    room_norm = (room or "").strip().lower()
    mine_ids = {str(slot.pk) for slot in rows}
    others = (
        [
            row
            for row in room_rows(organization, period_id=period_id, exclude_ids=exclude_ids)
            if str(row.pk) not in mine_ids
        ]
        if room_norm
        else []
    )
    periods = [row for row in schedule_grid.lesson_periods(organization) if not shift or row["shift"] == shift]

    out = []
    for weekday, day_label in weekdays:
        load = _day_load(rows, weekday, group_id, instructor_id)
        for period in periods:
            if others and _room_taken(
                others,
                weekday=weekday,
                start_time=period["start"],
                end_time=period["end"],
                week_type=week_type,
                room_norm=room_norm,
            ):
                continue
            clashes = detect(
                organization=organization,
                weekday=weekday,
                start_time=period["start"],
                end_time=period["end"],
                week_type=week_type,
                room=room,
                group_id=group_id,
                instructor_id=instructor_id,
                exclude_ids=exclude_ids,
                candidates=rows,
                period_id=period_id,
                subject_id=subject_id,
                kind=kind,
                offering_id=offering_id,
            )
            if clashes:
                continue
            out.append(
                {
                    "weekday": weekday,
                    "weekday_label": str(day_label),
                    "lesson_no": period["no"],
                    "time_slot": period["key"],
                    "start_time": period["start_text"],
                    "end_time": period["end_text"],
                    "shift": period["shift"],
                    "shift_label": str(schedule_grid.SHIFT_LABELS.get(period["shift"], "")),
                    "day_load": load,
                    "score": (0 if load else 1, period["no"], weekday),
                }
            )
    out.sort(key=lambda row: row["score"])
    for row in out:
        row.pop("score", None)
    return out[: max(1, int(limit or 8))]


__all__ = [
    "KIND_GROUP",
    "kind_label",
    "KIND_ORDER",
    "KIND_ROOM",
    "KIND_TEACHER",
    "describe",
    "detect",
    "is_parallel_subgroup",
    "live_slots",
    "suggest",
    "time_ranges_overlap",
    "week_types_overlap",
]
