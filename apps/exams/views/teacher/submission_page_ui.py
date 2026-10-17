"""Sual göndərişi səhifələrinin TƏQDİMAT qatı (Paket C, 2026-10-17).

Üç səhifə — müəllim detalı, kafedra baxışı, İmtahan Mərkəzi baxışı — eyni başlığı göstərir:
status nişanı · meta sətri · mərhələ zolağı (``ems_ui/_stepper``) · «növbəti addım» lenti ·
KPI sırası · hadisə lentı (``ems_ui/_timeline``).  Burada yalnız göndərişin artıq yüklənmiş
sahələri oxunur — əlavə SQL sorğusu YOXDUR (``submission_events`` view-dən siyahı kimi gəlir).

Status məntiqi əvvəl üç şablonda ayrı-ayrı ``{% if %}`` zəncirləri idi və köhnə statuslara
(«pending») baxırdı — ``center_review`` göndərişi «Geri qaytarılıb» görünürdü.  İndi tək yer.

msgctxt HƏR çağırışda LİTERAL yazılır (``makemessages`` dəyişən konteksti çıxara bilmir).
Mövcud tərcümələr təkrar işlədilir (eyni ctx + msgid); yenilər
``scripts/i18n_fill_pkg_c_2026_10_17.py``-dədir.
"""

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import pgettext

ROLE_TEACHER = "teacher"
ROLE_CHAIR = "chair"
ROLE_CENTER = "center"

#: Status açarı → badge tonu (kabinet siyahısı ``question_submissions_ui`` ilə eyni rəng dili).
_STATUS_TONES = {
    "draft": "neutral",
    "submitted_to_chair": "warning",
    "chair_revision": "danger",
    "chair_approved": "info",
    "center_review": "info",
    "center_revision": "danger",
    "accepted": "success",
    "rejected": "danger",
}

#: Müəllimin «düzəlt və yenidən göndər» əməli gözlənilən statuslar.
_RETURNED = ("chair_revision", "center_revision", "rejected")


def _when(value):
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return date_format(value, "d.m.Y H:i")


def _person(user):
    if user is None:
        return ""
    return user.get_full_name() or user.username


def status_label(status, *, role):
    labels = {
        "submitted_to_chair": pgettext("accounts.profile.question_submissions", "Kafedra müdirinə göndərilib"),
        "chair_revision": pgettext("accounts.profile.question_submissions", "Kafedra düzəliş istəyib"),
        "chair_approved": pgettext("accounts.profile.question_submissions", "Kafedra təsdiqləyib — İmtahan Mərkəzində"),
        "center_review": pgettext("accounts.profile.question_submissions", "İmtahan Mərkəzi baxır"),
        "center_revision": pgettext("accounts.profile.question_submissions", "İmtahan Mərkəzi düzəliş istəyib"),
        "accepted": pgettext("accounts.profile.question_submissions", "Qəbul"),
        "rejected": (
            pgettext("accounts.profile.question_submissions", "Rədd edilib — düzəldib yenidən göndərə bilərsiniz")
            if role == ROLE_TEACHER
            else pgettext("accounts.profile.question_submissions", "Rədd")
        ),
    }
    return labels.get(status, pgettext("accounts.profile.question_submissions", "Qaralama"))


def status_badge(submission, *, role):
    """``ems_ui/_status_badge.html`` müqaviləsi: ``css_class`` + ``label``."""
    tone = _STATUS_TONES.get(submission.status, "neutral")
    return {
        "css_class": f"ems-badge ems-badge--{tone} ems-badge--wrap",
        "label": status_label(submission.status, role=role),
    }


def _chair_step(submission):
    if submission.routed_to_dean:
        label = pgettext("exams.template.question_chain", "Dekanlıq təsdiqi")
    else:
        label = pgettext("exams.template.question_chain", "Kafedra təsdiqi")
    if submission.is_at_chair:
        state = "current"
    elif submission.status == "chair_revision" or submission.chair_decision == "rejected":
        state = "error"
    elif submission.chair_decision == "approved":
        state = "done"
    else:
        state = "todo"
    parts = [submission.chair_unit.name if submission.chair_unit_id and submission.chair_unit else ""]
    parts.append(_when(submission.chair_reviewed_at))
    return {"label": label, "state": state, "note": " · ".join(part for part in parts if part)}


def _center_step(submission):
    status = submission.status
    if submission.is_at_center:
        state = "current"
    elif status == "center_revision":
        state = "error"
    elif status == "accepted" or (status == "rejected" and submission.reviewed_at):
        state = "done"
    else:
        state = "todo"
    return {
        "label": pgettext("exams.template.question_chain", "İmtahan Mərkəzi"),
        "state": state,
        "note": _when(submission.reached_center_at),
    }


