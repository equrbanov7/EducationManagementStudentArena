"""Tələbə əməlləri: qaralamanı saxla, göndər, qaralamadakı faylı sil.

Auditoriya (aktiv qeydiyyat), pəncərə (son tarix / gecikmə), fayl ağ siyahısı və
ölçüsü, ``submission.pending``/``closed`` qaydaları ``services.submissions``-dadır.
Mətn sahəsi formada yoxdursa (tapşırıq mətn qəbul etmir) ``None`` ötürülür —
qaralamanın mətni dəyişmir.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .. import public
from ..constants import MAX_TEXT_ANSWER_CHARS
from .base import get_assignment, get_submission_file, get_task, json_ok, optional_field

_CTX = "subject_folder.ui"


def _target(request, organization):
    return get_task(organization, request.POST.get("task")), get_assignment(
        organization, request.POST.get("assignment")
    )


def draft_save(request, organization, user):
    task, assignment = _target(request, organization)
    public.save_draft(
        task=task,
        assignment=assignment,
        student=user,
        text=optional_field(request, "text", limit=MAX_TEXT_ANSWER_CHARS),
        files=request.FILES.getlist("files"),
        request=request,
    )
    return json_ok(message=pgettext(_CTX, "Qaralama saxlanıldı — müəllim hələ görmür."))


def submit(request, organization, user):
    task, assignment = _target(request, organization)
    row = public.submit(
        task=task,
        assignment=assignment,
        student=user,
        text=optional_field(request, "text", limit=MAX_TEXT_ANSWER_CHARS),
        files=request.FILES.getlist("files"),
        request=request,
    )
    if row.is_late:
        return json_ok(
            message=pgettext(_CTX, "İş göndərildi (son tarixdən sonra — gecikmə qeyd olundu)."), level="warning"
        )
    return json_ok(message=pgettext(_CTX, "İş göndərildi — müəllim yoxlayandan sonra nəticəni görəcəksiniz."))


def draft_file_remove(request, organization, user):
    public.remove_draft_file(get_submission_file(organization, request.POST.get("file")), student=user, request=request)
    return json_ok(message=pgettext(_CTX, "Fayl qaralamadan silindi."))


HANDLERS = {
    "draft_save": draft_save,
    "submit": submit,
    "draft_file_remove": draft_file_remove,
}

__all__ = ["HANDLERS"]
