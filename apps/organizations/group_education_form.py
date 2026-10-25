"""Qrup adından təhsil forması — sahibin qaydası (2026-10-25).

    «Qrup nömrəsində 4 rəqəm varsa (məs. «2232 K») — QİYABİDİR; 3 rəqəm varsa
    («234 KE») — ƏYANİDİR.»

Qayda YALNIZ birmənalı bakalavr qrup koduna tətbiq olunur — adın əvvəlindəki rəqəm bloku
(3 və ya 4 rəqəm) + istəyə bağlı hərf-şəkilçi («K», «KE», «İT ing», «TB1», «M RUS»):

* ``234 KE`` / ``234KE`` / ``036 ing`` / ``028`` → ``full_time`` (əyani)
* ``2232 K`` / ``2233KE`` / ``2534 ML`` → ``part_time`` (qiyabi)

Qeyri-standart adlar QAYDADAN KƏNARDIR (``None``) — avtomatik dəyişmir, hesabatda göstərilir:

* ``/`` olan kodlar — magistr («409/6MBA», «510/6BİEO»), kollec («104/9», «1701/0»), «3/336 F»;
* rəqəmdən dərhal sonra mötərizə, tire, nöqtə («1225(A)», «2029A-(qrupBMU)», «22(UNEC)»);
* YALNIZ 4 rəqəmdən ibarət ad («1025», «2026») — kollecin «<kurs><il>» kodu ilə toqquşur;
* «0» ilə başlayan 4 rəqəmli blok («0055 …» — Lifelong);
* 1, 2, 5+ rəqəmli bloklar, rəqəmsiz adlar («Level - Group 3»).

Kontekst istisnaları (ad standart olsa da): magistr qrupu (``settings.degree_level=master``) və
kollec qrupu (legacy ``kollec_or_uni=Kollec`` və ya əcdad bölmənin adında «Kollec») —
məs. «1226 A» kollec qrupudur, qiyabi deyil.

Dəyərlər ``registrar.EducationForm`` ilə eynidir (``full_time`` / ``part_time``) — modul sərhədi
səbəbindən burada string kimi saxlanılır.
"""

from __future__ import annotations

import re

FULL_TIME = "full_time"
PART_TIME = "part_time"

#: Rəqəm bloku + istəyə bağlı şəkilçi: şəkilçi HƏRFLƏ başlamalı, sonra hərf/rəqəm/boşluq/mötərizə
#: («229 BİO (Rafia)») və bir alt qrup tiresi («234 K-1», «235 İ-1 az»); «/», «.», rəqəmdən dərhal sonra gələn
#: mötərizə/tire («1225(A)», «630-İ») və tiredən sonra mötərizə («2029A-(qrupBMU)») qeyri-standartdır.
_CODE_RE = re.compile(r"^\s*(\d+)(?:\s*([^\W\d_][\w ()]*(?:-\s*\w[\w ]*)?))?\s*$")
_COLLEGE_MARKERS = ("kollec", "kolec", "college")

#: Qaydadan kənar qalma səbəbləri (hesabat açarları).
REASON_NONSTANDARD = "nonstandard_name"
REASON_BARE_FOUR_DIGITS = "bare_four_digits"
REASON_MASTER = "master"
REASON_COLLEGE = "college"


def _name_rule(name) -> tuple[str | None, str]:
    text = str(name or "").strip()
    match = _CODE_RE.match(text)
    if match is None:
        return None, REASON_NONSTANDARD
    digits, suffix = match.group(1), match.group(2)
    if len(digits) == 3:
        return FULL_TIME, ""
    if len(digits) == 4:
        if digits.startswith("0"):
            return None, REASON_NONSTANDARD
        if not suffix:
            return None, REASON_BARE_FOUR_DIGITS
        return PART_TIME, ""
    return None, REASON_NONSTANDARD


def education_form_from_group_name(name) -> str | None:
    """Ad birmənalı bakalavr qrup kodudursa forma (``full_time`` / ``part_time``), əks halda ``None``."""

    return _name_rule(name)[0]


def _is_college(settings: dict, ancestor_names) -> bool:
    legacy = settings.get("legacy") if isinstance(settings.get("legacy"), dict) else {}
    if str(legacy.get("kollec_or_uni") or "").strip().casefold() in _COLLEGE_MARKERS:
        return True
    return any(marker in str(name or "").casefold() for name in ancestor_names for marker in _COLLEGE_MARKERS)


def chain_names(parent) -> list[str]:
    """``parent`` və onun bütün əcdadlarının adları — materialized path ilə bir sorğu."""

    from .models import OrgUnit

    if parent is None:
        return []
    ids = [segment for segment in (getattr(parent, "path", "") or "").strip("/").split("/") if segment]
    if not ids:
        return [parent.name]
    return list(OrgUnit.objects.filter(pk__in=ids).values_list("name", flat=True))


def ancestor_names(unit) -> list[str]:
    """Qrupun əcdad bölmələrinin adları.

    Valideynin ``path``-ı işlədilir — yeni / valideyni dəyişən qrupun öz ``path``-ı hələ boşdur və ya köhnədir.
    """

    return chain_names(getattr(unit, "parent", None) if getattr(unit, "parent_id", None) else None)


def rule_form_for(name, *, settings=None, names=()) -> tuple[str | None, str]:
    """Qaydanın forması və (``None`` olarsa) səbəb — ad + ``settings`` (degree/legacy) + əcdad adları ilə."""

    settings = settings if isinstance(settings, dict) else {}
    form, reason = _name_rule(name)
    if form is None:
        return None, reason
    if str(settings.get("degree_level") or "").strip().casefold() == "master":
        return None, REASON_MASTER
    if _is_college(settings, names):
        return None, REASON_COLLEGE
    return form, ""


def group_rule_form(unit, *, names=None) -> tuple[str | None, str]:
    """Qrup (``OrgUnit``) üçün :func:`rule_form_for`; ``names`` verilməsə əcdad adları bir sorğu ilə oxunur."""

    form, reason = _name_rule(getattr(unit, "name", ""))
    if form is None:
        return None, reason
    return rule_form_for(
        unit.name, settings=getattr(unit, "settings", None), names=ancestor_names(unit) if names is None else names
    )


__all__ = [
    "FULL_TIME",
    "PART_TIME",
    "REASON_BARE_FOUR_DIGITS",
    "REASON_COLLEGE",
    "REASON_MASTER",
    "REASON_NONSTANDARD",
    "ancestor_names",
    "chain_names",
    "education_form_from_group_name",
    "group_rule_form",
    "rule_form_for",
]
