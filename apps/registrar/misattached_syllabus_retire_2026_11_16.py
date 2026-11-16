"""MR-000403 (2026-11-16): köhnə sistemdən SƏHV fənnə bağlanmış sillabus müəllimin siyahısından çıxarılır.

Tarix kafedrasının müəlliminin semestrsiz köçürülmüş dosyesi (mətni — tarix fənni) «QKU-2690 Zərərverici proqram
vasitələrinin təhlili (Malware analysis)» fənninə bağlanıb və onun «Sillabuslarım» siyahısında görünür; heç bir
jurnal ondan istifadə etmir. Dosye SİLİNMİR — yalnız ``is_active=False`` (qayda və qoruyucular
:mod:`.uiux_syllabus_retire_2026_11_12`-dədir: müəllif və fənn kodu gözlənilən kimi, aktiv jurnala bağlı deyil,
paylaşılmayıb). ``undo`` yalnız bu əmrin audit izinə görə geri açır.
"""

from __future__ import annotations

from . import uiux_syllabus_retire_2026_11_12 as base

RETIRED = "registrar.misattached_syllabus_retire_2026_11_16.retired"
REASON = "MR-000403: köhnə sistemdən səhv fənnə (QKU-2690) bağlanmış sillabus müəllimin siyahısından çıxarıldı"
TARGET = {
    "syllabus": "6e1a79f8-60bc-427f-a5a7-063d5075af05",
    "author": 7847,
    "subject_code": "QKU-2690",
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
