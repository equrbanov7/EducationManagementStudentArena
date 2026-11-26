#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-27: «Fəndən azad etmə» (kurs / kollec səbəbi + yekun bal + məcburi sənəd, jurnalda «Azad»).

``django`` kataloquna beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_subject_exemption_2026_11_27.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_R = "registrar.recognition"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (
        "organizations.permission.label",
        "Tələbəni fəndən azad etmək (kurs / sertifikat, kollec nəticəsi, başqa ali məktəb, Erasmus+ və s.) — səbəb, "
        "yekun bal və sənədlə",
    ): (
        "Exempt a student from a subject (course / certificate, college result, another university, Erasmus+ etc.) "
        "— with a reason, final score and document",
        "Освобождать студента от предмета (курс / сертификат, результат колледжа, другой вуз, Erasmus+ и т. д.) — "
        "с причиной, итоговым баллом и документом",
        "Öğrenciyi dersten muaf tutmak (kurs / sertifika, kolej sonucu, başka üniversite, Erasmus+ vb.) — gerekçe, "
        "nihai puan ve belge ile",
        "Studierende von einem Fach befreien (Kurs / Zertifikat, College-Ergebnis, andere Hochschule, Erasmus+ usw.) "
        "— mit Grund, Endnote und Dokument",
    ),
    ("profile.sidebar", "Fəndən azad etmə"): (
        "Subject exemption",
        "Освобождение от предмета",
        "Dersten muafiyet",
        "Fachbefreiung",
    ),
    (
        _R,
        "%(floor)s–100: tələbənin bu fəndən yekun balı olur və fənn keçilmiş sayılır; hərf universitetin şkalasından "
        "avtomatik.",
    ): (
        "%(floor)s–100: becomes the student's final score for this subject and the subject counts as passed; the "
        "letter comes from the university scale automatically.",
        "%(floor)s–100: становится итоговым баллом студента по предмету, предмет считается сданным; буква — "
        "автоматически по шкале университета.",
        "%(floor)s–100: öğrencinin bu dersten nihai puanı olur ve ders geçilmiş sayılır; harf notu üniversite "
        "ölçeğinden otomatik.",
        "%(floor)s–100: wird die Endnote der/des Studierenden in diesem Fach, das Fach gilt als bestanden; der "
        "Buchstabe ergibt sich automatisch aus der Hochschulskala.",
    ),
    (_R, "Azad et"): ("Exempt", "Освободить", "Muaf tut", "Befreien"),
    (_R, "Azad olunma səbəbi"): ("Exemption reason", "Причина освобождения", "Muafiyet gerekçesi", "Befreiungsgrund"),
    (_R, "Azad — %(score)s bal (%(letter)s)"): (
        "Exempt — %(score)s points (%(letter)s)",
        "Освобождён — %(score)s баллов (%(letter)s)",
        "Muaf — %(score)s puan (%(letter)s)",
        "Befreit — %(score)s Punkte (%(letter)s)",
    ),
    (_R, "Erasmus+ / mübadilə: xarici fənnin məlumatı məcburidir."): (
        "Erasmus+ / exchange: the foreign course details are required.",
        "Erasmus+ / обмен: данные зарубежного предмета обязательны.",
        "Erasmus+ / değişim: yabancı dersin bilgileri zorunludur.",
        "Erasmus+ / Austausch: Angaben zum ausländischen Fach sind Pflicht.",
    ),
    (_R, "Fəndən azad et"): (
        "Exempt from subject",
        "Освободить от предмета",
        "Dersten muaf tut",
        "Vom Fach befreien",
    ),
    (_R, "Fəndən azad olunanlar — fənn tanınmış balla keçilmiş sayılır"): (
        "Exempted students — the subject counts as passed with the recognised score",
        "Освобождённые — предмет считается сданным с признанным баллом",
        "Muaf tutulanlar — ders tanınan puanla geçilmiş sayılır",
        "Befreite Studierende — das Fach gilt mit der anerkannten Note als bestanden",
    ),
    (_R, "Fəndən azad — nəticə tanınıb"): (
        "Exempt — result recognised",
        "Освобождён — результат признан",
        "Muaf — sonuç tanındı",
        "Befreit — Ergebnis anerkannt",
    ),
    (_R, "Fəndən azad — nəticə tanınıb: %(trail)s"): (
        "Exempt — result recognised: %(trail)s",
        "Освобождён — результат признан: %(trail)s",
        "Muaf — sonuç tanındı: %(trail)s",
        "Befreit — Ergebnis anerkannt: %(trail)s",
    ),
    (_R, "Fənn üzrə yekun bal (100 bal)"): (
        "Final score for the subject (out of 100)",
        "Итоговый балл по предмету (из 100)",
        "Ders için nihai puan (100 üzerinden)",
        "Endnote im Fach (von 100)",
    ),
    (_R, "Hələ azad olunan yoxdur. Tələbəni axtarın və «Fəndən azad et» düyməsini basın."): (
        "No one has been exempted yet. Find the student and press “Exempt from subject”.",
        "Пока никто не освобождён. Найдите студента и нажмите «Освободить от предмета».",
        "Henüz muaf tutulan yok. Öğrenciyi bulun ve «Dersten muaf tut» düğmesine basın.",
        "Noch niemand befreit. Suchen Sie die Person und klicken Sie auf „Vom Fach befreien“.",
    ),
    (_R, "Kollec nəticəsi"): ("College result", "Результат колледжа", "Kolej sonucu", "College-Ergebnis"),
    (_R, "Kurs / sertifikat"): ("Course / certificate", "Курс / сертификат", "Kurs / sertifika", "Kurs / Zertifikat"),
    (
        _R,
        "Nəticə tanındı (%(score)s bal) — fənn keçilmiş sayılır; jurnal qeydiyyatı artıq aktiv deyildi.",
    ): (
        "Result recognised (%(score)s points) — the subject counts as passed; the journal enrolment was no longer "
        "active.",
        "Результат признан (%(score)s баллов) — предмет считается сданным; запись в журнале уже была неактивна.",
        "Sonuç tanındı (%(score)s puan) — ders geçilmiş sayılır; yoklama kaydı zaten aktif değildi.",
        "Ergebnis anerkannt (%(score)s Punkte) — das Fach gilt als bestanden; die Journaleinschreibung war nicht "
        "mehr aktiv.",
    ),
    (_R, "PDF, JPG və ya PNG · ən çox 10 MB · sənədsiz azad etmək olmur"): (
        "PDF, JPG or PNG · up to 10 MB · no exemption without a document",
        "PDF, JPG или PNG · до 10 МБ · без документа освободить нельзя",
        "PDF, JPG veya PNG · en fazla 10 MB · belgesiz muafiyet olmaz",
        "PDF, JPG oder PNG · bis 10 MB · ohne Dokument keine Befreiung",
    ),
    (_R, "Qurum (kurs təşkilatı, kollec, universitet)"): (
        "Institution (course provider, college, university)",
        "Организация (провайдер курса, колледж, университет)",
        "Kurum (kurs düzenleyici, kolej, üniversite)",
        "Einrichtung (Kursanbieter, College, Hochschule)",
    ),
    (_R, "Son qərarlar"): ("Recent decisions", "Последние решения", "Son kararlar", "Letzte Entscheidungen"),
    (_R, "Səbəb seçiləndən sonra bal və sənəd sahələri açılır."): (
        "The score and document fields open once a reason is chosen.",
        "Поля балла и документа откроются после выбора причины.",
        "Gerekçe seçildikten sonra puan ve belge alanları açılır.",
        "Die Felder für Note und Dokument öffnen sich nach Auswahl eines Grundes.",
    ),
    (
        _R,
        "Səbəbi seçin, yekun balı yazın və sənədi yükləyin — sənəd məcburidir. Tələbə jurnalda «Azad — bal» kimi "
        "qalır.",
    ): (
        "Choose the reason, enter the final score and upload the document — the document is required. The student "
        "stays in the journal as “Exempt — score”.",
        "Выберите причину, введите итоговый балл и загрузите документ — документ обязателен. Студент остаётся в "
        "журнале как «Освобождён — балл».",
        "Gerekçeyi seçin, nihai puanı yazın ve belgeyi yükleyin — belge zorunludur. Öğrenci yoklamada «Muaf — "
        "puan» olarak kalır.",
        "Grund wählen, Endnote eintragen und Dokument hochladen — das Dokument ist Pflicht. Die Person bleibt im "
        "Journal als „Befreit — Note“.",
    ),
    (_R, "Səbəbi seçin."): ("Choose the reason.", "Выберите причину.", "Gerekçeyi seçin.", "Wählen Sie den Grund."),
    (_R, "Səbəbin / kursun adı"): (
        "Name of the reason / course",
        "Название причины / курса",
        "Gerekçenin / kursun adı",
        "Bezeichnung des Grundes / Kurses",
    ),
    (
        _R,
        "Tələbə bu fəndən %(score)s bal ilə azad edildi — fənn keçilmiş sayılır, jurnalda «Azad» görünür.",
    ): (
        "The student was exempted from this subject with %(score)s points — the subject counts as passed and shows "
        "as “Exempt” in the journal.",
        "Студент освобождён от предмета с %(score)s баллами — предмет считается сданным, в журнале отмечено "
        "«Освобождён».",
        "Öğrenci bu dersten %(score)s puanla muaf tutuldu — ders geçilmiş sayılır, yoklamada «Muaf» görünür.",
        "Die Person wurde mit %(score)s Punkten von diesem Fach befreit — das Fach gilt als bestanden und steht im "
        "Journal als „Befreit“.",
    ),
    (
        _R,
        "Tələbə kurs / sertifikat, kollec nəticəsi, başqa ali məktəb, Erasmus+ və s. əsasında fəndən azad edilir: "
        "səbəb seçilir, yekun bal (ən çox 100) yazılır və sənəd məcburi yüklənir. Fənn bu balla keçilmiş sayılır — "
        "jurnalda «Azad» görünür, davamiyyət limiti və imtahan ona aid olmur, transkriptdə bu bal yazılır. Qərar "
        "səbəblə ləğv edilə bilər; hər addım audit izinə düşür.",
    ): (
        "A student is exempted from a subject on the basis of a course / certificate, college result, another "
        "university, Erasmus+ etc.: choose the reason, enter the final score (at most 100) and upload the required "
        "document. The subject counts as passed with this score — the journal shows “Exempt”, the attendance limit "
        "and the exam no longer apply, and the transcript shows this score. The decision can be revoked with a "
        "reason; every step is audited.",
        "Студент освобождается от предмета на основании курса / сертификата, результата колледжа, другого вуза, "
        "Erasmus+ и т. д.: выбирается причина, вводится итоговый балл (не более 100) и обязательно загружается "
        "документ. Предмет считается сданным с этим баллом — в журнале «Освобождён», лимит пропусков и экзамен не "
        "применяются, в транскрипте указан этот балл. Решение можно отменить с причиной; каждый шаг фиксируется в "
        "аудите.",
        "Öğrenci kurs / sertifika, kolej sonucu, başka üniversite, Erasmus+ vb. temelinde dersten muaf tutulur: "
        "gerekçe seçilir, nihai puan (en fazla 100) yazılır ve belge zorunlu olarak yüklenir. Ders bu puanla "
        "geçilmiş sayılır — yoklamada «Muaf» görünür, devamsızlık sınırı ve sınav uygulanmaz, transkriptte bu "
        "puan yazılır. Karar gerekçeyle iptal edilebilir; her adım denetim kaydına düşer.",
        "Studierende werden auf Grundlage eines Kurses / Zertifikats, eines College-Ergebnisses, einer anderen "
        "Hochschule, Erasmus+ usw. von einem Fach befreit: Grund wählen, Endnote (höchstens 100) eintragen und das "
        "Pflichtdokument hochladen. Das Fach gilt mit dieser Note als bestanden — im Journal steht „Befreit“, "
        "Fehlzeitenlimit und Prüfung entfallen, im Transkript steht diese Note. Die Entscheidung kann mit Begründung "
        "widerrufen werden; jeder Schritt wird protokolliert.",
    ),
    (_R, "Tələbəni fəndən azad etmək üçün səlahiyyətiniz yoxdur."): (
        "You do not have permission to exempt students from subjects.",
        "У вас нет прав освобождать студентов от предметов.",
        "Öğrencileri dersten muaf tutma yetkiniz yok.",
        "Sie sind nicht berechtigt, Studierende von Fächern zu befreien.",
    ),
    (_R, "məs. IELTS 7.0, Cisco CCNA, kollec diplomu"): (
        "e.g. IELTS 7.0, Cisco CCNA, college diploma",
        "напр. IELTS 7.0, Cisco CCNA, диплом колледжа",
        "örn. IELTS 7.0, Cisco CCNA, kolej diploması",
        "z. B. IELTS 7.0, Cisco CCNA, College-Diplom",
    ),
    (_R, "«Digər» seçilibsə məcburidir."): (
        "Required if “Other” is selected.",
        "Обязательно, если выбрано «Другое».",
        "«Diğer» seçildiyse zorunludur.",
        "Pflicht, wenn „Sonstiges“ gewählt ist.",
    ),
    (_R, "Əsas sənəd (sertifikat, kollec arayışı, transkript və ya əmr)"): (
        "Main document (certificate, college statement, transcript or order)",
        "Основной документ (сертификат, справка колледжа, транскрипт или приказ)",
        "Ana belge (sertifika, kolej belgesi, transkript veya karar)",
        "Hauptdokument (Zertifikat, College-Bescheinigung, Transkript oder Anordnung)",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        if added:
            po.save(path)
            subprocess.run(["msgfmt", "-o", path[:-2] + "mo", path], check=True)
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
