"""«Semestr hazırlığı» → «Xatırlat» — kafedra üzrə bildirişlər (sahib 2026-10-03).

Kimə nə gedir (hər alıcıya BİR, şəxsi bildiriş):

* **müəllim** — öz fənlərində sillabus təsdiqlənməyib / jurnalda dərs yazılmır (fənn · qrup siyahısı ilə).
  Cədvəl müəllimin işi deyil — müəllimə yazılmır;
* **cədvəli quranlar** (2026-10-19 düzəlişi) — dərs cədvəlini Tədris şöbəsi YOX, ``schedule.manage`` açarı olan
  dekanlıq / koordinator (və öz fənləri üçün kafedra) qurur. «Cədvəl yoxdur» fənlərinin QRUPUNU əhatə edən
  BÖLMƏ (UNIT) səviyyəli ``schedule.manage`` üzvlərinə (dekanlıq, fakültə/ixtisas koordinatoru) fənn · qrup
  siyahısı ilə ayrıca bildiriş gedir; təşkilat səviyyəli (mərkəzi) açar sahiblərinə — yox (xatırlatmanı onlar
  göndərir). Kafedra üzvü artıq xülasəni alırsa, ona ikinci bildiriş getmir;
* **kafedra rəhbəri + kafedra rolları** — kafedranın xülasəsi: müəllimsiz / sillabussuz / cədvəlsiz /
  jurnalı yazılmayan fənlərin sayı (müəllim təyinatı onların işidir; cədvəl sətri kimin qurduğunu yazır).

Spam qapısı: eyni dövr × kafedra üçün ``REMIND_COOLDOWN_SECONDS`` ərzində yalnız BİR göndəriş (keş); cədvəl
quranlara əlavə olaraq ALICI × dövr üzrə də (N kafedranı əhatə edən dekanlıq 12 saatda bir bildiriş alır).
Bildiriş mətni Azərbaycanca saxlanılır — mövcud semestr bildirişləri ilə eyni qayda.
"""

from __future__ import annotations

from django.core.cache import cache

from .semester_readiness import offering_issues

#: Eyni kafedraya təkrar xatırlatma arası (12 saat).
REMIND_COOLDOWN_SECONDS = 12 * 60 * 60

#: Bir bildirişdə sadalanan fənn sayının həddi (qalanı «və daha N» olur).
MAX_LISTED = 6

_TEACHER_LINES = {
    "no_syllabus": "Sillabus təsdiqlənməyib",
    "no_journal": "Jurnalda dərs yazılmır",
}
_CHAIR_LINES = (
    ("no_teacher", "müəllim təyin olunmayıb"),
    ("no_syllabus", "sillabus təsdiqlənməyib"),
    ("no_schedule", "dərs cədvəli yoxdur (cədvəli dekanlıq / koordinator qurur)"),
    ("no_journal", "jurnalda dərs yazılmır"),
)


def cooldown_key(period, chair_id: str) -> str:
    return f"semester-readiness-remind:{period.pk}:{chair_id or 'none'}"


def schedule_owner_cooldown_key(period, user_id) -> str:
    return f"semester-readiness-schedule-owner:{period.pk}:{user_id}"


def _listed(items: list) -> str:
    shown = ", ".join(items[:MAX_LISTED])
    extra = len(items) - MAX_LISTED
    return f"{shown} və daha {extra}" if extra > 0 else shown


def build_messages(organization, period, chair_id: str) -> dict:
    """``{"teachers": {user_id: mətn}, "chair": mətn|"", "counts": {...}}`` — göndərmədən (testlənə bilən)."""
    per_teacher: dict = {}
    counts = {"no_teacher": 0, "no_syllabus": 0, "no_schedule": 0, "no_journal": 0}
    for item in offering_issues(organization, period).values():
        if str(item["chair_id"] or "") != (chair_id or ""):
            continue
        for issue in item["issues"]:
            counts[issue] += 1
        if item["instructor_id"] is None:
            continue
        label = f"{item['subject']} · {item['group']}".strip(" ·")
        for issue in item["issues"]:
            if issue in _TEACHER_LINES:
                per_teacher.setdefault(item["instructor_id"], {}).setdefault(issue, []).append(label)

    teachers = {
        user_id: "\n".join(f"• {_TEACHER_LINES[issue]}: {_listed(labels)}" for issue, labels in issues.items())
        for user_id, issues in per_teacher.items()
    }
    chair_lines = [f"• {counts[key]} fənn — {text}" for key, text in _CHAIR_LINES if counts[key]]
    return {"teachers": teachers, "chair": "\n".join(chair_lines), "counts": counts}


