"""Rəsmi ixtisas şifrlərinin GÖSTƏRMƏ və AXTARIŞ qaydası — TƏK mənbə.

Niyə ``core``-da, ``apps/registrar``-da yox
------------------------------------------
Şifr sahələri ``registrar.Program``-a aiddir, amma etiketi quran səthlər YALNIZ
registrar-da deyil:

* ``apps.syllabus.services.coverage`` — «Əhatə» tabının proqram breakdown-u;
* ``apps.accounts.services.people`` — insanlar kataloqunun filtrləri/sətirləri;
* ``apps.accounts.views.academic_records`` — ixtisas seçicisi.

``apps.syllabus`` ``apps.registrar``-dan İDXAL EDƏ BİLMƏZ: dependency qrafında
artıq ``registrar → syllabus`` tili var (``scripts/module_deps.py``), tərs
istiqamət DÖVR yaradar və qapı düşər. Ona görə saf (model-siz, sorğu-suz)
formatlaşdırma və axtarış qaydası burada, paylaşılan kerneldə yaşayır; hər iki
tərəf onu idxal edir və ``registrar.Program`` yalnız DELEQASİYA edir
(``apps/registrar/models/_program_codes.py``).

İKİ NƏSİL şifr
--------------
``official_code``
    CARİ rəsmi dövlət şifri (NK 503/2024): ``6XXXXXX`` bakalavr, ``7XXXXXX``
    magistratura. Yeni təsnifatda ləğv olunmuş ixtisasda BOŞDUR.
``legacy_official_code``
    ƏVVƏLKİ nəsil şifr: ``050XXX`` bakalavr, ``060XXX`` magistratura. Köhnə
    tələbələrin diplomunda MƏHZ BU yazılıb.

DAXİLİ ``Program.code`` (``MYEDU-*``) buraya HEÇ VAXT daxil olmur.

AXTARIŞ İNVARİANTI
------------------
**Ekranda göstərilən hər şifr axtarışda da tapılmalıdır.** ``display_code``
cari şifr yoxdursa köhnəyə geri çəkildiyi üçün, yalnız ``official_code`` üzrə
süzən filtr istifadəçinin GÖRDÜYÜ şifri tapa bilmir (bloker: «Dünya
iqtisadiyyatı · 050401» görünür, «050401» yazanda sıfır nəticə). Ona görə hər
səth :func:`program_code_search_q` işlədir — sahə siyahısı bir yerdədir və
etiket qaydası ilə eyni faylda saxlanılır ki, biri dəyişəndə o biri unudulmasın.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils.translation import pgettext

#: Axtarışa DAXİL OLMALI şifr sahələri — :func:`program_display_code`-un
#: baxdığı sahələrlə eyni dəst olmalıdır (invariant).
PROGRAM_CODE_SEARCH_FIELDS = ("official_code", "legacy_official_code")


def _clean(value) -> str:
    return (value or "").strip()


def program_display_code(official_code, legacy_official_code) -> str:
    """Kompakt səthlər üçün TƏK şifr: cari varsa cari, yoxsa köhnə.

    Geri çəkilmə QƏSDLİDİR — yeni təsnifatda ləğv olunmuş ixtisasda proqram
    şifrsiz qalmamalıdır: köhnə şifr həmin tələbələrin diplomundakı şifrdir.
    """
    return _clean(official_code) or _clean(legacy_official_code)


def program_official_code_pair(official_code, legacy_official_code) -> str:
    """HƏR İKİ şifr bir sətirdə: ``6006004 · köhnə 050624``.

    Tək şifr varsa yalnız o qaytarılır, heç biri yoxdursa boş sətir — heç bir
    halda asılı qalmış ayırıcı yoxdur.
    """
    current = _clean(official_code)
    legacy = _clean(legacy_official_code)
    if current and legacy:
        # pgettext (lazy DEYİL): dəyər dərhal ``str``-ə çevrilir ki, audit
        # JSONField-inə lazy proxy sızmasın (bax core.audit qeydi).
        return f"{current} · {pgettext('registrar.program', 'köhnə')} {legacy}"
    return current or legacy


def program_display_label(name, official_code="", legacy_official_code="") -> str:
    """KOMPAKT etiket: ``Ad · <şifr>``, şifr yoxdursa yalnız ``Ad``.

    ``values()``/``annotate()`` ilə işləyən səthlər (model instansı olmayan)
    məhz bunu çağırır — sahələri ƏL İLƏ birləşdirmirlər.
    """
    label = _clean(name)
    code = program_display_code(official_code, legacy_official_code)
    if label and code:
        return f"{label} · {code}"
    return label or code


def program_display_label_full(name, official_code="", legacy_official_code="") -> str:
    """DETAL etiketi: ``Ad · <cari> · köhnə <köhnə>`` (transkript, kartlar)."""
    label = _clean(name)
    pair = program_official_code_pair(official_code, legacy_official_code)
    if label and pair:
        return f"{label} · {pair}"
    return label or pair


def program_code_search_q(query: str, *, prefix: str = "") -> Q:
    """Şifr üzrə axtarış filtri — HƏR İKİ nəsil şifri əhatə edir.

    ``prefix`` əlaqə yolu üçündür (``"program__"`` kimi). Boş sorğuda BOŞ ``Q``
    qaytarılır ki, çağıran yerdə ``if`` yazmaq məcburiyyəti olmasın.
    """
    token = _clean(query)
    if not token:
        return Q()
    combined = Q()
    for field_name in PROGRAM_CODE_SEARCH_FIELDS:
        combined |= Q(**{f"{prefix}{field_name}__icontains": token})
    return combined


__all__ = [
    "PROGRAM_CODE_SEARCH_FIELDS",
    "program_code_search_q",
    "program_display_code",
    "program_display_label",
    "program_display_label_full",
    "program_official_code_pair",
]
