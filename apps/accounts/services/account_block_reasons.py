"""Hesab dayandırılmasının SƏBƏB və «KİMƏ MÜRACİƏT ETMƏLİ» kataloqu (sahib 2026-10-03).

Sahib: «tələbənin hesabını dayandırarkən səbəb seçmək olsun (select), bunun üçün kimə yaxınlaşmalıdır
o görünsün — tələbə username/parolunu yazanda o çıxsın, amma başqa heç nəyə daxil ola bilməsin».

* ``REASONS`` — operatorun seçdiyi səbəb; hər səbəbin DEFAULT müraciət ünvanı var (formada avtomatik
  seçilir, operator dəyişə bilər);
* ``CONTACTS`` — tələbənin yaxınlaşacağı struktur;
* kodlar ``UserProfile.block_reason_code`` / ``block_contact_code``-da saxlanılır, etiketlər burada
  (dil dəyişəndə tərcümə olunsun deyə mətn DB-yə yazılmır). Köhnə (kodsuz) bloklar «Digər» sayılır.

2026-10-11 (sahib): dialoq HƏDƏFİN statusuna uyğun danışır — tələbə / müəllim / neytral («İstifadəçi»);
səbəblərin ``AUDIENCE``-i var (tələbəyə aid səbəb müəllim dialoqunda çıxmır və əksinə); müəllimlər üçün
«İşdən ayrılıb / müqavilə bitib» + «Kadrlar şöbəsi» / «Kafedra müdiri». «Digər» seçiləndə səbəb AYRICA,
məcburi «Səbəbi yazın» sahəsinə yazılır (``other_text``) — qeyd sahəsi (otaq, telefon) onu əvəz etmir.
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
    "hr": pgettext_lazy(_CTX, "Kadrlar şöbəsi (İnsan resursları)"),
    "chair": pgettext_lazy(_CTX, "Kafedra müdiri"),
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
    "employment_ended": (pgettext_lazy(_CTX, "İşdən ayrılıb / müqavilə bitib"), "hr"),
    "other": (pgettext_lazy(_CTX, "Digər"), "dean_office"),
}

DEFAULT_REASON = "other"

AUDIENCE_STUDENT = "student"
AUDIENCE_STAFF = "staff"
AUDIENCES = (AUDIENCE_STUDENT, AUDIENCE_STAFF)

#: Səbəb kimə aiddir (sahib 2026-10-11). Siyahıda olmayan səbəb hər iki dialoqda görünür.
REASON_AUDIENCE = {
    "tuition_debt": AUDIENCE_STUDENT,
    "academic_leave": AUDIENCE_STUDENT,
    "exam_violation": AUDIENCE_STUDENT,
    "employment_ended": AUDIENCE_STAFF,
}

#: Ünvan kimə aiddir — müəllim dialoqunda «Tələbə Xidmətləri», tələbə dialoqunda «Kadrlar şöbəsi» çıxmır.
CONTACT_AUDIENCE = {
    "student_services": AUDIENCE_STUDENT,
    "hr": AUDIENCE_STAFF,
    "chair": AUDIENCE_STAFF,
}

#: Müəllim/əməkdaş dialoqunda səbəbin DEFOLT ünvanı (tələbə defoltu orada mənasızdır).
STAFF_DEFAULT_CONTACT = {
    "missing_documents": "hr",
    "personal_data": "hr",
    "discipline": "hr",
    "other": "hr",
}

#: «Digər» səbəbin audit mətnində etiketdən sonra yazılan ayırıcı (``other_text_of`` onu geri oxuyur).
OTHER_SEPARATOR = " — "

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


def clean_other_text(reason_code: str, other_text: str) -> str:
    """«Digər» üçün yazılmış səbəb (≥3 simvol, məcburi); başqa səbəbdə boş sətir qaytarır."""
    if reason_code != "other":
        return ""
    text = " ".join(str(other_text or "").split())[:MAX_NOTE_LENGTH]
    if len(text) < 3:
        raise BlockReasonError(
            "other_text_required",
            str(pgettext_lazy(_CTX, "«Digər» seçilib — səbəbi «Səbəbi yazın» sahəsinə yazın (ən azı 3 simvol).")),
        )
    return text


def normalize_choice(reason_code: str, contact_code: str, note: str, other_text=None) -> tuple[str, str, str]:
    """Formadan gələn dəyərləri yoxlayır: ``(reason, contact, note)``. Ünvan boşdursa səbəbin default-u.

    ``other_text`` verilibsə (2026-10-11 dialoqu) «Digər» üçün izah ORADA tələb olunur; ``None`` — köhnə
    çağırış: izah qeyd sahəsindən gözlənilir.
    """
    reason_code = (reason_code or "").strip()
    if reason_code not in REASONS:
        raise BlockReasonError("reason_required", str(pgettext_lazy(_CTX, "Dayandırma səbəbini seçin.")))
    contact_code = (contact_code or "").strip() or REASONS[reason_code][1]
    if contact_code not in CONTACTS:
        raise BlockReasonError("contact_invalid", str(pgettext_lazy(_CTX, "Müraciət ünvanı yanlışdır.")))
    note = " ".join(str(note or "").split())[:MAX_NOTE_LENGTH]
    if other_text is not None:
        clean_other_text(reason_code, other_text)
    elif reason_code == "other" and len(note) < 3:
        raise BlockReasonError("note_required", str(pgettext_lazy(_CTX, "«Digər» seçildikdə səbəbi qısaca izah edin.")))
    return reason_code, contact_code, note


def _az_label(reason_code: str) -> str:
    from django.utils import translation

    with translation.override("az"):
        return str(REASONS[reason_code][0])


def audit_text(reason_code: str, note: str, other_text: str = "") -> str:
    """Audit / ``block_reason`` sahəsi üçün mətn: «Etiket — izah/qeyd» (Azərbaycanca, sabit)."""
    label = _az_label(reason_code)
    detail = other_text if reason_code == "other" and other_text else note
    return f"{label}{OTHER_SEPARATOR}{detail}" if detail else label


def other_text_of(reason_code: str, block_reason: str) -> str:
    """«Digər» blokunun yazılmış səbəbi (``audit_text`` formatından); başqa səbəbdə boş sətir."""
    if reason_code != "other":
        return ""
    prefix = _az_label("other") + OTHER_SEPARATOR
    text = str(block_reason or "")
    return text[len(prefix) :].strip() if text.startswith(prefix) else ""


def reason_label(code: str) -> str:
    return str(REASONS.get(code or DEFAULT_REASON, REASONS[DEFAULT_REASON])[0])


def display_reason(code: str, block_reason: str = "") -> str:
    """Bloklanmış şəxsə / karta göstərilən səbəb: «Digər»də yazılmış izahın özü, qalanlarda etiket."""
    return other_text_of(code, block_reason) or reason_label(code)


def contact_label(code: str, reason_code: str = "") -> str:
    fallback = REASONS.get(reason_code or DEFAULT_REASON, REASONS[DEFAULT_REASON])[1]
    return str(CONTACTS.get(code or fallback, CONTACTS[fallback]))


def form_options(audience: str = "") -> dict:
    """Dialoq üçün: səbəblər (default ünvanı ilə) və ünvanlar.

    ``audience`` (``student`` / ``staff``) verilibsə digər auditoriyaya aid səbəblər çıxarılır;
    boşdursa (hədəf naməlum) hamısı qalır.
    """
    audience = audience if audience in AUDIENCES else ""

    def visible(catalog_audience) -> bool:
        return not audience or catalog_audience in ("", audience)

    def default_contact(code, contact):
        return STAFF_DEFAULT_CONTACT.get(code, contact) if audience == AUDIENCE_STAFF else contact

    return {
        "audience": audience,
        "reasons": [
            {"value": code, "label": str(label), "contact": default_contact(code, contact)}
            for code, (label, contact) in REASONS.items()
            if visible(REASON_AUDIENCE.get(code, ""))
        ],
        "contacts": [
            {"value": code, "label": str(label)}
            for code, label in CONTACTS.items()
            if visible(CONTACT_AUDIENCE.get(code, ""))
        ],
    }


__all__ = [
    "AUDIENCES",
    "AUDIENCE_STAFF",
    "AUDIENCE_STUDENT",
    "CONTACTS",
    "CONTACT_AUDIENCE",
    "DEFAULT_REASON",
    "MAX_NOTE_LENGTH",
    "REASONS",
    "REASON_AUDIENCE",
    "STAFF_DEFAULT_CONTACT",
    "BlockReasonError",
    "audit_text",
    "clean_other_text",
    "contact_label",
    "display_reason",
    "form_options",
    "normalize_choice",
    "other_text_of",
    "reason_label",
]
