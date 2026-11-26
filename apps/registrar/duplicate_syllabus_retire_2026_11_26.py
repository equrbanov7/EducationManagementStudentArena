"""Firəngiz Azadəliyeva (2026-11-26): eyni fənnə (QKU-2416) ikinci, jurnala bağlı olmayan sillabus — biri ləğv olunsun.


Müəllimə yazır: «Genetik məlumatların ekspressiyasının tənzimlənmə mexanizmləri — buna aid 2 sillabus açılıb, biri ləğv
olunmalıdır». Jurnal (505/5 MB) Səliqə Qazinin 71%-lik təsdiqlənmiş sillabusunu işlədir; müəllimənin öz yaratdığı
semestrsiz 29%-lik nüsxəsi heç bir jurnala bağlı deyil — o passiv olur. Dosye SİLİNMİR — yalnız ``is_active=False``
(qoruyucular :mod:`.uiux_syllabus_retire_2026_11_12`-dədir: müəllif və fənn kodu gözlənilən kimi, aktiv jurnala bağlı
deyil, paylaşılmayıb). ``undo`` yalnız bu əmrin audit izinə görə geri açır.

MR-000850 (2026-11-26, Rəhim Həsənov): «Etika» (QKU-69) üzrə YAZ semestrinə yazılmış 4 boş qaralama (535 MRK, 535 Bİ,
335F1, 335F2) — fənn payızdadır, payız jurnallarının öz təsdiqlənmiş sillabusları (15 · 15) var; qaralamalar heç bir
jurnala bağlı deyil və müəllim onların siyahısından çıxarılmasını istəyib. Eyni qaydalarla passiv olurlar (``EXTRA``).
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


REASON_850 = "MR-000850 (2026-11-26): «Etika» QKU-69 üzrə yaz semestrinə yazılmış, jurnala bağlı olmayan boş qaralama"
EXTRA = tuple(
    {"syllabus": syllabus, "author": 9519, "subject_code": "QKU-69", "keeper_subject_code": "", "reason": REASON_850}
    for syllabus in (
        "8f5c4079-a231-4ea9-820d-8f3057421341",  # Marketinq (535 MRK)
        "53edaf58-6d6d-452c-9c53-2a0e91b3fdb7",  # Biznesin idarə edilməsi (535 Bİ)
        "3768e812-f6c8-410e-894e-e2bc1dfe4be1",  # Filologiya (335F1 / 335F2)
        "a3041e7d-5ac9-43fb-a32b-c63b8a6c0bf7",  # Filologiya (335F1 / 335F2)
    )
)
# MR-000852 (2026-11-26, Nərmin Heydərova): «Etika və estetika» (QKU-588) — 2235 M (Meşəçilik) və 2234 KE (Kompüter
# elmləri) üçün yaz semestrinə yazılmış, jurnala bağlı olmayan boş qaralamalar; müəllimin həmin qruplarda jurnalı yoxdur.
REASON_852 = "MR-000852 (2026-11-26): «Etika və estetika» QKU-588 üzrə yaz semestrinə yazılmış, jurnalsız boş qaralama"
EXTRA += tuple(
    {"syllabus": syllabus, "author": 8374, "subject_code": "QKU-588", "keeper_subject_code": "", "reason": REASON_852}
    for syllabus in (
        "f0f99f04-12cb-4fe0-9ee9-424c254227b4",  # Meşəçilik (2235 M)
        "1fd1e6b8-3a8c-41ef-bb1e-d25f39a617f8",  # Kompüter elmləri (2234 KE)
    )
)


def run(*, organization, actor, counts, apply=False, target=None) -> None:
    for item in [target] if target else [TARGET, *EXTRA]:
        base.run(
            organization=organization,
            actor=actor,
            counts=counts,
            apply=apply,
            target=item,
            resource_type=RETIRED,
            reason=item.get("reason") or REASON,
        )


def undo(*, organization, actor, counts, apply=False, target=None) -> None:
    base.undo(organization=organization, actor=actor, counts=counts, apply=apply, resource_type=RETIRED)


__all__ = ["EXTRA", "RETIRED", "TARGET", "run", "undo"]
