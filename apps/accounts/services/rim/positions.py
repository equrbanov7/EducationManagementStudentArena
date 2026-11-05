"""RİM «Vəzifə» seçicisinin standart vəzifələri (sahib 2026-11-04: «Vəzifə yaza bilim select option»).

Vəzifə ``UserProfile.staff_position``-da SƏRBƏST MƏTN kimi qalır (heç bir icazə / əhatə ondan törəmir —
``core.staff_position``). Seçici yalnız yazılışı vahidləşdirir: standart siyahı + «Digər» (əl ilə). Saxlanan dəyər
AZƏRBAYCANCA kanonik addır (dil dəyişəndə profil mətni dəyişməsin); seçicidə operatorun dilində etiket görünür.
Layihədə ayrıca vəzifə kataloqu yoxdur: elmi adlar (``UserProfile.AcademicTitle`` / dərs yükü
``TeacherPosition``) bu siyahının əvvəlindədir, ardınca inzibati vəzifələr.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

_CTX = "accounts.rim.position"

#: (saxlanan kanonik ad, göstərilən etiket). Sıra seçicidəki sıradır.
POSITIONS = (
    ("Assistent", pgettext_lazy(_CTX, "Assistent")),
    ("Müəllim", pgettext_lazy(_CTX, "Müəllim")),
    ("Baş müəllim", pgettext_lazy(_CTX, "Baş müəllim")),
    ("Dosent", pgettext_lazy(_CTX, "Dosent")),
    ("Professor", pgettext_lazy(_CTX, "Professor")),
    ("Kafedra müdiri", pgettext_lazy(_CTX, "Kafedra müdiri")),
    ("Dekan", pgettext_lazy(_CTX, "Dekan")),
    ("Dekan müavini", pgettext_lazy(_CTX, "Dekan müavini")),
    ("Rektor", pgettext_lazy(_CTX, "Rektor")),
    ("Prorektor", pgettext_lazy(_CTX, "Prorektor")),
    ("Tyutor", pgettext_lazy(_CTX, "Tyutor")),
    ("Metodist", pgettext_lazy(_CTX, "Metodist")),
    ("Laborant", pgettext_lazy(_CTX, "Laborant")),
    ("Baş laborant", pgettext_lazy(_CTX, "Baş laborant")),
    ("Şöbə müdiri", pgettext_lazy(_CTX, "Şöbə müdiri")),
    ("Şöbə müdirinin müavini", pgettext_lazy(_CTX, "Şöbə müdirinin müavini")),
    ("Sektor müdiri", pgettext_lazy(_CTX, "Sektor müdiri")),
    ("Mərkəz direktoru", pgettext_lazy(_CTX, "Mərkəz direktoru")),
    ("Baş mütəxəssis", pgettext_lazy(_CTX, "Baş mütəxəssis")),
    ("Aparıcı mütəxəssis", pgettext_lazy(_CTX, "Aparıcı mütəxəssis")),
    ("Mütəxəssis", pgettext_lazy(_CTX, "Mütəxəssis")),
    ("Baş mühasib", pgettext_lazy(_CTX, "Baş mühasib")),
    ("Mühasib", pgettext_lazy(_CTX, "Mühasib")),
    ("Hüquqşünas", pgettext_lazy(_CTX, "Hüquqşünas")),
    ("Psixoloq", pgettext_lazy(_CTX, "Psixoloq")),
    ("Kitabxanaçı", pgettext_lazy(_CTX, "Kitabxanaçı")),
    ("Kargüzar", pgettext_lazy(_CTX, "Kargüzar")),
    ("Katib", pgettext_lazy(_CTX, "Katib")),
    ("Operator", pgettext_lazy(_CTX, "Operator")),
    ("Proqramçı", pgettext_lazy(_CTX, "Proqramçı")),
    ("Sistem inzibatçısı", pgettext_lazy(_CTX, "Sistem inzibatçısı")),
)


def position_options() -> list:
    """Seçicinin variantları ``[{"value", "label"}]`` (etiket cari dildə)."""
    return [{"value": value, "label": str(label)} for value, label in POSITIONS]


__all__ = ["POSITIONS", "position_options"]
