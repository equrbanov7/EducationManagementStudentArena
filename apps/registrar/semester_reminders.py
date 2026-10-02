"""«Semestr hazırlığı» → «Xatırlat» — kafedra üzrə bildirişlər (sahib 2026-10-03).

Kimə nə gedir (hər alıcıya BİR, şəxsi bildiriş):

* **müəllim** — öz fənlərində sillabus təsdiqlənməyib / jurnalda dərs yazılmır (fənn · qrup siyahısı ilə).
  Cədvəl müəllimin işi deyil (Tədris şöbəsi qurur) — müəllimə yazılmır;
* **kafedra rəhbəri + kafedra rolları** — kafedranın xülasəsi: müəllimsiz / sillabussuz / cədvəlsiz /
  jurnalı yazılmayan fənlərin sayı (müəllim təyinatı onların işidir).

Spam qapısı: eyni dövr × kafedra üçün ``REMIND_COOLDOWN_SECONDS`` ərzində yalnız BİR göndəriş (keş).
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
    ("no_schedule", "dərs cədvəli yoxdur"),
    ("no_journal", "jurnalda dərs yazılmır"),
)


def cooldown_key(period, chair_id: str) -> str:
    return f"semester-readiness-remind:{period.pk}:{chair_id or 'none'}"


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


def send_reminders(organization, period, chair_unit, *, actor) -> dict:
    """Bildirişləri göndərir. ``{"teachers": N, "chair_members": M, "throttled": bool}``."""
    from django.contrib.auth import get_user_model

    from apps.notifications.models import NotificationType
    from apps.notifications.public import create_notification, create_notification_for_users

    from .semester_actions import chair_recipients

    chair_id = str(chair_unit.pk) if chair_unit is not None else ""
    key = cooldown_key(period, chair_id)
    if cache.get(key):
        return {"teachers": 0, "chair_members": 0, "throttled": True}

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

    cache.set(key, 1, REMIND_COOLDOWN_SECONDS)
    return {"teachers": sent_teachers, "chair_members": sent_chair, "throttled": False}


__all__ = ["REMIND_COOLDOWN_SECONDS", "build_messages", "cooldown_key", "send_reminders"]
