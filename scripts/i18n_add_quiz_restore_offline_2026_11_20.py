#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-20: nəzarətli quiz — bərpa (pauza vaxtı qaytarılır) + internet kəsilməsi.

Sahib (QuizPython577E): «dayandırdığım tələbəni bərpa edəndə olmur», «internet gedəndə full screen çıxmaq
ya da bal bərpa etmək olmur». Tələbə imtahan səhifəsinin «bağlantı yoxdur / bərpa olundu» mətnləri,
nəzarətçi siqnalı və «Nəzarət otağı» pauza dialoqunun izahı ``django`` kataloquna beş dildə əlavə olunur;
AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_quiz_restore_offline_2026_11_20.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_TAKE = "exams.template.take_exam"
_SIG = "exams.proctoring.signal"
_ROOM = "exams.supervision_room"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _TAKE, "İnternet bağlantısı kəsildi"): (
        "Internet connection lost",
        "Интернет-соединение прервано",
        "İnternet bağlantısı kesildi",
        "Internetverbindung unterbrochen",
    ),
    (
        "django",
        _TAKE,
        "Cavablarınız bu kompüterdə saxlanılır. Bağlantı qayıdanda tam ekrana qayıdın — bu pozuntu sayılmır.",
    ): (
        "Your answers are kept on this computer. Return to full screen when the connection is back — "
        "this is not counted as a violation.",
        "Ваши ответы сохраняются на этом компьютере. Когда связь восстановится, вернитесь в полноэкранный "
        "режим — это не считается нарушением.",
        "Cevaplarınız bu bilgisayarda saklanıyor. Bağlantı geri geldiğinde tam ekrana dönün — bu ihlal sayılmaz.",
        "Ihre Antworten werden auf diesem Computer gespeichert. Kehren Sie in den Vollbildmodus zurück, sobald "
        "die Verbindung wieder da ist – das gilt nicht als Verstoß.",
    ),
    ("django", _TAKE, "Bağlantı bərpa olundu"): (
        "Connection restored",
        "Соединение восстановлено",
        "Bağlantı yeniden kuruldu",
        "Verbindung wiederhergestellt",
    ),
    ("django", _TAKE, "Davam etmək üçün tam ekrana qayıdın. Bağlantının kəsilməsi pozuntu sayılmadı."): (
        "Return to full screen to continue. The connection loss was not counted as a violation.",
        "Вернитесь в полноэкранный режим, чтобы продолжить. Потеря связи не засчитана как нарушение.",
        "Devam etmek için tam ekrana dönün. Bağlantının kesilmesi ihlal sayılmadı.",
        "Kehren Sie in den Vollbildmodus zurück, um fortzufahren. Der Verbindungsabbruch wurde nicht als "
        "Verstoß gewertet.",
    ),
    ("django", _SIG, "İnternet bağlantısı kəsilmişdi (pozuntu sayılmadı)"): (
        "Internet connection was lost (not counted as a violation)",
        "Интернет-соединение прерывалось (не засчитано как нарушение)",
        "İnternet bağlantısı kesilmişti (ihlal sayılmadı)",
        "Internetverbindung war unterbrochen (nicht als Verstoß gewertet)",
    ),
    ("django", _ROOM, "Dayandırılma müddəti tələbənin vaxtından getmir — «Bərpa et» basılanda ona qaytarılır."): (
        "The paused time is not taken from the student — it is given back when you press “Resume”.",
        "Время паузы не вычитается у студента — оно возвращается при нажатии «Восстановить».",
        "Duraklatma süresi öğrencinin süresinden düşmez — «Geri yükle»ye basıldığında ona iade edilir.",
        "Die Pausenzeit wird dem Studierenden nicht abgezogen – sie wird beim Klick auf „Fortsetzen“ " "zurückgegeben.",
    ),
}


def main():
    for domain in ("django",):
        for lang in LOCALES:
            path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            po = polib.pofile(path)
            existing = {(e.msgctxt, e.msgid) for e in po}
            added = 0
            for (dom, ctx, msgid), (en, ru, tr, de) in STRINGS.items():
                if dom != domain or (ctx, msgid) in existing:
                    continue
                msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()
