"""Dərs cədvəlinin İDARƏSİ — icazə, əhatə və slot validasiyası (OXU qatı).

Yazma qatı ayrıdır: :mod:`apps.registrar.schedule_manage_actions`.

──────────────────────────────────────────────────────────────────────────────
QƏRAR (sahibin tələbi, 2026-09)
──────────────────────────────────────────────────────────────────────────────
Əvvəllər cədvəl slotunu YALNIZ dərsi aparan müəllim (və org sahibi/superuser)
əlavə edib silə bilirdi (``journal_access.is_direct_editor``). Bu, universitet
reallığına ziddir: cədvəli müəllim yox, **proqram koordinatoru / dekanlıq /
RİM** qurur. Ona görə qapı indi kanonik icazə açarındadır::

    schedule.manage   → slot əlavəsi/silinməsi (UNIT rollarında `scope_unit` alt-ağacı)

* ``program_coordinator`` — öz ixtisasının alt-ağacı (əsas sahib);
* ``ikt_rehber`` (RİM)    — org-wide;
* ``dean`` / ``chair_head`` — öz fakültə/kafedra alt-ağacı;
* ``rector`` / ``vice_rector`` / sahib / superuser — ``*`` ilə org-wide.

**Adi müəllimdə açar QƏSDƏN YOXDUR.** Müəllim öz həftəlik cədvəlini görür
(``my-schedule``), amma slot yaza/silə bilmir — açılışın müəllimi olmaq artıq
səlahiyyət vermir. Açarı olan müəllimə isə ADİ qaydalar tətbiq olunur (əhatə +
konflikt), yəni açar permission-editordan verilə bilər.

MODUL SƏRHƏDİ: registrar ``apps.organizations``-u Python səviyyəsində İMPORT
ETMİR (dövr yaranardı) — model app registry ilə həll olunur və alt-ağac
yoxlaması ``OrgUnit.user_permission_scope`` daxilindədir (``journal_scope`` naxışı).
"""

from __future__ import annotations

import datetime

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar import journal_scope, schedule
from apps.registrar.models import CourseOffering, ScheduleSlot, SlotKind, WeekType

#: Cədvəl slotlarını idarə etmək icazəsi (kataloq: organizations.permissions).
SCHEDULE_PERMISSION = "schedule.manage"

#: Yalnız-baxış açarı. 2026-10-13 (rol auditi B11): əvvəl heç nəyi açmırdı; indi «Cədvəl idarəetməsi»
#: bölməsini YALNIZ-OXU açır (prorektor, Tədris şöbəsi, RİM əməkdaşı, qəyyum, inzibati bölmə). Bütün
#: yazı səthləri (``can_manage_offering`` / ``scoped_groups`` / ``scoped_offerings`` default-u) yenə
#: ``schedule.manage`` tələb edir — oxu funksiyaları ayrıca ``permission=`` ilə çağırılır.
SCHEDULE_VIEW_PERMISSION = "schedule.view"

_CTX = "registrar.schedule_manage"


def _org_unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


# ── İcazə + əhatə ────────────────────────────────────────────────────────────


def actor_scope(user, organization, permission=SCHEDULE_PERMISSION):
    """Aktorun ``schedule.manage`` (və ya verilən açarın) struktur əhatəsi (``UnitScope``)."""
    return _org_unit_model().user_permission_scope(user, organization, permission)


def can_manage(user, organization) -> bool:
    """İcazə struktur əhatəsi verirmi (org və ya unit) — fail-closed."""
    if organization is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return True
    return actor_scope(user, organization).has_structure_access


def can_view(user, organization) -> bool:
    """«Cədvəl idarəetməsi»ni ən azı YALNIZ-OXU açmaq hüququ (B11): ``schedule.manage`` və ya
    ``schedule.view`` struktur əhatəsi. Yazma hüququ VERMİR — o, :func:`can_manage`-dədir."""
    if can_manage(user, organization):
        return True
    return actor_scope(user, organization, SCHEDULE_VIEW_PERMISSION).has_structure_access


