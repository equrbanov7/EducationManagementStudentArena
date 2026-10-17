#!/usr/bin/env python3
"""EMSArena i18n — cədvəl redaktorunda «Uyğun vaxtlar» + otaq tövsiyəsi 2026-10-17.

Sahib: «Cədvəl yaradarkən otaq tövsiyəsi də et … müəllim üçün uyğun / qrup üçün uyğun vaxt … qrupdakı uşaq
sayı limitinə görə … korpus məsələsi». Əlavə olunan mətnlər:
  * ``django`` / `accounts.schedule_manage` — hüceyrə dialoqunun paneli (`schedule/_planner.html`; JS mətnləri
    `data-t-*` atributlarındadır, `{n}` / `{room}` / `{groups}` / `{campus}` yer tutanları JS-də əvəz olunur);
  * ``django`` / `registrar.schedule_suggest` — qısa gün adları, qısa siyahının qeydləri, otaq problemi mətnləri
    (`apps/registrar/schedule_suggest.py`);
  * ``django`` / `accounts.schedule_editor` — `action=plan` 404 mətni.
  * ``djangojs`` — yoxdur (JS mətnləri şablondan gəlir).

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları
əlavə edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_schedule_suggest_2026_10_17.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

MANAGE = "accounts.schedule_manage"
SUGGEST = "registrar.schedule_suggest"
EDITOR = "accounts.schedule_editor"


def tr(en, ru, tr_, de):
    return {"en": en, "ru": ru, "tr": tr_, "de": de}


# domen → ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    "django": {
        MANAGE: {
            "Uyğun vaxtlar hesablanır…": tr(
                "Calculating suitable times…",
                "Подбираем подходящее время…",
                "Uygun saatler hesaplanıyor…",
                "Passende Zeiten werden berechnet…",
            ),
            "Təklifləri yükləmək olmadı.": tr(
                "Could not load the suggestions.",
                "Не удалось загрузить предложения.",
                "Öneriler yüklenemedi.",
                "Vorschläge konnten nicht geladen werden.",
            ),
            "Uyğun vaxtları görmək üçün əvvəlcə qrupu seçin.": tr(
                "Select the group first to see suitable times.",
                "Сначала выберите группу, чтобы увидеть подходящее время.",
                "Uygun saatleri görmek için önce grubu seçin.",
                "Wählen Sie zuerst die Gruppe, um passende Zeiten zu sehen.",
            ),
            "Müəllim seçilməyib — yalnız qrupun məşğulluğu nəzərə alınır.": tr(
                "No teacher selected — only the group's timetable is taken into account.",
                "Преподаватель не выбран — учитывается только занятость группы.",
                "Öğretim elemanı seçilmedi — yalnızca grubun programı dikkate alınır.",
                "Keine Lehrkraft gewählt — nur die Belegung der Gruppe wird berücksichtigt.",
            ),
            "Bu rejimdə uyğun boş xana tapılmadı.": tr(
                "No suitable free slot found in this mode.",
                "В этом режиме подходящих свободных ячеек нет.",
                "Bu modda uygun boş hücre bulunamadı.",
                "In diesem Modus wurde kein passender freier Platz gefunden.",
            ),
            "Ortaq boş vaxt": tr("Free for both", "Общее свободное время", "Ortak boş zaman", "Für beide frei"),
            "Müəllim və qrup boşdur, amma otaq problemi var": tr(
                "Teacher and group are free, but there is a room problem",
                "Преподаватель и группа свободны, но есть проблема с аудиторией",
                "Öğretim elemanı ve grup boş, ancak derslik sorunu var",
                "Lehrkraft und Gruppe sind frei, aber es gibt ein Raumproblem",
            ),
            "Müəllim məşğuldur": tr(
                "Teacher is busy", "Преподаватель занят", "Öğretim elemanı meşgul", "Lehrkraft belegt"
            ),
            "Qrup məşğuldur": tr("Group is busy", "Группа занята", "Grup meşgul", "Gruppe belegt"),
            "Müəllim də, qrup da məşğuldur": tr(
                "Both teacher and group are busy",
                "Заняты и преподаватель, и группа",
                "Hem öğretim elemanı hem grup meşgul",
                "Lehrkraft und Gruppe sind belegt",
            ),
            "{n} uyğun boş otaq": tr(
                "{n} suitable free rooms",
                "Подходящих свободных аудиторий: {n}",
                "{n} uygun boş derslik",
                "{n} passende freie Räume",
            ),
            "Qrupda {n} tələbə": tr(
                "{n} students in the group",
                "В группе {n} студентов",
                "Grupta {n} öğrenci",
                "{n} Studierende in der Gruppe",
            ),
            "Qrupun tələbə sayı məlum deyil — tutum yoxlanmır.": tr(
                "The group size is unknown — capacity is not checked.",
                "Численность группы неизвестна — вместимость не проверяется.",
                "Grubun öğrenci sayısı bilinmiyor — kapasite kontrol edilmiyor.",
                "Die Gruppengröße ist unbekannt — die Kapazität wird nicht geprüft.",
            ),
            "Axın: {groups} — cəmi {n} tələbə": tr(
                "Joint lecture: {groups} — {n} students in total",
                "Поток: {groups} — всего {n} студентов",
                "Ortak ders: {groups} — toplam {n} öğrenci",
                "Gemeinsame Vorlesung: {groups} — insgesamt {n} Studierende",
            ),
            "Qrupun korpusu: {campus}": tr(
                "Group's building: {campus}",
                "Корпус группы: {campus}",
                "Grubun binası: {campus}",
                "Gebäude der Gruppe: {campus}",
            ),
            "Qrupun korpusu təyin edilməyib — bütün korpuslar bərabər sıralanır.": tr(
                "The group has no building assigned — all buildings are ranked equally.",
                "Корпус группы не задан — все корпуса ранжируются одинаково.",
                "Grubun binası atanmamış — tüm binalar eşit sıralanır.",
                "Der Gruppe ist kein Gebäude zugeordnet — alle Gebäude werden gleich gereiht.",
            ),
            "Otaqların tutumu daxil edilməyib — təklif yalnız korpus və boşluğa görə sıralanır.": tr(
                "Room capacities are not filled in — suggestions are ranked only by building and availability.",
                "Вместимость аудиторий не указана — предложения ранжируются только по корпусу и занятости.",
                "Derslik kapasiteleri girilmemiş — öneriler yalnızca bina ve boşluğa göre sıralanır.",
                "Raumkapazitäten sind nicht erfasst — Vorschläge werden nur nach Gebäude und Verfügbarkeit gereiht.",
            ),
            "Otaq reyestri boşdur — otaqlar «İmtahan otaqları» bölməsində əlavə olunur.": tr(
                "The room registry is empty — rooms are added in the «Exam rooms» section.",
                "Реестр аудиторий пуст — аудитории добавляются в разделе «Экзаменационные аудитории».",
                "Derslik kaydı boş — derslikler «Sınav salonları» bölümünde eklenir.",
                "Das Raumverzeichnis ist leer — Räume werden im Bereich «Prüfungsräume» angelegt.",
            ),
            "Otaq təklifi üçün gün və dərs saatını seçin.": tr(
                "Select the day and class period to get room suggestions.",
                "Выберите день и пару, чтобы получить предложения аудиторий.",
                "Derslik önerisi için gün ve ders saatini seçin.",
                "Wählen Sie Tag und Unterrichtsstunde für Raumvorschläge.",
            ),
            "Bu saatda boş otaq yoxdur.": tr(
                "No room is free at this time.",
                "В это время свободных аудиторий нет.",
                "Bu saatte boş derslik yok.",
                "Zu dieser Zeit ist kein Raum frei.",
            ),
            "Bu saatda qrupa sığan boş otaq yoxdur — kiçik otaqlar xəbərdarlıqla göstərilir.": tr(
                "No free room fits the group at this time — smaller rooms are shown with a warning.",
                "В это время нет свободной аудитории, вмещающей группу, — меньшие показаны с предупреждением.",
                "Bu saatte grubu alan boş derslik yok — küçük derslikler uyarıyla gösteriliyor.",
                "Zu dieser Zeit passt kein freier Raum für die Gruppe — kleinere Räume werden mit Warnung angezeigt.",
            ),
            "{n} yer": tr("{n} seats", "{n} мест", "{n} kişilik", "{n} Plätze"),
            "tutum məlum deyil": tr(
                "capacity unknown", "вместимость неизвестна", "kapasite bilinmiyor", "Kapazität unbekannt"
            ),
            "kiçikdir": tr("too small", "мала", "küçük", "zu klein"),
            "başqa korpus": tr("other building", "другой корпус", "başka bina", "anderes Gebäude"),
            "laboratoriya": tr("laboratory", "лаборатория", "laboratuvar", "Labor"),
            "seçilib": tr("selected", "выбрана", "seçildi", "gewählt"),
            "Seçilmiş otaq bu saatda tutulub — boş otaqlardan birini seçin.": tr(
                "The selected room is taken at this time — pick one of the free rooms.",
                "Выбранная аудитория в это время занята — выберите одну из свободных.",
                "Seçilen derslik bu saatte dolu — boş dersliklerden birini seçin.",
                "Der gewählte Raum ist zu dieser Zeit belegt — wählen Sie einen freien Raum.",
            ),
            "Axın mühazirəsi {room} otağındadır.": tr(
                "The joint lecture is in room {room}.",
                "Поточная лекция проходит в аудитории {room}.",
                "Ortak ders {room} dersliğinde.",
                "Die gemeinsame Vorlesung findet in Raum {room} statt.",
            ),
            "Uyğun vaxtlar": tr("Suitable times", "Подходящее время", "Uygun saatler", "Passende Zeiten"),
            "Kim üçün uyğun": tr("Suitable for", "Для кого подходит", "Kimin için uygun", "Passend für"),
            "Hər ikisi üçün uyğun": tr(
                "Suitable for both", "Подходит обоим", "İkisi için de uygun", "Für beide passend"
            ),
            "Müəllim üçün uyğun": tr(
                "Suitable for the teacher",
                "Подходит преподавателю",
                "Öğretim elemanı için uygun",
                "Für die Lehrkraft passend",
            ),
            "Qrup üçün uyğun": tr(
                "Suitable for the group", "Подходит группе", "Grup için uygun", "Für die Gruppe passend"
            ),
            "ortaq boş": tr("free for both", "свободно обоим", "ortak boş", "für beide frei"),
            "otaq problemi": tr("room problem", "проблема с аудиторией", "derslik sorunu", "Raumproblem"),
            "müəllim məşğul": tr("teacher busy", "преподаватель занят", "öğretim elemanı meşgul", "Lehrkraft belegt"),
            "qrup məşğul": tr("group busy", "группа занята", "grup meşgul", "Gruppe belegt"),
            "hər ikisi məşğul": tr("both busy", "оба заняты", "ikisi de meşgul", "beide belegt"),
            "Otaq təklifi": tr("Room suggestion", "Предложение аудитории", "Derslik önerisi", "Raumvorschlag"),
        },
        SUGGEST: {
            "B.e.": tr("Mon", "Пн", "Pzt", "Mo"),
            "Ç.a.": tr("Tue", "Вт", "Sal", "Di"),
            "Ç.": tr("Wed", "Ср", "Çar", "Mi"),
            "C.a.": tr("Thu", "Чт", "Per", "Do"),
            "C.": tr("Fri", "Пт", "Cum", "Fr"),
            "Ş.": tr("Sat", "Сб", "Cmt", "Sa"),
            "B.": tr("Sun", "Вс", "Paz", "So"),
            "Müəllimin bu gün dərsi yoxdur": tr(
                "The teacher has no classes this day",
                "У преподавателя в этот день нет занятий",
                "Öğretim elemanının bu gün dersi yok",
                "Die Lehrkraft hat an diesem Tag keinen Unterricht",
            ),
            "Müəllimin dərsinə bitişik": tr(
                "Next to the teacher's class",
                "Рядом с занятием преподавателя",
                "Öğretim elemanının dersine bitişik",
                "Direkt neben dem Unterricht der Lehrkraft",
            ),
            "Müəllimin digər həftədəki dərsi ilə eyni saat": tr(
                "Same period as the teacher's class in the other week",
                "То же время, что и занятие преподавателя в другую неделю",
                "Öğretim elemanının diğer haftadaki dersiyle aynı saat",
                "Gleiche Stunde wie der Unterricht der Lehrkraft in der anderen Woche",
            ),
            "Müəllimin dərsləri arasında %(gap)s saat boşluq": tr(
                "%(gap)s free period(s) between the teacher's classes",
                "%(gap)s пар(ы) окна между занятиями преподавателя",
                "Öğretim elemanının dersleri arasında %(gap)s saat boşluk",
                "%(gap)s Freistunde(n) zwischen den Stunden der Lehrkraft",
            ),
            "Qrupun bu gün dərsi yoxdur — yeni gün": tr(
                "The group has no classes this day — a new day",
                "У группы в этот день нет занятий — новый день",
                "Grubun bu gün dersi yok — yeni gün",
                "Die Gruppe hat an diesem Tag keinen Unterricht — neuer Tag",
            ),
            "Qrupun dərsinə bitişik — boşluq yoxdur": tr(
                "Next to the group's class — no gap",
                "Рядом с занятием группы — без окна",
                "Grubun dersine bitişik — boşluk yok",
                "Direkt neben dem Unterricht der Gruppe — keine Lücke",
            ),
            "Qrupun digər həftədəki dərsi ilə eyni saat": tr(
                "Same period as the group's class in the other week",
                "То же время, что и занятие группы в другую неделю",
                "Grubun diğer haftadaki dersiyle aynı saat",
                "Gleiche Stunde wie der Unterricht der Gruppe in der anderen Woche",
            ),
            "Qrupun dərsləri arasında %(gap)s saat boşluq": tr(
                "%(gap)s free period(s) between the group's classes",
                "%(gap)s пар(ы) окна между занятиями группы",
                "Grubun dersleri arasında %(gap)s saat boşluk",
                "%(gap)s Freistunde(n) zwischen den Stunden der Gruppe",
            ),
            "Axın mühazirəsi %(room)s otağındadır — eyni otaq seçilməlidir.": tr(
                "The joint lecture is in room %(room)s — the same room must be chosen.",
                "Поточная лекция проходит в аудитории %(room)s — нужно выбрать ту же аудиторию.",
                "Ortak ders %(room)s dersliğinde — aynı derslik seçilmelidir.",
                "Die gemeinsame Vorlesung findet in Raum %(room)s statt — derselbe Raum muss gewählt werden.",
            ),
            "%(room)s otağı bu saatda tutulub.": tr(
                "Room %(room)s is taken at this time.",
                "Аудитория %(room)s в это время занята.",
                "%(room)s dersliği bu saatte dolu.",
                "Raum %(room)s ist zu dieser Zeit belegt.",
            ),
            "Bu saatda qrupa uyğun boş otaq yoxdur.": tr(
                "No free room suits the group at this time.",
                "В это время нет свободной аудитории для группы.",
                "Bu saatte gruba uygun boş derslik yok.",
                "Zu dieser Zeit gibt es keinen passenden freien Raum.",
            ),
        },
        EDITOR: {
            "Semestr tapılmadı.": tr(
                "Semester not found.", "Семестр не найден.", "Dönem bulunamadı.", "Semester nicht gefunden."
            ),
        },
    },
    "djangojs": {},
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _flags(msgid):
    return "#, python-format\n" if "%(" in msgid else ""


def fill(lang, domain):
    if not ENTRIES.get(domain):
        print(f"{lang}/{domain}: +0 entry")
        return
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES[domain].items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            blocks.append(f'{_flags(msgid)}{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        for name in ("django", "djangojs"):
            fill(locale, name)
