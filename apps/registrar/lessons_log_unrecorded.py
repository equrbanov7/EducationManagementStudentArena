"""«Keçilmiş dərslər» — «Cədvəldə var, qeydə alınmayıb» sayğacı (UNEC müqayisəsi P1-1, 2026-09-25).

Cədvəl slotu (həftə günü + üst/alt paritet + açılışın dövrü) KEÇMİŞ tarixə düşür, amma
həmin açılışın həmin tarixdə dərs sütunu (``Lesson``) yoxdur → «qeydə alınmayıb».

* **Pəncərə:** bölmədə seçilmiş dövr/aralıq, amma yalnız KEÇMİŞ günlər (bu gün sayılmır —
  müəllim onu hələ jurnalın «Aktivləşdir» düyməsi ilə aça bilər) və pəncərənin sonundan ən
  çoxu :data:`LOOKBACK_DAYS` gün geri («bütün illər» seçimi bütün tarixçəni gəzməsin).
* **Uyğunlaşdırma** (eyni açılış + eyni tarix daxilində): əvvəl eyni başlama saatı, sonra
  eyni növ, sonra istənilən dərs — dərs başqa saata yazılıbsa belə keçirilmiş sayılır
  (yalançı həyəcan olmasın). Parklanmış slotlar sayılmır; hər gün HƏMİN GÜN qüvvədə olan
  cədvələ görə yoxlanılır (slotun ``created_at`` … ``deleted_at`` aralığı — yenidən dərc
  olunmuş cədvəl keçmiş həftələri yeni slotlarla «yanlış» saymasın).
* **Əhatə** — ``lessons_log.scoped_lessons`` ilə eyni məntiq, slot tərəfdən: müəllim öz
  açılışlarının cədvəlini, nəzarətçi (``journal.roster`` / ``journal.lessons_unit``) struktur
  alt-ağacını (org-wide əhatədə bütün təşkilatı) görür; əhatəsiz nəzarətçi — boş.
* **Filtrlər** — bölmənin filtrləri ilə EYNİ məna (açılış, növ, qrup, müəllim, təhsil
  forması, axtarış, fakültə, kafedra), bax :func:`apply_slot_filters`.

Tətil/bayram təqvimi sistemdə YOXDUR — belə günlər də «qeydə alınmayıb» sayıla bilər
(bölmədə qeyd kimi yazılır). Sorğu: slotlar 1 + dərs cütləri 1, nəticə 300 s keşlənir.
"""

from __future__ import annotations

import datetime as _dt
import hashlib

from django.core.cache import cache
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.registrar import schedule
from apps.registrar.models import Lesson, ScheduleSlot, WeekType
from apps.registrar.models.catalog_meta import EducationForm

#: Geriyə baxış tavanı (gün) — təxminən bir semestr.
LOOKBACK_DAYS = 150
#: Bölmədə siyahıda göstərilən sətir tavanı (say tam qalır).
ITEM_LIMIT = 30
#: Keş müddəti — ``lessons_log_totals.TOTALS_CACHE_TTL`` ilə eyni siyasət.
CACHE_TTL = 300


def _scope_q(user, organization, *, supervisor):
    """Slot sorğusunun əhatə şərti; ``None`` → əhatə yoxdur (boş nəticə)."""
    if not supervisor:
        return Q(offering__instructor=user)
    from apps.registrar.lessons_log import _supervision_scopes

    scopes = _supervision_scopes(user, organization)
    if not scopes:
        return None
    if any(scope.is_org_wide for scope in scopes):
        return Q()
    combined = Q()
    for scope in scopes:
        combined |= scope.unit_subtree_q(path_field="offering__group__path", id_field="offering__group__id")
    return combined


def apply_slot_filters(slots, filters, *, supervisor):
    """Bölmə filtrlərinin slot qarşılığı (``lessons_log.apply_filters`` ilə eyni məna)."""
    filters = filters or {}
    q = (filters.get("q") or "").strip()
    if q:
        slots = slots.filter(
            Q(offering__subject__name__icontains=q)
            | Q(offering__subject__code__icontains=q)
            | Q(offering__group__name__icontains=q)
        )
    if filters.get("offering"):
        slots = slots.filter(offering_id=filters["offering"])
    if filters.get("kind"):
        slots = slots.filter(kind=filters["kind"])
    if filters.get("group"):
        slots = slots.filter(offering__group__name=filters["group"])
    form = filters.get("form")
    if form and form in {value for value, _label in EducationForm.choices}:
        slots = slots.filter(offering__group__settings__education_form=form)
    if filters.get("teacher") and supervisor:
        slots = slots.filter(offering__instructor_id=filters["teacher"])
    from apps.registrar import lessons_log_units

    if filters.get("faculty_unit") is not None:
        slots = slots.filter(lessons_log_units.faculty_q(filters["faculty_unit"]))
    if filters.get("kafedra_unit") is not None:
        slots = slots.filter(lessons_log_units.kafedra_slot_q(filters["kafedra_unit"]))
    if filters.get("invalid_unit"):
        slots = slots.filter(pk__isnull=True)  # `.none()` SQL vermir — keş açarı onun mətnindən qurulur
    return slots


def _local_date(value):
    if value is None:
        return None
    return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()