def read_permission(user, organization) -> str:
    """Oxu siyahılarının əhatə açarı: redaktor ``schedule.manage``, qalanı ``schedule.view`` əhatəsi.

    Redaktə hüququ olan aktor öz REDAKTƏ əhatəsini görür (siyahıda redaktə edə bilmədiyi qrup
    çıxmasın); yalnız-oxu aktor ``schedule.view`` əhatəsini."""
    return SCHEDULE_PERMISSION if can_manage(user, organization) else SCHEDULE_VIEW_PERMISSION


def can_manage_offering(user, organization, offering) -> bool:
    """Bu KONKRET açılışın cədvəlini aktor idarə edə bilirmi (fail-closed).

    Superuser/org sahibi həmişə; qalanlar üçün ``schedule.manage`` + açılışın
    QRUP bölməsinin aktorun alt-ağacında olması (və ya :func:`_extra_offering_q` —
    kafedranın öz fənni / aktorun tyutoru olduğu qrup). Açılışın MÜƏLLİMİ olmaq tək
    başına səlahiyyət VERMİR (sahibin qərarı).
    """
    if offering is None or organization is None:
        return False
    if getattr(offering, "organization_id", None) != getattr(organization, "pk", None):
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return True
    if journal_scope.offering_in_actor_scope(user, organization, offering, permission=SCHEDULE_PERMISSION):
        return True
    extra = _extra_offering_q(user, organization, actor_scope(user, organization, SCHEDULE_PERMISSION), widened=True)
    return extra is not None and CourseOffering.objects.filter(pk=offering.pk).filter(extra).exists()


def can_manage_group_subject(user, organization, group, subject) -> bool:
    """(qrup, fənn) cütünün cədvəlini aktor qura bilirmi — açılış YARADILMAZDAN / dəyişdirilməzdən ƏVVƏL.

    Review 2026-10-17 (FIX-D): «Xanaya dərs qoy» açılışı ``resolve_offering(create=True)`` ilə yaradır / müəllim
    bağlayır; ``ATOMIC_REQUESTS`` altında sonrakı 403 bu yazını GERİ ALMIR. Ona görə səlahiyyət cüt üzrə əvvəlcədən
    yoxlanılır — :func:`can_manage_offering` ilə EYNİ qayda (qrup alt-ağacı, kafedranın öz fənni, tyutorun qrupu).
    """
    if group is None or subject is None or organization is None:
        return False
    if getattr(group, "organization_id", None) != organization.pk:
        return False
    if getattr(subject, "organization_id", None) != organization.pk:
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return True
    scope = actor_scope(user, organization)
    if not scope.has_structure_access:
        return False
    if scope.is_org_wide:
        return True
    in_subtree = _org_unit_model().objects.filter(organization=organization, pk=group.pk).filter(scope.unit_subtree_q())
    if in_subtree.exists() or (group.head_id is not None and group.head_id == user.pk and group.is_active):
        return True
    chair_q = _chair_subject_q(organization, scope, prefix="")
    if chair_q is None:
        return False
    from apps.registrar.models import Subject

    return Subject.objects.filter(organization=organization, pk=subject.pk).filter(chair_q).exists()