def _final_step(submission):
    if submission.status == "accepted":
        label, state = pgettext("exams.template.question_chain", "Qəbul edildi"), "done"
    elif submission.status == "rejected":
        label, state = pgettext("exams.template.question_chain", "Rədd edildi"), "error"
    else:
        label, state = pgettext("exams.template.question_chain", "Yekun qərar"), "todo"
    return {"label": label, "state": state, "note": _when(submission.reviewed_at)}


def chain_steps(submission):
    """Müəllim → kafedra → mərkəz → yekun: ``ems_ui/_stepper.html`` addımları."""
    sent_note = _when(submission.created_at)
    if submission.resubmission_count:
        sent_note = f"{sent_note} · ×{submission.resubmission_count}"
    first = {
        "label": pgettext("exams.template.question_chain", "Müəllim göndərdi"),
        "state": "done",
        "note": sent_note,
    }
    return [first, _chair_step(submission), _center_step(submission), _final_step(submission)]


def kpi_tiles(submission):
    return [
        {
            "label": pgettext("exams.template.question_submission", "Ümumi sual sayı"),
            "value": submission.question_count,
            "tone": "accent-primary",
        },
        {
            "label": pgettext("exams.template.question_submission", "Xətalı"),
            "value": submission.error_count,
            "tone": "accent-danger" if submission.error_count else None,
        },
        {
            "label": pgettext("exams.template.question_submission", "Xəbərdarlıq"),
            "value": submission.warning_count,
            "tone": "accent-warning" if submission.warning_count else None,
        },
    ]


def _event_label(action):
    labels = {
        "submitted_to_chair": pgettext("exams.template.question_chain", "Kafedra müdirinə göndərildi"),
        "resubmitted_to_chair": pgettext("exams.template.question_chain", "Düzəldilib kafedraya yenidən göndərildi"),
        "chair_approved": pgettext(
            "exams.template.question_chain", "Kafedra təsdiqlədi — İmtahan Mərkəzinə göndərildi"
        ),
        "chair_revision": pgettext("exams.template.question_chain", "Kafedra düzəliş istədi"),
        "chair_rejected": pgettext("exams.template.question_chain", "Kafedra rədd etdi"),
        "center_opened": pgettext("exams.template.question_chain", "İmtahan Mərkəzi baxışa götürdü"),
        "center_accepted": pgettext("exams.template.question_chain", "İmtahan Mərkəzi qəbul etdi"),
        "center_revision": pgettext("exams.template.question_chain", "İmtahan Mərkəzi düzəliş istədi"),
        "center_rejected": pgettext("exams.template.question_chain", "İmtahan Mərkəzi rədd etdi"),
    }
    return labels.get(action)


_EVENT_TONES = {
    "chair_approved": "success",
    "center_accepted": "success",
    "chair_revision": "warning",
    "center_revision": "warning",
    "chair_rejected": "danger",
    "center_rejected": "danger",
    "center_opened": "info",
}


def timeline(events):
    """``ems_ui/_timeline.html`` girişləri — ən yenisi YUXARIDA (lent əlavə-only-dir)."""
    entries = []
    for event in events:
        who = event.actor_label or "—"
        if event.actor_role:
            who = f"{who} · {event.actor_role}"
        entries.append(
            {
                "who": who,
                "when": _when(event.created_at),
                "what": _event_label(event.action) or event.get_action_display(),
                "reason": event.reason,
                "tone": _EVENT_TONES.get(event.action, "primary"),
            }
        )
    entries.reverse()
    if entries:
        entries[0]["current"] = True
    return entries


def _teacher_next(submission, *, can_edit):
    status = submission.status
    note = submission.reviewer_note or submission.chair_note
    cta = {"href": "#qsubEdit", "label": pgettext("exams.template.question_submission", "Düzəlt və yenidən göndər")}
    if status == "submitted_to_chair":
        if submission.routed_to_dean:
            title = pgettext("exams.template.question_submission", "Dekanlığın təsdiqi gözlənilir")
        else:
            title = pgettext("exams.template.question_submission", "Kafedra müdirinin təsdiqi gözlənilir")
        body = pgettext(
            "exams.template.question_submission",
            "Təsdiqdən sonra dəst İmtahan Mərkəzinə gedəcək. Bu mərhələdə sualları hələ düzəldə bilərsiniz.",
        )
        return {"kind": "info", "title": title, "body": body, "variant": "pending"}
    if status in ("chair_approved", "center_review"):
        return {
            "kind": "info",
            "title": pgettext("accounts.profile.question_submissions", "İmtahan Mərkəzi baxır"),
            "body": pgettext(
                "exams.template.question_submission",
                "Kafedra təsdiqindən sonra dəst dondurulur — İmtahan Mərkəzinin qərarını gözləyin.",
            ),
            "variant": "pending",
        }
    if status == "accepted":
        return {
            "kind": "success",
            "title": pgettext("exams.template.question_submission", "Göndəriş qəbul edildi"),
            "note": submission.reviewer_note,
            "variant": "accepted",
        }
    if status in _RETURNED:
        if status == "chair_revision":
            title = pgettext("exams.template.question_submission", "Kafedra düzəliş istədi — düzəldib yenidən göndərin")
        elif status == "center_revision":
            title = pgettext(
                "exams.template.question_submission", "İmtahan Mərkəzi düzəliş istədi — düzəldib yenidən göndərin"
            )
        elif submission.reviewed_at:
            title = pgettext(
                "exams.template.question_submission", "İmtahan mərkəzi göndərişi geri qaytardı — düzəliş gözlənilir"
            )
        else:
            title = pgettext("exams.template.question_chain", "Kafedra rədd etdi")
        return {
            "kind": "danger" if status == "rejected" else "warning",
            "title": title,
            "note": note,
            "cta": cta if can_edit else None,
            "variant": "rejected",
        }
    return None


