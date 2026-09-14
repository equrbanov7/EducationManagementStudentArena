"""Toplu sual iş masası — pano/sürükləmə ilə şəkil yapışdırmanın ORTAQ view qolu.

W8 (2026-09-14) yalnız bank toplu əlavədə idi (`question_library/questions.py`);
2026-09-14 səhər (NIGHT_WAVES §5 «digər bank görünüşləri») eyni JSON qolu
`_bulk_question_workbench.html`-i işlədən bütün səhifələrə açıldı: imtahan dil
meneceri (`languages.py`), kafedra göndərişi yarat/redaktə (`submission_inbox.py`).

Ayrı URL yoxdur — hər view öz `request.path`-ini `wb_paste_url` kimi verir və POST
`action=paste_image|paste_image_remove` gələndə (fayl/preview emalından ƏVVƏL)
`paste_image_response` ilə cavab qaytarır. Stash DOCX bundle formatındadır, ona görə
preview/save-dəki `bind_import_manifest` / `attach_import_media_batch` dəyişmir.
"""

from django.http import JsonResponse
from django.utils.translation import pgettext

from apps.exams.services.import_media_paste import pasted_image_chips, remove_pasted_image, stash_pasted_image

PASTE_ACTIONS = ("paste_image", "paste_image_remove")


def requested_paste_action(request) -> str:
    """POST-un `action`-ı yapışdırma qoludursa onu, əks halda boş sətir qaytarır."""
    if request.method != "POST":
        return ""
    action = (request.POST.get("action") or "").strip()
    return action if action in PASTE_ACTIONS else ""


def paste_image_response(request, *, organization_id, math_token: str = "") -> JsonResponse:
    """`paste_image` → stash-a yaz, `[[img:N]]` marker qaytar; `paste_image_remove` → sil.

    Stash əhatəsi (`owner_id` + `organization_id`) fayl yükləməsi ilə eynidir — başqa
    müəllimin / tenantın tokeni ilə oxumaq-yazmaq `ValueError` verir (400).
    """
    action = (request.POST.get("action") or "").strip()
    math_token = (math_token or request.POST.get("math_token") or "").strip()
    scope = {"owner_id": request.user.pk, "organization_id": organization_id}
    try:
        if action == "paste_image":
            uploaded = request.FILES.get("image")
            if not uploaded:
                return JsonResponse(
                    {"ok": False, "error": pgettext("exams.view.bank.paste", "Şəkil göndərilməyib.")}, status=400
                )
            pasted = stash_pasted_image(uploaded, token=math_token, **scope)
            return JsonResponse(
                {
                    "ok": True,
                    "token": pasted.token,
                    "index": pasted.index,
                    "marker": pasted.marker,
                    "thumb": pasted.thumb,
                    "width": pasted.width,
                    "height": pasted.height,
                }
            )
        if action != "paste_image_remove":
            return JsonResponse({"ok": False, "error": "unknown_action"}, status=400)
        try:
            index = int(request.POST.get("index") or "")
        except ValueError:
            return JsonResponse(
                {"ok": False, "error": pgettext("exams.view.bank.paste", "Şəkil nömrəsi yanlışdır.")}, status=400
            )
        token = remove_pasted_image(math_token, index, **scope)
        return JsonResponse({"ok": True, "token": token, "index": index})
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except OSError:
        # Storage xətası — yol/backend detalı istifadəçiyə sızmasın.
        return JsonResponse(
            {"ok": False, "error": pgettext("exams.view.bank.paste", "Şəkil müvəqqəti yığına yazılmadı.")},
            status=400,
        )


def paste_context(request, *, organization_id, math_token: str = "") -> dict:
    """Şablon açarları: `wb_paste_url` (bu səhifə) + preview POST-dan sonra çiplərin bərpası."""
    return {
        "wb_paste_url": request.path,
        "wb_paste_images": pasted_image_chips(
            math_token or "", owner_id=request.user.pk, organization_id=organization_id
        ),
    }


__all__ = ["PASTE_ACTIONS", "paste_context", "paste_image_response", "requested_paste_action"]
