"""``Program`` şifr sahələri və göstərmə etiketləri — İKİ NƏSİL rəsmi təsnifat.

Niyə ayrıca modul
-----------------
``academic.py`` modul-ölçü büdcəsinin (600 sətir) altında qalmalıdır; şifr
məntiqi ora sığmayan yeganə ayrıla bilən hissədir və onsuz da müstəqil
mövzudur — bir yerdə oxunması daha asandır.

ÜÇ kod, qarışdırılmamalıdır
---------------------------
``code``
    **DAXİLİ** sabit identifikator (``MYEDU-<legacy_id>``). Tenant daxilində
    unikaldır və köçürmə xəttinin (``apps.legacy_import``) indeks açarıdır:
    ``program_pk_index()``, ``rehearsal_structure_targets``,
    ``rehearsal_catalog_targets`` məhz onun tək-mənalılığına söykənir. Ona görə
    NƏ boşaldıla, NƏ təkrarlana bilər — və istifadəçiyə **HEÇ VAXT
    GÖSTƏRİLMİR**: uydurma açardır, insan üçün mənası yoxdur.
``official_code``
    **CARİ** rəsmi dövlət şifri — NK 503 (02.12.2024), NK 109 (17.04.2026)
    düzəlişi ilə. 7 rəqəm: ``6XXXXXX`` bakalavr/baza tibb, ``7XXXXXX``
    magistratura/rezidentura.
``legacy_official_code``
    **ƏVVƏLKİ** nəsil rəsmi şifr: ``050XXX`` bakalavr, ``060XXX`` magistratura.
    Köhnə tələbələrin diplomunda MƏHZ BU şifr yazılıb.

Göstərmə qaydası
----------------
Formatlaşdırmanın ÖZÜ burada deyil — ``core/program_codes.py``-dadır (saf,
model-siz funksiyalar). Səbəb: eyni etiketi ``values()``/``annotate()`` ilə
işləyən səthlər və ``apps.syllabus`` da qurur, amma ``apps.syllabus``
``apps.registrar``-ı idxal edə bilməz (``registrar → syllabus`` tili artıq var,
tərsi dövr olardı). Aşağıdakı property-lər həmin funksiyalara deleqasiya edir.

Səthlər sahələri ƏL İLƏ birləşdirmir — buradakı üç etiketdən birini işlədir:

``display_label``    ``Ad · <şifr>``            kompakt (siyahı, açılan menyu, cədvəl)
``display_label_full`` ``Ad · <cari> · köhnə <köhnə>``  detal (transkript, kart)
``official_code_pair`` ``<cari> · köhnə <köhnə>``       yalnız şifr (nişan)

Heç biri boş şifrdə asılı qalmış ayırıcı («Ad · ») qaytarmır.

AXTARIŞ: göstərilən hər şifr axtarışda da tapılmalıdır — filtrlər
``core.program_codes.program_code_search_q()`` işlədir (HƏR İKİ nəsil şifr).
"""

from __future__ import annotations

from django.db import models

from core.program_codes import (
    program_display_code,
    program_display_label,
    program_display_label_full,
    program_official_code_pair,
)


def official_code_field() -> models.CharField:
    """CARİ (NK 503/2024) rəsmi dövlət ixtisas şifri sahəsi.

    Fabrik funksiyadır, modul səviyyəli sabit deyil: Django sahə obyekti
    ``contribute_to_class``-da özünə ``model``/``name`` yazır, ona görə eyni
    instansı iki modelə vermək olmaz.
    """
    return models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        help_text=(
            "CARİ rəsmi dövlət ixtisas şifri (NK 503/2024; 7 rəqəm — 6XXXXXX bakalavr, "
            "7XXXXXX magistratura). İxtisas yeni təsnifatda ləğv olunubsa BOŞ qalır. "
            "Unikal DEYİL: bir şifr bir neçə proqrama (magistr ixtisaslaşmaları, AZ/EN "
            "bölmələri, əyani/qiyabi formalar) aid ola bilər."
        ),
    )


def legacy_official_code_field() -> models.CharField:
    """ƏVVƏLKİ nəsil rəsmi ixtisas şifri sahəsi (fabrik — yuxarıdakı qeydə bax)."""
    return models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        help_text=(
            "ƏVVƏLKİ nəsil rəsmi ixtisas şifri (050XXX bakalavr, 060XXX magistratura). "
            "Köhnə tələbələrin diplom və arayışlarında yazılan şifrdir — saxlanılır və "
            "göstərilir. İxtisas yalnız 2024 təsnifatında varsa BOŞ qalır."
        ),
    )


class ProgramCodeLabelsMixin:
    """``Program`` üçün rəsmi şifr etiketləri (sahələri modelin özü elan edir).

    Formatlaşdırma qaydası BURADA DEYİL — ``core.program_codes``-dadır: eyni
    qaydanı model instansı olmayan səthlər (``values()``/``annotate()``, və
    ``apps.registrar``-ı idxal edə bilməyən ``apps.syllabus``) də işlədir. Bu
    mixin yalnız sahələri həmin saf funksiyalara ötürür.
    """

    @property
    def official_code_current(self) -> str:
        """CARİ (NK 503/2024) rəsmi şifr — kənar boşluqlar təmizlənmiş."""
        return (self.official_code or "").strip()

    @property
    def official_code_legacy(self) -> str:
        """ƏVVƏLKİ nəsil (050XXX/060XXX) rəsmi şifr — kənar boşluqlar təmizlənmiş."""
        return (self.legacy_official_code or "").strip()

    @property
    def display_code(self) -> str:
        """Kompakt səthlər üçün TƏK şifr: cari varsa cari, yoxsa köhnə.

        Geri çəkilmə QƏSDLİDİR — yeni təsnifatda LƏĞV olunmuş ixtisaslarda
        (məs. «Dünya iqtisadiyyatı», «Kommersiya») cari şifr yoxdur, amma
        proqram şifrsiz qalmamalıdır: köhnə şifr həmin tələbələrin
        diplomundakı şifrdir.
        """
        return program_display_code(self.official_code, self.legacy_official_code)

    @property
    def official_code_pair(self) -> str:
        """HƏR İKİ şifr bir sətirdə — yeri olan səthlər üçün.

        ``6006004 · köhnə 050624`` / ``6006004`` / ``050624`` / ``""``.
        Heç bir halda asılı qalmış ayırıcı qaytarmır.
        """
        return program_official_code_pair(self.official_code, self.legacy_official_code)

    @property
    def display_label(self) -> str:
        """İstifadəçiyə göstərilən KOMPAKT etiket: ``Ad · <şifr>``, yoxsa ``Ad``.

        Daxili ``code`` (``MYEDU-*``) buraya HEÇ VAXT daxil olmur. Şifr
        boşdursa ayırıcı da yazılmır — asılı qalmış "Ad · " quyruğu olmamalıdır.
        """
        return program_display_label(self.name, self.official_code, self.legacy_official_code)

    @property
    def display_label_full(self) -> str:
        """``Ad · <cari> · köhnə <köhnə>`` — detal səthləri (transkript, kartlar)."""
        return program_display_label_full(self.name, self.official_code, self.legacy_official_code)
