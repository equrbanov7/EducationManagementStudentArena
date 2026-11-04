"""«Müəllimlər müəyyən tarixdən bu günə keçmiş tarixli dərs əlavə edə bilər» — «Sistem tənzimləmələri» açarları.

Sahib 2026-11-04: «sistem tənzimləməsində olmalıdır ki, müəllimlər sentyabrın 15-dən indiyə dərs əlavə edə bilsin;
hələlik bunu sistem idarəetməsindən idarə edim.»

İki açar mövcud «journal» qrupuna düşür (yeni qrup yoxdur):

* ``journal.backdate_since_enabled`` — bayraq, DEFOLT SÖNÜLÜ (``settings.JOURNAL_BACKDATE_SINCE_ENABLED``);
* ``journal.backdate_since`` — başlanğıc tarixi, defolt 2026-09-15 (``settings.JOURNAL_BACKDATE_SINCE``);
  ISO mətni kimi saxlanır — ``kind="date"`` (``runtime_settings.coerce`` →
  :func:`core.runtime_settings_journal_late.coerce_date`).

Yandırılanda müəllimin YAZMA PƏNCƏRƏSİNİN alt həddi bu tarixə enir (əgər bu tarix adi «N gün geriyə» həddindən
köhnədirsə): həmin tarixdən bu günədək dərs açmaq və o dərslərin boş xanalarına q/b, i/e, bal yazmaq olur.
Gələcək tarix, dövr / semestr / intensiv kurs sərhədləri, xana kilidi və bağlı jurnal qaydası dəyişmir. Tətbiq
nöqtəsi YALNIZ ``apps.registrar.journal_edit_windows.earliest_entry_date``; oxu nöqtəsi YALNIZ
:func:`backdate_since`.

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

import datetime as _dt

from django.conf import settings
from django.utils.translation import pgettext_lazy

from core.runtime_settings_journal_late import parse_date

_CTX = "core.runtime_settings"

GROUP_CODE = "journal"
KEY_BACKDATE_ENABLED = "journal.backdate_since_enabled"
KEY_BACKDATE_SINCE = "journal.backdate_since"

#: Kod defoltu (sahib 2026-11-04: «sentyabrın 15-dən»). ``settings.JOURNAL_BACKDATE_SINCE`` ilə dəyişə bilər.
DEFAULT_BACKDATE_SINCE = "2026-09-15"


def _default_enabled() -> bool:
    return bool(getattr(settings, "JOURNAL_BACKDATE_SINCE_ENABLED", False))


def _default_since() -> str:
    return str(getattr(settings, "JOURNAL_BACKDATE_SINCE", DEFAULT_BACKDATE_SINCE))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_BACKDATE_ENABLED, GROUP_CODE, "bool", _default_enabled,
            pgettext_lazy(_CTX, "Müəllimlər müəyyən tarixdən bu günə keçmiş tarixli dərs əlavə edə bilər"),
            pgettext_lazy(
                _CTX,
                "Yandırılanda müəllim aşağıdakı başlanğıc tarixindən bu günədək istənilən tarixə dərs aça və həmin "
                "dərslərin boş xanalarına q/b, i/e və bal yaza bilər — adi «gecikmiş yazı müddəti» həddindən köhnə "
                "olsa da. Gələcək tarixə dərs açılmır; semestr sərhədi, yazılmış xananın kilidi və bağlı jurnal "
                "qaydası dəyişmir. Söndürüləndə adi yazma müddəti qayıdır.",
            ),
        ),
        spec_cls(
            KEY_BACKDATE_SINCE, GROUP_CODE, "date", _default_since,
            pgettext_lazy(_CTX, "Keçmiş tarixli dərsin başlanğıc tarixi"),
            pgettext_lazy(
                _CTX,
                "Yuxarıdakı bayraq yandırılıbsa müəllim bu tarixdən (daxil) bu günədək dərs əlavə edə bilər. "
                "Bayraq söndürülüdürsə bu tarix tətbiq olunmur.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarları ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açarlar mövcud «journal» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


def backdate_since() -> _dt.date | None:
    """Keçmiş tarixli dərsin başlanğıc tarixi; söndürülüdürsə və ya oxunmursa ``None`` (heç vaxt istisna atmır)."""
    try:
        from core import runtime_settings

        if not runtime_settings.get_bool(KEY_BACKDATE_ENABLED):
            return None
        return parse_date(runtime_settings.get(KEY_BACKDATE_SINCE)) or parse_date(_default_since())
    except Exception:  # noqa: BLE001 — oxunmasa adi yazma pəncərəsi qalır (təhlükəsiz tərəf)
        return None


__all__ = [
    "DEFAULT_BACKDATE_SINCE",
    "GROUP_CODE",
    "KEY_BACKDATE_ENABLED",
    "KEY_BACKDATE_SINCE",
    "backdate_since",
    "build_specs",
    "register",
]
