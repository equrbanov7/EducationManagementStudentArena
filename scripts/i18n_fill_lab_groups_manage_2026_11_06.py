#!/usr/bin/env python3
"""EMSArena i18n — jurnalın «Lab qrupları» ekranı (sahib 2026-11-06: qrupları yaratmaq / adlandırmaq / yerləşdirmək).

Kontekst: ``registrar.lab_groups`` (``apps/registrar/lab_groups_manage.py``, ``lab_groups_views.py``,
``journal_lab_groups.html``, jurnal başlığındakı keçid) + ``registrar.model.lab_group.meta`` (model adı).
⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir. Sonra `.mo`
faylları `msgfmt` ilə yığılır.

İstifadə:  python scripts/i18n_fill_lab_groups_manage_2026_11_06.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def _t(az, en, ru, tr, de):
    return {"az": az, "en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "registrar.lab_groups": {
        "%(n)s tələbə yerləşdirildi: %(group)s.": _t(
            "%(n)s tələbə yerləşdirildi: %(group)s.",
            "%(n)s students placed: %(group)s.",
            "Распределено студентов: %(n)s — %(group)s.",
            "%(n)s öğrenci yerleştirildi: %(group)s.",
            "%(n)s Studierende zugeordnet: %(group)s.",
        ),
        "%(n)s tələbənin öz qrupunun dərslərində qeydi var — onlar köçürülmədi (qeydlər itməsin deyə).": _t(
            "%(n)s tələbənin öz qrupunun dərslərində qeydi var — onlar köçürülmədi (qeydlər itməsin deyə).",
            "%(n)s students have records in their own group's lessons — they were not moved (so the records are kept).",
            "У %(n)s студентов есть отметки на занятиях их группы — они не перемещены (чтобы отметки не потерялись).",
            "%(n)s öğrencinin kendi grubunun derslerinde kaydı var — taşınmadılar (kayıtlar kaybolmasın diye).",
            "%(n)s Studierende haben Einträge in Stunden ihrer Gruppe — sie wurden nicht verschoben (damit die Einträge erhalten bleiben).",
        ),
        "Ad (istəyə bağlı)": _t(
            "Ad (istəyə bağlı)", "Name (optional)", "Название (необязательно)", "Ad (isteğe bağlı)", "Name (optional)"
        ),
        "Ad dəyişmədi.": _t(
            "Ad dəyişmədi.",
            "The name did not change.",
            "Название не изменилось.",
            "Ad değişmedi.",
            "Der Name wurde nicht geändert.",
        ),
        "Adı saxla": _t("Adı saxla", "Save name", "Сохранить название", "Adı kaydet", "Namen speichern"),
        "Bağlı dərs": _t("Bağlı dərs", "Bound lessons", "Привязанных занятий", "Bağlı ders", "Zugeordnete Stunden"),
        "Bu adda laboratoriya qrupu artıq var.": _t(
            "Bu adda laboratoriya qrupu artıq var.",
            "A lab group with this name already exists.",
            "Лабораторная группа с таким названием уже есть.",
            "Bu adda bir laboratuvar grubu zaten var.",
            "Eine Laborgruppe mit diesem Namen gibt es bereits.",
        ),
        "Bu jurnal hələ laboratoriya qruplarına bölünməyib. «Qrup əlavə et» ilə Lab-1, Lab-2 … yaradın, sonra tələbələri yerləşdirin.": _t(
            "Bu jurnal hələ laboratoriya qruplarına bölünməyib. «Qrup əlavə et» ilə Lab-1, Lab-2 … yaradın, sonra tələbələri yerləşdirin.",
            "This journal is not split into lab groups yet. Create Lab 1, Lab 2 … with “Add group”, then place the students.",
            "Этот журнал ещё не разделён на лабораторные группы. Создайте Лаб-1, Лаб-2 … кнопкой «Добавить группу», затем распределите студентов.",
            "Bu yoklama henüz laboratuvar gruplarına bölünmedi. «Grup ekle» ile Lab 1, Lab 2 … oluşturun, sonra öğrencileri yerleştirin.",
            "Dieses Journal ist noch nicht in Laborgruppen geteilt. Legen Sie mit „Gruppe hinzufügen“ Labor-1, Labor-2 … an und ordnen Sie dann die Studierenden zu.",
        ),
        "Bu qrupa %(n)s dərs bağlıdır — əvvəlcə həmin dərslərin qrupunu dəyişin və ya dərsləri silin.": _t(
            "Bu qrupa %(n)s dərs bağlıdır — əvvəlcə həmin dərslərin qrupunu dəyişin və ya dərsləri silin.",
            "%(n)s lessons are bound to this group — first change those lessons' group or delete the lessons.",
            "К этой группе привязано занятий: %(n)s — сначала измените группу этих занятий или удалите их.",
            "Bu gruba %(n)s ders bağlı — önce bu derslerin grubunu değiştirin veya dersleri silin.",
            "Dieser Gruppe sind %(n)s Stunden zugeordnet — ändern Sie zuerst deren Gruppe oder löschen Sie die Stunden.",
        ),
        "Bütün tələbələr qrupa yerləşdirilib.": _t(
            "Bütün tələbələr qrupa yerləşdirilib.",
            "All students are placed in a group.",
            "Все студенты распределены по группам.",
            "Tüm öğrenciler bir gruba yerleştirildi.",
            "Alle Studierenden sind einer Gruppe zugeordnet.",
        ),
        "Bəli, qrupu silirəm": _t(
            "Bəli, qrupu silirəm",
            "Yes, delete the group",
            "Да, удалить группу",
            "Evet, grubu siliyorum",
            "Ja, Gruppe löschen",
        ),
        "Hamısını seç": _t("Hamısını seç", "Select all", "Выбрать всех", "Tümünü seç", "Alle auswählen"),
        "Hansı qrupa": _t("Hansı qrupa", "To which group", "В какую группу", "Hangi gruba", "In welche Gruppe"),
        "Hansı qrupa köçürüləcəyini seçin.": _t(
            "Hansı qrupa köçürüləcəyini seçin.",
            "Choose the group to move to.",
            "Выберите, в какую группу перенести.",
            "Hangi gruba taşınacağını seçin.",
            "Wählen Sie die Zielgruppe.",
        ),
        "Jurnala qayıt": _t(
            "Jurnala qayıt", "Back to the journal", "Вернуться к журналу", "Yoklamaya dön", "Zurück zum Journal"
        ),
        "Jurnalda ən çox %(max)s laboratoriya qrupu ola bilər.": _t(
            "Jurnalda ən çox %(max)s laboratoriya qrupu ola bilər.",
            "A journal can have at most %(max)s lab groups.",
            "В журнале может быть не более %(max)s лабораторных групп.",
            "Bir yoklamada en fazla %(max)s laboratuvar grubu olabilir.",
            "Ein Journal kann höchstens %(max)s Laborgruppen haben.",
        ),
        "Köçür": _t("Köçür", "Move", "Перенести", "Taşı", "Verschieben"),
        "Lab qrupları": _t("Lab qrupları", "Lab groups", "Лаб. группы", "Lab grupları", "Laborgruppen"),
        "Laboratoriya qruplarını yarat, adlandır və tələbələri yerləşdir": _t(
            "Laboratoriya qruplarını yarat, adlandır və tələbələri yerləşdir",
            "Create and name lab groups and place the students",
            "Создать и назвать лабораторные группы, распределить студентов",
            "Laboratuvar gruplarını oluştur, adlandır ve öğrencileri yerleştir",
            "Laborgruppen anlegen, benennen und Studierende zuordnen",
        ),
        "Mühazirə və seminar bütün qrupladır. Qrupu seçilmiş laboratoriya dərsi yalnız həmin qrupun tələbələrinə yazılır.": _t(
            "Mühazirə və seminar bütün qrupladır. Qrupu seçilmiş laboratoriya dərsi yalnız həmin qrupun tələbələrinə yazılır.",
            "Lectures and seminars are for the whole group. A lab lesson with a selected group is recorded only for that group's students.",
            "Лекции и семинары проходят со всей группой. Лабораторное занятие с выбранной группой записывается только её студентам.",
            "Ders ve seminer tüm grupla yapılır. Grubu seçilmiş laboratuvar dersi yalnızca o grubun öğrencilerine yazılır.",
            "Vorlesungen und Seminare finden mit der ganzen Gruppe statt. Eine Laborstunde mit gewählter Gruppe wird nur für deren Studierende erfasst.",
        ),
        "Naməlum əməl.": _t(
            "Naməlum əməl.", "Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem.", "Unbekannte Aktion."
        ),
        "Qrup əlavə et": _t("Qrup əlavə et", "Add group", "Добавить группу", "Grup ekle", "Gruppe hinzufügen"),
        "Qrupa dərs bağlıdır — silmək olmaz. Əvvəlcə həmin dərslərin qrupunu dəyişin.": _t(
            "Qrupa dərs bağlıdır — silmək olmaz. Əvvəlcə həmin dərslərin qrupunu dəyişin.",
            "Lessons are bound to the group — it cannot be deleted. First change those lessons' group.",
            "К группе привязаны занятия — удалить нельзя. Сначала измените группу этих занятий.",
            "Gruba ders bağlı — silinemez. Önce bu derslerin grubunu değiştirin.",
            "Der Gruppe sind Stunden zugeordnet — sie kann nicht gelöscht werden. Ändern Sie zuerst deren Gruppe.",
        ),
        "Qrupda hələ tələbə yoxdur.": _t(
            "Qrupda hələ tələbə yoxdur.",
            "No students in this group yet.",
            "В группе пока нет студентов.",
            "Grupta henüz öğrenci yok.",
            "Noch keine Studierenden in dieser Gruppe.",
        ),
        "Qruplar": _t("Qruplar", "Groups", "Группы", "Gruplar", "Gruppen"),
        "Qruplu laboratoriya dərsləri bu tələbələrə aid deyil — onları qrupa yerləşdirin.": _t(
            "Qruplu laboratoriya dərsləri bu tələbələrə aid deyil — onları qrupa yerləşdirin.",
            "Group lab lessons do not apply to these students — place them in a group.",
            "Групповые лабораторные занятия к этим студентам не относятся — распределите их по группам.",
            "Gruplu laboratuvar dersleri bu öğrencilere ait değil — onları bir gruba yerleştirin.",
            "Gruppen-Laborstunden gelten nicht für diese Studierenden — ordnen Sie sie einer Gruppe zu.",
        ),
        "Qrupsuz": _t("Qrupsuz", "No group", "Без группы", "Grupsuz", "Ohne Gruppe"),
        "Qrupsuz et": _t(
            "Qrupsuz et", "Remove from group", "Убрать из группы", "Gruptan çıkar", "Aus der Gruppe entfernen"
        ),
        "Qrupsuz tələbələr": _t(
            "Qrupsuz tələbələr",
            "Students without a group",
            "Студенты без группы",
            "Grupsuz öğrenciler",
            "Studierende ohne Gruppe",
        ),
        "Qrupu sil": _t("Qrupu sil", "Delete group", "Удалить группу", "Grubu sil", "Gruppe löschen"),
        "Qrupun adı": _t("Qrupun adı", "Group name", "Название группы", "Grup adı", "Gruppenname"),
        "Qrupun adı yeniləndi: %(label)s.": _t(
            "Qrupun adı yeniləndi: %(label)s.",
            "Group name updated: %(label)s.",
            "Название группы обновлено: %(label)s.",
            "Grup adı güncellendi: %(label)s.",
            "Gruppenname aktualisiert: %(label)s.",
        ),
        "Seçilib": _t("Seçilib", "Selected", "Выбрано", "Seçildi", "Ausgewählt"),
        "Seçilən tələbələr artıq bu qrupdadır.": _t(
            "Seçilən tələbələr artıq bu qrupdadır.",
            "The selected students are already in this group.",
            "Выбранные студенты уже в этой группе.",
            "Seçilen öğrenciler zaten bu grupta.",
            "Die ausgewählten Studierenden sind bereits in dieser Gruppe.",
        ),
        "Seçilən tələbələrdən biri bu jurnalda deyil.": _t(
            "Seçilən tələbələrdən biri bu jurnalda deyil.",
            "One of the selected students is not in this journal.",
            "Один из выбранных студентов не состоит в этом журнале.",
            "Seçilen öğrencilerden biri bu yoklamada değil.",
            "Eine der ausgewählten Personen ist nicht in diesem Journal.",
        ),
        "Sil": _t("Sil", "Delete", "Удалить", "Kaldır", "Löschen"),
        "Silməni təsdiqləyin.": _t(
            "Silməni təsdiqləyin.",
            "Confirm the deletion.",
            "Подтвердите удаление.",
            "Silmeyi onaylayın.",
            "Bestätigen Sie das Löschen.",
        ),
        "Tələbə": _t("Tələbə", "Students", "Студентов", "Öğrenci", "Studierende"),
        "Tələbə axtar": _t("Tələbə axtar", "Search students", "Поиск студента", "Öğrenci ara", "Studierende suchen"),
        "Tələbə axtar…": _t(
            "Tələbə axtar…", "Search students…", "Поиск студента…", "Öğrenci ara…", "Studierende suchen…"
        ),
        "Tələbə heç bir laboratoriya qrupuna yerləşdirilməyib — qruplu lab dərsləri ona aid deyil. Jurnalın «Lab qrupları» bölməsində yerləşdirin.": _t(
            "Tələbə heç bir laboratoriya qrupuna yerləşdirilməyib — qruplu lab dərsləri ona aid deyil. Jurnalın «Lab qrupları» bölməsində yerləşdirin.",
            "The student is not in any lab group — group lab lessons do not apply to them. Place them in the journal's “Lab groups” section.",
            "Студент не распределён ни в одну лабораторную группу — групповые лабораторные занятия к нему не относятся. Распределите в разделе журнала «Лаб. группы».",
            "Öğrenci hiçbir laboratuvar grubuna yerleştirilmedi — gruplu laboratuvar dersleri ona ait değil. Yoklamanın «Lab grupları» bölümünde yerleştirin.",
            "Die Person ist keiner Laborgruppe zugeordnet — Gruppen-Laborstunden gelten nicht für sie. Ordnen Sie sie im Bereich „Laborgruppen“ des Journals zu.",
        ),
        "Tələbə seçilməyib.": _t(
            "Tələbə seçilməyib.",
            "No student selected.",
            "Студент не выбран.",
            "Öğrenci seçilmedi.",
            "Keine Person ausgewählt.",
        ),
        "Tələbələr": _t("Tələbələr", "Students", "Студенты", "Öğrenciler", "Studierende"),
        "Tələbənin öz qrupunun dərslərində qeydi var — köçürmək olmaz (qeydlər itməsin deyə).": _t(
            "Tələbənin öz qrupunun dərslərində qeydi var — köçürmək olmaz (qeydlər itməsin deyə).",
            "The student has records in their own group's lessons — they cannot be moved (so the records are kept).",
            "У студента есть отметки на занятиях его группы — перенести нельзя (чтобы отметки не потерялись).",
            "Öğrencinin kendi grubunun derslerinde kaydı var — taşınamaz (kayıtlar kaybolmasın diye).",
            "Die Person hat Einträge in Stunden ihrer Gruppe — sie kann nicht verschoben werden (damit die Einträge erhalten bleiben).",
        ),
        "Yeni qrupun adı (istəyə bağlı)": _t(
            "Yeni qrupun adı (istəyə bağlı)",
            "New group name (optional)",
            "Название новой группы (необязательно)",
            "Yeni grubun adı (isteğe bağlı)",
            "Name der neuen Gruppe (optional)",
        ),
        "qeyd var": _t("qeyd var", "has records", "есть отметки", "kayıt var", "hat Einträge"),
        "tələbə": _t("tələbə", "students", "студентов", "öğrenci", "Studierende"),
        "«%(label)s» qrupu silindi — %(n)s tələbə qrupsuz qaldı.": _t(
            "«%(label)s» qrupu silindi — %(n)s tələbə qrupsuz qaldı.",
            "Group “%(label)s” deleted — %(n)s students are now without a group.",
            "Группа «%(label)s» удалена — без группы осталось студентов: %(n)s.",
            "«%(label)s» grubu silindi — %(n)s öğrenci grupsuz kaldı.",
            "Gruppe „%(label)s“ gelöscht — %(n)s Studierende sind jetzt ohne Gruppe.",
        ),
        "«%(label)s» qrupu yaradıldı — tələbələri aşağıda yerləşdirin.": _t(
            "«%(label)s» qrupu yaradıldı — tələbələri aşağıda yerləşdirin.",
            "Group “%(label)s” created — place the students below.",
            "Группа «%(label)s» создана — распределите студентов ниже.",
            "«%(label)s» grubu oluşturuldu — öğrencileri aşağıda yerleştirin.",
            "Gruppe „%(label)s“ angelegt — ordnen Sie die Studierenden unten zu.",
        ),
        "«%(label)s» silinəcək; qrupsuz qalacaq tələbə: %(n)s.": _t(
            "«%(label)s» silinəcək; qrupsuz qalacaq tələbə: %(n)s.",
            "“%(label)s” will be deleted; students left without a group: %(n)s.",
            "«%(label)s» будет удалена; студентов без группы останется: %(n)s.",
            "«%(label)s» silinecek; grupsuz kalacak öğrenci: %(n)s.",
            "„%(label)s“ wird gelöscht; Studierende ohne Gruppe danach: %(n)s.",
        ),
    },
    "registrar.model.lab_group.meta": {
        "laboratoriya qrupu": _t(
            "laboratoriya qrupu", "lab group", "лабораторная группа", "laboratuvar grubu", "Laborgruppe"
        ),
        "laboratoriya qrupları": _t(
            "laboratoriya qrupları", "lab groups", "лабораторные группы", "laboratuvar grupları", "Laborgruppen"
        ),
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain="django"):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(translations[lang])}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for lang in LOCALES:
        fill(lang)
