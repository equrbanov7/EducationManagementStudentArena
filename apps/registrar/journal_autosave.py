"""Jurnalın AVTOMATİK yadda saxlanması — server tərəfi (sahib 2026-10-14).

«Yadda saxla click etməyi unudulsa da avtomatik yadda saxlanılsın.» Klient
(``registrar/js/journal_grid_autosave.js``) dəyişən xanaları MÖVCUD formanın MÖVCUD ünvanına
göndərir — davamiyyət/bal ``journal_detail`` (``action=save_marks``), Midterm/kollokvium
``kollokvium_save``. Yeni yazı yolu YOXDUR: icazə (birbaşa redaktor), jurnal kilidi, dərs günü
qaydası, 2 saat pəncərəsi, İmtahan Mərkəzi pəncərəsi, roster yoxlaması və audit eyni servisdən
(``gradebook.save_marks`` / ``save_component_scores``) keçir.

Fərq yalnız CAVABDADIR: POST gövdəsində ``autosave=1`` olanda redirect + flash mesaj əvəzinə
JSON qaytarılır (flash mesaj sessiyaya yığılıb növbəti səhifədə «Jurnal yadda saxlanıldı» kimi
çıxmasın). Bayraq başlıqda deyil, GÖVDƏDƏDİR — səhifə bağlananda ``navigator.sendBeacon``
başlıq göndərə bilmir. Dublikat mümkün deyil: ``LessonMark (lesson, enrollment)`` unikaldır və
yazılar açılış sətrinin ``FOR UPDATE`` kilidi ilə ardıcıllaşır (bax ``gradebook_marks.save_marks``).
"""

from __future__ import annotations

from django.http import JsonResponse

FIELD = "autosave"


def requested(request) -> bool:
    """POST avtomatik yadda saxlamadandır (JSON cavab gözləyir)."""
    return request.method == "POST" and request.POST.get(FIELD) == "1"


def saved(*, sent: int, written: int, rejected: int = 0, blocked: bool = False) -> JsonResponse:
    """Yazı getdi. ``skipped`` — server qaydası ilə ötürülən xanalar (kilid / dərs günü / pəncərə)."""
    skipped = max(0, sent - written - rejected)
    return JsonResponse(
        {
            "ok": True,
            "sent": sent,
            "written": written,
            "rejected": rejected,
            "skipped": skipped,
            "blocked": bool(blocked),
        }
    )


def marks_response(result: dict, *, sent: int) -> JsonResponse:
    """``save_marks(report=True)`` nəticəsi → JSON. Kilidli xanaya dəyişiklik gəlib və heç nə yazılmayıbsa
    409 (``code="mark_locked"``) — API birbaşa çağırılsa da kilid server qərarıdır (sahib 2026-10-25)."""
    written, rejected = result["written"], result["rejected"]
    if result.get("locked") and not written:
        return refused(result["locked_reason"], code="mark_locked")
    return saved(sent=sent, written=written, rejected=rejected)


def refused(message, *, code: str = "refused", status: int = 409) -> JsonResponse:
    """Heç nə yazılmadı və təkrar cəhd kömək etməz (jurnal bağlı, pəncərə bağlı…)."""
    return JsonResponse({"ok": False, "code": code, "message": str(message)}, status=status)
