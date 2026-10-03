"""Hesab dayandırılmasının SƏBƏB və «KİMƏ MÜRACİƏT ETMƏLİ» kataloqu (sahib 2026-10-03).

Sahib: «tələbənin hesabını dayandırarkən səbəb seçmək olsun (select), bunun üçün kimə yaxınlaşmalıdır
o görünsün — tələbə username/parolunu yazanda o çıxsın, amma başqa heç nəyə daxil ola bilməsin».

* ``REASONS`` — operatorun seçdiyi səbəb; hər səbəbin DEFAULT müraciət ünvanı var (formada avtomatik
  seçilir, operator dəyişə bilər);
* ``CONTACTS`` — tələbənin yaxınlaşacağı struktur;
* kodlar ``UserProfile.block_reason_code`` / ``block_contact_code``-da saxlanılır, etiketlər burada
  (dil dəyişəndə tərcümə olunsun deyə mətn DB-yə yazılmır). Köhnə (kodsuz) bloklar «Digər» sayılır.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

_CTX = "accounts.account_block"

#: Kod → tələbəyə görünən etiket.
CONTACTS = {
    "dean_office": pgettext_lazy(_CTX, "Fakültənizin dekanlığı"),
    "finance": pgettext_lazy(_CTX, "Maliyyə şöbəsi (mühasibatlıq)"),
    "student_services": pgettext_lazy(_CTX, "Tələbə Xidmətləri Mərkəzi"),
    "teaching_office": pgettext_lazy(_CTX, "Tədris şöbəsi"),
    "exam_center": pgettext_lazy(_CTX, "İmtahan Mərkəzi"),
    "rim": pgettext_lazy(_CTX, "RİM — Rəqəmsal İnkişaf Mərkəzi"),
}

#: Kod → (etiket, default müraciət kodu). Sıra formadakı sıradır.
REASONS = {
    "tuition_debt": (pgettext_lazy(_CTX, "Təhsil haqqı üzrə borc"), "finance"),
    "missing_documents": (pgettext_lazy(_CTX, "Sənədlər tam təqdim edilməyib"), "student_services"),
    "personal_data": (pgettext_lazy(_CTX, "Şəxsi məlumatlar dəqiqləşdirilməlidir"), "student_services"),
    "academic_leave": (pgettext_lazy(_CTX, "Akademik məzuniyyət"), "dean_office"),
    "discipline": (pgettext_lazy(_CTX, "İntizam qaydalarının pozulması"), "dean_office"),
    "exam_violation": (pgettext_lazy(_CTX, "İmtahan qaydalarının pozulması"), "exam_center"),
    "security": (pgettext_lazy(_CTX, "Hesabın təhlükəsizliyi (şübhəli giriş)"), "rim"),
    "other": (pgettext_lazy(_CTX, "Digər"), "dean_office"),
}

DEFAULT_REASON = "other"

#: Tələbəyə görünən əlavə qeydin (otaq, telefon, iş saatı) yuxarı həddi.
MAX_NOTE_LENGTH = 200


class BlockReasonError(ValueError):
    """Səbəb / ünvan kodu kataloqda yoxdur və ya «Digər» üçün izah yazılmayıb."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)

    @property
    def code(self) -> str:
        return self.args[0]

    @property
    def message(self) -> str:
        return self.args[1]


def normalize_choice(reason_code: str, contact_code: str, note: str) -> tuple[str, str, str]:
    """Formadan gələn dəyərləri yoxlayır: ``(reason, contact, note)``. Ünvan boşdursa səbəbin default-u."""
    reason_code = (reason_code or "").strip()
    if reason_code not in REASONS:
        raise BlockReasonError("reason_required", str(pgettext_lazy(_CTX, "Dayandırma səbəbini seçin.")))
    contact_code = (contact_code or "").strip() or REASONS[reason_code][1]
    if contact_code not in CONTACTS:
        raise BlockReasonError("contact_invalid", str(pgettext_lazy(_CTX, "Müraciət ünvanı yanlışdır.")))
    note = " ".join(str(note or "").split())[:MAX_NOTE_LENGTH]
    if reason_code == "other" and len(note) < 3:
        raise BlockReasonError("note_required", str(pgettext_lazy(_CTX, "«Digər» seçildikdə səbəbi qısaca izah edin.")))
    return reason_code, contact_code, note


def audit_text(reason_code: str, note: str) -> str:
    """Audit / köhnə ``block_reason`` sahəsi üçün mətn: «Etiket — qeyd» (Azərbaycanca, sabit)."""
    from django.utils import translation

    with translation.override("az"):
        label = str(REASONS[reason_code][0])
    return f"{label} — {note}" if note else label


def reason_label(code: str) -> str:
    return str(REASONS.get(code or DEFAULT_REASON, REASONS[DEFAULT_REASON])[0])


def contact_label(code: str, reason_code: str = "") -> str:
    fallback = REASONS.get(reason_code or DEFAULT_REASON, REASONS[DEFAULT_REASON])[1]
    return str(CONTACTS.get(code or fallback, CONTACTS[fallback]))


def form_options() -> dict:
    """Dialoq üçün: səbəblər (default ünvanı ilə) və ünvanlar."""
    return {
        "reasons": [
            {"value": code, "label": str(label), "contact": contact} for code, (label, contact) in REASONS.items()
        ],
        "contacts": [{"value": code, "label": str(label)} for code, label in CONTACTS.items()],
    }


__all__ = [
    "CONTACTS",
    "DEFAULT_REASON",
    "MAX_NOTE_LENGTH",
    "REASONS",
    "BlockReasonError",
    "audit_text",
    "contact_label",
    "form_options",
    "normalize_choice",
    "reason_label",
]
