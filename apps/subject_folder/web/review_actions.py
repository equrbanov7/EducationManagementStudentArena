"""Müəllimin baxış əməlləri: qəbul (bal), qaytarma, yoxlandı, rədd, yenidən açma, toplu baxış, oxşarlıq qərarı.

İcazə (qrupun canlı müəllimi / inzibatçı), cəm ≤ 10, slot maksimumu, rəy uzunluğu —
hamısı ``services.review``-dədir. Qəbuldan sonra bal commit-də jurnala ötürülür;
cavab həmin ötürmənin NƏTİCƏSİNİ (düşdü / gözləyir / jurnal qəbul etmədi) bildirir.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .. import public
from ..constants import JournalSyncStatus
from .base import ActionError, field, get_match, get_submission, json_ok, uuid_or_none

_CTX = "subject_folder.ui"


def _journal_message(submission) -> tuple[str, str]:
    submission.refresh_from_db(fields=["journal_sync_status", "journal_sync_message"])
    status = submission.journal_sync_status
    if status == JournalSyncStatus.SYNCED:
        return pgettext(_CTX, "Qəbul edildi — bal jurnala düşdü."), "success"
    if status == JournalSyncStatus.BLOCKED:
        return (
            pgettext(_CTX, "Qəbul edildi, amma jurnal balı qəbul etmədi: %(reason)s")
            % {"reason": submission.journal_sync_message},
            "warning",
        )
    return pgettext(_CTX, "Qəbul edildi — bal jurnala ötürülmək üçün növbədədir."), "warning"


def accept(request, organization, user):
    submission = get_submission(organization, request.POST.get("submission"))
    public.accept(
        submission,
        by_user=user,
        points=str(request.POST.get("points") or ""),
        feedback=field(request, "feedback", limit=6000),
        request=request,
    )
    message, level = _journal_message(submission)
    return json_ok(message=message, level=level)


def return_for_revision(request, organization, user):
    submission = get_submission(organization, request.POST.get("submission"))
    public.return_for_revision(
        submission, by_user=user, feedback=field(request, "feedback", limit=6000), request=request
    )
    return json_ok(message=pgettext(_CTX, "İş rəylə qaytarıldı — tələbə yenidən göndərə bilər."))


def check(request, organization, user):
    submission = get_submission(organization, request.POST.get("submission"))
    public.check_homework(submission, by_user=user, feedback=field(request, "feedback", limit=6000), request=request)
    return json_ok(message=pgettext(_CTX, "Ev tapşırığı «yoxlanıldı» kimi qeyd olundu."))


def reject(request, organization, user):
    submission = get_submission(organization, request.POST.get("submission"))
    public.reject(
        submission,
        by_user=user,
        reason=str(request.POST.get("reason") or "").strip(),
        feedback=field(request, "feedback", limit=6000),
        request=request,
    )
    return json_ok(message=pgettext(_CTX, "Göndəriş rədd edildi."))


def reopen(request, organization, user):
    submission = get_submission(organization, request.POST.get("submission"))
    public.reopen(submission, by_user=user, feedback=field(request, "feedback", limit=6000), request=request)
    return json_ok(message=pgettext(_CTX, "Rədd ləğv edildi — tələbə yenidən göndərə bilər."))


#: Toplu baxışın dəstəklənən əməlləri (``services.review.bulk_review`` ilə eyni açarlar).
BULK_ACTIONS = ("accept", "return", "check", "reject")
#: Bir sorğuda ən çox bu qədər göndəriş (servis hər birini ayrıca kilidləyir).
BULK_LIMIT = 100


def bulk(request, organization, user):
    action = str(request.POST.get("bulk_action") or "").strip()
    if action not in BULK_ACTIONS:
        raise ActionError("bulk_action_invalid", pgettext(_CTX, "Toplu əməl seçilməyib."))
    ids = [pk for pk in (uuid_or_none(value) for value in request.POST.getlist("submission")) if pk is not None]
    if not ids:
        raise ActionError("bulk_empty", pgettext(_CTX, "Heç bir göndəriş seçilməyib."))
    if len(ids) > BULK_LIMIT:
        raise ActionError(
            "bulk_too_many", pgettext(_CTX, "Bir dəfəyə ən çox %(max)s göndəriş seçmək olar.") % {"max": BULK_LIMIT}
        )
    submissions = list(
        public.list_submissions(organization=organization, actor=user, current_only=False).filter(pk__in=ids)
    )
    points = request.POST.get("points") if action == "accept" else None
    result = public.bulk_review(
        submissions,
        by_user=user,
        action=action,
        points=points,
        feedback=field(request, "feedback", limit=6000),
        reason=str(request.POST.get("reason") or "").strip(),
        request=request,
    )
    failed = result.get("failed", {})
    missing = len(ids) - len(submissions)
    done = len(result.get("ok", []))
    message = pgettext(_CTX, "%(done)s göndəriş işləndi.") % {"done": done}
    details = [row.get("message", "") for row in failed.values()][:5]
    if failed or missing:
        message = pgettext(_CTX, "%(done)s göndəriş işləndi, %(failed)s göndəriş alınmadı.") % {
            "done": done,
            "failed": len(failed) + missing,
        }
    return json_ok(message=message, warnings=details, level="warning" if (failed or missing) else "success")


def match_dismiss(request, organization, user):
    match = get_match(organization, request.POST.get("match"))
    public.dismiss_match(match, by_user=user, note=field(request, "note", limit=6000), request=request)
    return json_ok(message=pgettext(_CTX, "Oxşarlıq «plagiat deyil» kimi qeyd olundu."))


def match_restore(request, organization, user):
    match = get_match(organization, request.POST.get("match"))
    public.restore_match(match, by_user=user, request=request)
    return json_ok(message=pgettext(_CTX, "Oxşarlıq qərarı geri alındı."))


HANDLERS = {
    "review_accept": accept,
    "review_return": return_for_revision,
    "review_check": check,
    "review_reject": reject,
    "review_reopen": reopen,
    "review_bulk": bulk,
    "match_dismiss": match_dismiss,
    "match_restore": match_restore,
}

__all__ = ["BULK_ACTIONS", "BULK_LIMIT", "HANDLERS"]
