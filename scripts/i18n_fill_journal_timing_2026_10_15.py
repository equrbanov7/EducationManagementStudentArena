#!/usr/bin/env python3
"""EMSArena i18n — jurnal vaxt qaydaları «Sistem tənzimləmələri»ndə 2026-10-15.

Sahib: «dəqiqə olaraq settings-ə əlavə et: q/b, bal yazandan sonra düzəliş müddəti; dərs tarixindən N gün
sonra yaza bilməsin; aktivləşdirmədən maks 2 saat ərzində yazmaq». Əlavə olunan mətnlər:
  * `core.runtime_settings` — yeni sahələrin etiket / izahları (`core/runtime_settings.py`);
  * `registrar.journal_timing` — müddət mətnləri və servis xəta mesajları (`apps/registrar/journal_edit_windows.py`);
  * `registrar.journal` — jurnal şablonlarında «2 saat» əvəzinə faktiki müddət (`_jd_grid.html`,
    `_jd_lesson_modal.html`, `_jd_coursework.html`).

msgid AZ cümlədir → az msgstr = msgid. `{% blocktrans %}` dəyişənləri kataloqda `%(w)s` kimidir.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir (mövcudluq
`polib` ilə yoxlanılır — sarılmış uzun msgid-lər də tanınır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_journal_timing_2026_10_15.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RS = "core.runtime_settings"
TIMING = "registrar.journal_timing"
JOURNAL = "registrar.journal"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    RS: {
        "Müəllim dərsi yaratdıqdan sonra bu qədər dəqiqə ərzində onun tarixini, növünü, mövzusunu, saatını "
        "dəyişə və ya dərsi silə bilər (120 dəqiqə = 2 saat). Sonra yalnız rəsmi düzəliş yolu.": {
            "en": "After creating a lesson, the teacher can change its date, type, topic and time or delete it "
            "within this many minutes (120 minutes = 2 hours). After that, only the official correction path.",
            "ru": "После создания занятия преподаватель в течение стольких минут может изменить его дату, тип, тему, "
            "время или удалить его (120 минут = 2 часа). Затем — только официальная корректировка.",
            "tr": "Öğretmen dersi oluşturduktan sonra bu kadar dakika içinde tarihini, türünü, konusunu, saatini "
            "değiştirebilir veya dersi silebilir (120 dakika = 2 saat). Sonrasında yalnızca resmî düzeltme yolu.",
            "de": "Nach dem Anlegen einer Lehrveranstaltung kann die Lehrkraft innerhalb so vieler Minuten Datum, "
            "Art, Thema und Uhrzeit ändern oder sie löschen (120 Minuten = 2 Stunden). Danach nur noch über die "
            "offizielle Korrektur.",
        },
        "Müəllimin yazdığı q/b, i/e və bal yazıldıqdan bu qədər dəqiqə sonra donur — sonra yalnız rəsmi "
        "düzəliş yolu. Verilənlər bazası da eyni müddəti yoxlayır (120 dəqiqə = 2 saat).": {
            "en": "Absences, attendance marks and scores entered by the teacher freeze this many minutes after "
            "entry — after that, only the official correction path. The database checks the same window "
            "(120 minutes = 2 hours).",
            "ru": "Отметки о пропуске, присутствии и баллы, внесённые преподавателем, замораживаются через столько "
            "минут после записи — затем только официальная корректировка. База данных проверяет тот же срок "
            "(120 минут = 2 часа).",
            "tr": "Öğretmenin girdiği devamsızlık, katılım ve puan, girildikten bu kadar dakika sonra kilitlenir — "
            "sonrasında yalnızca resmî düzeltme yolu. Veritabanı da aynı süreyi denetler (120 dakika = 2 saat).",
            "de": "Von der Lehrkraft eingetragene Fehlzeiten, Anwesenheiten und Punkte werden so viele Minuten nach "
            "dem Eintrag eingefroren — danach nur noch über die offizielle Korrektur. Die Datenbank prüft dieselbe "
            "Frist (120 Minuten = 2 Stunden).",
        },
        "Dərs tarixindən sonra gecikmiş yazı müddəti": {
            "en": "Late entry period after the lesson date",
            "ru": "Срок поздней записи после даты занятия",
            "tr": "Ders tarihinden sonra gecikmeli giriş süresi",
            "de": "Frist für verspätete Einträge nach dem Unterrichtsdatum",
        },
        "0 — dərs və yeni q/b, i/e, bal yalnız dərsin öz günündə yazılır. N — müəllim dərs tarixindən ən "
        "çox N gün sonra həmin tarixə dərs aça və yeni qeyd yaza bilər; müddət bitəndə yazı bağlanır. "
        "RİM rəhbərinin rəsmi düzəliş yolu bu həddə tabe deyil.": {
            "en": "0 — the lesson and new absences, attendance marks and scores are entered only on the lesson day "
            "itself. N — the teacher can open a lesson for that date and enter new marks up to N days after the "
            "lesson date; when the period ends, entry is closed. The official correction path of the head of the "
            "Registrar's Office is not bound by this limit.",
            "ru": "0 — занятие и новые отметки (пропуск, присутствие, балл) вносятся только в сам день занятия. "
            "N — преподаватель может открыть занятие на эту дату и внести новые отметки не позднее чем через N дней "
            "после даты занятия; по истечении срока запись закрывается. Официальная корректировка руководителя "
            "регистратуры этому лимиту не подчиняется.",
            "tr": "0 — ders ve yeni devamsızlık, katılım, puan yalnızca dersin kendi gününde girilir. N — öğretmen "
            "ders tarihinden en fazla N gün sonrasına kadar o tarihe ders açabilir ve yeni kayıt girebilir; süre "
            "dolunca giriş kapanır. Kayıt Ofisi başkanının resmî düzeltme yolu bu sınıra tabi değildir.",
            "de": "0 — die Lehrveranstaltung und neue Fehlzeiten, Anwesenheiten und Punkte werden nur am "
            "Unterrichtstag selbst eingetragen. N — die Lehrkraft kann bis zu N Tage nach dem Unterrichtsdatum "
            "eine Lehrveranstaltung für dieses Datum anlegen und neue Einträge vornehmen; danach ist die Eingabe "
            "geschlossen. Die offizielle Korrektur durch die Leitung des Studienbüros unterliegt dieser Grenze nicht.",
        },
        "Aktivləşdirmədən sonra yazı müddəti": {
            "en": "Entry period after activation",
            "ru": "Срок записи после активации",
            "tr": "Etkinleştirmeden sonra giriş süresi",
            "de": "Eingabefrist nach der Aktivierung",
        },
        "Yalnız «Aktivləşdir» yanılıdırsa: müəllim dərsi aktivləşdirdikdən (jurnalda açdıqdan) sonra q/b, "
        "i/e və balı bu qədər dəqiqə ərzində yazmalıdır; sonra həmin dərsə yeni qeyd yazılmır. Əvvəlcədən "
        "açılmış dərsdə müddət dərsin başlama saatından sayılır.": {
            "en": "Only when «Activate» is on: after activating (opening) the lesson in the journal, the teacher must "
            "enter absences, attendance marks and scores within this many minutes; after that, no new marks can be "
            "entered for that lesson. For a lesson opened in advance, the period counts from the lesson start time.",
            "ru": "Только если включена «Активировать»: после активации (открытия) занятия в журнале преподаватель "
            "должен внести пропуски, присутствие и баллы в течение стольких минут; затем новые отметки по этому "
            "занятию не вносятся. Для занятия, открытого заранее, срок отсчитывается от времени начала занятия.",
            "tr": "Yalnızca «Etkinleştir» açıksa: öğretmen dersi yoklama defterinde etkinleştirdikten (açtıktan) "
            "sonra devamsızlık, katılım ve puanı bu kadar dakika içinde girmelidir; sonrasında o derse yeni kayıt "
            "girilmez. Önceden açılmış derste süre dersin başlama saatinden sayılır.",
            "de": "Nur wenn «Aktivieren» eingeschaltet ist: Nach dem Aktivieren (Öffnen) der Lehrveranstaltung im "
            "Journal muss die Lehrkraft Fehlzeiten, Anwesenheiten und Punkte innerhalb so vieler Minuten eintragen; "
            "danach sind für diese Lehrveranstaltung keine neuen Einträge möglich. Bei einer im Voraus angelegten "
            "Lehrveranstaltung zählt die Frist ab Beginn der Lehrveranstaltung.",
        },
    },
    TIMING: {
        "%(n)s saat": {"en": "%(n)s h", "ru": "%(n)s ч", "tr": "%(n)s sa.", "de": "%(n)s Std."},
        "%(h)s saat %(m)s dəqiqə": {
            "en": "%(h)s h %(m)s min",
            "ru": "%(h)s ч %(m)s мин",
            "tr": "%(h)s saat %(m)s dakika",
            "de": "%(h)s Std. %(m)s Min.",
        },
        "%(n)s dəqiqə": {"en": "%(n)s min", "ru": "%(n)s мин", "tr": "%(n)s dakika", "de": "%(n)s Min."},
        "Keçmiş tarixə dərs əlavə etmək olmaz.": {
            "en": "You cannot add a lesson for a past date.",
            "ru": "Нельзя добавить занятие на прошедшую дату.",
            "tr": "Geçmiş bir tarihe ders eklenemez.",
            "de": "Für ein vergangenes Datum kann keine Lehrveranstaltung angelegt werden.",
        },
        "Dərs tarixi ən çox %(d)s gün geriyə ola bilər — ən erkən %(date)s. Daha köhnə tarix üçün RİM-ə "
        "müraciət edin.": {
            "en": "The lesson date can be at most %(d)s day(s) back — the earliest is %(date)s. For an older date, "
            "contact the Registrar's Office.",
            "ru": "Дата занятия может быть не более чем на %(d)s дн. назад — самая ранняя %(date)s. Для более "
            "ранней даты обратитесь в регистратуру.",
            "tr": "Ders tarihi en fazla %(d)s gün geriye olabilir — en erken %(date)s. Daha eski bir tarih için "
            "Kayıt Ofisine başvurun.",
            "de": "Das Unterrichtsdatum darf höchstens %(d)s Tag(e) zurückliegen — frühestens %(date)s. Für ein "
            "älteres Datum wenden Sie sich an das Studienbüro.",
        },
        "Gələcək tarixli dərsə qeyd hələ yazıla bilməz.": {
            "en": "Marks cannot be entered yet for a lesson with a future date.",
            "ru": "Для занятия с будущей датой отметки пока вносить нельзя.",
            "tr": "İleri tarihli bir derse henüz kayıt girilemez.",
            "de": "Für eine Lehrveranstaltung mit künftigem Datum können noch keine Einträge vorgenommen werden.",
        },
        "Yeni qeyd yalnız dərsin öz günündə yazılır — keçmiş dərsə yazmaq olmaz.": {
            "en": "New marks are entered only on the lesson day itself — a past lesson cannot be filled in.",
            "ru": "Новые отметки вносятся только в сам день занятия — в прошедшее занятие вносить нельзя.",
            "tr": "Yeni kayıt yalnızca dersin kendi gününde girilir — geçmiş bir derse girilemez.",
            "de": "Neue Einträge sind nur am Unterrichtstag selbst möglich — eine vergangene Lehrveranstaltung kann "
            "nicht nachgetragen werden.",
        },
        "Dərs tarixindən %(d)s gündən çox keçib — %(date)s tarixli dərsə yeni qeyd yazmaq olmaz.": {
            "en": "More than %(d)s day(s) have passed since the lesson date — new marks cannot be entered for the "
            "lesson of %(date)s.",
            "ru": "С даты занятия прошло более %(d)s дн. — в занятие от %(date)s новые отметки вносить нельзя.",
            "tr": "Ders tarihinden bu yana %(d)s günden fazla geçti — %(date)s tarihli derse yeni kayıt girilemez.",
            "de": "Seit dem Unterrichtsdatum sind mehr als %(d)s Tag(e) vergangen — für die Lehrveranstaltung vom "
            "%(date)s sind keine neuen Einträge möglich.",
        },
        "Dərs aktivləşdiriləndən %(w)s keçib — q/b, i/e və bal yalnız aktivləşdirmədən sonrakı %(w)s ərzində "
        "yazılır.": {
            "en": "%(w)s have passed since the lesson was activated — absences, attendance marks and scores are "
            "entered only within %(w)s after activation.",
            "ru": "С активации занятия прошло %(w)s — пропуски, присутствие и баллы вносятся только в течение "
            "%(w)s после активации.",
            "tr": "Dersin etkinleştirilmesinden bu yana %(w)s geçti — devamsızlık, katılım ve puan yalnızca "
            "etkinleştirmeden sonraki %(w)s içinde girilir.",
            "de": "Seit der Aktivierung der Lehrveranstaltung sind %(w)s vergangen — Fehlzeiten, Anwesenheiten und "
            "Punkte werden nur innerhalb von %(w)s nach der Aktivierung eingetragen.",
        },
    },
    JOURNAL: {
        "Redaktə / sil (pəncərə: %(w)s)": {
            "en": "Edit / delete (window: %(w)s)",
            "ru": "Изменить / удалить (окно: %(w)s)",
            "tr": "Düzenle / sil (süre: %(w)s)",
            "de": "Bearbeiten / löschen (Frist: %(w)s)",
        },
        "Davamiyyət dərs günü və ondan sonra ən çox %(d)s gün ərzində qeyd edilə bilər · yazılmış qeyd %(w)s "
        "sonra kilidlənir — düzəliş üçün Tyutor xidmətinə yazılı müraciət edilir.": {
            "en": "Attendance can be recorded on the lesson day and up to %(d)s day(s) after it · a recorded mark "
            "locks after %(w)s — for a correction, submit a written request to the Tutor service.",
            "ru": "Посещаемость отмечается в день занятия и не позднее %(d)s дн. после него · запись блокируется "
            "через %(w)s — для исправления подаётся письменное обращение в службу тьюторов.",
            "tr": "Devam, ders günü ve sonrasında en fazla %(d)s gün içinde kaydedilebilir · girilen kayıt %(w)s "
            "sonra kilitlenir — düzeltme için Tutor hizmetine yazılı başvuru yapılır.",
            "de": "Die Anwesenheit kann am Unterrichtstag und bis zu %(d)s Tag(e) danach erfasst werden · ein "
            "Eintrag wird nach %(w)s gesperrt — für eine Korrektur ist ein schriftlicher Antrag beim Tutorendienst "
            "nötig.",
        },
        "Davamiyyət yalnız dərs günü qeyd edilə bilər · yazılmış qeyd %(w)s sonra kilidlənir — düzəliş üçün "
        "Tyutor xidmətinə yazılı müraciət edilir.": {
            "en": "Attendance can be recorded only on the lesson day · a recorded mark locks after %(w)s — for a "
            "correction, submit a written request to the Tutor service.",
            "ru": "Посещаемость отмечается только в день занятия · запись блокируется через %(w)s — для исправления "
            "подаётся письменное обращение в службу тьюторов.",
            "tr": "Devam yalnızca ders günü kaydedilebilir · girilen kayıt %(w)s sonra kilitlenir — düzeltme için "
            "Tutor hizmetine yazılı başvuru yapılır.",
            "de": "Die Anwesenheit kann nur am Unterrichtstag erfasst werden · ein Eintrag wird nach %(w)s gesperrt "
            "— für eine Korrektur ist ein schriftlicher Antrag beim Tutorendienst nötig.",
        },
        "aktivləşdirilmiş dərsə qeydlər aktivləşdirmədən sonra %(a)s ərzində yazılır.": {
            "en": "marks for an activated lesson are entered within %(a)s after activation.",
            "ru": "отметки в активированное занятие вносятся в течение %(a)s после активации.",
            "tr": "etkinleştirilmiş derse kayıtlar etkinleştirmeden sonraki %(a)s içinde girilir.",
            "de": "Einträge für eine aktivierte Lehrveranstaltung erfolgen innerhalb von %(a)s nach der Aktivierung.",
        },
        "Keçmiş tarixə dərs ən çox %(d)s gün geriyə açmaq olar.": {
            "en": "A lesson can be opened for a past date at most %(d)s day(s) back.",
            "ru": "Занятие на прошедшую дату можно открыть не более чем на %(d)s дн. назад.",
            "tr": "Geçmiş bir tarihe en fazla %(d)s gün geriye ders açılabilir.",
            "de": "Eine Lehrveranstaltung kann höchstens %(d)s Tag(e) rückwirkend angelegt werden.",
        },
        "Bu dərs kilidlənib (%(w)s keçib). Tarix/tip/saat/mövzu/müəllim dəyişikliyi VƏ YA dərsin silinməsi rəsmi "
        "sənədlə (təqdimat) audit olunur.": {
            "en": "This lesson is locked (%(w)s have passed). Changing the date/type/time/topic/teacher OR deleting "
            "the lesson is audited with an official document (submission).",
            "ru": "Занятие заблокировано (прошло %(w)s). Изменение даты/типа/времени/темы/преподавателя ИЛИ удаление "
            "занятия проводится с официальным документом (представлением) и фиксируется в аудите.",
            "tr": "Bu ders kilitlendi (%(w)s geçti). Tarih/tür/saat/konu/öğretmen değişikliği VEYA dersin silinmesi "
            "resmî belgeyle (dilekçe) denetlenir.",
            "de": "Diese Lehrveranstaltung ist gesperrt (%(w)s vergangen). Änderungen an Datum/Art/Uhrzeit/Thema/"
            "Lehrkraft ODER das Löschen werden mit einem offiziellen Dokument (Antrag) protokolliert.",
        },
        "Dərs əlavə edildikdə davamiyyət cədvəlinə yeni tarix sütunu açılır; qeydlər dərs günü və ondan sonra ən "
        "çox %(d)s gün ərzində aparılır. Səhv açılmış dərsi %(w)s ərzində silmək/düzəltmək olar.": {
            "en": "Adding a lesson opens a new date column in the attendance table; marks are entered on the lesson "
            "day and up to %(d)s day(s) after it. A lesson opened by mistake can be deleted/fixed within %(w)s.",
            "ru": "При добавлении занятия в таблице посещаемости открывается новый столбец даты; отметки вносятся в "
            "день занятия и не позднее %(d)s дн. после него. Ошибочно открытое занятие можно удалить/исправить в "
            "течение %(w)s.",
            "tr": "Ders eklendiğinde devam tablosunda yeni bir tarih sütunu açılır; kayıtlar ders günü ve sonrasında "
            "en fazla %(d)s gün içinde girilir. Yanlış açılan ders %(w)s içinde silinebilir/düzeltilebilir.",
            "de": "Beim Hinzufügen einer Lehrveranstaltung wird in der Anwesenheitstabelle eine neue Datumsspalte "
            "geöffnet; Einträge erfolgen am Unterrichtstag und bis zu %(d)s Tag(e) danach. Eine versehentlich "
            "angelegte Lehrveranstaltung kann innerhalb von %(w)s gelöscht/korrigiert werden.",
        },
        "Dərs əlavə edildikdə davamiyyət cədvəlinə yeni tarix sütunu açılır və qeydlər həmin gün aparılır. Səhv "
        "açılmış dərsi %(w)s ərzində silmək/düzəltmək olar.": {
            "en": "Adding a lesson opens a new date column in the attendance table and marks are entered on that "
            "day. A lesson opened by mistake can be deleted/fixed within %(w)s.",
            "ru": "При добавлении занятия в таблице посещаемости открывается новый столбец даты, и отметки вносятся "
            "в тот же день. Ошибочно открытое занятие можно удалить/исправить в течение %(w)s.",
            "tr": "Ders eklendiğinde devam tablosunda yeni bir tarih sütunu açılır ve kayıtlar o gün girilir. Yanlış "
            "açılan ders %(w)s içinde silinebilir/düzeltilebilir.",
            "de": "Beim Hinzufügen einer Lehrveranstaltung wird in der Anwesenheitstabelle eine neue Datumsspalte "
            "geöffnet, und die Einträge erfolgen an diesem Tag. Eine versehentlich angelegte Lehrveranstaltung kann "
            "innerhalb von %(w)s gelöscht/korrigiert werden.",
        },
        "Redaktə (pəncərə: %(w)s)": {
            "en": "Edit (window: %(w)s)",
            "ru": "Изменить (окно: %(w)s)",
            "tr": "Düzenle (süre: %(w)s)",
            "de": "Bearbeiten (Frist: %(w)s)",
        },
        "Redaktə pəncərəsi (%(w)s) bağlanıb": {
            "en": "The edit window (%(w)s) has closed",
            "ru": "Окно редактирования (%(w)s) закрыто",
            "tr": "Düzenleme süresi (%(w)s) doldu",
            "de": "Die Bearbeitungsfrist (%(w)s) ist abgelaufen",
        },
        "Kurs işi balı yekun cədvəldə ayrıca sütunda göstərilir. Yazılan qeyd %(w)s sonra kilidlənir.": {
            "en": "The coursework score is shown in a separate column of the final table. A recorded entry locks "
            "after %(w)s.",
            "ru": "Балл курсовой работы показывается в отдельной колонке итоговой таблицы. Запись блокируется через "
            "%(w)s.",
            "tr": "Dönem ödevi puanı final tablosunda ayrı bir sütunda gösterilir. Girilen kayıt %(w)s sonra "
            "kilitlenir.",
            "de": "Die Punktzahl der Kursarbeit wird in einer eigenen Spalte der Abschlusstabelle angezeigt. Ein "
            "Eintrag wird nach %(w)s gesperrt.",
        },
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
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