def _chair_subject_q(organization, scope, *, prefix="subject__"):
    """QA 2026-10-17 F-05: KAFEDRA kökləri üçün açılışın FƏNNİNİN sahib kafedrası (``subject.chair_unit``).

    Bu universitetdə qruplar kafedranın deyil, fakültənin altındadır — kafedra alt-ağacında qrup yoxdur,
    ona görə kafedra müdiri (və kafedraya təyin olunmuş tyutor) «Cədvəl idarəetməsi»ndə 0 qrup görürdü.
    Kafedra kökünün əhatəsi indi ÖZ KAFEDRASININ fənlərinin açılışlarıdır (başqa kafedranın fənni yox).
    Yalnız ``chair`` / ``department`` tipli köklər (``Subject.chair_unit`` ikisini də qəbul edir);
    fakültə / ixtisas / qrup kökləri əvvəlki kimi qrup alt-ağacı ilə qalır.
    """
    from apps.organizations.public import kafedra_unit_types

    if not scope.is_unit_scoped or not scope.unit_ids:
        return None
    chairs = list(
        _org_unit_model()
        .objects.filter(
            organization=organization,
            pk__in=list(scope.unit_ids),
            unit_type__in=kafedra_unit_types(organization),
            is_active=True,
        )
        .values_list("pk", "path")
    )
    if not chairs:
        return None
    q = Q(**{f"{prefix}chair_unit_id__in": [pk for pk, _path in chairs]})
    for _pk, path in chairs:
        if path:
            q |= Q(**{f"{prefix}chair_unit__path__startswith": f"{path}/"})
    return q


def _extra_offering_q(user, organization, scope, *, widened=False):
    """Qrup alt-ağacından ƏLAVƏ açılış əhatəsi: aktorun TYUTORU olduğu qruplar (+ ``widened``: kafedra fənləri).

    Tyutor qrupun «rəhbəri»dir (``OrgUnit.head`` — qrup reyestrindəki «Tyutor» sütunu); açar
    (``schedule.manage``) struktur əhatəsi verirsə, öz qruplarının cədvəlini də qurur — bu, QRUP səviyyəli
    əhatədir (dar). Kafedra fənləri yalnız AÇILIŞ səviyyəlidir (``widened=True``): redaktorun oxu görünüşü və
    hüceyrə əməlləri; qrup səviyyəli yazılar (növbə siyasəti, generator əhatəsi, dərc) dar əhatədə qalır.
    Əhatəsiz aktora heç nə əlavə olunmur (fail-closed). ``None`` — əlavə əhatə yoxdur.
    """
    if not scope.is_unit_scoped:
        return None
    headed = Q(group__head_id=getattr(user, "pk", None), group__is_active=True)
    extra = _chair_subject_q(organization, scope) if widened else None
    return headed if extra is None else (extra | headed)


def scoped_groups(user, organization, *, permission=SCHEDULE_PERMISSION, widened=False):
    """Aktorun cədvəlini qura (``permission=schedule.view`` ilə: görə) biləcəyi QRUP bölmələri (fail-closed).

    Defolt DAR əhatədir (alt-ağac + tyutorun qrupları) — qrup səviyyəli yazılar və generator bunu işlədir.
    ``widened=True`` kafedra fənninin açılışı olan qrupları da qatır (yalnız redaktorun oxu görünüşü / hüceyrə
    seçimi; hüceyrə yazısı əlavə olaraq :func:`can_manage_group_subject` ilə yoxlanılır)."""
    from core.constants import OrgUnitType

    org_unit_model = _org_unit_model()
    if organization is None:
        return org_unit_model.objects.none()
    base = org_unit_model.objects.filter(organization=organization, is_active=True, unit_type=OrgUnitType.GROUP)
    if getattr(user, "is_superuser", False) or getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return base.order_by("name")
    scope = actor_scope(user, organization, permission)
    if not scope.has_structure_access:
        return org_unit_model.objects.none()
    if scope.is_org_wide:
        return base.order_by("name")
    groups_q = scope.unit_subtree_q()
    extra = _extra_offering_q(user, organization, scope, widened=widened)
    if extra is not None:
        extra_groups = CourseOffering.objects.filter(organization=organization, is_active=True).filter(extra)
        groups_q |= Q(pk__in=extra_groups.values("group_id"))
    return base.filter(groups_q).order_by("name")


