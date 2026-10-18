"""«Sistem tənzimləmələri» — 25% təkrar imtahan / alt qrup müraciəti açarları (sahib 2026-10-18).

``core/runtime_settings.py`` modul-ölçü tavanına (600) yaxındır; açarlar burada təyin olunub oradan
``SPECS``-ə qatılır. Oxu nöqtəsi YALNIZ ``apps.registrar.retake_rules`` — çağıranlar açarı birbaşa oxumur.
``Spec`` sinfi parametr kimi gəlir (dövri import yoxdur).
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP = ("retake", pgettext_lazy(_CTX, "25% təkrar imtahan və alt qrup"))
#: 2026-10-19 (sahib): Mühasibatlığın plan ↔ fakt kənarlaşma bandı da buradan idarə olunur.
ACCOUNTING_GROUP = ("accounting", pgettext_lazy(_CTX, "Mühasibatlıq"))
GROUPS = (GROUP, ACCOUNTING_GROUP)


def retake_specs(spec_class) -> tuple:
    return (
        spec_class(
            "retake.applications_open",
            "retake",
            "bool",
            lambda: bool(getattr(settings, "RETAKE_APPLICATIONS_OPEN", True)),
            pgettext_lazy(_CTX, "Müraciət pəncərəsi açıqdır"),
            pgettext_lazy(
                _CTX,
                "Açıq olanda tələbə kəsr fənlər üzrə 25% təkrar imtahan və ya alt qrup müraciəti göndərə bilir. "
                "Bağlananda yeni müraciət qəbul olunmur; artıq göndərilmiş müraciətlərə baxış və qərarlar davam edir.",
            ),
        ),
        spec_class(
            "retake.max_attempts",
            "retake",
            "int",
            lambda: int(getattr(settings, "RETAKE_MAX_ATTEMPTS", 1)),
            pgettext_lazy(_CTX, "Bir fənn üzrə 25% cəhd sayı"),
            pgettext_lazy(
                _CTX,
                "Bir fənn üzrə tələbəyə ən çox neçə dəfə 25% təkrar imtahan verilir (buraxılmış, cəhdi verilmiş "
                "və tamamlanmış müraciətlər sayılır). Limit dolanda yalnız alt qrup yolu qalır.",
            ),
            pgettext_lazy(_CTX, "cəhd"),
            min=1,
            max=10,
        ),
        # 2026-10-19 (sahib: «İlliyə görə hesablanır, amma dəqiq bilmirəm»): təxmini məbləğin düsturu —
        # illik təhsil haqqı × faiz ÷ 100 × (fənnin krediti ÷ illik kredit). Oxu nöqtəsi: ``apps.registrar.retake_fees``.
        spec_class(
            "retake.fee_percent",
            "retake",
            "decimal",
            lambda: getattr(settings, "RETAKE_FEE_PERCENT", 25),
            pgettext_lazy(_CTX, "25% ödənişinin faizi"),
            pgettext_lazy(
                _CTX,
                "Təxmini məbləğ = illik təhsil haqqı × bu faiz ÷ 100 × (fənnin krediti ÷ illik kredit). Dəqiq məbləği "
                "Mühasibatlıq qəbzi yoxlayanda təsdiqləyir; fərq xəbərdarlıqdır, blok deyil.",
            ),
            "%",
            min=0,
            max=100,
        ),
        spec_class(
            "retake.fee_annual_credits",
            "retake",
            "int",
            lambda: int(getattr(settings, "RETAKE_FEE_ANNUAL_CREDITS", 60)),
            pgettext_lazy(_CTX, "İllik kredit (məbləğ düsturu üçün)"),
            pgettext_lazy(
                _CTX,
                "Fənnin payı = fənnin krediti ÷ bu ədəd. 0 yazılsa kreditə bölünmür: məbləğ = illik haqq × faiz ÷ 100.",
            ),
            pgettext_lazy(_CTX, "kredit"),
            min=0,
            max=120,
        ),
        spec_class(
            "accounting.deviation_percent",
            "accounting",
            "int",
            lambda: int(getattr(settings, "ACCOUNTING_DEVIATION_PERCENT", 10)),
            pgettext_lazy(_CTX, "Plan ↔ fakt kənarlaşma bandı"),
            pgettext_lazy(
                _CTX,
                "Keçirilmiş dərs saatı planın ±bu faiz daxilindədirsə «Plana uyğun» sayılır; azdırsa «Plandan az», "
                "çoxdursa «Plandan çox».",
            ),
            "%",
            min=0,
            max=50,
        ),
    )


__all__ = ["ACCOUNTING_GROUP", "GROUP", "GROUPS", "retake_specs"]
