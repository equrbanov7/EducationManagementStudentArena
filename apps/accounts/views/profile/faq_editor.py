from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from core.audit import log_action
from core.constants import AuditAction

from ...models import FaqVideoGuide
from .faq_catalog import GUIDES
from .faq_editor_catalog import can_manage_videos
from .faq_editor_forms import GuideForm, version
from .faq_uploads import MAX_FORM_BYTES


def _permission(request):
    if not can_manage_videos(request):
        raise PermissionDenied
    return request.organization


@login_required
@never_cache
@require_http_methods(["GET", "HEAD"])
def editor(request):
    org = _permission(request)
    rows = {row.key: row for row in FaqVideoGuide.objects.filter(organization=org).order_by("-id")}
    originals = {guide.key: guide for guide in GUIDES}
    keys = [key for key in rows if key not in originals] + list(originals)
    query = request.GET.get("q", "").strip()[:120]
    items = []
    for key in keys:
        row, source = rows.get(key), originals.get(key)
        title = row.title if row and row.title else getattr(source, "title", key)
        topic = row.topic if row and row.topic else getattr(source, "topic", "")
        if query.casefold() not in f"{title} {topic}".casefold():
            continue
        items.append(
            {
                "key": key,
                "title": title,
                "topic": topic,
                "custom": source is None,
                "hidden": bool(row and row.hidden),
                "unclassified": source is None and not row.required_guides,
            }
        )
    page = Paginator(items, 15).get_page(request.GET.get("page"))
    return render(request, "accounts/profile/faq_editor/list.html", {"page": page, "q": query})


def _delete_replaced(pairs):
    for storage, name in pairs:
        storage.delete(name)


@transaction.non_atomic_requests
@login_required
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def edit_guide(request, key=None):
    return _save_or_display(request, key, upload=False)


@transaction.non_atomic_requests
@csrf_exempt
@login_required
@never_cache
@require_POST
def upload_guide(request, key=None):
    return _save_or_display(request, key, upload=True)


def _save_or_display(request, key, *, upload):
    # Begin the transaction before reading memberships when PostgreSQL uses SET LOCAL.
    uploaded = []
    try:
        with transaction.atomic():
            org = _permission(request)
            if upload:
                try:
                    length = int(request.META.get("CONTENT_LENGTH") or 0)
                except (TypeError, ValueError):
                    return HttpResponse(_("Yükləmənin ölçüsü düzgün deyil."), status=400)
                if length > MAX_FORM_BYTES:
                    return HttpResponse(_("Sorğu çox böyükdür. MP4 üçün ən çox 200 MiB qəbul edilir."), status=413)
                if not hasattr(request, "_files"):
                    request.upload_handlers = [TemporaryFileUploadHandler(request)]
                # CSRF reads multipart form data. Authorize and bound the request first.
                return csrf_protect(_edit_guide)(request, key, uploaded, org)
            return _edit_guide(request, key, uploaded, org)
    except Exception:
        _delete_replaced(uploaded)
        raise


def _edit_guide(request, key, uploaded, org):
    source = next((g for g in GUIDES if g.key == key), None)
    rows = FaqVideoGuide.objects.filter(organization=org)
    row = rows.filter(key=key).first() if key else None
    if key and not (source or row):
        raise Http404
    form = GuideForm(
        request.POST if request.method == "POST" else None, request.FILES or None, org=org, row=row, original=source
    )
    context = {"form": form, "row": row, "original": source, "editing": bool(key), "key": key}
    template = "accounts/profile/faq_editor/form.html"
    if request.method != "POST":
        return render(request, template, context)
    action = request.POST.get("action", "save")
    if (
        action not in {"save", "remove", "restore"}
        or (action == "restore" and not (row and source))
        or (action == "remove" and not key)
    ):
        raise Http404
    if action == "save" and not form.is_valid():
        return render(request, template, context, status=400)
    if action == "remove" and request.POST.get("confirm") != "yes":
        context["operation_error"] = _("Silməni təsdiqləyin.")
        return render(request, template, context, status=400)
    record_key = key or ("custom-" + form.cleaned_data["create_token"].hex)
    # Serialize the first override as well as edits to a pre-existing row.
    type(org).objects.select_for_update().only("pk").get(pk=org.pk)
    locked = rows.select_for_update().filter(key=record_key).first()
    if (row and not locked) or version(locked) != request.POST.get("version"):
        context["operation_error"] = _("Dərs başqa pəncərədə dəyişdirilib. Səhifəni yenidən açın.")
        return render(request, template, context, status=409)
    existing = [(f.storage, f.name) for f in (locked.video_file, locked.subtitle_file) if f] if locked else []
    if action == "restore" or (action == "remove" and not source):
        locked.delete()
        remaining = set()
    else:
        item = locked or FaqVideoGuide(organization=org, key=record_key)
        if action == "remove":
            item.hidden = True
        else:
            data = form.cleaned_data
            item.title, item.topic, item.steps = data["title"], data["topic"], data["steps"]
            item.audience_roles, item.chapters = data["audience"], data["chapters"]
            item.required_guides = data["required_guides"]
            item.hidden = False
            if data["video"] or data["omit_subtitles"]:
                item.subtitle_file = ""
                item.omit_subtitles = True
            for name, upload in (("video_file", data["video"]), ("subtitle_file", data["subtitles"])):
                if upload:
                    field = getattr(item, name)
                    field.save(upload.name, upload, save=False)
                    uploaded.append((field.storage, field.name))
            if data["subtitles"]:
                item.omit_subtitles = False
            item.duration = form.duration
        item.revision = (locked.revision + 1) if locked else 1
        item.save()
        remaining = {f.name for f in (item.video_file, item.subtitle_file) if f}
    obsolete = [pair for pair in existing if pair[1] not in remaining]
    if obsolete:
        transaction.on_commit(lambda: _delete_replaced(obsolete), robust=True)
    log_action(
        AuditAction.DELETE if action == "remove" else AuditAction.UPDATE if key else AuditAction.CREATE,
        user=request.user,
        organization=org,
        request=request,
        resource_type="faq_video_guide",
        resource_id=record_key,
        reason=action,
    )
    messages.success(
        request,
        {
            "save": _("Video dərsi saxlanıldı."),
            "remove": _("Video dərsi kataloqdan çıxarıldı."),
            "restore": _("İlkin dərs bərpa edildi."),
        }[action],
    )
    return redirect("accounts:faq_video_editor")
