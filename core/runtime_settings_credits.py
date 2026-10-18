"""«Kredit yükü və alt qrup» — «Sistem tənzimləmələri» açarları (sahib 2026-10-18).

Sahib: «Hər tələbənin bir semestrdə götürə biləcəyi max kredit var — alt qrupa və s. yazılanda o hesablanır;
bunu sistem tərəfindən tənzimləmək olsun». Oxu nöqtəsi YALNIZ ``apps.registrar.credit_load`` — çağıranlar
açarları birbaşa oxumur.

NİYƏ AYRI MODUL: ``core/runtime_settings.py`` modul ölçüsü büdcəsinə (600) yaxındır. Bu modul ``Spec`` sinfini
IMPORT ETMİR (dövri import olmasın) — ``runtime_settings`` öz ``Spec``-ini :func:`build_specs`-ə ötürür.

Defoltlar (QA klonunda real yazılışlar, 2026-10-18): semestr yükünün medianı 27–28, 95-ci faiz 34–35 kredit;
tədris planı semestri 30 ECTS (``SEMESTER_CREDIT_TARGET``). Ona görə: adi hədd 30, alt qrupla birlikdə 36.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

GROUP = ("credits", pgettext_lazy("core.runtime_settings", "Kredit yükü və alt qrup"))

MAX_PER_SEMESTER_DEFAULT = 30
MAX_WITH_SUBGROUP_DEFAULT = 36


def build_specs(spec_cls) -> tuple:
    """``runtime_settings.Spec`` nümunələri (sinif çağırandan gəlir — dövri import yoxdur)."""
    unit = pgettext_lazy("core.runtime_settings", "kredit")
    return (
        spec_cls(
            "credits.max_per_semester", "credits", "int", lambda: MAX_PER_SEMESTER_DEFAULT,
            pgettext_lazy("core.runtime_settings", "Semestrdə maksimum kredit"),
            pgettext_lazy(
                "core.runtime_settings",
                "Tələbənin bir semestrdə daşıya biləcəyi adi kredit yükü (öz qrupunun fənləri). Kabinetdə «Bu semestr: "
                "27 / 30 kredit» kimi göstərilir. Tədris planı bu həddi keçirsə də öz fənləri bloklanmır — yalnız "
                "xəbərdarlıq görünür.",
            ),
            unit, min=10, max=90,
        ),
        spec_cls(
            "credits.max_with_subgroup", "credits", "int", lambda: MAX_WITH_SUBGROUP_DEFAULT,
            pgettext_lazy("core.runtime_settings", "Alt qrupla birlikdə maksimum kredit"),
            pgettext_lazy(
                "core.runtime_settings",
                "Tələbə alt qrupa (başqa qrupun jurnalına) yerləşdiriləndə öz fənləri + alt qrup fənləri birlikdə bu "
                "həddi keçə bilməz — keçərsə yerləşdirmə edilmir. 0 — ayrıca hədd yoxdur, «Semestrdə maksimum "
                "kredit» tətbiq olunur.",
            ),
            unit, min=0, max=90,
        ),
        spec_cls(
            "credits.clash_blocks", "credits", "bool", lambda: False,
            pgettext_lazy("core.runtime_settings", "Cədvəl toqquşması yerləşdirməni bloklasın"),
            pgettext_lazy(
                "core.runtime_settings",
                "Söndürülübsə alt qrupun dərs saatı tələbənin öz cədvəli ilə üst-üstə düşəndə yalnız xəbərdarlıq "
                "göstərilir və işçi bunu təsdiqləyib davam edə bilər. Yandırılıbsa toqquşan yerləşdirmə edilmir.",
            ),
        ),
        spec_cls(
            "credits.journal_capacity", "credits", "int", lambda: 0,
            pgettext_lazy("core.runtime_settings", "Bir jurnalda maksimum tələbə"),
            pgettext_lazy(
                "core.runtime_settings",
                "Alt qrup yerləşdirməsində hədəf jurnalın tutumu: jurnalda bu qədər aktiv tələbə varsa yeni tələbə "
                "əlavə olunmur. 0 — tutum həddi yoxdur.",
            ),
            pgettext_lazy("core.runtime_settings", "tələbə"), min=0, max=500,
        ),
    )  # fmt: skip


__all__ = ["GROUP", "MAX_PER_SEMESTER_DEFAULT", "MAX_WITH_SUBGROUP_DEFAULT", "build_specs"]