def _occurrences(slot, start, end):
    """Slotun ``[start, end]`` aralığında (dövrü və QÜVVƏDƏ olduğu müddət daxilində) keçirildiyi tarixlər.

    Cədvəl yenidən dərc olunanda köhnə slotlar YUMŞAQ silinir, yeniləri yaradılır
    (``schedule_publish``) — ona görə hər keçmiş gün həmin gün qüvvədə olan cədvələ görə
    yoxlanılır: slot yaradılandan (``created_at``) silinənə (``deleted_at``) qədər."""
    period = slot.offering.period
    if period is not None:
        start = max(start, period.start_date)
        end = min(end, period.end_date)
    created = _local_date(getattr(slot, "created_at", None))
    if created is not None:
        start = max(start, created)
    if getattr(slot, "is_deleted", False):
        deleted = _local_date(slot.deleted_at)
        if deleted is None:
            return
        end = min(end, deleted - _dt.timedelta(days=1))
    day = start + _dt.timedelta(days=(slot.weekday - start.isoweekday()) % 7)
    while day <= end:
        if slot.week_type not in (WeekType.ODD, WeekType.EVEN) or slot.week_type == schedule.week_parity(
            period, day - _dt.timedelta(days=day.weekday())
        ):
            yield day
        day += _dt.timedelta(days=7)


def _unmatched(slots, lessons):
    """Bir açılış + bir tarix: əvvəl eyni saat, sonra eyni növ, sonra istənilən dərs."""
    left = list(lessons)
    pending = sorted(slots, key=lambda item: item.start_time)
    for same in (
        lambda slot, lesson: lesson[0] == slot.start_time,
        lambda slot, lesson: lesson[1] == slot.kind,
        lambda slot, lesson: True,
    ):
        still = []
        for slot in pending:
            match = next((lesson for lesson in left if same(slot, lesson)), None)
            if match is None:
                still.append(slot)
            else:
                left.remove(match)
        pending = still
    return pending


def _teacher_label(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def unrecorded_slots(user, organization, *, supervisor, window, periods=None, filters=None, today=None) -> dict:
    """``{"count", "items", "start", "end", "limit", "slots"}`` — «Cədvəldə var, qeydə alınmayıb»."""
    today = today or timezone.localdate()
    end = min(window["end"], today - _dt.timedelta(days=1))
    # Tavan pəncərənin SONUNDAN sayılır — keçmiş semestrə baxan kafedra müdiri də nəticə görür.
    start = max(window["start"], end - _dt.timedelta(days=LOOKBACK_DAYS))
    # ``slots`` = əhatədəki cədvəl slotlarının sayı — 0 olanda bölmə kartı ümumiyyətlə göstərmir.
    empty = {"count": 0, "items": [], "start": start, "end": end, "limit": ITEM_LIMIT, "slots": 0}
    scope = _scope_q(user, organization, supervisor=supervisor)
    if scope is None or start > end:
        return empty
    # Silinmiş slotlar da oxunur, amma yalnız pəncərədə hələ qüvvədə olanlar (bax `_occurrences`).
    slots_qs = (
        ScheduleSlot.all_objects.filter(organization=organization, is_parked=False)
        .filter(Q(is_deleted=False) | Q(deleted_at__date__gt=start))
        .filter(scope)
    )
    slots_qs = slots_qs.filter(offering__period__start_date__lte=end, offering__period__end_date__gte=start)
    if periods is not None:
        slots_qs = slots_qs.filter(offering__period__in=periods)
    slots_qs = apply_slot_filters(slots_qs, filters, supervisor=supervisor)

    raw = f"{slots_qs.order_by().values('id').query}|{start}|{end}"
    key = "registrar:lessons_log_unrecorded:" + hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return dict(cached)

    slots = list(
        slots_qs.select_related(
            "offering__period", "offering__subject", "offering__group", "offering__instructor"
        ).order_by("weekday", "start_time")
    )
    if not slots:
        cache.set(key, empty, CACHE_TTL)
        return empty
    held: dict = {}
    # Alt-sorğu (IN (SELECT …)): org-wide nəzarətçidə minlərlə açılış id-si parametr siyahısına düşmür.
    for offering_id, day, start_time, kind in Lesson.objects.filter(
        offering_id__in=slots_qs.values("offering_id"), date__gte=start, date__lte=end
    ).values_list("offering_id", "date", "start_time", "kind"):
        held.setdefault((offering_id, day), []).append((start_time, kind))

    due: dict = {}
    for slot in slots:
        for day in _occurrences(slot, start, end):
            due.setdefault((slot.offering_id, day), []).append(slot)
    missing = []
    for (offering_id, day), day_slots in due.items():
        for slot in _unmatched(day_slots, held.get((offering_id, day), ())):
            missing.append((day, slot))
    missing.sort(key=lambda item: (-item[0].toordinal(), item[1].start_time))  # yeni gün əvvəl, gün içində saat sırası

    items = []
    for day, slot in missing[:ITEM_LIMIT]:
        offering = slot.offering
        items.append(
            {
                "date": day,
                "start": slot.start_time,
                "end": slot.end_time,
                "kind": slot.kind,
                "kind_label": str(slot.get_kind_display()),
                "subject": getattr(offering.subject, "name", "") or "",
                "group": getattr(offering.group, "name", "") or "",
                "teacher": _teacher_label(offering.instructor),
                "room": slot.room,
                "journal_url": reverse("registrar:journal_detail", args=[offering.pk]),
            }
        )
    result = {
        "count": len(missing),
        "items": items,
        "start": start,
        "end": end,
        "limit": ITEM_LIMIT,
        "slots": len(slots),
    }
    cache.set(key, result, CACHE_TTL)
    return result


__all__ = ["CACHE_TTL", "ITEM_LIMIT", "LOOKBACK_DAYS", "apply_slot_filters", "unrecorded_slots"]
