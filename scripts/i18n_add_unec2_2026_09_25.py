#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: UNEC müqayisəsindən jurnal imkanları (brif U2, slug `unec2`).

* «Dəyişiklik tarixçəsi» paneli (registrar.journal_history).
* «Dərsi aktivləşdir» — cədvəl zolağı, cədvəldən kənar dərsin səbəbi, «Jurnalı aç»,
  «Keçilmiş dərslər»də «Cədvəldə var, qeydə alınmayıb» (registrar.journal_activation,
  accounts.dashboard, accounts.lessons_log, registrar.lessons_log).
* «Yekun qiymət» tabının audit sütunları (registrar.journal).
* «Keçilmiş dərslər»də «Fakültə» / «Kafedra» filtrləri (accounts.lessons_log).
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_unec2_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

_H = "registrar.journal_history"
_A = "registrar.journal_activation"
_D = "accounts.dashboard"
_L = "accounts.lessons_log"
_J = "registrar.journal"

STRINGS = {
    # ── 1. «Dəyişiklik tarixçəsi» paneli ────────────────────────────────────
    (_H, "Davamiyyət / bal"): ("Attendance / score", "Посещаемость / балл", "Devam / puan"),
    (_H, "Komponent balı"): ("Component score", "Балл компонента", "Bileşen puanı"),
    (_H, "Yekun imtahan"): ("Final exam", "Итоговый экзамен", "Final sınavı"),
    (_H, "Təkrar imtahan"): ("Resit exam", "Пересдача", "Bütünleme sınavı"),
    (_H, "Sənədli düzəliş — bal / davamiyyət"): (
        "Documented correction — score / attendance",
        "Документированное исправление — балл / посещаемость",
        "Belgeli düzeltme — puan / devam",
    ),
    (_H, "Sənədli düzəliş — dərs"): (
        "Documented correction — lesson",
        "Документированное исправление — занятие",
        "Belgeli düzeltme — ders",
    ),
    (_H, "Sənədli düzəliş — dərs silindi"): (
        "Documented correction — lesson deleted",
        "Документированное исправление — занятие удалено",
        "Belgeli düzeltme — ders silindi",
    ),
    (_H, "Sənədli düzəliş — sərbəst iş"): (
        "Documented correction — independent work",
        "Документированное исправление — самостоятельная работа",
        "Belgeli düzeltme — bağımsız çalışma",
    ),
    (_H, "Sənədli düzəliş — kurs işi"): (
        "Documented correction — course work",
        "Документированное исправление — курсовая работа",
        "Belgeli düzeltme — dönem ödevi",
    ),
    (_H, "Sənədli düzəliş — komponent"): (
        "Documented correction — component",
        "Документированное исправление — компонент",
        "Belgeli düzeltme — bileşen",
    ),
    (_H, "Düzəlişin geri alınması"): ("Correction reverted", "Отмена исправления", "Düzeltmenin geri alınması"),
    (_H, "Sistem"): ("System", "Система", "Sistem"),
    (_H, "Akademik qeyd"): ("Academic record", "Академическая запись", "Akademik kayıt"),
    (_H, "Bu gün"): ("Today", "Сегодня", "Bugün"),
    (_H, "Dünən"): ("Yesterday", "Вчера", "Dün"),
    (_H, "dəyişiklik"): ("changes", "изменений", "değişiklik"),
    (_H, "Dərs sütunu"): ("Lesson column", "Столбец занятия", "Ders sütunu"),
    (_H, "başqasının adından · əsl aktor"): (
        "on behalf of another user · actual actor",
        "от имени другого пользователя · фактический автор",
        "başkası adına · gerçek kullanıcı",
    ),
    (_H, "sətir daha göstər"): ("more rows", "ещё строк", "satır daha göster"),
    (_H, "Yığ"): ("Collapse", "Свернуть", "Daralt"),
    (_H, "sətir paneldə göstərilmir — bu saxlama çox böyükdür"): (
        "rows are not shown in the panel — this save is very large",
        "строк не показано в панели — это сохранение слишком большое",
        "satır panelde gösterilmiyor — bu kayıt çok büyük",
    ),
    (_H, "qeyd göstərilir"): ("entries shown", "записей показано", "kayıt gösteriliyor"),
    (_H, "qeyd"): ("entries", "записей", "kayıt"),
    (_H, "Dəyişiklik tarixçəsi"): ("Change history", "История изменений", "Değişiklik geçmişi"),
    (_H, "Paneli bağla"): ("Close panel", "Закрыть панель", "Paneli kapat"),
    (_H, "DƏRS TARİXİ"): ("LESSON DATE", "ДАТА ЗАНЯТИЯ", "DERS TARİHİ"),
    (_H, "Tarix axtar…"): ("Search date…", "Поиск даты…", "Tarih ara…"),
    (_H, "Uyğun tarix yoxdur"): ("No matching date", "Нет подходящей даты", "Uygun tarih yok"),
    (_H, "Bütün tarixlər"): ("All dates", "Все даты", "Tüm tarihler"),
    (_H, "TƏLƏBƏ"): ("STUDENT", "СТУДЕНТ", "ÖĞRENCİ"),
    (_H, "Ad və ya soyad…"): ("First or last name…", "Имя или фамилия…", "Ad veya soyad…"),
    (_H, "Qeyd növü"): ("Entry type", "Тип записи", "Kayıt türü"),
    (_H, "Hamısı"): ("All", "Все", "Tümü"),
    (_H, "Komponent"): ("Component", "Компонент", "Bileşen"),
    (_H, "Yekun"): ("Final", "Итог", "Final"),
    (_H, "Sənədli düzəlişlər"): ("Documented corrections", "Документированные исправления", "Belgeli düzeltmeler"),
    (_H, "Yüklənir…"): ("Loading…", "Загрузка…", "Yükleniyor…"),
    (_H, "Tarixçə açıla bilmədi. Səhifəni yeniləyib yenidən cəhd edin."): (
        "The history could not be loaded. Refresh the page and try again.",
        "Не удалось загрузить историю. Обновите страницу и попробуйте снова.",
        "Geçmiş yüklenemedi. Sayfayı yenileyip tekrar deneyin.",
    ),
    (_H, "Hələ dəyişiklik qeydə alınmayıb"): (
        "No changes recorded yet",
        "Изменений пока нет",
        "Henüz değişiklik kaydedilmedi",
    ),
    (_H, "Bal, davamiyyət, komponent və düzəlişlər yazılan kimi burada görünəcək."): (
        "Scores, attendance, components and corrections appear here as soon as they are saved.",
        "Баллы, посещаемость, компоненты и исправления появятся здесь сразу после сохранения.",
        "Puan, devam, bileşen ve düzeltmeler kaydedilir kaydedilmez burada görünür.",
    ),
    (_H, "Süzgəcə uyğun qeyd yoxdur"): (
        "No entries match the filter",
        "Нет записей по фильтру",
        "Filtreye uyan kayıt yok",
    ),
    (_H, "Süzgəci dəyişin və ya aşağıdan köhnə qeydləri də yükləyin."): (
        "Change the filter or load older entries below.",
        "Измените фильтр или загрузите более старые записи ниже.",
        "Filtreyi değiştirin veya aşağıdan eski kayıtları da yükleyin.",
    ),
    (_H, "Tələbə və növ süzgəci yüklənmiş qeydlər üzrə işləyir — köhnə qeydlər üçün «Daha çox» basın."): (
        "The student and type filters apply to loaded entries — press “More” for older ones.",
        "Фильтры по студенту и типу работают по загруженным записям — для старых нажмите «Ещё».",
        "Öğrenci ve tür filtresi yüklenen kayıtlarda çalışır — eski kayıtlar için «Daha fazla»ya basın.",
    ),
    (_H, "Daha çox"): ("More", "Ещё", "Daha fazla"),
    (_H, "Bağla"): ("Close", "Закрыть", "Kapat"),
    (_H, "Tələbə"): ("Student", "Студент", "Öğrenci"),
    (_H, "Nə dəyişdi"): ("What changed", "Что изменилось", "Ne değişti"),
    (_H, "Köhnə → yeni"): ("Old → new", "Было → стало", "Eski → yeni"),
    (_H, "Kim, nə vaxt, nəyi dəyişib — jurnalın dəyişiklik tarixçəsi"): (
        "Who changed what and when — the journal change history",
        "Кто, когда и что изменил — история изменений журнала",
        "Kim, ne zaman, neyi değiştirdi — defterin değişiklik geçmişi",
    ),
    (_H, "Tarixçə"): ("History", "История", "Geçmiş"),
    (_H, "Bu dərsin tarixçəsi"): ("This lesson's history", "История этого занятия", "Bu dersin geçmişi"),
    # ── 2. «Dərsi aktivləşdir» (cədvəldən) ─────────────────────────────────
    (_A, "Bu cədvəl dərsi bu fənnə aid deyil."): (
        "This timetable slot does not belong to this course.",
        "Это занятие расписания не относится к этому предмету.",
        "Bu program dersi bu derse ait değil.",
    ),
    (_A, "Bu cədvəl dərsi %(date)s tarixində keçirilmir (həftə günü və ya üst/alt həftə uyğun deyil)."): (
        "This timetable slot is not held on %(date)s (weekday or odd/even week does not match).",
        "Это занятие расписания не проводится %(date)s (не совпадает день недели или верхняя/нижняя неделя).",
        "Bu program dersi %(date)s tarihinde yapılmıyor (haftanın günü veya tek/çift hafta uymuyor).",
    ),
    (
        _A,
        "Bu tarix və saatda cədvəldə bu fənnin dərsi yoxdur — cədvəldən kənar dərs üçün səbəbi yazın "
        "(məs. əvəzetmə, kompensasiya dərsi). Cədvəldəki dərs üçün jurnalın üstündəki «Aktivləşdir» düyməsini işlədin.",
    ): (
        "The timetable has no class of this course at this date and time — enter a reason for an off-timetable "
        "lesson (e.g. substitution, make-up class). For a timetabled class use the “Activate” button above the journal.",
        "В расписании нет занятия по этому предмету в эту дату и время — укажите причину занятия вне расписания "
        "(напр. замена, компенсационное занятие). Для занятия по расписанию используйте кнопку «Активировать» над журналом.",
        "Bu tarih ve saatte programda bu dersin dersi yok — program dışı ders için nedeni yazın "
        "(ör. yerine ders, telafi dersi). Programdaki ders için defterin üstündeki «Etkinleştir» düğmesini kullanın.",
    ),
    (_A, "Bu cədvəl dərsi bu gün artıq aktivləşdirilib."): (
        "This timetable class has already been activated today.",
        "Это занятие расписания сегодня уже активировано.",
        "Bu program dersi bugün zaten etkinleştirildi.",
    ),
    (_A, "Dərs aktivləşdirildi: %(time)s · %(kind)s%(topic)s."): (
        "Lesson activated: %(time)s · %(kind)s%(topic)s.",
        "Занятие активировано: %(time)s · %(kind)s%(topic)s.",
        "Ders etkinleştirildi: %(time)s · %(kind)s%(topic)s.",
    ),
    (_A, "Bu günün cədvəl dərsləri"): (
        "Today's timetable",
        "Занятия по расписанию на сегодня",
        "Bugünkü program dersleri",
    ),
    (_A, "Dərsi bir kliklə açın — saat, növ, otaq və növbəti mövzu cədvəldən və sillabusdan götürülür."): (
        "Open the lesson in one click — time, type, room and the next topic come from the timetable and the syllabus.",
        "Откройте занятие одним щелчком — время, тип, аудитория и следующая тема берутся из расписания и силлабуса.",
        "Dersi tek tıkla açın — saat, tür, derslik ve sonraki konu programdan ve izlenceden alınır.",
    ),
    (_A, "indi"): ("now", "сейчас", "şimdi"),
    (_A, "Mövzu"): ("Topic", "Тема", "Konu"),
    (_A, "Növbəti mövzu"): ("Next topic", "Следующая тема", "Sonraki konu"),
    (_A, "Sillabusda bu növ üçün keçilməmiş mövzu yoxdur — mövzunu sonra dərsi redaktə edərək yaza bilərsiniz."): (
        "The syllabus has no uncovered topic for this type — you can add the topic later by editing the lesson.",
        "В силлабусе нет непройденной темы для этого типа — тему можно указать позже, отредактировав занятие.",
        "İzlencede bu tür için işlenmemiş konu yok — konuyu daha sonra dersi düzenleyerek yazabilirsiniz.",
    ),
    (_A, "Jurnalda bu dərsin sütununa keç"): (
        "Go to this lesson's column in the journal",
        "Перейти к столбцу этого занятия в журнале",
        "Defterde bu dersin sütununa git",
    ),
    (_A, "Aktivləşdirilib"): ("Activated", "Активировано", "Etkinleştirildi"),
    (_A, "Aktivləşdir"): ("Activate", "Активировать", "Etkinleştir"),
    (_A, "Aktivləşdirilməyib"): ("Not activated", "Не активировано", "Etkinleştirilmedi"),
    (_A, "Bu gün cədvəldə bu fənnin dərsi yoxdur."): (
        "There is no class of this course in today's timetable.",
        "Сегодня в расписании нет занятия по этому предмету.",
        "Bugün programda bu dersin dersi yok.",
    ),
    (_A, "Növbəti dərs"): ("Next class", "Следующее занятие", "Sonraki ders"),
    (_A, "Bu gün cədvəldən kənar açılmış dərs"): (
        "Off-timetable lesson opened today",
        "Занятие вне расписания, открытое сегодня",
        "Bugün program dışı açılan ders",
    ),
    (_A, "cədvəldən kənar"): ("off-timetable", "вне расписания", "program dışı"),
    (_A, "CƏDVƏLDƏN KƏNAR DƏRS — SƏBƏB"): (
        "OFF-TIMETABLE LESSON — REASON",
        "ЗАНЯТИЕ ВНЕ РАСПИСАНИЯ — ПРИЧИНА",
        "PROGRAM DIŞI DERS — NEDEN",
    ),
    (_A, "Məs.: əvəzetmə, kompensasiya dərsi, cədvəl dəyişikliyi…"): (
        "E.g. substitution, make-up class, timetable change…",
        "Напр.: замена, компенсационное занятие, изменение расписания…",
        "Ör.: yerine ders, telafi dersi, program değişikliği…",
    ),
    (_A, "Cədvəldən kənar dərsin səbəbi"): (
        "Reason for the off-timetable lesson",
        "Причина занятия вне расписания",
        "Program dışı dersin nedeni",
    ),
    (
        _A,
        "Bu tarix və saatda cədvəldə dərs yoxdur — səbəb məcburidir və «Keçilmiş dərslər»də «cədvəldən kənar» "
        "kimi işarələnir. Cədvəldəki dərs üçün jurnalın üstündəki «Aktivləşdir» düyməsini işlədin.",
    ): (
        "The timetable has no class at this date and time — a reason is required and the lesson is flagged "
        "“off-timetable” in “Lessons held”. For a timetabled class use the “Activate” button above the journal.",
        "В расписании нет занятия в эту дату и время — причина обязательна, а занятие помечается «вне расписания» "
        "в «Проведённых занятиях». Для занятия по расписанию используйте кнопку «Активировать» над журналом.",
        "Bu tarih ve saatte programda ders yok — neden zorunludur ve ders «İşlenen dersler»de «program dışı» "
        "olarak işaretlenir. Programdaki ders için defterin üstündeki «Etkinleştir» düğmesini kullanın.",
    ),
    (_D, "Bu fənnin jurnalını aç — bu günün dərsini oradan «Aktivləşdir» ilə açın"): (
        "Open this course's journal — activate today's class from there",
        "Открыть журнал предмета — активируйте сегодняшнее занятие оттуда",
        "Bu dersin defterini aç — bugünkü dersi oradan «Etkinleştir» ile açın",
    ),
    (_D, "Jurnalı aç"): ("Open journal", "Открыть журнал", "Defteri aç"),
    (_L, "Cədvəldə var, qeydə alınmayıb"): (
        "In the timetable, not recorded",
        "В расписании есть, не отмечено",
        "Programda var, kaydedilmedi",
    ),
    (_L, "cədvəl slotu keçmiş tarixə düşür, amma jurnalda həmin gün dərs sütunu açılmayıb"): (
        "the timetable slot falls on a past date, but no lesson column was opened in the journal that day",
        "занятие расписания пришлось на прошедшую дату, но в журнале в этот день столбец не открыт",
        "program dersi geçmiş bir tarihe denk geliyor, ancak o gün defterde ders sütunu açılmamış",
    ),
    (_L, "Siyahı"): ("List", "Список", "Liste"),
    (_L, "Tarix"): ("Date", "Дата", "Tarih"),
    (_L, "Jurnal"): ("Journal", "Журнал", "Defter"),
    (_L, "Jurnalı aç"): ("Open journal", "Открыть журнал", "Defteri aç"),
    (_L, "Ən yeni %(shown)s slot göstərilir — cəmi %(total)s. Daha dar dövr seçin."): (
        "The newest %(shown)s slots are shown — %(total)s in total. Choose a narrower period.",
        "Показаны последние %(shown)s занятий — всего %(total)s. Выберите более узкий период.",
        "En yeni %(shown)s ders gösteriliyor — toplam %(total)s. Daha dar bir dönem seçin.",
    ),
    (
        _L,
        "Keçmiş tarixə dərs sütununu yalnız RİM rəhbəri aça bilər (audit izinə düşür). Bayram/tətil günləri "
        "cədvəldə ayrıca qeyd olunmadığı üçün burada sayıla bilər.",
    ): (
        "Only the RİM head can open a lesson column for a past date (it is audited). Holidays are not marked "
        "in the timetable, so they may be counted here.",
        "Открыть столбец занятия за прошедшую дату может только руководитель РИМ (попадает в аудит). "
        "Праздники в расписании отдельно не отмечены, поэтому могут учитываться здесь.",
        "Geçmiş tarihe ders sütununu yalnızca RİM başkanı açabilir (denetim kaydına düşer). Tatil günleri "
        "programda ayrıca işaretlenmediği için burada sayılabilir.",
    ),
    (_L, "cədvəldəki bütün keçmiş dərslər jurnalda açılıb"): (
        "every past timetabled class has a lesson column in the journal",
        "для всех прошедших занятий по расписанию в журнале открыты столбцы",
        "programdaki tüm geçmiş dersler defterde açılmış",
    ),
    (_L, "cədvəldən kənar"): ("off-timetable", "вне расписания", "program dışı"),
    ("registrar.lessons_log", "Cədvəldən kənar (səbəb)"): (
        "Off-timetable (reason)",
        "Вне расписания (причина)",
        "Program dışı (neden)",
    ),
    # ── «Keçilmiş dərslər»: Fakültə / Kafedra filtrləri ────────────────────
    (_L, "Fakültə"): ("Faculty", "Факультет", "Fakülte"),
    (_L, "Kafedra"): ("Department", "Кафедра", "Bölüm"),
    (_L, "Bütün fakültələr"): ("All faculties", "Все факультеты", "Tüm fakülteler"),
    (_L, "Bütün kafedralar"): ("All departments", "Все кафедры", "Tüm bölümler"),
    # ── 3. «Yekun qiymət» — audit sütunları ────────────────────────────────
    (_J, "AUDİTORİYA SAATI"): ("CLASS HOURS", "АУДИТОРНЫЕ ЧАСЫ", "DERS SAATİ"),
    (_J, "keçirilib / plan"): ("held / planned", "проведено / план", "yapılan / plan"),
    (_J, "BURAXILAN SAAT"): ("MISSED HOURS", "ПРОПУЩЕНО ЧАСОВ", "DEVAMSIZ SAAT"),
    (_J, "üzrsüz q/b"): ("unexcused absences", "без уважительной причины", "mazeretsiz devamsızlık"),
    # Şablon `{% trans %}` literalındakı «%» axtarışda «%%»-ə çevrilir (django.template.base) —
    # kataloqda da «%%» olmalıdır (mövcud «25%%» qeydləri kimi); göstərişdə yenə «%» çıxır.
    (_J, "QAYIB %%"): ("ABSENCE %%", "ПРОПУСКИ %%", "DEVAMSIZLIK %%"),
    (_J, "buraxılan ÷ plan"): ("missed ÷ planned", "пропущено ÷ план", "devamsız ÷ plan"),
    (_J, "Buraxılış həddi"): ("Admission limit", "Порог допуска", "Sınava kabul sınırı"),
    (_J, "icazəli"): ("allowed", "допустимо", "izin verilen"),
    (_J, "Qayıb %% = buraxılan saat ÷ auditoriya saatı (plan) — buraxılış qərarı ilə eyni məxrəc."): (
        "Absence %% = missed hours ÷ class hours (planned) — the same denominator as the exam admission decision.",
        "Пропуски %% = пропущенные часы ÷ аудиторные часы (план) — тот же знаменатель, что и в решении о допуске.",
        "Devamsızlık %% = devamsız saat ÷ ders saati (plan) — sınava kabul kararıyla aynı payda.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
