"""Müəllim əməlləri: qovluq, mövzu, material, tapşırıq, qoşma, təyinat, son tarix.

Hər handler ``(request, organization, user) -> JsonResponse``. İcazəni servis qatı
yoxlayır (sahib / inzibatçı / canlı müəllim) və ``FolderError`` qaldırır — burada
yalnız obyekt aktiv təşkilat daxilində tapılır və forma sahələri çevrilir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils.translation import pgettext

from .. import public
from ..constants import SECTION_TEACHER
from ..services import lookups
from ..services.notify import profile_link
from .base import (
    ActionError,
    extensions,
    field,
    flag,
    get_assignment,
    get_attachment,
    get_folder,
    get_material,
    get_task,
    get_topic,
    int_or_none,
    json_ok,
    local_datetime,
    optional_field,
    optional_flag,
    optional_topic,
    uuid_or_none,
)

_CTX = "subject_folder.ui"


def _topic_arg(folder, request):
    """Redaktədə mövzu sahəsi formada yoxdursa DƏYİŞMİR (servisin ``"__keep__"`` işarəsi)."""
    if "topic" not in request.POST:
        return "__keep__"
    return optional_topic(folder, request.POST.get("topic"))


def _folder_url(folder, **params) -> str:
    return profile_link(SECTION_TEACHER, sf_folder=folder.pk, **params)


def _period_model():
    return django_apps.get_model("organizations", "AcademicPeriod")


def _subject_and_period(organization, raw: str):
    """«<subject_uuid>|<period_uuid>» (semestr boş ola bilər) → (Subject, AcademicPeriod|None)."""
    subject_raw, _sep, period_raw = str(raw or "").partition("|")
    subject_id = uuid_or_none(subject_raw)
    subject = (
        lookups.subject_model().objects.filter(organization=organization, pk=subject_id).first() if subject_id else None
    )
    if subject is None:
        raise ActionError("subject_required", pgettext(_CTX, "Fənn seçilməyib."))
    period = None
    if period_raw.strip():
        period_id = uuid_or_none(period_raw)
        period = _period_model().objects.filter(organization=organization, pk=period_id).first() if period_id else None
        if period is None:
            raise ActionError("period_invalid", pgettext(_CTX, "Semestr tapılmadı."))
    return subject, period


# ── Qovluq ──────────────────────────────────────────────────────────────────


def folder_create(request, organization, user):
    subject, period = _subject_and_period(organization, request.POST.get("subject_period"))
    offerings = lookups.offering_model().objects.filter(organization=organization, subject=subject, is_active=True)
    if period is not None:
        offerings = offerings.filter(period=period)
    offering = offerings.filter(lookups.taught_offerings_q(user)).order_by("pk").first()
    folder, created, _summary = public.create_folder(
        organization=organization,
        subject=subject,
        owner=user,
        by_user=user,
        period=period,
        title=field(request, "title", limit=300),
        description=field(request, "description"),
        offering=offering,
        request=request,
    )
    message = (
        pgettext(_CTX, "Qovluq yaradıldı — mövzular və sərbəst iş slotları sillabusdan çəkildi.")
        if created
        else pgettext(_CTX, "Bu fənn və semestr üçün qovluğunuz artıq var — o açılır.")
    )
    return json_ok(message=message, folder=str(folder.pk), created=created, url=_folder_url(folder))


def folder_update(request, organization, user):
    folder = get_folder(organization, request.POST.get("folder"))
    public.update_folder(
        folder,
        by_user=user,
        title=optional_field(request, "title", limit=300),
        description=optional_field(request, "description"),
        request=request,
    )
    return json_ok(message=pgettext(_CTX, "Qovluq yeniləndi."))


def folder_status(request, organization, user):
    folder = get_folder(organization, request.POST.get("folder"))
    status = str(request.POST.get("status") or "").strip()
    public.set_folder_status(folder, by_user=user, status=status, request=request)
    messages = {
        public.FolderStatus.ACTIVE.value: pgettext(_CTX, "Qovluq aktivdir — təyin olunmuş qruplar onu görür."),
        public.FolderStatus.ARCHIVED.value: pgettext(_CTX, "Qovluq arxivləndi — yalnız oxu rejimindədir."),
        public.FolderStatus.DRAFT.value: pgettext(_CTX, "Qovluq qaralamaya qaytarıldı."),
    }
    return json_ok(message=str(messages.get(status, "")))


def folder_resync(request, organization, user):
    folder = get_folder(organization, request.POST.get("folder"))
    summary = public.resync_folder(folder, by_user=user, request=request)
    if not summary.get("has_syllabus"):
        return json_ok(message=pgettext(_CTX, "Təsdiqlənmiş sillabus tapılmadı — struktur dəyişmədi."), level="warning")
    return json_ok(message=pgettext(_CTX, "Qovluq sillabusla uzlaşdırıldı."))


def folder_clone(request, organization, user):
    folder = get_folder(organization, request.POST.get("folder"))
    period_id = uuid_or_none(request.POST.get("period"))
    period = _period_model().objects.filter(organization=organization, pk=period_id).first() if period_id else None
    if period is None:
        raise ActionError("period_required", pgettext(_CTX, "Hədəf semestri seçin."))
    target, summary = public.clone_folder(folder, by_user=user, period=period, request=request)
    message = (
        pgettext(_CTX, "Qovluq yeni semestrə köçürüldü.")
        if summary.get("created", True)
        else pgettext(_CTX, "Hədəf semestrdə qovluq artıq var — o açılır.")
    )
    return json_ok(message=message, folder=str(target.pk), url=_folder_url(target))


# ── Mövzu ───────────────────────────────────────────────────────────────────


def topic_save(request, organization, user):
    folder = get_folder(organization, request.POST.get("folder"))
    week_no = int_or_none(request.POST.get("week_no"))
    if request.POST.get("topic"):
        topic = get_topic(folder, request.POST.get("topic"))
        public.update_topic(
            topic,
            by_user=user,
            title=optional_field(request, "title", limit=300),
            description=optional_field(request, "description"),
            week_no=week_no,
            request=request,
        )
        return json_ok(message=pgettext(_CTX, "Mövzu yeniləndi."))
    public.create_topic(
        folder,
        by_user=user,
        title=field(request, "title", limit=300),
        description=field(request, "description"),
        week_no=week_no,
        request=request,
    )
    return json_ok(message=pgettext(_CTX, "Mövzu əlavə olundu."))


def topic_hide(request, organization, user):
    folder = get_folder(organization, request.POST.get("folder"))
    topic = get_topic(folder, request.POST.get("topic"))
    hidden = flag(request, "hidden")
    public.set_topic_hidden(topic, by_user=user, hidden=hidden, request=request)
    return json_ok(message=pgettext(_CTX, "Mövzu gizlədildi.") if hidden else pgettext(_CTX, "Mövzu yenidən görünür."))


def topic_delete(request, organization, user):
    folder = get_folder(organization, request.POST.get("folder"))
    public.delete_topic(get_topic(folder, request.POST.get("topic")), by_user=user, request=request)
    return json_ok(message=pgettext(_CTX, "Mövzu silindi."))


# ── Material ────────────────────────────────────────────────────────────────


def material_save(request, organization, user):
    upload = request.FILES.get("file")
    if request.POST.get("material"):
        material = get_material(organization, request.POST.get("material"))
        public.update_material(
            material,
            by_user=user,
            title=optional_field(request, "title", limit=300),
            description=optional_field(request, "description"),
            topic=_topic_arg(material.folder, request),
            file=upload,
            url=optional_field(request, "url", limit=1100),
            code_text=optional_field(request, "code_text", limit=210_000),
            code_language=optional_field(request, "code_language", limit=20),
            request=request,
        )
        return json_ok(message=pgettext(_CTX, "Material yeniləndi."))
    folder = get_folder(organization, request.POST.get("folder"))
    material = public.create_material(
        folder,
        by_user=user,
        kind=str(request.POST.get("kind") or "").strip(),
        title=field(request, "title", limit=300),
        description=field(request, "description"),
        topic=optional_topic(folder, request.POST.get("topic")),
        file=upload,
        url=field(request, "url", limit=1100),
        code_text=field(request, "code_text", limit=210_000),
        code_language=field(request, "code_language", limit=20),
        is_published=flag(request, "is_published"),
        request=request,
    )
    message = (
        pgettext(_CTX, "Material əlavə olundu və tələbələrə görünür.")
        if material.is_published
        else pgettext(_CTX, "Material qaralama kimi əlavə olundu — dərc edəndə tələbələr görəcək.")
    )
    return json_ok(message=message)


def material_publish(request, organization, user):
    material = get_material(organization, request.POST.get("material"))
    published = flag(request, "published")
    public.set_material_published(material, by_user=user, published=published, request=request)
    return json_ok(
        message=pgettext(_CTX, "Material dərc edildi.") if published else pgettext(_CTX, "Material gizlədildi.")
    )


def material_archive(request, organization, user):
    material = get_material(organization, request.POST.get("material"))
    public.archive_material(material, by_user=user, archived=True, request=request)
    return json_ok(message=pgettext(_CTX, "Material silindi."))


# ── Tapşırıq ────────────────────────────────────────────────────────────────


def _task_limits(request):
    return {
        "allowed_extensions": extensions(request.POST.get("allowed_extensions")),
        "max_file_mb": int_or_none(request.POST.get("max_file_mb")),
        "max_files": int_or_none(request.POST.get("max_files")),
    }


def homework_create(request, organization, user):
    folder = get_folder(organization, request.POST.get("folder"))
    public.create_homework(
        folder,
        by_user=user,
        title=field(request, "title", limit=300),
        instructions=field(request, "instructions"),
        topic=optional_topic(folder, request.POST.get("topic")),
        allow_text_answer=flag(request, "allow_text_answer"),
        allow_files=flag(request, "allow_files"),
        is_published=flag(request, "is_published"),
        request=request,
        **_task_limits(request),
    )
    return json_ok(message=pgettext(_CTX, "Ev tapşırığı əlavə olundu."))


def task_update(request, organization, user):
    task = get_task(organization, request.POST.get("task"))
    public.update_task(
        task,
        by_user=user,
        title=optional_field(request, "title", limit=300),
        instructions=optional_field(request, "instructions"),
        topic=_topic_arg(task.folder, request),
        allow_text_answer=optional_flag(request, "allow_text_answer"),
        allow_files=optional_flag(request, "allow_files"),
        request=request,
        **_task_limits(request),
    )
    for upload in request.FILES.getlist("attachments"):
        public.add_task_attachment(task, by_user=user, file=upload, request=request)
    return json_ok(message=pgettext(_CTX, "Tapşırıq yeniləndi."))


def task_publish(request, organization, user):
    task = get_task(organization, request.POST.get("task"))
    published = flag(request, "published")
    public.set_task_published(task, by_user=user, published=published, request=request)
    return json_ok(
        message=(
            pgettext(_CTX, "Tapşırıq dərc edildi — tələbələrə bildiriş göndərildi.")
            if published
            else pgettext(_CTX, "Tapşırıq gizlədildi.")
        )
    )


def task_archive(request, organization, user):
    task = get_task(organization, request.POST.get("task"))
    archived = not flag(request, "restore")
    public.archive_task(task, by_user=user, archived=archived, request=request)
    return json_ok(
        message=pgettext(_CTX, "Tapşırıq arxivləndi.") if archived else pgettext(_CTX, "Tapşırıq bərpa olundu.")
    )


def task_delete(request, organization, user):
    public.delete_task(get_task(organization, request.POST.get("task")), by_user=user, request=request)
    return json_ok(message=pgettext(_CTX, "Tapşırıq silindi."))


def attachment_remove(request, organization, user):
    attachment = get_attachment(organization, request.POST.get("attachment"))
    public.remove_task_attachment(attachment, by_user=user, request=request)
    return json_ok(message=pgettext(_CTX, "Qoşma silindi."))


# ── Təyinat və son tarix ────────────────────────────────────────────────────


def assign(request, organization, user):
    folder = get_folder(organization, request.POST.get("folder"))
    ids = {uuid_or_none(value) for value in request.POST.getlist("offering")} - {None}
    if not ids:
        raise ActionError("offering_required", pgettext(_CTX, "Ən azı bir qrup seçin."))
    allowed = {row["offering"].pk: row["offering"] for row in public.assignable_offerings(folder, user)}
    offerings = [allowed[pk] for pk in ids if pk in allowed]
    if len(offerings) != len(ids):
        raise ActionError(
            "permission.not_teaching", pgettext(_CTX, "Seçilən qruplardan bəzisini siz tədris etmirsiniz."), status=403
        )
    results = public.assign_folder(folder, offerings, by_user=user, request=request)
    warnings = [warning["message"] for row in results for warning in row.get("warnings", [])]
    return json_ok(
        message=pgettext(_CTX, "Qovluq seçilən qruplara təyin olundu."),
        warnings=warnings,
        level="warning" if warnings else "success",
    )


def unassign(request, organization, user):
    assignment = get_assignment(organization, request.POST.get("assignment"))
    public.unassign(assignment, by_user=user, request=request)
    return json_ok(message=pgettext(_CTX, "Qrupun təyinatı ləğv edildi — göndərişlər saxlanılır."))


def deadline_set(request, organization, user):
    task = get_task(organization, request.POST.get("task"))
    window = {
        "opens_at": local_datetime(request.POST.get("opens_at")),
        "due_at": local_datetime(request.POST.get("due_at")),
        "late_policy": str(request.POST.get("late_policy") or public.LatePolicy.NONE),
    }
    if request.POST.get("assignment"):
        assignment = get_assignment(organization, request.POST.get("assignment"))
        if assignment.folder_id != task.folder_id:
            raise ActionError("assignment.not_in_folder", pgettext(_CTX, "Təyinat bu qovluğa aid deyil."))
        if window["opens_at"] is None and window["due_at"] is None:
            public.clear_deadline(assignment, task, by_user=user, request=request)
            return json_ok(message=pgettext(_CTX, "Son tarix götürüldü — tapşırıq həmişə açıqdır."))
        public.set_deadline(assignment, task, by_user=user, request=request, **window)
    else:
        public.set_deadline_for_all(task, by_user=user, request=request, **window)
    return json_ok(message=pgettext(_CTX, "Son tarix saxlanıldı."))


HANDLERS = {
    "folder_create": folder_create,
    "folder_update": folder_update,
    "folder_status": folder_status,
    "folder_resync": folder_resync,
    "folder_clone": folder_clone,
    "topic_save": topic_save,
    "topic_hide": topic_hide,
    "topic_delete": topic_delete,
    "material_save": material_save,
    "material_publish": material_publish,
    "material_archive": material_archive,
    "homework_create": homework_create,
    "task_update": task_update,
    "task_publish": task_publish,
    "task_archive": task_archive,
    "task_delete": task_delete,
    "attachment_remove": attachment_remove,
    "assign": assign,
    "unassign": unassign,
    "deadline_set": deadline_set,
}

__all__ = ["HANDLERS"]
