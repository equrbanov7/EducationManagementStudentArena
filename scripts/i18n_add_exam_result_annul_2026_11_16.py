#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-16: imtahan nəticəsinin ləğvi (uzaqlaşdırma / köçürmə / digər).

Sahib: «uzaqlaşdırılmış tələbələrin midterm nəticəsi ləğv olmalıdır, qeyd kimi də düşməlidir»; «“Bitir” vurub
balı düşən tələbənin balı izahatla ləğv edilə bilsin». ``django`` kataloquna beş dildə; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_exam_result_annul_2026_11_16.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_A = "exams.final_center.annul"
_E = "exams.final_center.error"
_M = "exams.final_center.message"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_A, "İmtahandan uzaqlaşdırıldığına görə"): (
        "Removed from the exam",
        "Удалён с экзамена",
        "Sınavdan uzaklaştırıldığı için",
        "Von der Prüfung ausgeschlossen",
    ),
    (_A, "Köçürmə"): ("Cheating", "Списывание", "Kopya", "Täuschungsversuch"),
    (_A, "Digər səbəb"): ("Other reason", "Другая причина", "Diğer neden", "Anderer Grund"),
    (_E, "Ləğv səbəbi seçilməyib."): (
        "No annulment reason selected.",
        "Не выбрана причина аннулирования.",
        "İptal nedeni seçilmedi.",
        "Kein Annullierungsgrund gewählt.",
    ),
    (_E, "İzahat yazılmadan nəticə ləğv edilə bilməz."): (
        "A result cannot be annulled without an explanation.",
        "Результат нельзя аннулировать без пояснения.",
        "Açıklama yazılmadan sonuç iptal edilemez.",
        "Ein Ergebnis kann ohne Begründung nicht annulliert werden.",
    ),
    (_E, "Bu biletdə imtahan cəhdi yoxdur."): (
        "This ticket has no exam attempt.",
        "У этого билета нет попытки экзамена.",
        "Bu bilette sınav denemesi yok.",
        "Zu diesem Ticket gibt es keinen Prüfungsversuch.",
    ),
    (_E, "Sınaq cəhdinin nəticəsi jurnala düşmür."): (
        "A trial attempt's result is not written to the journal.",
        "Результат пробной попытки не попадает в журнал.",
        "Deneme girişiminin sonucu deftere yazılmaz.",
        "Das Ergebnis eines Probeversuchs wird nicht ins Journal übernommen.",
    ),
    (_E, "İmtahan hələ davam edir — əvvəlcə tələbəni imtahandan çıxarın."): (
        "The exam is still in progress — remove the student from the exam first.",
        "Экзамен ещё идёт — сначала удалите студента с экзамена.",
        "Sınav hâlâ devam ediyor — önce öğrenciyi sınavdan çıkarın.",
        "Die Prüfung läuft noch — schließen Sie den Studierenden zuerst aus.",
    ),
    (_M, "Nəticə ləğv edildi: jurnalda 0 bal, tələbəyə qeyd göstərilir."): (
        "Result annulled: 0 points in the journal, the student sees a note.",
        "Результат аннулирован: в журнале 0 баллов, студент видит пометку.",
        "Sonuç iptal edildi: defterde 0 puan, öğrenciye not gösteriliyor.",
        "Ergebnis annulliert: 0 Punkte im Journal, der Studierende sieht einen Hinweis.",
    ),
    (_M, "Bu nəticə artıq ləğv olunub."): (
        "This result has already been annulled.",
        "Этот результат уже аннулирован.",
        "Bu sonuç zaten iptal edildi.",
        "Dieses Ergebnis wurde bereits annulliert.",
    ),
    ("", "Nəticə ləğv olunub"): (
        "Result annulled",
        "Результат аннулирован",
        "Sonuç iptal edildi",
        "Ergebnis annulliert",
    ),
    ("", "Nəticəni ləğv et"): ("Annul result", "Аннулировать результат", "Sonucu iptal et", "Ergebnis annullieren"),
    ("", "Nəticə ləğv edilsin? Jurnalda 0 bal yazılacaq."): (
        "Annul the result? 0 points will be written to the journal.",
        "Аннулировать результат? В журнал будет записано 0 баллов.",
        "Sonuç iptal edilsin mi? Deftere 0 puan yazılacak.",
        "Ergebnis annullieren? Im Journal werden 0 Punkte eingetragen.",
    ),
    ("", "Səbəb"): ("Reason", "Причина", "Neden", "Grund"),
    ("", "İzahat"): ("Explanation", "Пояснение", "Açıklama", "Begründung"),
    ("", "Ləğv et"): ("Annul", "Аннулировать", "İptal et", "Annullieren"),
    ("", "Nəticəniz ləğv olunub"): (
        "Your result has been annulled",
        "Ваш результат аннулирован",
        "Sonucunuz iptal edildi",
        "Ihr Ergebnis wurde annulliert",
    ),
    ("", "İmtahandan uzaqlaşdırıldığınıza görə nəticəniz ləğv olunub (jurnalda 0 bal)."): (
        "Because you were removed from the exam, your result has been annulled (0 points in the journal).",
        "Так как вы были удалены с экзамена, ваш результат аннулирован (в журнале 0 баллов).",
        "Sınavdan uzaklaştırıldığınız için sonucunuz iptal edildi (defterde 0 puan).",
        "Da Sie von der Prüfung ausgeschlossen wurden, wurde Ihr Ergebnis annulliert (0 Punkte im Journal).",
    ),
    ("", "Bu imtahanın nəticəsi ləğv olunub (jurnalda 0 bal)."): (
        "The result of this exam has been annulled (0 points in the journal).",
        "Результат этого экзамена аннулирован (в журнале 0 баллов).",
        "Bu sınavın sonucu iptal edildi (defterde 0 puan).",
        "Das Ergebnis dieser Prüfung wurde annulliert (0 Punkte im Journal).",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt or "", e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
