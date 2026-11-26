"""08.11 «aktivliyi olmayan tələbə» dondurulması — «Tələbəni bərpa et» pəncərəsinin bərpa yolu (sahib 2026-11-26).

Sahib: «bərpa etmək istəyirəm, olmur» — pəncərə dondurulmuş tələbəni göstərirdi, amma seçmək olmurdu və izah onu
qrup reyestrinə (məzuniyyət / xaric / məzun) göndərirdi. Halbuki 08.11 dondurulması akademik status deyil: əmr
tələbənin açıq dövrlərdəki yazılışlarını ``suspended`` edib hesabı bloklayıb (:mod:`apps.accounts.services.
inactive_students_2026_11_08`). Geri qaytarma da EYNİ əmrin ``--undo --only <hesab>`` yoludur.

Hesab və audit izi accounts-dadır; registrar → accounts importu modul dövrü yaradır, ona görə accounts ``ready()``
provayderi buradan qeydiyyatdan keçirir (provayder yoxdursa heç nə tanınmır — fail-closed). Provayder:

* ``frozen_enrollment_ids(organization, student_ids) -> set[str]`` — əmrin dondurduğu yazılış id-ləri;
* ``undo_student(*, organization, actor, student_id) -> dict`` — tələbənin bütün dondurulmasını geri qaytarır.
"""

from __future__ import annotations

_provider = None


def register_inactive_freeze_provider(provider) -> None:
    global _provider
    _provider = provider


def frozen_enrollment_ids(organization, student_ids) -> set:
    ids = {pk for pk in student_ids if pk}
    if _provider is None or organization is None or not ids:
        return set()
    return {str(pk) for pk in _provider.frozen_enrollment_ids(organization, ids)}


def undo_student(*, organization, actor, student_id) -> dict:
    if _provider is None:
        raise RuntimeError("inactive_freeze_provider_missing")
    return dict(_provider.undo_student(organization=organization, actor=actor, student_id=student_id))


__all__ = ["frozen_enrollment_ids", "register_inactive_freeze_provider", "undo_student"]
