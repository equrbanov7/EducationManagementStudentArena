#!/usr/bin/env python3
"""EMSArena i18n — xarici rəy düzəlişləri (2026-10-21): R08 audit fail-closed + R06 ən son planın təsdiqi.

* ``registrar.audit`` — rəsmi bal audit izi yazılmayanda istifadəçi xətası (``audit_write.audit_failure_message``);
* ``accounts.semester`` — «Semestr açılışı» önizləməsi / təsdiq siyahısı (``cohort_plans``, ``semester_actions``,
  ``semester_howto``, ``_generate_fields.html``, ``_semester_opening.html``).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud ``(msgctxt, msgid)`` toxunulmur); sonra
`compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

AUDIT = "registrar.audit"
SEM = "accounts.semester"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    AUDIT: {
        "Audit izi yazıla bilmədi — bal saxlanmadı. Bir az sonra yenidən cəhd edin; "
        "təkrarlanarsa İKT şöbəsinə bildirin.": t(
            "The audit trail could not be written — the score was not saved. Please try again shortly; "
            "if it happens again, notify the IT department.",
            "Не удалось записать журнал аудита — балл не сохранён. Повторите попытку чуть позже; "
            "если ошибка повторится, сообщите в отдел ИКТ.",
            "Denetim kaydı yazılamadı — puan kaydedilmedi. Biraz sonra yeniden deneyin; "
            "tekrarlanırsa BT birimine bildirin.",
            "Der Prüfpfad konnte nicht geschrieben werden — die Punktzahl wurde nicht gespeichert. Bitte versuchen "
            "Sie es gleich erneut; tritt der Fehler wieder auf, informieren Sie die IT-Abteilung.",
        ),
    },
    SEM: {
        # cohort_plans.fallback_reason_label
        "Qrupun qəbul ili bilinmir": t(
            "The group's admission year is unknown",
            "Год приёма группы неизвестен",
            "Grubun kabul yılı bilinmiyor",
            "Das Aufnahmejahr der Gruppe ist unbekannt",
        ),
        "Bu qəbul ili üçün təsdiqlənmiş plan yoxdur": t(
            "There is no approved plan for this admission year",
            "Для этого года приёма нет утверждённого плана",
            "Bu kabul yılı için onaylanmış plan yok",
            "Für diesen Aufnahmejahrgang gibt es keinen genehmigten Plan",
        ),
        # cohort_plans.skipped_fallback_messages
        "Ən son planın tətbiqi təsdiqlənmədiyi üçün %(n)d qrup atlandı (açılış yaradılmadı): %(groups)s. "
        "Lazımdırsa qrupun qəbul ili üçün planı təsdiqləyin və ya açılışı yenidən təsdiqlə başladın.": t(
            "%(n)d group(s) were skipped because applying the latest plan was not confirmed (no offerings were "
            "created): %(groups)s. If needed, approve the plan for the group's admission year or run the "
            "opening again and confirm.",
            "Пропущено групп: %(n)d — применение последнего плана не подтверждено (открытия не созданы): "
            "%(groups)s. При необходимости утвердите план для года приёма группы или запустите открытие снова "
            "с подтверждением.",
            "En son planın uygulanması onaylanmadığı için %(n)d grup atlandı (açılış oluşturulmadı): %(groups)s. "
            "Gerekirse grubun kabul yılı için planı onaylayın veya açılışı onayla yeniden başlatın.",
            "%(n)d Gruppe(n) wurden übersprungen, weil die Anwendung des neuesten Plans nicht bestätigt wurde "
            "(keine Angebote erstellt): %(groups)s. Genehmigen Sie bei Bedarf den Plan für den Aufnahmejahrgang "
            "der Gruppe oder starten Sie die Eröffnung erneut mit Bestätigung.",
        ),
        # semester_actions._fallback_confirmation_required
        "%(n)d qrupun qəbul ili üçün təsdiqlənmiş plan yoxdur — onlara ən son plan tətbiq olunacaq. "
        "Aşağıdakı siyahıda hər qrupu ayrıca təsdiqləyin; təsdiqlənməyən qrup üçün açılış yaradılmır.": t(
            "%(n)d group(s) have no approved plan for their admission year — the latest plan would be applied to "
            "them. Confirm each group in the list below; no offerings are created for unconfirmed groups.",
            "Для года приёма %(n)d групп(ы) нет утверждённого плана — к ним будет применён последний план. "
            "Подтвердите каждую группу в списке ниже; для неподтверждённых групп открытия не создаются.",
            "%(n)d grubun kabul yılı için onaylanmış plan yok — bunlara en son plan uygulanacak. Aşağıdaki "
            "listede her grubu ayrı ayrı onaylayın; onaylanmayan grup için açılış oluşturulmaz.",
            "Für %(n)d Gruppe(n) gibt es keinen genehmigten Plan ihres Aufnahmejahrgangs — auf sie würde der "
            "neueste Plan angewendet. Bestätigen Sie jede Gruppe in der Liste unten; für nicht bestätigte "
            "Gruppen werden keine Angebote erstellt.",
        ),
        # semester_howto (mətn yeniləndi: ən son plan yalnız təsdiqlə)
        "Yuxarıdakı süzgəcdən semestri seçin. «Plandan açılış yarat» həmin semestri oxuyan (kursu uyğun) "
        "hər qrup üçün qrupun ÖZ qəbul ilinin təsdiqlənmiş tədris planının (yoxdursa — təsdiqinizlə ən "
        "son planın) məcburi fənlərindən açılış yaradır və qrupun aktiv "
        "tələbələrini dərhal qeydiyyata alır; seçmə fənlər qrupun seçimi ilə açılır. Mövcud sətir "
        "təkrarlanmır, heç nə silinmir. «Plan yoxdur» ixtisaslar üçün sətir yaranmır — əvvəlcə «Tədris "
        "planı» bölməsində planı təsdiqləyin.": t(
            "Select the semester in the filter above. “Create offerings from plan” creates offerings for every "
            "group studying that semester (matching year of study) from the compulsory subjects of the approved "
            "curriculum of the group's OWN admission year (if there is none — the latest plan, with your "
            "confirmation) and immediately enrols the group's active students; electives open according to the "
            "group's choice. Existing rows are not duplicated, nothing is deleted. No rows are created for "
            "programmes with “No plan” — approve the plan in the “Curriculum” section first.",
            "Выберите семестр в фильтре выше. «Создать открытия по плану» создаёт открытия для каждой группы, "
            "изучающей этот семестр (подходящий курс), из обязательных дисциплин утверждённого учебного плана "
            "СОБСТВЕННОГО года приёма группы (если его нет — последнего плана, с вашим подтверждением) и сразу "
            "зачисляет активных студентов группы; элективы открываются по выбору группы. Существующие строки не "
            "дублируются, ничего не удаляется. Для специальностей «Нет плана» строки не создаются — сначала "
            "утвердите план в разделе «Учебный план».",
            "Yukarıdaki filtreden yarıyılı seçin. “Plandan açılış oluştur”, o yarıyılı okuyan (sınıfı uygun) her "
            "grup için grubun KENDİ kabul yılının onaylanmış öğretim planındaki (yoksa — onayınızla en son "
            "plandaki) zorunlu derslerden açılış oluşturur ve grubun aktif öğrencilerini hemen kaydeder; seçmeli "
            "dersler grubun seçimine göre açılır. Mevcut satır tekrarlanmaz, hiçbir şey silinmez. “Plan yok” "
            "programlar için satır oluşturulmaz — önce “Öğretim planı” bölümünde planı onaylayın.",
            "Wählen Sie das Semester im Filter oben. „Angebote aus dem Plan erstellen“ erstellt für jede Gruppe, "
            "die dieses Semester studiert (passendes Studienjahr), Angebote aus den Pflichtfächern des "
            "genehmigten Studienplans des EIGENEN Aufnahmejahrgangs der Gruppe (falls keiner vorhanden ist — des "
            "neuesten Plans, mit Ihrer Bestätigung) und schreibt die aktiven Studierenden der Gruppe sofort ein; "
            "Wahlfächer werden nach Wahl der Gruppe geöffnet. Vorhandene Zeilen werden nicht dupliziert, nichts "
            "wird gelöscht. Für Studiengänge mit „Kein Plan“ entstehen keine Zeilen — genehmigen Sie zuerst den "
            "Plan im Bereich „Studienplan“.",
        ),
        # _semester_opening.html (dialoq alt başlığı yeniləndi)
        "Hər qrup üçün qrupun öz qəbul ilinin TƏSDİQLƏNMİŞ planından açılış sətirləri yaradılır (həmin il üçün "
        "plan yoxdursa — ən son plandan, yalnız siyahını təsdiqlədikdən sonra). Əməl idempotentdir — mövcud "
        "açılış təkrarlanmır və heç nə silinmir.": t(
            "Offering rows are created for each group from the APPROVED plan of the group's own admission year "
            "(if there is no plan for that year — from the latest plan, only after you confirm the list). The "
            "action is idempotent — existing offerings are not duplicated and nothing is deleted.",
            "Для каждой группы строки открытий создаются по УТВЕРЖДЁННОМУ плану её собственного года приёма (если "
            "для этого года плана нет — по последнему плану, только после подтверждения списка). Действие "
            "идемпотентно — существующие открытия не дублируются, ничего не удаляется.",
            "Her grup için grubun kendi kabul yılının ONAYLANMIŞ planından açılış satırları oluşturulur (o yıl "
            "için plan yoksa — en son plandan, yalnızca listeyi onayladıktan sonra). İşlem idempotenttir — mevcut "
            "açılış tekrarlanmaz ve hiçbir şey silinmez.",
            "Für jede Gruppe werden Angebotszeilen aus dem GENEHMIGTEN Plan ihres eigenen Aufnahmejahrgangs "
            "erstellt (gibt es für dieses Jahr keinen Plan — aus dem neuesten Plan, erst nachdem Sie die Liste "
            "bestätigt haben). Die Aktion ist idempotent — vorhandene Angebote werden nicht dupliziert und nichts "
            "wird gelöscht.",
        ),
        # _generate_fields.html — təsdiq siyahısı
        "Qrup": t("Group", "Группа", "Grup", "Gruppe"),
        "Qəbul ili": t("Admission year", "Год приёма", "Kabul yılı", "Aufnahmejahr"),
        "Səbəb": t("Reason", "Причина", "Neden", "Grund"),
        "Tətbiq olunacaq plan": t("Plan to be applied", "Применяемый план", "Uygulanacak plan", "Anzuwendender Plan"),
        "Planın qəbul ili": t(
            "Plan's admission year", "Год приёма плана", "Planın kabul yılı", "Aufnahmejahrgang des Plans"
        ),
        "Təsdiq edirəm": t("I confirm", "Подтверждаю", "Onaylıyorum", "Ich bestätige"),
        "bilinmir": t("unknown", "неизвестен", "bilinmiyor", "unbekannt"),
        "Hamısını təsdiq edirəm": t("I confirm all", "Подтверждаю все", "Tümünü onaylıyorum", "Ich bestätige alle"),
        "Təsdiqlənməyən qrup üçün açılış yaradılmır və nəticədə adı ilə göstərilir. Semestr və ya ixtisas "
        "dəyişsə siyahı yenidən yoxlanılır.": t(
            "No offerings are created for an unconfirmed group; it is listed by name in the result. If the "
            "semester or programme changes, the list is checked again.",
            "Для неподтверждённой группы открытия не создаются, в результате она указывается по названию. Если "
            "семестр или специальность меняются, список проверяется заново.",
            "Onaylanmayan grup için açılış oluşturulmaz ve sonuçta adıyla gösterilir. Yarıyıl veya program "
            "değişirse liste yeniden kontrol edilir.",
            "Für eine nicht bestätigte Gruppe werden keine Angebote erstellt; sie wird im Ergebnis namentlich "
            "aufgeführt. Ändern sich Semester oder Studiengang, wird die Liste erneut geprüft.",
        ),
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
