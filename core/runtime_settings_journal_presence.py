"""«Elektron jurnal» — i/e xanasının dəyişmə müddəti (sahib 2026-11-21, RİM rəhbəri).

Sahib: «i/e qoyulandan sonra 1 gün ərzində müəllim onu dəyişə bilsin, sonra q/b kimi donsun; q/b və bal yazılandan
15 dəqiqə sonra donur; əvvəlki olanlarda elə donsun; boş xanalara yazmaq olsun; hamısını sistem tənzimləmələrindən
idarə edim.» Ona görə iki açar (hər ikisi «journal» qrupunda, ``journal.mark_edit_minutes``-in DƏRHAL ardınca):

* ``journal.presence_lock_enabled`` (defolt yanılı) — söndürüləndə əvvəlki qayda (sahib 2026-10-26): balsız i/e
  dərsin yazma müddəti ərzində həmişə dəyişir;
* ``journal.presence_edit_minutes`` (defolt 1440 = 1 gün) — i/e ilk yazılışından bu qədər dəqiqə sonra donur.

Oxu nöqtəsi YALNIZ ``apps.registrar.journal_edit_windows.presence_edit_window``; Postgres trigger-i (registrar 0125)
eyni açarları oxuyur. Testlərdə defolt ``settings.JOURNAL_PRESENCE_*`` ilə dəyişir (``override_settings``).
``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

KEY_PRESENCE_LOCK = "journal.presence_lock_enabled"
KEY_PRESENCE_MINUTES = "journal.presence_edit_minutes"
DEFAULT_PRESENCE_MINUTES = 1440  # sahib 2026-11-21: «1 gün»
#: Yeni açarlar «Sistem tənzimləmələri»ndə bu açarın ardınca göstərilir (q/b və bal sətrinin yanında).
_ANCHOR = "journal.mark_edit_minutes"


def _lock_default() -> bool:
    return bool(getattr(settings, "JOURNAL_PRESENCE_LOCK_ENABLED", True))


def _minutes_default() -> int:
    return int(getattr(settings, "JOURNAL_PRESENCE_EDIT_MINUTES", DEFAULT_PRESENCE_MINUTES))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_PRESENCE_LOCK, "journal", "bool", _lock_default,
            pgettext_lazy(_CTX, "i/e xanası müddət bitəndə donur"),
            pgettext_lazy(
                _CTX,
                "Yandırılıbsa müəllimin yazdığı i/e aşağıdakı müddət ərzində dəyişir, sonra q/b kimi donur — "
                "köhnə sistemdən köçürülmüş i/e də. Sonra yalnız RİM-in rəsmi düzəlişi. Söndürüləndə i/e dərsin "
                "yazma müddəti ərzində həmişə dəyişir. Boş xanaya yazma qaydası dəyişmir.",
            ),
        ),
        spec_cls(
            KEY_PRESENCE_MINUTES, "journal", "int", _minutes_default,
            pgettext_lazy(_CTX, "i/e-ni dəyişmə müddəti"),
            pgettext_lazy(
                _CTX,
                "Müəllimin yazdığı i/e İLK yazılışdan bu qədər dəqiqə sonra donur (defolt 1440 dəqiqə = 1 gün). "
                "Müddət ərzində i/e q/b-yə və ya bala dəyişdirilsə, yeni q/b və balın öz müddəti (yuxarıdakı sətir) "
                "dəyişiklik anından başlayır. Yalnız yuxarıdakı açar yandırılıbsa işləyir.",
            ),
            pgettext_lazy(_CTX, "dəqiqə"), min=1, max=43200,
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarları ``SPECS``-də ``journal.mark_edit_minutes``-in ardına qoyur (forma sırası); ``GROUPS`` dəyişmir.

    ``SPECS`` yerində yenidən sıralanır (eyni obyekt — digər modulların istinadı pozulmur).
    """
    new = {spec.key: spec for spec in build_specs(spec_cls)}
    if _ANCHOR not in specs:
        specs.update(new)
        return groups
    items = [(key, spec) for key, spec in specs.items() if key not in new]
    specs.clear()
    for key, spec in items:
        specs[key] = spec
        if key == _ANCHOR:
            specs.update(new)
    return groups


__all__ = ["DEFAULT_PRESENCE_MINUTES", "KEY_PRESENCE_LOCK", "KEY_PRESENCE_MINUTES", "build_specs", "register"]
