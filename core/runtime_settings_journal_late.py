"""«"Gec yazılıb" nəzarətinin başlanğıc tarixi» — «Sistem tənzimləmələri» açarı (sahib 2026-10-25).

Sahib: «o "Gec yazılıb"ı hər yerdən sil, çünki datanı inteqrasiya etmişik. Full bazada kimdəsə olmasın o, gələn
həftədən ola bilər.» Dərsin TARİXİ bu tarixdən əvvəldirsə dərs heç vaxt «gec» sayılmır (nişan, say, KPI, export);
bu tarixdən sonrakı dərslər üçün mövcud 48 saat qaydası işləyir. Açar «journal» qrupuna düşür (yeni qrup yoxdur).

Oxu nöqtəsi YALNIZ :func:`late_check_from` (çağıran: ``apps.registrar.lessons_late_rule``). Dəyər ISO tarixi
(``YYYY-MM-DD``) kimi saxlanır — ``kind="date"`` (:func:`coerce_date`; ``runtime_settings.coerce`` ona yönləndirir).

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

import datetime as _dt

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP_CODE = "journal"
KEY_LATE_CHECK_FROM = "journal.late_check_from"

#: Kod defoltu (2026-10-26, bazar ertəsi). ``settings.JOURNAL_LATE_CHECK_FROM`` ilə dəyişə bilər (test ayarları
#: köhnə tarixli test datası üçün onu çox erkən tarixə qoyur).
DEFAULT_LATE_CHECK_FROM = "2026-10-26"


def _default() -> str:
    return str(getattr(settings, "JOURNAL_LATE_CHECK_FROM", DEFAULT_LATE_CHECK_FROM))


def parse_date(raw) -> _dt.date | None:
    """``date`` / ``YYYY-MM-DD`` mətni → ``date``; tanınmırsa ``None`` (``datetime`` və ``bool`` qəbul olunmur)."""
    if isinstance(raw, _dt.datetime) or isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, _dt.date):
        return raw
    try:
        return _dt.date.fromisoformat(str(raw).strip())
    except ValueError:
        return None


def coerce_date(spec, raw):
    """``kind="date"`` üçün: yararlı tarix → ISO mətni, əks halda ``None`` (``spec.kind`` başqadırsa ``None``)."""
    if spec.kind != "date":
        return None
    value = parse_date(raw)
    return None if value is None else value.isoformat()


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_LATE_CHECK_FROM, GROUP_CODE, "date", _default,
            pgettext_lazy(_CTX, "«Gec yazılıb» nəzarətinin başlanğıc tarixi"),
            pgettext_lazy(
                _CTX,
                "Tarixi bu gündən əvvəl olan dərs heç vaxt «Gec yazılıb» sayılmır — nişanda, «Keçilmiş dərslər» "
                "sayında, KPI-da və ixracda. Bu tarixdən (və sonrakı) dərslər üçün qayda dəyişmir: dərsin ilk "
                "xanası dərs tarixindən 48 saatdan gec yazılıbsa «gec»dir. Köhnə sistemdən köçürülmüş data üçün "
                "tarixi köçürmə sonrası ilk iş gününə qoyun.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarı ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açar mövcud «journal» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


def late_check_from() -> _dt.date:
    """«Gec» nəzarətinin başlanğıc tarixi. Tənzimləmə oxunmasa — kod defoltu (heç vaxt istisna atmır)."""
    try:
        from core import runtime_settings

        value = parse_date(runtime_settings.get(KEY_LATE_CHECK_FROM))
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa da «Keçilmiş dərslər» açılmalıdır
        value = None
    return value or parse_date(_default()) or parse_date(DEFAULT_LATE_CHECK_FROM)


__all__ = [
    "DEFAULT_LATE_CHECK_FROM",
    "GROUP_CODE",
    "KEY_LATE_CHECK_FROM",
    "build_specs",
    "coerce_date",
    "late_check_from",
    "parse_date",
    "register",
]
