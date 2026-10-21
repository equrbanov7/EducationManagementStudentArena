"""Ekran 07 «Semestr açılışı» — «Necə işləyir» kartının mətnləri.

2026-10-21: ``semester_open``-dan çıxarılıb (modul 600 sətir tavanına çatmışdı; açılış önizləməsi —
kohort planı təsdiqi — üçün yer lazım idi). ``semester_open.semester_howto`` re-eksport kimi qalır.
"""

from __future__ import annotations

from django.utils.translation import pgettext

_CTX = "accounts.semester"


def semester_howto(steps: list) -> list:
    """«Necə işləyir» kartı — hər addımda NƏ edilir, HANSI düymə, KİM edir.

    Stepper yalnız vəziyyəti göstərir; bu mətnlər prosesi düymə axtarmadan
    başa düşmək üçündür (sahib rəyi 2026-09-07: «izahı biraz çətindi»).
    Vəziyyət (`done/current/todo/error`) stepper addımından götürülür.
    """
    items = [
        {
            "title": pgettext(_CTX, "Tədris dövrünü seçin və plandan açılış yaradın"),
            "text": pgettext(
                _CTX,
                "Yuxarıdakı süzgəcdən semestri seçin. «Plandan açılış yarat» həmin semestri oxuyan (kursu uyğun) "
                "hər qrup üçün qrupun ÖZ qəbul ilinin təsdiqlənmiş tədris planının (yoxdursa — təsdiqinizlə ən "
                "son planın) məcburi fənlərindən açılış yaradır və qrupun aktiv "
                "tələbələrini dərhal qeydiyyata alır; seçmə fənlər qrupun seçimi ilə açılır. Mövcud sətir "
                "təkrarlanmır, heç nə silinmir. «Plan yoxdur» ixtisaslar üçün sətir yaranmır — əvvəlcə «Tədris "
                "planı» bölməsində planı təsdiqləyin.",
            ),
            "button": pgettext(_CTX, "Plandan açılış yarat"),
            "who": pgettext(_CTX, "Tədris şöbəsi"),
        },
        {
            "title": pgettext(_CTX, "Kafedralara göndərin"),
            "text": pgettext(
                _CTX,
                "Açılış sətirləri hazır olanda «Kafedraya göndər» kafedra rəhbərlərinə bildiriş göndərir — "
                "bundan sonra onlar «Dərs yükü» bölməsində öz fənlərinə müəllim təyin edə bilir.",
            ),
            "button": pgettext(_CTX, "Kafedraya göndər"),
            "who": pgettext(_CTX, "Tədris şöbəsi"),
        },
        {
            "title": pgettext(_CTX, "Kafedra müəllim təyin edir"),
            "text": pgettext(
                _CTX,
                "Hər açılışa müəllim təyin olunmalıdır. Aşağıdakı «Kafedralar üzrə açılış» cədvəli neçə sətrin "
                "müəllim gözlədiyini göstərir; açılış sətrindəki «Müəllim» əməli ilə buradan da təyin etmək olar.",
            ),
            "button": pgettext(_CTX, "Dərs yükü → Müəllim təyin et"),
            "who": pgettext(_CTX, "Kafedra rəhbəri"),
        },
        {
            "title": pgettext(_CTX, "Jurnallar açılır"),
            "text": pgettext(
                _CTX,
                "Müəllim təyin olunan kimi həmin fənnin elektron jurnalı avtomatik yaranır. "
                "Jurnalı olmayan sətir müəllimi olmayan sətirdir — ayrıca əməl tələb olunmur.",
            ),
            "button": "",
            "who": pgettext(_CTX, "Sistem (avtomatik)"),
        },
        {
            "title": pgettext(_CTX, "Semestri kilidləyin"),
            "text": pgettext(
                _CTX,
                "Üç şərt ödənəndə (plan təsdiqlənib, bütün açılışlara müəllim var, jurnallar açılıb) "
                "«Semestri kilidlə» aktivləşir. Kilid açılış sətirlərini dondurur; onu yalnız ayrıca "
                "səlahiyyətli şəxs səbəb yazmaqla aça bilər.",
            ),
            "button": pgettext(_CTX, "Semestri kilidlə"),
            "who": pgettext(_CTX, "Tədris şöbəsi rəhbəri"),
        },
    ]
    for item, step in zip(items, steps):
        item["state"] = step.get("state", "todo")
    return items


__all__ = ["semester_howto"]
