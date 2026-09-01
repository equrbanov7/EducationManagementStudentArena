"""Sillabusun OXU-REJİMİ görünüşü — siyahının baxış paneli + redaktorun «Yekun görünüş».

Blokları quran kod ARTIQ BURADA DEYİL: o, :mod:`apps.syllabus.document`-ə
köçürülüb, çünki jurnal və tələbə kabineti (``apps.registrar``) də eyni sənədi
göstərməlidir, ``registrar → accounts`` idxalı isə modul-sərhəd qapısında YENİ
DÖVR yaradır (``accounts`` onsuz da ``registrar``-ı idxal edir). Burada yalnız
UI-ya aid qat qalır: status → ton adı və statusa görə izah banneri.

Beləliklə tələbənin, kafedra müdirinin və müəllimin gördüyü mətn EYNİ koddan
çıxır — dizayn tələbi «tələbə və kafedra ilə eyni görünüş» məhz budur.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.document import BLOCK_TITLES, build_preview_blocks  # noqa: F401  (geriyə-uyğun ad)

from .labels import STATUS_TONES

_CTX = "accounts.syllabus"

#: Baxış panelinin yuxarısındakı izah banneri — statusa görə (dizayn §3.1).
BANNERS = {
    SyllabusStatus.APPROVED.value: pgettext_lazy(
        _CTX,
        "Bu versiya təsdiqlənib və dəyişdirilə bilmir. Elektron jurnalın mövzu siyahısı, qiymətləndirmə strukturu "
        "və sərbəst iş konfiqurasiyası bu sənəddən götürülür.",
    ),
    SyllabusStatus.REVISION.value: pgettext_lazy(
        _CTX, "Kafedra müdiri düzəliş tələb edib. Qeydləri nəzərə alıb yenidən göndərin."
    ),
    SyllabusStatus.REJECTED.value: pgettext_lazy(_CTX, "Versiya rədd edilib. Səbəbi oxuyub yeni versiya yaradın."),
    SyllabusStatus.SUBMITTED.value: pgettext_lazy(
        _CTX, "Göndərilmiş versiya baxış müddətində kilidlidir. Dəyişiklik lazımsa təqdimatı geri çağırın."
    ),
    SyllabusStatus.REVIEW.value: pgettext_lazy(
        _CTX, "Kafedra müdiri versiyanı açıb — baxış davam edir, redaktə bağlıdır."
    ),
    SyllabusStatus.ARCHIVED.value: pgettext_lazy(_CTX, "Arxiv nüsxəsi — yalnız baxış üçündür."),
    SyllabusStatus.DRAFT.value: pgettext_lazy(
        _CTX, "Qaralama tələbələrə görünmür — yalnız təsdiqlənmiş versiya aktiv olur."
    ),
}


def build_preview_payload(syllabus) -> dict:
    """Siyahının baxış paneli üçün JSON gövdəsi."""
    from apps.syllabus.services import section_data_map, version_timeline

    version = syllabus.current_version
    status = version.status if version is not None else SyllabusStatus.DRAFT.value
    section_map = section_data_map(version) if version is not None else {}

    history = []
    for event in version_timeline(syllabus):
        actor = event.get("actor")
        who = ""
        if actor is not None:
            who = (actor.get_full_name() or "").strip() or getattr(actor, "username", "")
        history.append(
            {
                "version": event.get("version", ""),
                "what": (
                    str(SyllabusStatus(event["status"]).label)
                    if event.get("kind") == "version"
                    else str(event.get("reason") or "")
                ),
                "who": who,
                "at": event["at"].strftime("%d.%m.%Y %H:%M") if event.get("at") else "",
            }
        )

    return {
        "code": syllabus.subject.code,
        "name": syllabus.subject.name,
        "program": syllabus.program.display_label if syllabus.program_id else "",
        "period": (f"{syllabus.period.year_display} · {syllabus.period.name}" if syllabus.period_id else ""),
        "version": version.label if version is not None else "—",
        "status": status,
        "status_label": str(SyllabusStatus(status).label),
        "status_tone": STATUS_TONES.get(status, "neutral"),
        "banner": str(BANNERS.get(status, "")),
        "decision_reason": (version.decision_reason or "") if version is not None else "",
        "blocks": [
            {"title": str(block["title"]), "body": block["body"]} for block in build_preview_blocks(section_map)
        ],
        "history": history,
    }


__all__ = ["BANNERS", "BLOCK_TITLES", "build_preview_blocks", "build_preview_payload"]