def scoped_offerings(user, organization, *, period=None, group=None, permission=SCHEDULE_PERMISSION, widened=False):
    """Aktorun cədvəlinə slot yaza (``permission=schedule.view`` ilə: görə) biləcəyi açılışlar (fail-closed).

    ``widened`` — :func:`scoped_groups` ilə eyni məna (kafedra fənləri yalnız redaktorun oxu görünüşündə)."""
    if organization is None:
        return CourseOffering.objects.none()
    queryset = CourseOffering.objects.filter(organization=organization, is_active=True)
    if period is not None:
        queryset = queryset.filter(period=period)
    if group is not None:
        queryset = queryset.filter(group=group)
    if getattr(user, "is_superuser", False) or getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return queryset
    scope = actor_scope(user, organization, permission)
    if not scope.has_structure_access:
        return CourseOffering.objects.none()
    if scope.is_org_wide:
        return queryset
    units = _org_unit_model().objects.filter(organization=organization).filter(scope.unit_subtree_q())
    offerings_q = Q(group__in=units.values("pk"))
    extra = _extra_offering_q(user, organization, scope, widened=widened)
    if extra is not None:
        offerings_q |= extra
    return queryset.filter(offerings_q)


# ── Slot validasiyası (PREVENT, don't save) ──────────────────────────────────


def parse_payload(data) -> tuple[dict, dict]:
    """Xam POST/JSON sözlüyünü təmizlənmiş dəyərlərə çevirir.

    Qaytarır ``(cleaned, errors)``. Vaxt həm standart dərs saatı seçimi
    (``time_slot`` = "HH:MM|HH:MM"), həm də sərbəst ``start_time``/``end_time``
    ilə verilə bilər — birincinin üstünlüyü var.
    """
    from django.utils.dateparse import parse_time

    errors: dict = {}
    cleaned: dict = {}

    try:
        weekday = int(str(data.get("weekday") or "").strip() or 0)
    except (TypeError, ValueError):
        weekday = 0
    if not 1 <= weekday <= 7:
        errors["weekday"] = pgettext(_CTX, "Həftənin günü 1–7 aralığında olmalıdır.")
    cleaned["weekday"] = weekday

    start_time, end_time = schedule.parse_time_slot(data.get("time_slot"))
    if start_time is None:
        start_time = parse_time(str(data.get("start_time") or "").strip())
        end_time = parse_time(str(data.get("end_time") or "").strip())
    if start_time is None or end_time is None:
        errors["time_slot"] = pgettext(_CTX, "Başlama və bitmə vaxtı düzgün seçilməlidir.")
    elif end_time <= start_time:
        errors["time_slot"] = pgettext(_CTX, "Bitmə vaxtı başlama vaxtından sonra olmalıdır.")
    cleaned["start_time"] = start_time
    cleaned["end_time"] = end_time

    week_type = str(data.get("week_type") or "").strip()
    cleaned["week_type"] = week_type if week_type in dict(WeekType.choices) else WeekType.ALL
    slot_kind = str(data.get("slot_kind") or data.get("kind") or "").strip()
    cleaned["kind"] = slot_kind if slot_kind in dict(SlotKind.choices) else SlotKind.LECTURE

    room = str(data.get("room") or "").strip()
    # QA 2026-09-05 (P3-22): 300 simvollu auditoriya adı `[:64]` ilə səssizcə
    # 64-ə kəsilirdi (`ScheduleSlot.room` `max_length=64`) — istifadəçiyə heç
    # bir xəbərdarlıq getmirdi. İndi açıq rədd edilir.
    if len(room) > 64:
        errors["room"] = pgettext(_CTX, "Auditoriya adı 64 simvoldan uzun ola bilməz.")
    cleaned["room"] = room
    return cleaned, errors


def period_window_error(offering) -> str:
    """Açılışın dövrü cədvəl yazmağa açıqdırmı — bağlıdırsa səbəb mətni."""
    period = getattr(offering, "period", None)
    end_date = getattr(period, "end_date", None)
    if isinstance(end_date, str):
        try:
            end_date = datetime.date.fromisoformat(end_date)
        except ValueError:
            end_date = None
    elif isinstance(end_date, datetime.datetime):
        end_date = end_date.date()
    if end_date and end_date < timezone.localdate():
        return pgettext(_CTX, "Bu semestr bitib — cədvəl slotu əlavə edilə bilməz.")
    return ""


