"""«Cədvəl idarəetməsi»nin müəllim seçicisi: seçilmiş DÖVRDƏ AKTİV müəllimlər (sahib, 2026-10-25).

Sahibin tələbi: «Müəllim axtar yerində ancaq AKTİV müəllimlər görünsün — həmin ildəki. Köhnə ilə baxanda,
köhnədə aktiv idisə, ona görünə bilər.» Əvvəl seçici əhatədəki açılışların jurnal sahiblərindən +
slot müəllimlərindən qurulurdu və hesabın indiki vəziyyətinə baxmırdı: bloklanmış, işdən çıxmış və ya o
semestrdə heç bir yükü olmayan müəllim də siyahıda idi.

QAYDA
-----
Dövrün müəllimi (``period_teacher_q``) — həmin ``AcademicPeriod`` üçün aşağıdakılardan BİRİ:

(a) dərs yükü bölgüsü — ``workload.TeacherAssignment`` (sətrin dövrü, dövrsüz sətirdə isə tədris ili);
(b) açılışın jurnal sahibi (``CourseOffering.instructor``) və ya dərsin müəllimi (``Lesson.instructor``);
(c) dövrün açılışlarında cədvəl slotunun müəllimi (``ScheduleSlot.instructor``).

(b) və (c) yalnız aktorun ƏHATƏSİNDƏKİ açılışlardan götürülür (fail-closed); (a) isə həmin əhatənin qrupları /
kafedra fənləri üzrə süzülür (``schedule_manage.scoped_assignments``).

CARİ və ya gələcək dövr (``end_date`` keçməyib) üçün əlavə qapı: hesab aktiv (``is_active``), silinməmiş,
arxivlənməmiş (``access_state``) VƏ təşkilatda aktiv müəllim üzvlüyü (``grade.input`` rolu) olmalıdır —
yazı yolundakı (``schedule_slot_teachers.authorized_teacher_ids``) dəstlə EYNİ. BİTMİŞ dövrə baxanda qapı
YOXDUR: o vaxt dərs deyən hər kəs (hesabı indi bloklanmış olsa da) görünür.

PERFORMANS: hər şey BİR istifadəçi sorğusunda alt-sorğularla (+ rol id-ləri üçün bir kiçik sorğu).
"""

from __future__ import annotations

import datetime

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

#: Girişi bağlayan ``UserProfile.access_state`` dəyərləri (``accounts.models.UserProfile.AccessState``) —
#: registrar ``apps.accounts``-u import etmir (module_deps), ona görə sətir sabitləri.
_BLOCKED_ACCESS_STATES = ("staged", "archived")
_CANCELLED_TASK = "cancelled"


def is_historical_period(period, *, today: datetime.date | None = None) -> bool:
    """Dövr BİTİBMİ (``end_date`` keçib) — bitmişdə hesab-vəziyyət qapısı tətbiq olunmur."""
    end_date = getattr(period, "end_date", None)
    if isinstance(end_date, datetime.datetime):
        end_date = end_date.date()
    return bool(end_date and end_date < (today or timezone.localdate()))


def instructor_role_ids(organization) -> list:
    """Aktiv ``grade.input`` daşıyan rolların id-ləri (jurnal sahibi ola bilən rollar) — bir sorğu."""
    from core.permissions import has_permission

    from .integrity import INSTRUCTOR_PERMISSION

    Role = django_apps.get_model("organizations", "Role")
    return [
        role_id
        for role_id, permissions in Role.objects.filter(organization=organization, is_active=True).values_list(
            "id", "permissions"
        )
        if has_permission(list(permissions or []), INSTRUCTOR_PERMISSION)
    ]


def _active_teacher_filter(organization) -> Q | None:
    """Cari dövrün hesab-vəziyyət qapısı (``User`` üzərində Q); heç bir müəllim rolu yoxdursa ``None``."""
    role_ids = instructor_role_ids(organization)
    if not role_ids:
        return None
    Membership = django_apps.get_model("organizations", "Membership")
    members = Membership.objects.filter(
        organization=organization,
        organization__is_active=True,
        is_active=True,
        role__is_active=True,
        role_id__in=role_ids,
    ).values("user_id")
    return (
        Q(is_active=True, pk__in=members)
        & ~Q(profile__is_deleted=True)
        & ~Q(profile__access_state__in=_BLOCKED_ACCESS_STATES)
    )


def assignments_for_period(organization, period):
    """Dövrün dərs yükü bölgüsü (müəllimi təyin olunmuş, ləğv olunmamış tapşırıqlar) — ``TeacherAssignment``."""
    Assignment = django_apps.get_model("workload", "TeacherAssignment")
    return (
        Assignment.objects.filter(organization=organization, teacher__isnull=False)
        .filter(Q(row__period=period) | Q(row__period__isnull=True, row__task__academic_year=period.academic_year))
        .exclude(row__task__status=_CANCELLED_TASK)
    )


def period_teacher_q(*, offerings, assignments=None) -> Q:
    """``User`` üzərində Q: (a) bölgü + (b) jurnal sahibi / dərsin müəllimi + (c) slot müəllimi.

    ``offerings`` — aktorun əhatəsindəki (və dövrə görə süzülmüş) açılış queryset-i; ``assignments`` —
    əhatəyə düşən ``TeacherAssignment`` queryset-i (``None`` — bölgü nəzərə alınmır)."""
    from .models import Lesson, ScheduleSlot

    offering_ids = offerings.values("pk")
    q = Q(pk__in=offerings.exclude(instructor__isnull=True).values("instructor_id"))
    q |= Q(pk__in=Lesson.objects.filter(offering__in=offering_ids, instructor__isnull=False).values("instructor_id"))
    q |= Q(
        pk__in=ScheduleSlot.objects.filter(offering__in=offering_ids, instructor__isnull=False, is_parked=False).values(
            "instructor_id"
        )
    )
    if assignments is not None:
        q |= Q(pk__in=assignments.values("teacher_id"))
    return q


def period_teacher_rows(*, organization, period, offerings, assignments=None, today=None) -> list[dict]:
    """Seçicinin sətirləri ``[{"id": "<pk>", "name": "Ad Soyad"}]`` — ada görə sıralı.

    Cari / gələcək dövrdə yalnız AKTİV müəllimlər, bitmiş dövrdə o vaxtkı bütün müəllimlər (modul sənədinə bax)."""
    users = get_user_model().objects.filter(period_teacher_q(offerings=offerings, assignments=assignments))
    if period is not None and not is_historical_period(period, today=today):
        gate = _active_teacher_filter(organization)
        if gate is None:
            return []
        users = users.filter(gate)
    rows = {}
    for pk, first_name, last_name, username in users.values_list("pk", "first_name", "last_name", "username"):
        full = f"{first_name or ''} {last_name or ''}".strip()
        rows[str(pk)] = full or str(username or "")
    return [{"id": key, "name": name} for key, name in sorted(rows.items(), key=lambda item: (item[1], item[0]))]


__all__ = [
    "assignments_for_period",
    "instructor_role_ids",
    "is_historical_period",
    "period_teacher_q",
    "period_teacher_rows",
]
