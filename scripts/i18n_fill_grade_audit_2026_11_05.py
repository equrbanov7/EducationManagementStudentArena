#!/usr/bin/env python3
"""Append the grade audit's missing translations without rewriting existing entries.

Run serially, then compile the five django catalogs. Existing context/msgid pairs
are preserved, matching the repository's other idempotent catalog fill scripts.
"""

from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LOCALES = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "appeals.history": {
        "{no}-ci sual: cavab açarı düzəldildi — {credited}/{affected} cəhd üçün düzəliş": t(
            "Question {no}: answer key corrected — adjustment for {credited}/{affected} attempts",
            "Вопрос {no}: ключ ответа исправлен — корректировка для {credited}/{affected} попыток",
            "Soru {no}: cevap anahtarı düzeltildi — {credited}/{affected} deneme için düzeltme",
            "Frage {no}: Lösungsschlüssel korrigiert — Anpassung für {credited}/{affected} Versuche",
        ),
    },
    "appeals.view.message": {
        (
            "Cavab açarı düzəldildi: {affected} cəhd yoxlanıldı, {credited} cəhd üçün düzəliş tətbiq edildi. "
            "Əvvəlki apellyasiya balı təkrar əlavə edilmir."
        ): t(
            "Answer key corrected: {affected} attempts checked, adjustments applied to {credited} attempts. "
            "Points previously awarded on appeal are not added again.",
            "Ключ ответа исправлен: проверено {affected} попыток, корректировка применена к {credited} попыткам. "
            "Баллы, ранее начисленные по апелляции, повторно не добавляются.",
            "Cevap anahtarı düzeltildi: {affected} deneme kontrol edildi, {credited} denemeye düzeltme uygulandı. "
            "Önceki itirazda verilen puanlar yeniden eklenmez.",
            "Lösungsschlüssel korrigiert: {affected} Versuche geprüft, {credited} Versuche angepasst. "
            "Zuvor aufgrund eines Widerspruchs vergebene Punkte werden nicht erneut hinzugefügt.",
        ),
    },
    "exams.attempt_reset": {
        "əvvəlki sənədli imtahan balının bərpası ayrıca yoxlanmalıdır — cəhd silinmədi": t(
            "restoring the previous documented exam score requires a separate review — the attempt was not deleted",
            "восстановление предыдущего документально подтверждённого экзаменационного балла требует отдельной "
            "проверки — попытка не удалена",
            "önceki belgeli sınav puanının geri yüklenmesi ayrıca kontrol edilmelidir — deneme silinmedi",
            "die Wiederherstellung der vorherigen dokumentierten Prüfungspunktzahl muss gesondert geprüft werden — "
            "der Versuch wurde nicht gelöscht",
        ),
        "əvvəlki sənədli midterm balının bərpası ayrıca yoxlanmalıdır — cəhd silinmədi": t(
            "restoring the previous documented midterm score requires a separate review — the attempt was not deleted",
            "восстановление предыдущего документально подтверждённого балла промежуточного экзамена требует "
            "отдельной проверки — попытка не удалена",
            "önceki belgeli vize puanının geri yüklenmesi ayrıca kontrol edilmelidir — deneme silinmedi",
            "die Wiederherstellung der vorherigen dokumentierten Zwischenprüfungspunktzahl muss gesondert "
            "geprüft werden — der Versuch wurde nicht gelöscht",
        ),
    },
    "registrar.legacy_grade_review": {
        "Müsbət imtahan balı ilə yekundan kəsilmək mümkündür. Bu hal təkbaşına məlumat səhvi deyil.": t(
            "A positive exam score can still result in an overall fail. This alone is not a data error.",
            "Даже при положительном экзаменационном балле итоговый результат может быть неудовлетворительным. "
            "Само по себе это не является ошибкой данных.",
            "Sınav puanı pozitif olsa da genel sonuç başarısız olabilir. Bu durum tek başına veri hatası değildir.",
            "Auch mit einer positiven Prüfungspunktzahl kann das Gesamtergebnis nicht bestanden sein. "
            "Dies allein ist kein Datenfehler.",
        ),
        "Tarixi bal şkalası dəqiqləşdirilməlidir": t(
            "The historical score scale needs clarification",
            "Необходимо уточнить историческую шкалу баллов",
            "Geçmiş puan ölçeği netleştirilmelidir",
            "Die historische Punkteskala muss geklärt werden",
        ),
        (
            "Tarixi mənbə balı ilə cari imtahan balı fərqlidir. Son rəsmi nəticə, cəhd və apellyasiya qərarı ilə "
            "uzlaşdırılmalıdır; fərq təkbaşına bal itkisini sübut etmir."
        ): t(
            "The historical source score differs from the current exam score. It must be reconciled with the latest "
            "official result, attempt and appeal decision; the difference alone does not prove a loss of points.",
            "Балл в историческом источнике отличается от текущего экзаменационного балла. Его необходимо сверить "
            "с последним официальным результатом, попыткой и решением по апелляции; само различие не доказывает "
            "потерю баллов.",
            "Geçmiş kaynak puanı ile mevcut sınav puanı farklıdır. Son resmî sonuç, deneme ve itiraz kararıyla "
            "karşılaştırılıp uzlaştırılmalıdır; fark tek başına puan kaybını kanıtlamaz.",
            "Die Punktzahl in der historischen Quelle weicht von der aktuellen Prüfungspunktzahl ab. Sie muss mit "
            "dem letzten offiziellen Ergebnis, dem Versuch und der Widerspruchsentscheidung abgeglichen werden; "
            "die Abweichung allein belegt keinen Punkteverlust.",
        ),
        (
            "Xam bal 50-dən yüksəkdir, lakin bu mənbəyə 50-ballıq həddin aid olduğu təsdiqlənməyib. Mənbənin şkalası "
            "yoxlanılmalıdır; bal avtomatik səhv sayılmır."
        ): t(
            "The raw score is above 50, but a 50-point limit has not been confirmed for this source. "
            "The source scale must be checked; the score is not automatically considered incorrect.",
            "Исходный балл выше 50, но применимость предела в 50 баллов к этому источнику не подтверждена. "
            "Необходимо проверить шкалу источника; балл не считается ошибочным автоматически.",
            "Ham puan 50'nin üzerindedir, ancak bu kaynak için 50 puan sınırının geçerli olduğu doğrulanmamıştır. "
            "Kaynağın ölçeği kontrol edilmelidir; puan otomatik olarak hatalı sayılmaz.",
            "Die Rohpunktzahl liegt über 50, doch eine Grenze von 50 Punkten ist für diese Quelle nicht bestätigt. "
            "Die Skala der Quelle muss geprüft werden; die Punktzahl gilt nicht automatisch als falsch.",
        ),
    },
}


def fill(lang):
    path = BASE / "locale" / lang / "LC_MESSAGES" / "django.po"
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    blocks = []
    for context, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (context, msgid) in existing:
                continue
            entry = polib.POEntry(
                msgctxt=context,
                msgid=msgid,
                msgstr=msgid if lang == "az" else translations[lang],
                flags=["python-brace-format"] if "{" in msgid else [],
            )
            blocks.append(str(entry))
    if blocks:
        path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + "\n".join(blocks), encoding="utf-8")
    print(f"{lang}: +{len(blocks)} entries")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