def duplicate_slot(*, offering, weekday, start_time, end_time, week_type, room, exclude_id=None):
    """Eyni açılış üçün EYNİ slot artıq varmı (təkrar yazılış)."""
    queryset = ScheduleSlot.objects.filter(
        organization_id=offering.organization_id,
        offering=offering,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        week_type=week_type,
    )
    if exclude_id:
        queryset = queryset.exclude(pk=exclude_id)
    room_norm = (room or "").strip().lower()
    for slot in queryset:
        if (slot.room or "").strip().lower() == room_norm:
            return slot
    return None


def conflict_reason(*, offering, conflict, instructor_id=None) -> str:
    """Konfliktin SƏBƏBİ (qrup / müəllim / otaq) — istifadəçiyə açıq mətn.

    Müəllim hər iki tərəfdə EFFEKTİVDİR: ``instructor_id`` yoxlanan slotun öz müəllimi (yoxdursa
    açılışınkı), toqquşan slot üçün ``schedule.effective_instructor_id``."""
    other = conflict.offering
    if offering.group_id and other.group_id == offering.group_id:
        return pgettext(_CTX, "qrup")
    teacher_id = instructor_id or offering.instructor_id
    if teacher_id and str(schedule.effective_instructor_id(conflict)) == str(teacher_id):
        return pgettext(_CTX, "müəllim")
    return pgettext(_CTX, "auditoriya")


def describe_conflict(conflict, *, offering=None, instructor_id=None) -> dict:
    """Konflikt slotunun UI müqaviləsi (JSON) — açar adları dəyişməz."""
    other = conflict.offering
    teacher = schedule.effective_instructor(conflict)
    return {
        "id": str(conflict.pk),
        "reason": (
            conflict_reason(offering=offering, conflict=conflict, instructor_id=instructor_id)
            if offering is not None
            else ""
        ),
        "subject_code": getattr(other.subject, "code", "") or "",
        "subject_name": getattr(other.subject, "name", "") or "",
        "group": getattr(other.group, "name", "") or "",
        "instructor": (getattr(teacher, "get_full_name", lambda: "")() or "").strip()
        or str(getattr(teacher, "username", "") or ""),
        "room": conflict.room or "",
        "weekday": conflict.weekday,
        "start_time": conflict.start_time.strftime("%H:%M"),
        "end_time": conflict.end_time.strftime("%H:%M"),
        "week_type": conflict.week_type,
    }


def check_slot(*, offering, cleaned, exclude_id=None) -> dict:
    """Bütün saxlama-öncəsi yoxlamalar — ``{sahə: mətn}`` (boşdursa təmizdir).

    Sıra qəsdən belədir: dövr pəncərəsi → təkrar → konflikt. Birinci tapılan
    problemə görə qalanları hesablamaq mənasızdır (istifadəçi onsuz da düzəldib
    yenidən göndərəcək), amma sahələr fərqli olduğu üçün hamısı toplanır.
    """
    errors: dict = {}
    window = period_window_error(offering)
    if window:
        errors["period"] = window
    if errors:
        return errors

    duplicate = duplicate_slot(
        offering=offering,
        weekday=cleaned["weekday"],
        start_time=cleaned["start_time"],
        end_time=cleaned["end_time"],
        week_type=cleaned["week_type"],
        room=cleaned["room"],
        exclude_id=exclude_id,
    )
    if duplicate is not None:
        errors["time_slot"] = pgettext(_CTX, "Bu slot artıq cədvəldədir.")
        return errors

    instructor_id = cleaned.get("instructor_id")
    conflict = schedule.find_conflict(
        organization=offering.organization,
        offering=offering,
        weekday=cleaned["weekday"],
        start_time=cleaned["start_time"],
        end_time=cleaned["end_time"],
        week_type=cleaned["week_type"],
        room=cleaned["room"],
        exclude_id=exclude_id,
        kind=cleaned.get("kind"),
        instructor_id=instructor_id,
    )
    if conflict is not None:
        errors["conflict"] = pgettext(_CTX, "Bu vaxt %(subject)s ilə üst-üstə düşür (%(reason)s).") % {
            "subject": getattr(conflict.offering.subject, "code", "") or "",
            "reason": conflict_reason(offering=offering, conflict=conflict, instructor_id=instructor_id),
        }
        errors["_conflict"] = describe_conflict(conflict, offering=offering, instructor_id=instructor_id)
    return errors