def schedule_owner_messages(organization, period, chair_id: str, *, exclude_ids=()) -> dict:
    """``{user_id: (user, mətn)}`` — «Cədvəl yoxdur» fənlərinin qrupunu əhatə edən UNIT səviyyəli ``schedule.manage``.

    ALICILAR bu kafedranın «Cədvəl yoxdur» fənlərindən seçilir; MƏTN isə alıcının əhatəsindəki BÜTÜN kafedraların
    cədvəlsiz fənlərini birləşdirir (rəy 2026-10-19): «Xatırlat» kafedra üzrədir, N kafedranı əhatə edən dekanlıq
    bir bildirişdə tam siyahını alır, təkrar göndəriş isə alıcı başına soyuma ilə kəsilir (``send_reminders``).
    Sorğu: problem xəritəsi (``offering_issues``) + açılışlar 1 + üzvlüklər 1.
    """
    from django.apps import apps as django_apps

    from apps.organizations.public import ancestor_unit_ids
    from core.constants import RoleScopeType
    from core.permissions import has_permission

    from .models import CourseOffering
    from .schedule_manage import SCHEDULE_PERMISSION

    issues = offering_issues(organization, period)
    all_ids = [offering_id for offering_id, item in issues.items() if "no_schedule" in item["issues"]]
    chair_ids = {
        offering_id for offering_id in all_ids if str(issues[offering_id]["chair_id"] or "") == (chair_id or "")
    }
    if not chair_ids:
        return {}
    offerings = list(
        CourseOffering.objects.filter(pk__in=all_ids, group__isnull=False).select_related("group", "subject")
    )
    covering = {offering.pk: set(ancestor_unit_ids(offering.group)) for offering in offerings}
    unit_ids = set().union(*(covering[offering.pk] for offering in offerings if offering.pk in chair_ids))
    Membership = django_apps.get_model("organizations", "Membership")
    memberships = [
        membership
        for membership in Membership.objects.filter(
            organization=organization,
            is_active=True,
            role__is_active=True,
            scope_unit_id__in=list(unit_ids),
            user__is_active=True,
        )
        .exclude(role__scope_type=RoleScopeType.ORGANIZATION)
        .select_related("user", "role")
        if has_permission(list(membership.role.permissions or []), SCHEDULE_PERMISSION)
        and membership.user_id not in set(exclude_ids)
    ]
    per_user: dict = {}
    for offering in offerings:  # bütün kafedralar — alıcının əhatəsindəki tam siyahı
        label = f"{offering.subject.name} · {offering.group.name}"
        for membership in memberships:
            if str(membership.scope_unit_id) in covering[offering.pk]:
                per_user.setdefault(membership.user_id, (membership.user, []))[1].append(label)
    return {
        user_id: (user, f"• Dərs cədvəlində yeri yoxdur: {_listed(sorted(set(labels)))}")
        for user_id, (user, labels) in per_user.items()
    }


def send_reminders(organization, period, chair_unit, *, actor) -> dict:
    """Bildirişləri göndərir. ``{"teachers": N, "chair_members": M, "throttled": bool}``."""
    from django.contrib.auth import get_user_model

    from apps.notifications.models import NotificationType
    from apps.notifications.public import create_notification, create_notification_for_users

    from .semester_actions import chair_recipients

    chair_id = str(chair_unit.pk) if chair_unit is not None else ""
    key = cooldown_key(period, chair_id)
    if cache.get(key):
        return {"teachers": 0, "chair_members": 0, "schedule_owners": 0, "schedule_owners_recent": 0, "throttled": True}

    messages = build_messages(organization, period, chair_id)
    title = f"Semestr hazırlığı: {period.year_display} · {period.name}"[:255]
    metadata = {"event": "semester_readiness_reminder", "period_id": str(period.pk), "chair_id": chair_id}

    users = get_user_model().objects.filter(pk__in=list(messages["teachers"]), is_active=True)
    sent_teachers = 0
    for user in users:
        if user.pk == getattr(actor, "pk", None):
            continue
        create_notification(
            recipient=user,
            title=title,
            message=(
                "Fənlərinizdə çatışmayanlar var — semestrin normal getməsi üçün düzəldin:\n"
                f"{messages['teachers'][user.pk]}"
            ),
            link="/jurnal/",
            notification_type=NotificationType.SYSTEM,
            organization=organization,
            metadata=metadata,
        )
        sent_teachers += 1

    sent_chair = 0
    recipients = []
    if chair_unit is not None and messages["chair"]:
        recipients = chair_recipients(organization, chair_unit, actor_id=getattr(actor, "pk", None))
        if recipients:
            create_notification_for_users(
                recipients=recipients,
                title=title,
                message=f"«{chair_unit.name}» kafedrası üzrə:\n{messages['chair']}",
                link="/accounts/profile/?section=workload-distribution",
                notification_type=NotificationType.SYSTEM,
                organization=organization,
                metadata=metadata,
            )
            sent_chair = len(recipients)

    sent_schedule = skipped_schedule = 0
    if messages["counts"]["no_schedule"]:
        skip = {getattr(actor, "pk", None), *(user.pk for user in recipients)}
        for user_id, (user, text) in schedule_owner_messages(organization, period, chair_id, exclude_ids=skip).items():
            # Alıcı başına soyuma: N kafedranı əhatə edən dekanlıq 12 saatda BİR «Cədvəl yoxdur» bildirişi alır
            # (mətn onsuz da əhatəsindəki bütün kafedraların siyahısıdır).
            owner_key = schedule_owner_cooldown_key(period, user_id)
            if cache.get(owner_key):
                skipped_schedule += 1
                continue
            cache.set(owner_key, 1, REMIND_COOLDOWN_SECONDS)
            create_notification(
                recipient=user,
                title=title,
                message=f"Bu fənlərin dərs cədvəli qurulmayıb — cədvəli siz qurursunuz:\n{text}",
                link="/accounts/profile/?section=schedule-manage",
                notification_type=NotificationType.SYSTEM,
                organization=organization,
                metadata={**metadata, "audience": "schedule_owner"},
            )
            sent_schedule += 1

    cache.set(key, 1, REMIND_COOLDOWN_SECONDS)
    return {
        "teachers": sent_teachers,
        "chair_members": sent_chair,
        "schedule_owners": sent_schedule,
        "schedule_owners_recent": skipped_schedule,
        "throttled": False,
    }


__all__ = [
    "REMIND_COOLDOWN_SECONDS",
    "build_messages",
    "cooldown_key",
    "schedule_owner_cooldown_key",
    "schedule_owner_messages",
    "send_reminders",
]