def _decider_next(submission, *, role, can_decide, decide_href=None):
    if role == ROLE_CHAIR:
        waiting = submission.is_at_chair
        anchor = "#qchairDecision"
    else:
        waiting = submission.is_pending
        anchor = "#qsubDecision"
    if waiting and can_decide:
        if role == ROLE_CHAIR:
            body = pgettext(
                "exams.template.question_submission",
                "Sualları və xəbərdarlıqları yoxlayın, sonra təsdiqləyin, düzəliş istəyin və ya rədd edin.",
            )
        else:
            body = pgettext(
                "exams.template.question_submission",
                "Qəbul etsəniz suallar seçdiyiniz banka yazılır; düzəliş və rədd üçün müəllimə qeyd məcburidir.",
            )
        return {
            "kind": "info",
            "title": pgettext("exams.template.question_submission", "Qərarınız gözlənilir"),
            "body": body,
            # Detal səhifəsində qərar formu yoxdur — CTA baxış (review) səhifəsinə aparır.
            "cta": {
                "href": decide_href or anchor,
                "label": pgettext("exams.template.question_submission", "Qərar ver"),
            },
            "variant": "pending",
        }
    if waiting:
        return {
            "kind": "info",
            "title": "",
            "body": pgettext(
                "exams.template.question_submission",
                "Yalnız baxış: göndərişə qərarı «İmtahan mərkəzinin qərarları» səlahiyyəti olan istifadəçi "
                "(imtahan mərkəzi rəhbəri) verir.",
            ),
            "variant": "readonly",
        }
    if role == ROLE_CHAIR:
        return {
            "kind": "info",
            "title": status_label(submission.status, role=role),
            "body": pgettext(
                "exams.template.question_chair",
                "Bu göndəriş artıq kafedra mərhələsində deyil — qərar dəyişdirilə bilməz.",
            ),
            "variant": "closed",
        }
    tone = {"accepted": "success", "rejected": "danger"}.get(submission.status, "info")
    return {
        "kind": tone,
        "title": status_label(submission.status, role=role),
        "note": submission.reviewer_note,
        "variant": "closed",
    }


def next_action(submission, *, role, can_edit=False, can_decide=False, decide_href=None):
    """«İndi nə olur / nə etməliyəm» lenti — vəziyyət və növbəti əməl bir baxışda."""
    if role == ROLE_TEACHER:
        return _teacher_next(submission, can_edit=can_edit)
    return _decider_next(submission, role=role, can_decide=can_decide, decide_href=decide_href)


def meta_items(submission, *, show_teacher):
    items = []
    if show_teacher:
        items.append({"icon": "fa-user", "text": _person(submission.teacher)})
    if submission.chair_unit_id and submission.chair_unit:
        items.append({"icon": "fa-sitemap", "text": submission.chair_unit.name})
    items.append({"icon": "fa-book", "text": submission.subject})
    if submission.exam_kind:
        items.append({"icon": "fa-flag-checkered", "text": submission.get_exam_kind_display()})
    if submission.group_label:
        items.append({"icon": "fa-users", "text": submission.group_label})
    items.append({"icon": "fa-globe", "text": submission.get_language_display()})
    items.append({"icon": "fa-clock", "text": _when(submission.created_at)})
    return [item for item in items if item["text"]]


def page_context(submission, events, *, role, can_edit=False, can_decide=False, decide_href=None):
    """Üç səhifənin ortaq başlıq konteksti (``qsx_*`` açarları)."""
    return {
        "qsx_role": role,
        "qsx_status": status_badge(submission, role=role),
        "qsx_meta": meta_items(submission, show_teacher=role != ROLE_TEACHER),
        "qsx_steps": chain_steps(submission),
        "qsx_kpis": kpi_tiles(submission),
        "qsx_next": next_action(
            submission, role=role, can_edit=can_edit, can_decide=can_decide, decide_href=decide_href
        ),
        "qsx_timeline": timeline(events),
    }


__all__ = [
    "ROLE_CENTER",
    "ROLE_CHAIR",
    "ROLE_TEACHER",
    "chain_steps",
    "next_action",
    "page_context",
    "status_badge",
    "timeline",
]