def scoped_assignments(user, organization, *, period, permission=SCHEDULE_PERMISSION, widened=False):
    """Aktorun əhatəsinə düşən dövr bölgüsü (``workload.TeacherAssignment``) — müəllim seçicisinin (a) qolu.

    Əhatə :func:`scoped_offerings` ilə eyni məntiqdədir: org-geniş / sahib / superuser — dövrün bütün bölgüsü;
    unit əhatəsi — sətrin qrupu alt-ağacda olan (və ya ``widened``: fənni aktorun kafedrasına aid olan) bölgü.
    Əhatəsiz aktor üçün ``none()`` (fail-closed); təşkilat / dövr yoxdursa ``None``."""
    from . import schedule_teachers

    if organization is None or period is None:
        return None
    queryset = schedule_teachers.assignments_for_period(organization, period)
    if getattr(user, "is_superuser", False) or getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return queryset
    scope = actor_scope(user, organization, permission)
    if not scope.has_structure_access:
        return queryset.none()
    if scope.is_org_wide:
        return queryset
    units = _org_unit_model().objects.filter(organization=organization).filter(scope.unit_subtree_q())
    assignments_q = Q(row__groups__in=units.values("pk"))
    if widened:
        chair_q = _chair_subject_q(organization, scope, prefix="row__subject__")
        if chair_q is not None:
            assignments_q |= chair_q
    return queryset.filter(assignments_q)


def scoped_teacher_rows(offerings, *, organization=None, period=None, assignments=None, today=None) -> list[dict]:
    """«Müəllim cədvəli» seçicisi: seçilmiş DÖVRDƏ aktiv müəllimlər (sahib 2026-10-25, bax :mod:`schedule_teachers`).

    ``offerings`` — aktorun əhatəsindəki açılış queryset-i (``scoped_offerings``). Bölünmüş tədrisdə
    seminarı aparan assistentin öz açılışı olmaya bilər; o da siyahıda olmalıdır ki, koordinator onun
    həftəsini görsün (``get_teacher_schedule`` effektiv müəllimə görə süzür).

    ``organization`` + ``period`` verilibsə: cari/gələcək dövrdə yalnız aktiv hesab + aktiv müəllim üzvlüyü olanlar,
    bitmiş dövrdə o vaxt dərs deyən hər kəs; ``assignments`` — (a) qolu (``scoped_assignments``). Dövrsüz çağırış
    əvvəlki davranışı saxlayır (qapısız, yalnız açılış + slot müəllimləri)."""
    from . import schedule_teachers

    if organization is not None and period is not None:
        return schedule_teachers.period_teacher_rows(
            organization=organization, period=period, offerings=offerings, assignments=assignments, today=today
        )
    users = get_user_model().objects.filter(schedule_teachers.period_teacher_q(offerings=offerings))
    rows = {}
    for user in users:
        full = (user.get_full_name() or "").strip()
        rows[str(user.pk)] = full or user.username
    return [{"id": key, "name": name} for key, name in sorted(rows.items(), key=lambda item: item[1])]


__all__ = [
    "SCHEDULE_PERMISSION",
    "SCHEDULE_VIEW_PERMISSION",
    "actor_scope",
    "can_manage",
    "can_manage_group_subject",
    "can_manage_offering",
    "can_view",
    "check_slot",
    "conflict_reason",
    "describe_conflict",
    "duplicate_slot",
    "parse_payload",
    "period_window_error",
    "read_permission",
    "scoped_assignments",
    "scoped_groups",
    "scoped_offerings",
    "scoped_teacher_rows",
]
