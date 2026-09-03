"""Baxış PANELİNİN məzmunu: bölmələr · versiya fərqi · audit xronologiyası.

Dizayn təhvili §3.3-ün sağ panelidir. Üç tab, bir mənbə:

* **bölmələr** — sillabusun 8 məzmun bölməsi, hər birinə şərh sahəsi;
* **fərqlər** — TƏSDİQLƏNMİŞ versiya ilə TƏQDİM EDİLMİŞ versiyanın yanaşı
  müqayisəsi (dizayndakı köhnə/yeni kartı);
* **audit** — mövcud domen qeydlərindən (``SyllabusReview`` + versiya
  xronologiyası) qurulan nöqtəli tarixçə. Yeni jurnal İCAD EDİLMİR.

Mətn qatı burada saxlanılır (domen kodları mətn daşımır), rəng isə YALNIZ «ton»
adı kimi verilir — hex şablonda deyil, CSS tokenindədir.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from apps.syllabus.constants import RULE_SECTIONS, SectionKey, SyllabusStatus
from apps.syllabus.models import ReviewDecision, SyllabusReview

from .labels import STATUS_TONES
from .preview import build_preview_blocks
from .review_rows import percent_tone, person, wait_text, wait_tone, waiting_days

_CTX = "accounts.syllabus"

_EMPTY = pgettext_lazy(_CTX, "— doldurulmayıb —")
_NO_TEACHER_NOTE = pgettext_lazy(_CTX, "Müəllim təqdimata əlavə qeyd yazmayıb.")
_INFO_TEACHER = pgettext_lazy(_CTX, "Müəllim: %(value)s")
_INFO_OFFICE = pgettext_lazy(_CTX, "Məsləhət saatı: %(value)s")
_INFO_PREREQ = pgettext_lazy(_CTX, "Prerekvizit: %(value)s")
_NO_BASE = pgettext_lazy(_CTX, "Bu, dosyenin ilk təsdiq namizədidir — müqayisə üçün əvvəlki versiya yoxdur.")
_COMPARE = pgettext_lazy(_CTX, "Müqayisə: təsdiqlənmiş %(old)s ilə təqdim edilmiş %(new)s arasında.")
_DIFF_COUNT = pgettext_lazy(_CTX, "%(changed)s bölmə dəyişib · %(same)s bölmə dəyişməyib")
_VERSION_CREATED = pgettext_lazy(_CTX, "%(version)s versiyası yaradıldı")
_SUBMITTED_META = pgettext_lazy(_CTX, "Təqdim: %(sent)s · tamamlanma %(percent)s%%")

#: Fərq növünün etiketi — struktur bölmələri jurnala TOXUNUR, ona görə ayrılır.
_KIND_STRUCTURE = pgettext_lazy(_CTX, "struktur dəyişikliyi")
_KIND_CONTENT = pgettext_lazy(_CTX, "məzmun dəyişikliyi")
_KIND_SAME = pgettext_lazy(_CTX, "dəyişməmişdir")

#: Jurnala təsir edən bölmələr — dizayndakı sarı xəbərdarlıq zolağı.
STRUCTURAL_SECTIONS = (SectionKey.WEEK.value, SectionKey.ASSESS.value, SectionKey.SELF.value)

DIFF_WARNINGS = {
    SectionKey.WEEK.value: pgettext_lazy(
        _CTX,
        "Bu, jurnalın mövzu siyahısını dəyişir. Cari semestrdə jurnal artıq açılıbsa, dəyişiklik yalnız "
        "növbəti semestrdən qüvvəyə minir.",
    ),
    SectionKey.ASSESS.value: pgettext_lazy(
        _CTX,
        "Qiymətləndirmə çəkiləri jurnalın sütun strukturunu dəyişir. Mövcud qiymətlər arxivdə saxlanılır və "
        "silinmir.",
    ),
    SectionKey.SELF.value: pgettext_lazy(
        _CTX,
        "Sərbəst iş sütunlarının sayı dəyişir. Köhnə sütunların qiymətləri arxivdə saxlanılır və silinmir.",
    ),
}

#: Qərar → (tarixçə mətni, nöqtə tonu).
_DECISION_EVENTS = {
    ReviewDecision.SUBMITTED.value: (pgettext_lazy(_CTX, "%(version)s təsdiqə göndərildi"), "primary"),
    ReviewDecision.WITHDRAWN.value: (pgettext_lazy(_CTX, "%(version)s təqdimatı geri çağırıldı"), "warning"),
    ReviewDecision.OPENED.value: (pgettext_lazy(_CTX, "%(version)s baxışa götürüldü"), "primary"),
    ReviewDecision.APPROVED.value: (pgettext_lazy(_CTX, "%(version)s təsdiqləndi"), "success"),
    ReviewDecision.REVISION.value: (pgettext_lazy(_CTX, "%(version)s düzəliş üçün geri qaytarıldı"), "warning"),
    ReviewDecision.REJECTED.value: (pgettext_lazy(_CTX, "%(version)s rədd edildi"), "danger"),
}


def _stamp(moment) -> str:
    return moment.strftime("%d.%m.%Y, %H:%M") if moment else ""


def _info_body(data: dict) -> str:
    lines = []
    for key, template in (
        ("teacher", _INFO_TEACHER),
        ("office_hours", _INFO_OFFICE),
        ("prerequisites", _INFO_PREREQ),
    ):
        value = (data.get(key) or "").strip() if isinstance(data.get(key), str) else ""
        if value:
            lines.append(str(template) % {"value": value})
    return "\n".join(lines) or str(_EMPTY)


def compose_bodies(section_map: dict) -> dict:
    """``{section_id: oxunaqlı mətn}`` — 8 məzmun bölməsi üçün.

    ``desc`` bölməsi oxu-rejimində İKİ blok verir (təsvir + məqsəd); burada onlar
    bir bölmə kartında birləşdirilir ki, kart sayı redaktordakı bölmə sayı ilə
    eyni qalsın.
    """
    blocks = build_preview_blocks(section_map)
    bodies = {SectionKey.INFO.value: _info_body(section_map.get(SectionKey.INFO.value, {}) or {})}
    bodies[SectionKey.DESC.value] = "\n\n".join([blocks[0]["body"], blocks[1]["body"]])
    for index, section_id in enumerate(
        (
            SectionKey.OUT.value,
            SectionKey.WEEK.value,
            SectionKey.METHOD.value,
            SectionKey.ASSESS.value,
            SectionKey.SELF.value,
            SectionKey.LIT.value,
        ),
        start=2,
    ):
        bodies[section_id] = blocks[index]["body"]
    return bodies


def build_sections(section_map: dict, diff: dict, notes: dict) -> list:
    """Bölmə kartları — başlıq, mətn, «dəyişib» nişanı, mövcud şərh."""
    bodies = compose_bodies(section_map)
    rows = []
    for section_id in RULE_SECTIONS:
        rows.append(
            {
                "id": section_id,
                "label": str(SectionKey(section_id).label),
                "body": bodies.get(section_id, str(_EMPTY)),
                "changed": bool((diff.get(section_id) or {}).get("changed")),
                "note": (notes.get(section_id) or ""),
            }
        )
    return rows


def build_diffs(old_map: dict, new_map: dict, diff: dict) -> dict:
    """Yanaşı müqayisə kartları + dəyişiklik sayğacı."""
    old_bodies = compose_bodies(old_map)
    new_bodies = compose_bodies(new_map)
    rows, changed = [], 0
    for section_id in RULE_SECTIONS:
        is_changed = bool((diff.get(section_id) or {}).get("changed"))
        changed += 1 if is_changed else 0
        if is_changed:
            kind = _KIND_STRUCTURE if section_id in STRUCTURAL_SECTIONS else _KIND_CONTENT
        else:
            kind = _KIND_SAME
        rows.append(
            {
                "id": section_id,
                "label": str(SectionKey(section_id).label),
                "kind": str(kind),
                "changed": is_changed,
                "old": old_bodies.get(section_id, str(_EMPTY)),
                "new": new_bodies.get(section_id, str(_EMPTY)),
                "warning": str(DIFF_WARNINGS[section_id]) if (is_changed and section_id in DIFF_WARNINGS) else "",
            }
        )
    return {
        "rows": rows,
        "count": str(_DIFF_COUNT) % {"changed": changed, "same": len(RULE_SECTIONS) - changed},
    }


def build_timeline(events) -> list:
    """Audit xronologiyası — yeni → köhnə, nöqtə rəngi hadisə tonundadır."""
    rows = []
    for event in events:
        version_label = event.get("version") or ""
        if event.get("kind") == "version":
            what = str(_VERSION_CREATED) % {"version": version_label}
            tone = STATUS_TONES.get(event.get("status"), "neutral")
            body = ""
        else:
            template, tone = _DECISION_EVENTS.get(
                event.get("decision"), (pgettext_lazy(_CTX, "%(version)s yeniləndi"), "neutral")
            )
            what = str(template) % {"version": version_label}
            body = event.get("reason") or ""
        rows.append(
            {
                "what": what,
                "when": _stamp(event.get("at")),
                "who": person(event.get("actor")),
                "body": body,
                "tone": tone,
            }
        )
    return rows


def _teacher_note(version) -> str:
    row = (
        SyllabusReview.objects.filter(version=version, decision=ReviewDecision.SUBMITTED)
        .order_by("-created_at")
        .first()
    )
    text = ((row.comment or "").strip() if row is not None else "") or ""
    return text or str(_NO_TEACHER_NOTE)


def _existing_notes(version) -> dict:
    """Bu versiyaya əvvəl yazılmış bölmə şərhləri (qərar verilməmiş qaralama)."""
    row = SyllabusReview.objects.filter(version=version).order_by("-created_at").first()
    notes = getattr(row, "section_comments", None)
    return dict(notes) if isinstance(notes, dict) else {}


def build_review_payload(version, *, now) -> dict:
    """Baxış panelinin JSON gövdəsi (dizayn §3.3 sağ panel)."""
    from apps.syllabus.services import section_data_map, version_diff, version_timeline

    syllabus = version.syllabus
    approved = syllabus.approved_version
    days = waiting_days(version, now=now)
    new_map = section_data_map(version)
    old_map = section_data_map(approved) if approved is not None else {}
    # ⚠️ Baza YOXDURSA fərq DE HESABLANMIR. `version_diff(None, …)` hər bölməni
    # «dəyişib» sayardı (boş ↔ dolu) və ilk təsdiq namizədində bütün kartlar sarı
    # yanardı — bu, müdiri yanlış istiqamətləndirir.
    diff = version_diff(approved, version) if approved is not None else {}
    notes = _existing_notes(version)

    return {
        "version_id": str(version.pk),
        "code": syllabus.subject.code,
        "name": syllabus.subject.name,
        "version_label": version.label,
        "status_label": str(SyllabusStatus(version.status).label),
        "status_tone": STATUS_TONES.get(version.status, "neutral"),
        "wait_text": wait_text(days),
        "wait_tone": wait_tone(days),
        "percent": version.completion_percent or 0,
        "percent_tone": percent_tone(version.completion_percent or 0),
        "meta": " · ".join(
            filter(
                None,
                [
                    syllabus.program.display_label if syllabus.program_id else "",
                    person(syllabus.author or version.submitted_by),
                    str(_SUBMITTED_META)
                    % {"sent": _stamp(version.submitted_at), "percent": version.completion_percent or 0},
                ],
            )
        ),
        "teacher_note": _teacher_note(version),
        "compare": (
            str(_COMPARE) % {"old": approved.label, "new": version.label} if approved is not None else str(_NO_BASE)
        ),
        "has_base": approved is not None,
        "sections": build_sections(new_map, diff, notes),
        "diff": build_diffs(old_map, new_map, diff),
        "timeline": build_timeline(version_timeline(syllabus)),
    }


__all__ = [
    "DIFF_WARNINGS",
    "STRUCTURAL_SECTIONS",
    "build_diffs",
    "build_review_payload",
    "build_sections",
    "build_timeline",
    "compose_bodies",
]
