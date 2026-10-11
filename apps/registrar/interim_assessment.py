"""Aralıq qiymətləndirmə rejimi — 3 kollokvium (keçmiş dövrlər) və ya 1 midterm (2026/2027-dən).

SAHİBİN QƏRARI (2026-09-25): «3 kollokvium olmayacaq, 1 midterm olacaq — 20 ballıq; bal yazma
vaxtını İmtahan Mərkəzi təyin edir; hər yerdə kollokviumu midterm ilə əvəz et; müəllim
skalasında 0–20 görünsün; köhnə tələbələrdə indiyə qədər olan kollokvium forması qalsın,
bu ildən midterm görünsün».

Texniki qərar — midterm AYRI komponent növü DEYİL. Mövcud ``ComponentKind.KOLLOKVIUM``
mexanizmi (İmtahan Mərkəzinin bal-yazma pəncərəsi, 2 saat kilidinin yerinə pəncərə,
giriş balına CƏM kimi əlavə, sənədli düzəliş axını, bildirişlər) olduğu kimi qalır; rejimlər
arasında fərq yalnız bu üç şeydir:

* SAY — 3 (K1/K2/K3) → 1;
* TAVAN — hər biri 10 → 20 (sahib 2026-10-10: sərbəst iş ləğv olunanda 30 — :func:`midterm_max`);
* AD — «Kollokvium N» → «Midterm».

Beləliklə hesablama yolları (``gradebook.entry_score_for``, ``analytics`` güzgüsü,
``finals_batch``) dəyişmir, keçmiş dövrlərin datası (1,4 mln-dan çox kollokvium balı)
toxunulmaz qalır və əvvəlki kimi K1–K3 görünür.

Rejim açılışın DÖVRÜNDƏN çıxır: tədris ili ``MIDTERM_FROM_YEAR``-dan (2026 → «2026/2027»)
başlayan dövrlər midterm, əvvəlkilər kollokvium rejimindədir. Təşkilat bu həddi
``Organization.settings["registrar"]["midterm_from_year"]`` ilə dəyişə bilər (kod dəyişmədən).

Bu modul rejim qərarının YEGANƏ mənbəyidir — jurnal, İmtahan Mərkəzi pəncərələri, tələbə
kabineti və sillabus eyni cavabı buradan alır.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import pgettext_lazy

# Dövr-il məntiqi sillabus/fənn qovluğu ilə ortaqdır (onlar registrar-ı import edə bilmir) — tək mənbə core-dadır;
# adlar bu modulda qalır ki, mövcud çağıranlar (``interim_assessment.midterm_from_year`` …) dəyişməsin.
from core.academic_rules import (  # noqa: F401
    MIDTERM_FROM_YEAR,
    midterm_from_year,
    period_start_year,
    period_uses_new_rules,
)

_CTX = "registrar.interim"

MODE_KOLLOKVIUM = "kollokvium"
MODE_MIDTERM = "midterm"

KOLLOKVIUM_COUNT = 3
KOLLOKVIUM_MAX = 10
MIDTERM_COUNT = 1
#: Sərbəst iş AÇIQ olanda midterm tavanı (2026-09-25 qaydası). Cari tavan — :func:`midterm_max`:
#: sahib 2026-10-10 sərbəst işi ləğv etdi, onun 10 balı midterm-ə keçir (30); RİM bayrağı ilə geri qayıdır.
MIDTERM_MAX = 20


def midterm_max() -> int:
    """Midterm komponentinin cari tavanı (30; sərbəst iş açıqdırsa 20) — ``core.academic_rules``."""
    from core.academic_rules import midterm_max as _rule

    return _rule()


#: Komponent adı DB-də saxlanan DATA-dır (tərcümə olunmur); görünən ad ``InterimSpec``-dən gəlir.
MIDTERM_COMPONENT_NAME = "Midterm"
KOLLOKVIUM_NAME_PATTERN = "Kollokvium {n}"


@dataclass(frozen=True)
class InterimSpec:
    """Bir rejimin görünüş + say + tavan təsviri (şablonlar üçün sadə atributlar)."""

    mode: str
    count: int
    max_score: int
    component_names: tuple[str, ...]
    #: Sütun/pəncərə qısa adları: ("K1", "K2", "K3") və ya ("Midterm",).
    short_labels: tuple[str, ...]
    #: Bölmə/tab başlığı: «Kollokvium» / «Midterm».
    title: str
    #: Tam izah: «3 kollokvium (hər biri 0–10 bal)» / «Midterm — aralıq imtahan (0–30 bal)» (tavan :func:`midterm_max`).
    description: str

    @property
    def is_midterm(self) -> bool:
        return self.mode == MODE_MIDTERM

    @property
    def total_max(self) -> int:
        return self.count * self.max_score

    @property
    def scale_label(self) -> str:
        return f"0–{self.max_score}"

    def label_for(self, index: int) -> str:
        """``k_index`` (0-dan) → «K2» / «Midterm»; hüdud xaricində «K{n}»."""
        if 0 <= index < len(self.short_labels):
            return self.short_labels[index]
        return f"K{index + 1}"


def _kollokvium_spec() -> InterimSpec:
    return InterimSpec(
        mode=MODE_KOLLOKVIUM,
        count=KOLLOKVIUM_COUNT,
        max_score=KOLLOKVIUM_MAX,
        component_names=tuple(KOLLOKVIUM_NAME_PATTERN.format(n=i) for i in range(1, KOLLOKVIUM_COUNT + 1)),
        short_labels=tuple(f"K{i}" for i in range(1, KOLLOKVIUM_COUNT + 1)),
        title=str(pgettext_lazy(_CTX, "Kollokvium")),
        description=str(pgettext_lazy(_CTX, "3 kollokvium (hər biri 0–10 bal)")),
    )


def _midterm_spec() -> InterimSpec:
    max_score = midterm_max()
    return InterimSpec(
        mode=MODE_MIDTERM,
        count=MIDTERM_COUNT,
        max_score=max_score,
        component_names=(MIDTERM_COMPONENT_NAME,),
        short_labels=(str(pgettext_lazy(_CTX, "Midterm")),),
        title=str(pgettext_lazy(_CTX, "Midterm")),
        description=str(pgettext_lazy(_CTX, "Midterm — aralıq imtahan (0–%(max)s bal)") % {"max": max_score}),
    )


def spec_for_mode(mode: str) -> InterimSpec:
    """Rejim → təsvir (dil hər çağırışda aktiv dildən oxunur)."""
    return _midterm_spec() if mode == MODE_MIDTERM else _kollokvium_spec()


def mode_for_period(period, organization=None) -> str:
    """Dövr üçün rejim. Dövr/il məlum deyilsə — yeni qayda (midterm). Qərar ``core.academic_rules``-dadır."""
    return MODE_MIDTERM if period_uses_new_rules(period, organization) else MODE_KOLLOKVIUM


def mode_for_offering(offering) -> str:
    if offering is None:
        return MODE_MIDTERM
    return mode_for_period(getattr(offering, "period", None), getattr(offering, "organization", None))


def spec_for_period(period, organization=None) -> InterimSpec:
    return spec_for_mode(mode_for_period(period, organization))


def spec_for_offering(offering) -> InterimSpec:
    return spec_for_mode(mode_for_offering(offering))


def is_midterm_offering(offering) -> bool:
    return mode_for_offering(offering) == MODE_MIDTERM


__all__ = [
    "InterimSpec",
    "KOLLOKVIUM_COUNT",
    "KOLLOKVIUM_MAX",
    "MIDTERM_COMPONENT_NAME",
    "MIDTERM_COUNT",
    "MIDTERM_FROM_YEAR",
    "MIDTERM_MAX",
    "MODE_KOLLOKVIUM",
    "MODE_MIDTERM",
    "is_midterm_offering",
    "midterm_from_year",
    "midterm_max",
    "mode_for_offering",
    "mode_for_period",
    "period_start_year",
    "spec_for_mode",
    "spec_for_offering",
    "spec_for_period",
]
