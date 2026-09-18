#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-19: ATİS «Bakalavr» qəbul sütunları (reyestr, RİM forması,
tələbə idxalı, enum etiketləri). Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr =
msgid. İdempotent; sonra `compilemessages`.

İstifadə:  python scripts/i18n_add_atis_admission_2026_09_19.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

# (ctx, msgid): (en, ru, tr)
STRINGS = {
    ("accounts.student_registry", "Ad, FİN, vəsiqə № və ya tələbə kodu"): ("Name, FIN, ID number or student code", "Имя, FIN, № удостоверения или код студента", "Ad, FİN, kimlik no veya öğrenci kodu"),
    ("accounts.student_registry", "Müraciət tarixi"): ("Application date", "Дата заявления", "Başvuru tarihi"),
    ("accounts.student_registry", "Qeyd"): ("Note", "Примечание", "Not"),
    ("accounts.student_registry", "Qeydiyyat ünvanı"): ("Registered address", "Адрес регистрации", "Kayıt adresi"),
    ("accounts.student_registry", "Qəbul növü"): ("Admission type", "Тип приёма", "Kabul türü"),
    ("accounts.student_registry", "Qəbul tarixi"): ("Admission date", "Дата зачисления", "Kabul tarihi"),
    ("accounts.student_registry", "Qəbul xətti"): ("Admission channel", "Канал приёма", "Kabul kanalı"),
    ("accounts.student_registry", "Tur"): ("Round", "Тур", "Kabul turu"),
    ("accounts.student_registry", "Tədris dili"): ("Language of instruction", "Язык обучения", "Eğitim dili"),
    ("accounts.student_registry", "Təhsil haqqı məbləği"): ("Tuition fee amount", "Сумма оплаты за обучение", "Öğrenim ücreti tutarı"),
    ("accounts.student_registry", "Vətəndaşlıq"): ("Citizenship", "Гражданство", "Vatandaşlık"),
    ("accounts.student_registry", "Şəxsiyyət vəsiqəsi"): ("ID document", "Удостоверение личности", "Kimlik belgesi"),
    ("profile.rim", "Qəbul növü"): ("Admission type", "Тип приёма", "Kabul türü"),
    ("profile.rim", "Qəbul növü tanınmadı."): ("Admission type not recognised.", "Тип приёма не распознан.", "Kabul türü tanınmadı."),
    ("profile.rim", "Qəbul xətti"): ("Admission channel", "Канал приёма", "Kabul kanalı"),
    ("profile.rim", "Qəbul xətti tanınmadı."): ("Admission channel not recognised.", "Канал приёма не распознан.", "Kabul kanalı tanınmadı."),
    ("profile.rim", "Seçilməyib"): ("Not selected", "Не выбрано", "Seçilmedi"),
    ("profile.rim", "Tur"): ("Round", "Тур", "Kabul turu"),
    ("profile.rim", "Tur tanınmadı."): ("Round not recognised.", "Тур не распознан.", "Kabul turu tanınmadı."),
    ("profile.rim", "Tədris dili"): ("Language of instruction", "Язык обучения", "Eğitim dili"),
    ("profile.rim", "Tədris dili tanınmadı."): ("Language of instruction not recognised.", "Язык обучения не распознан.", "Eğitim dili tanınmadı."),
    ("profile.rim", "Təhsil haqqı məbləği (AZN)"): ("Tuition fee amount (AZN)", "Сумма оплаты за обучение (AZN)", "Öğrenim ücreti tutarı (AZN)"),
    ("profile.rim", "Təhsil haqqı məbləği rəqəm olmalıdır."): ("Tuition fee amount must be a number.", "Сумма оплаты должна быть числом.", "Öğrenim ücreti tutarı sayı olmalıdır."),
    ("profile.rim", "Vəsiqə nömrəsi"): ("ID number", "Номер удостоверения", "Kimlik numarası"),
    ("profile.rim", "Vəsiqə seriyası"): ("ID series", "Серия удостоверения", "Kimlik serisi"),
    ("profile.rim", "Vətəndaşlıq"): ("Citizenship", "Гражданство", "Vatandaşlık"),
    ("registrar.admission_channel", "DİM vasitəsilə"): ("Via DİM exam", "Через экзамен DİM", "DİM sınavı ile"),
    ("registrar.admission_channel", "İmtahansız qəbul"): ("Exam-free admission", "Приём без экзамена", "Sınavsız kabul"),
    ("registrar.admission_status", "Güzəştli qəbul edildi"): ("Admitted with concession", "Зачислен(а) на льготных условиях", "İndirimli kabul edildi"),
    ("registrar.admission_status", "Möhlətlə qəbul edildi"): ("Admitted with deferral", "Зачислен(а) с отсрочкой", "Ertelemeli kabul edildi"),
    ("registrar.admission_status", "Qəbul edildi"): ("Admitted", "Зачислен(а)", "Kabul edildi"),
    ("registrar.admission_status", "Sosial TTK ilə qəbul edildi"): ("Admitted via social TTK", "Зачислен(а) по социальной TTK", "Sosyal TTK ile kabul edildi"),
    ("registrar.admission_status", "Standart TTK ilə qəbul edildi"): ("Admitted via standard TTK", "Зачислен(а) по стандартной TTK", "Standart TTK ile kabul edildi"),
    ("registrar.admission_tour", "I tur"): ("Round I", "I тур", "I. tur"),
    ("registrar.admission_tour", "II tur"): ("Round II", "II тур", "II. tur"),
    ("registrar.instruction_language", "Alman dili"): ("German", "Немецкий", "Almanca"),
    ("registrar.instruction_language", "Azərbaycan dili"): ("Azerbaijani", "Азербайджанский", "Azerbaycanca"),
    ("registrar.instruction_language", "Rus dili"): ("Russian", "Русский", "Rusça"),
    ("registrar.instruction_language", "İngilis dili"): ("English", "Английский", "İngilizce"),
    ("student_intake", "AA / AB / AZE"): ("Series: AA / AB / AZE", "Серия: AA / AB / AZE", "Seri: AA / AB / AZE"),
    ("student_intake", "DİM vasitəsilə / imtahansız"): ("via DİM / exam-free", "через DİM / без экзамена", "DİM ile / sınavsız"),
    ("student_intake", "FirstTour / SecondTour"): ("FirstTour or SecondTour", "FirstTour или SecondTour", "FirstTour veya SecondTour"),
    ("student_intake", "Müraciət tarixi"): ("Application date", "Дата заявления", "Başvuru tarihi"),
    ("student_intake", "Qeyd"): ("Note", "Примечание", "Not"),
    ("student_intake", "Qeydiyyat ünvanı"): ("Registered address", "Адрес регистрации", "Kayıt adresi"),
    ("student_intake", "Qəbul statusu"): ("Admission status", "Статус приёма", "Kabul durumu"),
    ("student_intake", "Qəbul statusu tanınmadı — «qəbul edildi» tətbiq olunur."): ("Admission status not recognised — “admitted” is applied.", "Статус приёма не распознан — применяется «зачислен».", "Kabul durumu tanınmadı — «kabul edildi» uygulanır."),
    ("student_intake", "Qəbul tarixi"): ("Admission date", "Дата зачисления", "Kabul tarihi"),
    ("student_intake", "Qəbul xətti"): ("Admission channel", "Канал приёма", "Kabul kanalı"),
    ("student_intake", "Tur"): ("Round", "Тур", "Kabul turu"),
    ("student_intake", "Təhsil haqqı məbləği"): ("Tuition fee amount", "Сумма оплаты за обучение", "Öğrenim ücreti tutarı"),
    ("student_intake", "Təhsil haqqı məbləği tanınmadı — boş saxlanılır."): ("Tuition fee amount not recognised — left empty.", "Сумма оплаты не распознана — остаётся пустой.", "Öğrenim ücreti tutarı tanınmadı — boş bırakılır."),
    ("student_intake", "Vəsiqə nömrəsi"): ("ID number", "Номер удостоверения", "Kimlik numarası"),
    ("student_intake", "Vəsiqə seriyası"): ("ID series", "Серия удостоверения", "Kimlik serisi"),
    ("student_intake", "Vətəndaşlıq"): ("Citizenship", "Гражданство", "Vatandaşlık"),
    ("student_intake", "iiii-aa-gg ss:dd"): ("yyyy-mm-dd hh:mm", "гггг-мм-дд чч:мм", "yyyy-aa-gg ss:dd"),
    ("student_intake", "qəbul edildi / möhlətlə / güzəştli / TTK"): ("admitted / deferred / concession / TTK", "зачислен / с отсрочкой / льготный / TTK", "kabul edildi / ertelemeli / indirimli / TTK"),
    ("student_intake", "İllik, AZN — məs. 3900"): ("Per year, AZN — e.g. 3900", "В год, AZN — напр. 3900", "Yıllık, AZN — örn. 3900"),
    ("student_intake", "İxtisaslaşma"): ("Specialisation", "Специализация", "Uzmanlık"),
    ("student_intake", "Qrup tutumu dolub — kafedra sonradan bölə bilər."): ("Group is at capacity — the chair can split it later.", "Группа заполнена — кафедра сможет разделить её позже.", "Grup kapasitesi dolu — bölüm daha sonra ayırabilir."),
}  # fmt: skip


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            target = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            entry = existing.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=target))
                added += 1
            elif not entry.msgstr:
                entry.msgstr = target
                added += 1
        po.save(path)
        print(f"{lang}: {added} əlavə/doldurma")


if __name__ == "__main__":
    main()
