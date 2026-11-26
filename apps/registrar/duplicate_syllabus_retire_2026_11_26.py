"""Firəngiz Azadəliyeva (2026-11-26): eyni fənnə (QKU-2416) ikinci, jurnala bağlı olmayan sillabus — biri ləğv olunsun.


Müəllimə yazır: «Genetik məlumatların ekspressiyasının tənzimlənmə mexanizmləri — buna aid 2 sillabus açılıb, biri ləğv
olunmalıdır». Jurnal (505/5 MB) Səliqə Qazinin 71%-lik təsdiqlənmiş sillabusunu işlədir; müəllimənin öz yaratdığı
semestrsiz 29%-lik nüsxəsi heç bir jurnala bağlı deyil — o passiv olur. Dosye SİLİNMİR — yalnız ``is_active=False``
(qoruyucular :mod:`.uiux_syllabus_retire_2026_11_12`-dədir: müəllif və fənn kodu gözlənilən kimi, aktiv jurnala bağlı
deyil, paylaşılmayıb). ``undo`` yalnız bu əmrin audit izinə görə geri açır.
"""

from __future__ import annotations

from . import uiux_syllabus_retire_2026_11_12 as base

RETIRED = "registrar.duplicate_syllabus_retire_2026_11_26.retired"
REASON = "Müəllimənin müraciəti 2026-11-26: QKU-2416 üzrə jurnala bağlı olmayan ikinci sillabus ləğv olundu"
TARGET = {
    "syllabus": "adf27bf9-ec8b-490e-bc03-6aac90dd70a5",
    "author": 11622,
    "subject_code": "QKU-2416",
    "keeper_subject_code": "",
}


def run(*, organization, actor, counts, apply=False, target=None) -> None:
    base.run(
        organization=organization,
        actor=actor,
        counts=counts,
        apply=apply,
        target=target or TARGET,
        resource_type=RETIRED,
        reason=REASON,
    )


def undo(*, organization, actor, counts, apply=False, target=None) -> None:
    base.undo(organization=organization, actor=actor, counts=counts, apply=apply, resource_type=RETIRED)


__all__ = ["RETIRED", "TARGET", "run", "undo"]
