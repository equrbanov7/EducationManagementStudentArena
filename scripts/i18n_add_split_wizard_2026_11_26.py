#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-26: «Bölgü sehrbazı» (Yük bölgüsü — seminar / lab bölgüsü addım-addım).

Sahib: «bölmə axını aydın deyil … imtahan yaratma forması kimi addımlı modal olsun». ``django`` kataloquna
(``workload.split_wizard``, ``registrar.split_wizard``, ``accounts.workload``) və ``djangojs`` kataloquna (kontekstsiz
``gettext``) beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_split_wizard_2026_11_26.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_W = "workload.split_wizard"
_R = "registrar.split_wizard"
_A = "accounts.workload"
JS = None  # djangojs — kontekst yoxdur

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    # ── şablon + servis (django) ──────────────────────────────────────────
    ("django", _A, "Lab qrupu sayı"): ("Lab groups", "Число лаб. групп", "Laboratuvar grubu sayısı", "Laborgruppen"),
    ("django", _A, "0 — «Qrup/yarımqrup sayı» ilə eyni"): (
        "0 — same as “Groups/subgroups”",
        "0 — как «Число групп/подгрупп»",
        "0 — «Grup/alt grup sayısı» ile aynı",
        "0 — wie „Gruppen/Untergruppen“",
    ),
    ("django", _W, "Bölgü sehrbazı"): (
        "Split wizard",
        "Мастер распределения",
        "Bölme sihirbazı",
        "Aufteilungsassistent",
    ),
    ("django", _W, "Sehrbazın addımları"): (
        "Wizard steps",
        "Шаги мастера",
        "Sihirbaz adımları",
        "Schritte des Assistenten",
    ),
    ("django", _W, "Qruplar"): ("Groups", "Группы", "Gruplar", "Gruppen"),
    ("django", _W, "Hansı qrupları bölürük"): (
        "Which groups to split",
        "Какие группы делим",
        "Hangi grupları bölüyoruz",
        "Welche Gruppen aufteilen",
    ),
    ("django", _W, "Seminar"): ("Seminar", "Семинар", "Seminer", "Seminar"),
    ("django", _W, "Alt qruplar və tələbələr"): (
        "Subgroups and students",
        "Подгруппы и студенты",
        "Alt gruplar ve öğrenciler",
        "Untergruppen und Studierende",
    ),
    ("django", _W, "Laboratoriya"): ("Laboratory", "Лаборатория", "Laboratuvar", "Labor"),
    ("django", _W, "Lab qrupları və tələbələr"): (
        "Lab groups and students",
        "Лаб. группы и студенты",
        "Laboratuvar grupları ve öğrenciler",
        "Laborgruppen und Studierende",
    ),
    ("django", _W, "Müəllimlər"): ("Teachers", "Преподаватели", "Öğretmenler", "Lehrende"),
    ("django", _W, "Hər bölməyə müəllim və saat"): (
        "A teacher and hours for each section",
        "Преподаватель и часы для каждой секции",
        "Her bölüme öğretmen ve saat",
        "Lehrende und Stunden je Abschnitt",
    ),
    ("django", _W, "Yoxla"): ("Review", "Проверка", "Kontrol", "Prüfen"),
    ("django", _W, "Xülasə və təsdiq"): (
        "Summary and confirmation",
        "Итог и подтверждение",
        "Özet ve onay",
        "Zusammenfassung und Bestätigung",
    ),
    (
        "django",
        _W,
        "«Təsdiqlə» basılana qədər heç nə yadda saxlanmır — addımlar arasında rahat gedib-gələ bilərsiniz.",
    ): (
        "Nothing is saved until you press “Confirm” — you can move freely between the steps.",
        "Ничего не сохраняется, пока вы не нажмёте «Подтвердить» — между шагами можно свободно переходить.",
        "«Onayla»ya basılana kadar hiçbir şey kaydedilmez — adımlar arasında serbestçe gidip gelebilirsiniz.",
        "Bis Sie „Bestätigen“ drücken, wird nichts gespeichert — Sie können frei zwischen den Schritten wechseln.",
    ),
    ("django", _W, "Bağla"): ("Close", "Закрыть", "Kapat", "Schließen"),
    ("django", _W, "Yüklənir…"): ("Loading…", "Загрузка…", "Yükleniyor…", "Wird geladen…"),
    ("django", _W, "1. Qrupları seçin"): (
        "1. Choose the groups",
        "1. Выберите группы",
        "1. Grupları seçin",
        "1. Gruppen wählen",
    ),
    (
        "django",
        _W,
        "Bölmək istədiyiniz qrupu (və ya bir neçə qrupu) seçin. Reyestrdə alt qrupları (məs. 234 K1, 234 K2) olan qrup "
        "bunu nişanla göstərir.",
    ): (
        "Choose the group (or several groups) to split. A group that has subgroups in the registry (e.g. 234 K1, "
        "234 K2) shows a badge.",
        "Выберите группу (или несколько групп) для деления. Группа с подгруппами в реестре (напр. 234 K1, 234 K2) "
        "отмечена значком.",
        "Bölmek istediğiniz grubu (veya birkaç grubu) seçin. Kayıtta alt grupları olan grup (ör. 234 K1, 234 K2) "
        "bunu bir rozetle gösterir.",
        "Wählen Sie die aufzuteilende Gruppe (oder mehrere). Eine Gruppe mit Untergruppen im Register (z. B. 234 K1, "
        "234 K2) ist markiert.",
    ),
    ("django", _W, "2. Seminar — neçə alt qrup?"): (
        "2. Seminar — how many subgroups?",
        "2. Семинар — сколько подгрупп?",
        "2. Seminer — kaç alt grup?",
        "2. Seminar — wie viele Untergruppen?",
    ),
    (
        "django",
        _W,
        "Hər qrup üçün seminarın neçə alt qrupa bölündüyünü seçin, sonra tələbələri alt qruplara yerləşdirin. Mühazirə "
        "bütün qrupla keçir.",
    ): (
        "For each group choose how many seminar subgroups there are, then place the students. Lectures stay with the "
        "whole group.",
        "Для каждой группы выберите число подгрупп семинара, затем распределите студентов. Лекция идёт для всей группы.",
        "Her grup için seminerin kaç alt gruba bölündüğünü seçin, sonra öğrencileri yerleştirin. Ders tüm grupla yapılır.",
        "Wählen Sie je Gruppe die Zahl der Seminar-Untergruppen und verteilen Sie dann die Studierenden. Die Vorlesung "
        "bleibt bei der ganzen Gruppe.",
    ),
    ("django", _W, "3. Laboratoriya — lab qrupları"): (
        "3. Laboratory — lab groups",
        "3. Лаборатория — лаб. группы",
        "3. Laboratuvar — laboratuvar grupları",
        "3. Labor — Laborgruppen",
    ),
    (
        "django",
        _W,
        "Lab qrupları seminar alt qrupunun içində (hər alt qrup yenə bölünür) və ya ondan asılı olmadan qurula bilər. "
        "Hər tələbə bir lab qrupunda olur.",
    ): (
        "Lab groups can be built inside each seminar subgroup (each subgroup is split again) or independently. Every "
        "student is in exactly one lab group.",
        "Лаб. группы можно создать внутри каждой подгруппы семинара (подгруппа делится ещё раз) или независимо. Каждый "
        "студент — ровно в одной лаб. группе.",
        "Laboratuvar grupları her seminer alt grubunun içinde (alt grup tekrar bölünür) veya ondan bağımsız kurulabilir. "
        "Her öğrenci tek bir laboratuvar grubundadır.",
        "Laborgruppen können innerhalb jeder Seminar-Untergruppe (erneut geteilt) oder unabhängig gebildet werden. Jede "
        "Person ist in genau einer Laborgruppe.",
    ),
    ("django", _W, "4. Müəllimləri təyin edin"): (
        "4. Assign the teachers",
        "4. Назначьте преподавателей",
        "4. Öğretmenleri atayın",
        "4. Lehrende zuweisen",
    ),
    (
        "django",
        _W,
        "Hər sətir bir bölmədir: mühazirə, hər seminar alt qrupu, hər lab qrupu. Müəllim seçin; saat bölmənin planı ilə "
        "doldurulub.",
    ): (
        "Each line is one section: the lecture, every seminar subgroup, every lab group. Choose a teacher; the hours "
        "are pre-filled from the section plan.",
        "Каждая строка — одна секция: лекция, каждая подгруппа семинара, каждая лаб. группа. Выберите преподавателя; "
        "часы заполнены по плану секции.",
        "Her satır bir bölümdür: ders, her seminer alt grubu, her laboratuvar grubu. Öğretmen seçin; saatler bölüm "
        "planından doldurulmuştur.",
        "Jede Zeile ist ein Abschnitt: Vorlesung, jede Seminar-Untergruppe, jede Laborgruppe. Wählen Sie Lehrende; die "
        "Stunden sind aus dem Plan vorbelegt.",
    ),
    ("django", _W, "5. Yoxlayın və təsdiqləyin"): (
        "5. Review and confirm",
        "5. Проверьте и подтвердите",
        "5. Kontrol edin ve onaylayın",
        "5. Prüfen und bestätigen",
    ),
    ("django", _W, "Aşağıda nə yazılacağı görünür. Xəbərdarlıqları düzəldin, sonra «Təsdiqlə» basın."): (
        "Below is what will be saved. Fix the warnings, then press “Confirm”.",
        "Ниже — что будет сохранено. Исправьте предупреждения и нажмите «Подтвердить».",
        "Aşağıda nelerin kaydedileceği görünür. Uyarıları düzeltin, sonra «Onayla»ya basın.",
        "Unten sehen Sie, was gespeichert wird. Beheben Sie die Warnungen und drücken Sie „Bestätigen“.",
    ),
    ("django", _W, "Geri"): ("Back", "Назад", "Geri", "Zurück"),
    ("django", _W, "Növbəti"): ("Next", "Далее", "İleri", "Weiter"),
    ("django", _W, "Təsdiqlə"): ("Confirm", "Подтвердить", "Onayla", "Bestätigen"),
    ("django", _W, "Vakant"): ("Vacant", "Вакансия", "Boş", "Unbesetzt"),
    ("django", _W, "seminar"): ("seminar", "семинар", "seminer", "Seminar"),
    ("django", _W, "laboratoriya"): ("laboratory", "лаборатория", "laboratuvar", "Labor"),
    ("django", _W, "Sətir tapılmadı."): (
        "Row not found.",
        "Строка не найдена.",
        "Satır bulunamadı.",
        "Zeile nicht gefunden.",
    ),
    ("django", _W, "Sətir seçilməyib."): (
        "No row selected.",
        "Строка не выбрана.",
        "Satır seçilmedi.",
        "Keine Zeile gewählt.",
    ),
    ("django", _W, "Sətir bu tapşırığın tədris sətri deyil."): (
        "This row is not a teaching row of this task.",
        "Эта строка не является учебной строкой данного задания.",
        "Bu satır bu görevin ders satırı değil.",
        "Diese Zeile ist keine Lehrzeile dieses Auftrags.",
    ),
    ("django", _W, "Sətirlər eyni fənn və semestrdə olmalıdır."): (
        "The rows must belong to the same subject and semester.",
        "Строки должны относиться к одной дисциплине и семестру.",
        "Satırlar aynı ders ve dönemde olmalıdır.",
        "Die Zeilen müssen zum selben Fach und Semester gehören.",
    ),
    ("django", _W, "Müəllim düzgün seçilməyib."): (
        "The teacher is not selected correctly.",
        "Преподаватель выбран неверно.",
        "Öğretmen doğru seçilmedi.",
        "Die Lehrperson ist nicht korrekt gewählt.",
    ),
    ("django", _W, "Bölmələr dəyişib — sehrbazı bağlayıb yenidən açın."): (
        "The sections have changed — close the wizard and open it again.",
        "Секции изменились — закройте мастер и откройте снова.",
        "Bölümler değişti — sihirbazı kapatıp yeniden açın.",
        "Die Abschnitte haben sich geändert — schließen und öffnen Sie den Assistenten erneut.",
    ),
    ("django", _W, "Saat sıfırdan böyük olmalıdır."): (
        "Hours must be greater than zero.",
        "Часы должны быть больше нуля.",
        "Saat sıfırdan büyük olmalıdır.",
        "Die Stunden müssen größer als null sein.",
    ),
    (
        "django",
        _W,
        "%(groups)s: %(activity)s üçün %(hours)s saat paylanıb, sətrin cəmi isə %(total)s saatdır. «Yoxla» addımında "
        "«Sətri düzəlt» seçin və ya saatı azaldın.",
    ): (
        "%(groups)s: %(hours)s hours are allocated for %(activity)s, but the row total is %(total)s hours. Choose "
        "“Fix the row” in the Review step or reduce the hours.",
        "%(groups)s: на %(activity)s распределено %(hours)s ч, а итог строки — %(total)s ч. Выберите «Исправить "
        "строку» на шаге «Проверка» или уменьшите часы.",
        "%(groups)s: %(activity)s için %(hours)s saat dağıtıldı, satır toplamı ise %(total)s saat. «Kontrol» adımında "
        "«Satırı düzelt»i seçin veya saati azaltın.",
        "%(groups)s: Für %(activity)s sind %(hours)s Stunden verteilt, die Zeilensumme beträgt %(total)s Stunden. "
        "Wählen Sie im Schritt „Prüfen“ „Zeile korrigieren“ oder verringern Sie die Stunden.",
    ),
    ("django", _W, "Bu mərhələdə sətrin cəmini dəyişmək olmur — tədris şöbəsinə müraciət edin."): (
        "The row total cannot be changed at this stage — contact the teaching office.",
        "На этом этапе итог строки менять нельзя — обратитесь в учебный отдел.",
        "Bu aşamada satır toplamı değiştirilemez — eğitim birimine başvurun.",
        "In dieser Phase kann die Zeilensumme nicht geändert werden — wenden Sie sich an das Studienbüro.",
    ),
    ("django", _W, "Mühazirəçini bu sətirdə seçmək olmur."): (
        "The lecturer cannot be chosen on this row.",
        "Лектора на этой строке выбрать нельзя.",
        "Bu satırda dersi veren seçilemez.",
        "Für diese Zeile kann keine Vorlesungsperson gewählt werden.",
    ),
    ("django", _W, "Jurnal tapşırıq dekanlıqda təsdiqlənəndən sonra yaranır — indi yalnız saatı bölmək olar."): (
        "The journal is created after the dean's office approves the task — for now only the hours can be split.",
        "Журнал создаётся после утверждения задания деканатом — пока можно распределить только часы.",
        "Not defteri görev dekanlıkça onaylandıktan sonra oluşur — şimdilik yalnızca saatler bölünebilir.",
        "Das Journal entsteht nach der Freigabe durch das Dekanat — bis dahin können nur die Stunden verteilt werden.",
    ),
    ("django", _R, "Seminar"): ("Seminar", "Семинар", "Seminer", "Seminar"),
    ("django", _R, "Laboratoriya"): ("Laboratory", "Лаборатория", "Laboratuvar", "Labor"),
    ("django", _R, "Jurnal tapılmadı."): (
        "Journal not found.",
        "Журнал не найден.",
        "Not defteri bulunamadı.",
        "Journal nicht gefunden.",
    ),
    ("django", _R, "Bölmə sayı düzgün deyil."): (
        "The number of sections is invalid.",
        "Неверное число секций.",
        "Bölüm sayısı geçersiz.",
        "Die Anzahl der Abschnitte ist ungültig.",
    ),
    ("django", _R, "Bölmə sayı 1–%(max)s arası olmalıdır."): (
        "The number of sections must be between 1 and %(max)s.",
        "Число секций должно быть от 1 до %(max)s.",
        "Bölüm sayısı 1 ile %(max)s arasında olmalıdır.",
        "Die Anzahl der Abschnitte muss zwischen 1 und %(max)s liegen.",
    ),
    ("django", _R, "%(kind)s: %(n)s tələbə heç bir bölməyə yerləşdirilməyib."): (
        "%(kind)s: %(n)s students are not placed in any section.",
        "%(kind)s: %(n)s студентов не распределены ни в одну секцию.",
        "%(kind)s: %(n)s öğrenci hiçbir bölüme yerleştirilmedi.",
        "%(kind)s: %(n)s Studierende sind keinem Abschnitt zugeordnet.",
    ),
    ("django", _R, "İki bölmənin adı eynidir — adları fərqləndirin."): (
        "Two sections have the same name — make the names different.",
        "У двух секций одинаковое название — измените названия.",
        "İki bölümün adı aynı — adları farklılaştırın.",
        "Zwei Abschnitte heißen gleich — bitte unterschiedlich benennen.",
    ),
    (
        "django",
        _R,
        "%(group)s: «%(section)s» bölməsinə dərs bağlıdır — əvvəlcə həmin dərslərin bölməsini jurnalda dəyişin, sonra "
        "bölmə sayını azaldın.",
    ): (
        "%(group)s: lessons are linked to “%(section)s” — first change those lessons' section in the journal, then "
        "reduce the number of sections.",
        "%(group)s: к секции «%(section)s» привязаны занятия — сначала измените их секцию в журнале, затем уменьшите "
        "число секций.",
        "%(group)s: «%(section)s» bölümüne dersler bağlı — önce not defterinde bu derslerin bölümünü değiştirin, sonra "
        "bölüm sayısını azaltın.",
        "%(group)s: Mit „%(section)s“ sind Stunden verknüpft — ändern Sie zuerst deren Abschnitt im Journal und "
        "verringern Sie dann die Anzahl.",
    ),
    (
        "django",
        _R,
        "%(group)s: «%(section)s» bölməsinə dərs bağlıdır — onun tələbələrini sehrbazda dəyişmək olmaz. Tələbəni "
        "jurnalın öz ekranında köçürün.",
    ): (
        "%(group)s: lessons are linked to “%(section)s” — its students cannot be changed in the wizard. Move the "
        "student on the journal's own screen.",
        "%(group)s: к секции «%(section)s» привязаны занятия — её студентов нельзя менять в мастере. Переведите "
        "студента на экране самого журнала.",
        "%(group)s: «%(section)s» bölümüne dersler bağlı — öğrencileri sihirbazda değiştirilemez. Öğrenciyi not "
        "defterinin kendi ekranında taşıyın.",
        "%(group)s: Mit „%(section)s“ sind Stunden verknüpft — die Studierenden können im Assistenten nicht geändert "
        "werden. Verschieben Sie sie im Journal selbst.",
    ),
    ("django", _R, "«%(lab)s» lab qrupunda iki seminar alt qrupunun tələbəsi var — qarışdırmaq olmaz."): (
        "Lab group “%(lab)s” contains students of two seminar subgroups — they must not be mixed.",
        "В лаб. группе «%(lab)s» студенты двух подгрупп семинара — смешивать нельзя.",
        "«%(lab)s» laboratuvar grubunda iki seminer alt grubunun öğrencisi var — karıştırılamaz.",
        "Laborgruppe „%(lab)s“ enthält Studierende zweier Seminar-Untergruppen — nicht mischen.",
    ),
    ("django", _R, "Bu jurnalın bölmələrini dəyişməyə icazəniz yoxdur."): (
        "You are not allowed to change the sections of this journal.",
        "У вас нет права менять секции этого журнала.",
        "Bu not defterinin bölümlerini değiştirme yetkiniz yok.",
        "Sie dürfen die Abschnitte dieses Journals nicht ändern.",
    ),
    ("django", _R, "Bölgü sehrbazı: seminar alt qrupları və lab qrupları"): (
        "Split wizard: seminar subgroups and lab groups",
        "Мастер распределения: подгруппы семинара и лаб. группы",
        "Bölme sihirbazı: seminer alt grupları ve laboratuvar grupları",
        "Aufteilungsassistent: Seminar-Untergruppen und Laborgruppen",
    ),
    # ── JS (djangojs, kontekstsiz) ────────────────────────────────────────
    ("djangojs", JS, " və "): (" and ", " и ", " ve ", " und "),
    ("djangojs", JS, "%(group)s: %(n)s tələbə yerləşdirilməyib."): (
        "%(group)s: %(n)s students are not placed.",
        "%(group)s: %(n)s студентов не распределены.",
        "%(group)s: %(n)s öğrenci yerleştirilmedi.",
        "%(group)s: %(n)s Studierende sind nicht zugeordnet.",
    ),
    ("djangojs", JS, "%(group)s: iki bölmənin adı eynidir."): (
        "%(group)s: two sections have the same name.",
        "%(group)s: у двух секций одинаковое название.",
        "%(group)s: iki bölümün adı aynı.",
        "%(group)s: Zwei Abschnitte heißen gleich.",
    ),
    ("djangojs", JS, "%(group)s: «%(name)s» bölməsinə dərs bağlıdır."): (
        "%(group)s: lessons are linked to “%(name)s”.",
        "%(group)s: к секции «%(name)s» привязаны занятия.",
        "%(group)s: «%(name)s» bölümüne dersler bağlı.",
        "%(group)s: Mit „%(name)s“ sind Stunden verknüpft.",
    ),
    ("djangojs", JS, "%(groups)s laboratoriyanı birlikdə keçir — bir bölmə, bir müəllim."): (
        "%(groups)s take the lab together — one section, one teacher.",
        "%(groups)s проходят лабораторию вместе — одна секция, один преподаватель.",
        "%(groups)s laboratuvarı birlikte yapar — bir bölüm, bir öğretmen.",
        "%(groups)s haben das Labor gemeinsam — ein Abschnitt, eine Lehrperson.",
    ),
    ("djangojs", JS, "%(groups)s seminarı birlikdə keçir — bir bölmə, bir müəllim."): (
        "%(groups)s take the seminar together — one section, one teacher.",
        "%(groups)s проходят семинар вместе — одна секция, один преподаватель.",
        "%(groups)s semineri birlikte yapar — bir bölüm, bir öğretmen.",
        "%(groups)s haben das Seminar gemeinsam — ein Abschnitt, eine Lehrperson.",
    ),
    ("djangojs", JS, "%(groups)s — seminar və laboratoriya:"): (
        "%(groups)s — seminar and laboratory:",
        "%(groups)s — семинар и лаборатория:",
        "%(groups)s — seminer ve laboratuvar:",
        "%(groups)s — Seminar und Labor:",
    ),
    ("djangojs", JS, "%(groups)s — sətrin saatı bölmələrə uyğun deyil"): (
        "%(groups)s — the row hours do not match the sections",
        "%(groups)s — часы строки не соответствуют секциям",
        "%(groups)s — satır saatleri bölümlerle uyuşmuyor",
        "%(groups)s — die Stunden der Zeile passen nicht zu den Abschnitten",
    ),
    (
        "djangojs",
        JS,
        "%(groups)s: %(kind)s üçün %(used)s paylanıb, sətrin cəmi %(total)s. «Sətri düzəlt» seçin və ya saatı azaldın.",
    ): (
        "%(groups)s: %(used)s allocated for %(kind)s, but the row total is %(total)s. Choose “Fix the row” or reduce the hours.",
        "%(groups)s: на %(kind)s распределено %(used)s, итог строки — %(total)s. Выберите «Исправить строку» или уменьшите часы.",
        "%(groups)s: %(kind)s için %(used)s dağıtıldı, satır toplamı %(total)s. «Satırı düzelt»i seçin veya saati azaltın.",
        "%(groups)s: Für %(kind)s sind %(used)s verteilt, die Zeilensumme ist %(total)s. Wählen Sie „Zeile korrigieren“ oder verringern Sie die Stunden.",
    ),
    ("djangojs", JS, "%(kind)s cəmi: %(old)s → %(new)s"): (
        "%(kind)s total: %(old)s → %(new)s",
        "%(kind)s, итого: %(old)s → %(new)s",
        "%(kind)s toplamı: %(old)s → %(new)s",
        "%(kind)s gesamt: %(old)s → %(new)s",
    ),
    ("djangojs", JS, "%(kind)s — %(group)s (bütün qrup)"): (
        "%(kind)s — %(group)s (whole group)",
        "%(kind)s — %(group)s (вся группа)",
        "%(kind)s — %(group)s (tüm grup)",
        "%(kind)s — %(group)s (ganze Gruppe)",
    ),
    ("djangojs", JS, "%(kind)s — %(groups)s (birlikdə)"): (
        "%(kind)s — %(groups)s (together)",
        "%(kind)s — %(groups)s (вместе)",
        "%(kind)s — %(groups)s (birlikte)",
        "%(kind)s — %(groups)s (gemeinsam)",
    ),
    ("djangojs", JS, "%(list)s ilə bir sətir"): (
        "one row with %(list)s",
        "одна строка с %(list)s",
        "%(list)s ile aynı satır",
        "eine Zeile mit %(list)s",
    ),
    ("djangojs", JS, "%(list)s kimi böl"): (
        "Split as %(list)s",
        "Разделить как %(list)s",
        "%(list)s olarak böl",
        "Aufteilen wie %(list)s",
    ),
    ("djangojs", JS, "%(n)s alt qrup"): ("%(n)s subgroups", "%(n)s подгрупп", "%(n)s alt grup", "%(n)s Untergruppen"),
    ("djangojs", JS, "%(n)s bölməyə müəllim seçilməyib — onların saatı «bölünməyib» qalacaq."): (
        "%(n)s sections have no teacher — their hours will stay “not allocated”.",
        "Для %(n)s секций преподаватель не выбран — их часы останутся «не распределены».",
        "%(n)s bölüme öğretmen seçilmedi — saatleri «dağıtılmadı» olarak kalacak.",
        "%(n)s Abschnitte ohne Lehrperson — ihre Stunden bleiben „nicht verteilt“.",
    ),
    ("djangojs", JS, "%(n)s tələbə (plan)"): (
        "%(n)s students (plan)",
        "%(n)s студентов (план)",
        "%(n)s öğrenci (plan)",
        "%(n)s Studierende (Plan)",
    ),
    ("djangojs", JS, "%(n)s tələbə · seminar planı %(h)s (bir alt qrup üçün)"): (
        "%(n)s students · seminar plan %(h)s (per subgroup)",
        "%(n)s студентов · план семинара %(h)s (на подгруппу)",
        "%(n)s öğrenci · seminer planı %(h)s (alt grup başına)",
        "%(n)s Studierende · Seminarplan %(h)s (je Untergruppe)",
    ),
    ("djangojs", JS, "%(n)s-ci bölmənin adı"): (
        "Name of section %(n)s",
        "Название секции %(n)s",
        "%(n)s. bölümün adı",
        "Name von Abschnitt %(n)s",
    ),
    ("djangojs", JS, "%(name)s başqa seminar alt qrupunun lab qrupundadır."): (
        "%(name)s is in a lab group of another seminar subgroup.",
        "%(name)s находится в лаб. группе другой подгруппы семинара.",
        "%(name)s başka bir seminer alt grubunun laboratuvar grubunda.",
        "%(name)s ist in einer Laborgruppe einer anderen Seminar-Untergruppe.",
    ),
    ("djangojs", JS, "%(unit)s: saat sıfırdan böyük olmalıdır."): (
        "%(unit)s: hours must be greater than zero.",
        "%(unit)s: часы должны быть больше нуля.",
        "%(unit)s: saat sıfırdan büyük olmalıdır.",
        "%(unit)s: Die Stunden müssen größer als null sein.",
    ),
    ("djangojs", JS, "(+%(n)s başqa)"): ("(+%(n)s more)", "(+ещё %(n)s)", "(+%(n)s diğer)", "(+%(n)s weitere)"),
    ("djangojs", JS, "2 alt qrup"): ("2 subgroups", "2 подгруппы", "2 alt grup", "2 Untergruppen"),
    ("djangojs", JS, "3 alt qrup"): ("3 subgroups", "3 подгруппы", "3 alt grup", "3 Untergruppen"),
    ("djangojs", JS, "4 alt qrup"): ("4 subgroups", "4 подгруппы", "4 alt grup", "4 Untergruppen"),
    ("djangojs", JS, "Addım %(n)s / %(total)s"): (
        "Step %(n)s / %(total)s",
        "Шаг %(n)s / %(total)s",
        "Adım %(n)s / %(total)s",
        "Schritt %(n)s / %(total)s",
    ),
    ("djangojs", JS, "Addım-addım: qrupları alt qruplara bölün, tələbələri yerləşdirin, hər bölməyə müəllim verin."): (
        "Step by step: split groups into subgroups, place the students, give each section a teacher.",
        "Пошагово: разделите группы на подгруппы, распределите студентов, назначьте преподавателя каждой секции.",
        "Adım adım: grupları alt gruplara bölün, öğrencileri yerleştirin, her bölüme öğretmen atayın.",
        "Schritt für Schritt: Gruppen aufteilen, Studierende zuordnen, jedem Abschnitt eine Lehrperson geben.",
    ),
    (
        "djangojs",
        JS,
        "Axında keçir: aparıcı «%(groups)s», mühazirəçi — %(teacher)s. Dəyişmək üçün kartda «Axınları dəyiş».",
    ): (
        "Taught in a stream: lead “%(groups)s”, lecturer — %(teacher)s. To change it use “Change streams” on the card.",
        "Читается в потоке: ведущая «%(groups)s», лектор — %(teacher)s. Изменить — «Изменить потоки» на карточке.",
        "Akışta yapılır: öncü «%(groups)s», dersi veren — %(teacher)s. Değiştirmek için kartta «Akışları değiştir».",
        "Im Strom: führend „%(groups)s“, Lehrende(r) — %(teacher)s. Ändern über „Ströme ändern“ auf der Karte.",
    ),
    ("djangojs", JS, "Bir tapşırıq sətrinin qrupları birlikdə seçilir."): (
        "The groups of one task row are selected together.",
        "Группы одной строки задания выбираются вместе.",
        "Bir görev satırının grupları birlikte seçilir.",
        "Die Gruppen einer Auftragszeile werden gemeinsam gewählt.",
    ),
    ("djangojs", JS, "Bu jurnalın bölmələrini dəyişməyə icazəniz yoxdur."): (
        "You are not allowed to change the sections of this journal.",
        "У вас нет права менять секции этого журнала.",
        "Bu not defterinin bölümlerini değiştirme yetkiniz yok.",
        "Sie dürfen die Abschnitte dieses Journals nicht ändern.",
    ),
    ("djangojs", JS, "Bu köhnə bölgülər silinəcək:"): (
        "These old allocations will be removed:",
        "Эти старые распределения будут удалены:",
        "Bu eski dağılımlar silinecek:",
        "Diese alten Zuteilungen werden entfernt:",
    ),
    ("djangojs", JS, "Bu mərhələdə sətrin cəmi dəyişdirilmir — tədris şöbəsinə müraciət edin."): (
        "The row total is not changed at this stage — contact the teaching office.",
        "На этом этапе итог строки не меняется — обратитесь в учебный отдел.",
        "Bu aşamada satır toplamı değiştirilmez — eğitim birimine başvurun.",
        "In dieser Phase wird die Zeilensumme nicht geändert — wenden Sie sich an das Studienbüro.",
    ),
    (
        "djangojs",
        JS,
        "Bu qrupun jurnalı hələ yaradılmayıb. Tələbələri bölmək üçün əvvəlcə jurnalı yaradın — bölgü saatını isə indi də seçə bilərsiniz.",
    ): (
        "This group's journal has not been created yet. Create it first to split the students — the hours can be allocated now.",
        "Журнал этой группы ещё не создан. Чтобы распределить студентов, сначала создайте его — часы можно распределить уже сейчас.",
        "Bu grubun not defteri henüz oluşturulmadı. Öğrencileri bölmek için önce oluşturun — saatleri şimdi de dağıtabilirsiniz.",
        "Das Journal dieser Gruppe existiert noch nicht. Legen Sie es zuerst an, um Studierende aufzuteilen — Stunden können Sie schon jetzt verteilen.",
    ),
    (
        "djangojs",
        JS,
        "Bu qrupun jurnalı hələ yoxdur — tapşırıq dekanlıqda təsdiqlənəndən sonra yaranacaq. İndi yalnız say seçilir, tələbələr sonra bölünür.",
    ): (
        "This group has no journal yet — it will be created after the dean's office approves the task. For now only the number is chosen; students are split later.",
        "У этой группы пока нет журнала — он появится после утверждения задания деканатом. Сейчас выбирается только число, студенты — позже.",
        "Bu grubun henüz not defteri yok — görev dekanlıkça onaylandıktan sonra oluşacak. Şimdi yalnızca sayı seçilir, öğrenciler sonra bölünür.",
        "Diese Gruppe hat noch kein Journal — es entsteht nach der Freigabe durch das Dekanat. Jetzt wird nur die Anzahl gewählt, Studierende später.",
    ),
    ("djangojs", JS, "Bölgü artıq təsdiqlənib — «Təsdiqlə» basanda düzəliş səbəbi və qeydi soruşulacaq."): (
        "The allocation is already approved — pressing “Confirm” will ask for an amendment reason and note.",
        "Распределение уже утверждено — при нажатии «Подтвердить» будут запрошены причина и примечание изменения.",
        "Dağılım zaten onaylandı — «Onayla»ya basınca düzeltme nedeni ve notu sorulacak.",
        "Die Verteilung ist bereits freigegeben — bei „Bestätigen“ werden Änderungsgrund und Notiz abgefragt.",
    ),
    ("djangojs", JS, "— Səbəb seçin —"): ("— Choose a reason —", "— Выберите причину —", "— Neden seçin —", "— Grund wählen —"),
    ("djangojs", JS, "Bölgü artıq təsdiqlənib — dəyişiklik audit jurnalına yazılır. Səbəbi seçin və qısa qeyd yazın."): (
        "The allocation is already approved — the change is written to the audit log. Choose a reason and write a short note.",
        "Распределение уже утверждено — изменение записывается в журнал аудита. Выберите причину и напишите короткое примечание.",
        "Dağılım zaten onaylandı — değişiklik denetim günlüğüne yazılır. Nedeni seçin ve kısa bir not yazın.",
        "Die Verteilung ist bereits freigegeben — die Änderung wird im Prüfprotokoll erfasst. Wählen Sie einen Grund und schreiben Sie eine kurze Notiz.",
    ),
    ("djangojs", JS, "Səbəb"): ("Reason", "Причина", "Neden", "Grund"),
    ("djangojs", JS, "Qeyd"): ("Note", "Примечание", "Not", "Notiz"),
    ("djangojs", JS, "Məsələn: seminar 2 alt qrupa bölündü"): (
        "For example: the seminar was split into 2 subgroups",
        "Например: семинар разделён на 2 подгруппы",
        "Örneğin: seminer 2 alt gruba bölündü",
        "Zum Beispiel: Seminar in 2 Untergruppen geteilt",
    ),
    ("djangojs", JS, "Düzəliş səbəbi və qeydi məcburidir."): (
        "An amendment reason and note are required.",
        "Причина и примечание изменения обязательны.",
        "Düzeltme nedeni ve notu zorunludur.",
        "Änderungsgrund und Notiz sind erforderlich.",
    ),
    ("djangojs", JS, "Bölgü yadda saxlandı."): (
        "Allocation saved.",
        "Распределение сохранено.",
        "Dağılım kaydedildi.",
        "Verteilung gespeichert.",
    ),
    ("djangojs", JS, "Bölmə"): ("Section", "Секция", "Bölüm", "Abschnitt"),
    ("djangojs", JS, "Bölünmür"): ("Not split", "Не делится", "Bölünmüyor", "Nicht geteilt"),
    ("djangojs", JS, "Bütün bölmələrə eyni müəllim"): (
        "Same teacher for all sections",
        "Один преподаватель для всех секций",
        "Tüm bölümlere aynı öğretmen",
        "Gleiche Lehrperson für alle Abschnitte",
    ),
    ("djangojs", JS, "Düzəldiləcək"): ("Will be fixed", "Будет исправлено", "Düzeltilecek", "Wird korrigiert"),
    ("djangojs", JS, "Hamısına:"): ("For all:", "Для всех:", "Hepsine:", "Für alle:"),
    ("djangojs", JS, "Heç bir bölməyə yerləşdirilməyib: %(n)s tələbə."): (
        "Not placed in any section: %(n)s students.",
        "Не распределены ни в одну секцию: %(n)s студентов.",
        "Hiçbir bölüme yerleştirilmedi: %(n)s öğrenci.",
        "Keinem Abschnitt zugeordnet: %(n)s Studierende.",
    ),
    ("djangojs", JS, "Hər qrup ayrıca"): (
        "Each group separately",
        "Каждая группа отдельно",
        "Her grup ayrı",
        "Jede Gruppe einzeln",
    ),
    ("djangojs", JS, "Hər seminar alt qrupunda neçə lab qrupu:"): (
        "Lab groups per seminar subgroup:",
        "Лаб. групп в каждой подгруппе семинара:",
        "Her seminer alt grubunda laboratuvar grubu sayısı:",
        "Laborgruppen je Seminar-Untergruppe:",
    ),
    ("djangojs", JS, "Hər seminar alt qrupunu böl (%(n)s alt qrup)"): (
        "Split each seminar subgroup (%(n)s subgroups)",
        "Делить каждую подгруппу семинара (%(n)s подгрупп)",
        "Her seminer alt grubunu böl (%(n)s alt grup)",
        "Jede Seminar-Untergruppe teilen (%(n)s Untergruppen)",
    ),
    ("djangojs", JS, "Jurnal bağlıdır"): (
        "Journal closed",
        "Журнал закрыт",
        "Not defteri kapalı",
        "Journal geschlossen",
    ),
    ("djangojs", JS, "Jurnal hələ yoxdur"): (
        "No journal yet",
        "Журнала пока нет",
        "Henüz not defteri yok",
        "Noch kein Journal",
    ),
    ("djangojs", JS, "Jurnal yaradılmadı."): (
        "The journal was not created.",
        "Журнал не создан.",
        "Not defteri oluşturulmadı.",
        "Das Journal wurde nicht angelegt.",
    ),
    ("djangojs", JS, "Jurnalda aktiv tələbə yoxdur."): (
        "The journal has no active students.",
        "В журнале нет активных студентов.",
        "Not defterinde aktif öğrenci yok.",
        "Das Journal hat keine aktiven Studierenden.",
    ),
    ("djangojs", JS, "Jurnalı indi yarat"): (
        "Create the journal now",
        "Создать журнал сейчас",
        "Not defterini şimdi oluştur",
        "Journal jetzt anlegen",
    ),
    ("djangojs", JS, "Lab %(h)s"): ("Lab %(h)s", "Лаб. %(h)s", "Laboratuvar %(h)s", "Labor %(h)s"),
    ("djangojs", JS, "Lab qrupu sayı:"): (
        "Number of lab groups:",
        "Число лаб. групп:",
        "Laboratuvar grubu sayısı:",
        "Anzahl der Laborgruppen:",
    ),
    ("djangojs", JS, "Lab qrupu sayı: %(old)s → %(new)s"): (
        "Lab groups: %(old)s → %(new)s",
        "Число лаб. групп: %(old)s → %(new)s",
        "Laboratuvar grubu sayısı: %(old)s → %(new)s",
        "Laborgruppen: %(old)s → %(new)s",
    ),
    ("djangojs", JS, "Lab: %(n)s qrup"): (
        "Lab: %(n)s groups",
        "Лаб.: %(n)s групп",
        "Laboratuvar: %(n)s grup",
        "Labor: %(n)s Gruppen",
    ),
    ("djangojs", JS, "Laboratoriya"): ("Laboratory", "Лаборатория", "Laboratuvar", "Labor"),
    ("djangojs", JS, "Laboratoriya bütün qrupla keçir — bir bölmə, bir müəllim."): (
        "The lab is taught to the whole group — one section, one teacher.",
        "Лаборатория проводится для всей группы — одна секция, один преподаватель.",
        "Laboratuvar tüm grupla yapılır — bir bölüm, bir öğretmen.",
        "Das Labor findet mit der ganzen Gruppe statt — ein Abschnitt, eine Lehrperson.",
    ),
    ("djangojs", JS, "Mühazirə %(h)s"): ("Lecture %(h)s", "Лекция %(h)s", "Ders %(h)s", "Vorlesung %(h)s"),
    ("djangojs", JS, "Mühazirə bir neçə müəllim arasında bölünüb: %(list)s. Dəyişmək üçün «Ətraflı cədvəl»."): (
        "The lecture is split between several teachers: %(list)s. To change it use “Detailed table”.",
        "Лекция разделена между несколькими преподавателями: %(list)s. Изменить — «Подробная таблица».",
        "Ders birkaç öğretmen arasında bölünmüş: %(list)s. Değiştirmek için «Ayrıntılı tablo».",
        "Die Vorlesung ist auf mehrere Lehrende verteilt: %(list)s. Ändern über „Detaillierte Tabelle“.",
    ),
    ("djangojs", JS, "Mühazirə — %(groups)s"): (
        "Lecture — %(groups)s",
        "Лекция — %(groups)s",
        "Ders — %(groups)s",
        "Vorlesung — %(groups)s",
    ),
    ("djangojs", JS, "Mühazirə — %(groups)s (bütün qrup)"): (
        "Lecture — %(groups)s (whole group)",
        "Лекция — %(groups)s (вся группа)",
        "Ders — %(groups)s (tüm grup)",
        "Vorlesung — %(groups)s (ganze Gruppe)",
    ),
    ("djangojs", JS, "Müəllim"): ("Teacher", "Преподаватель", "Öğretmen", "Lehrperson"),
    ("djangojs", JS, "Məlumat yüklənmədi. Səhifəni yeniləyib yenidən cəhd edin."): (
        "The data did not load. Refresh the page and try again.",
        "Данные не загрузились. Обновите страницу и попробуйте снова.",
        "Veriler yüklenmedi. Sayfayı yenileyip tekrar deneyin.",
        "Die Daten wurden nicht geladen. Seite neu laden und erneut versuchen.",
    ),
    ("djangojs", JS, "Qrup/yarımqrup sayı: %(old)s → %(new)s"): (
        "Groups/subgroups: %(old)s → %(new)s",
        "Число групп/подгрупп: %(old)s → %(new)s",
        "Grup/alt grup sayısı: %(old)s → %(new)s",
        "Gruppen/Untergruppen: %(old)s → %(new)s",
    ),
    ("djangojs", JS, "Reyestrdə alt qruplar: %(list)s"): (
        "Registry subgroups: %(list)s",
        "Подгруппы в реестре: %(list)s",
        "Kayıttaki alt gruplar: %(list)s",
        "Untergruppen im Register: %(list)s",
    ),
    ("djangojs", JS, "Saxlanır: %(list)s"): (
        "Kept: %(list)s",
        "Сохраняется: %(list)s",
        "Korunuyor: %(list)s",
        "Beibehalten: %(list)s",
    ),
    ("djangojs", JS, "Seminar"): ("Seminar", "Семинар", "Seminer", "Seminar"),
    ("djangojs", JS, "Seminar %(h)s"): ("Seminar %(h)s", "Семинар %(h)s", "Seminer %(h)s", "Seminar %(h)s"),
    ("djangojs", JS, "Seminar alt qrupundan doldur (əlifba ilə)"): (
        "Fill from the seminar subgroup (alphabetically)",
        "Заполнить из подгруппы семинара (по алфавиту)",
        "Seminer alt grubundan doldur (alfabetik)",
        "Aus der Seminar-Untergruppe füllen (alphabetisch)",
    ),
    ("djangojs", JS, "Seminar bütün qrupla keçir — bir bölmə, bir müəllim."): (
        "The seminar is taught to the whole group — one section, one teacher.",
        "Семинар проводится для всей группы — одна секция, один преподаватель.",
        "Seminer tüm grupla yapılır — bir bölüm, bir öğretmen.",
        "Das Seminar findet mit der ganzen Gruppe statt — ein Abschnitt, eine Lehrperson.",
    ),
    ("djangojs", JS, "Seminar: %(n)s alt qrup"): (
        "Seminar: %(n)s subgroups",
        "Семинар: %(n)s подгрупп",
        "Seminer: %(n)s alt grup",
        "Seminar: %(n)s Untergruppen",
    ),
    ("djangojs", JS, "Seminardan asılı olmadan"): (
        "Independent of the seminar",
        "Независимо от семинара",
        "Seminerden bağımsız",
        "Unabhängig vom Seminar",
    ),
    ("djangojs", JS, "Seçilib: %(n)s qrup"): (
        "Selected: %(n)s groups",
        "Выбрано: %(n)s групп",
        "Seçildi: %(n)s grup",
        "Ausgewählt: %(n)s Gruppen",
    ),
    ("djangojs", JS, "Seçilmiş qruplarda laboratoriya saatı yoxdur — bu addımı keçin."): (
        "The selected groups have no lab hours — skip this step.",
        "У выбранных групп нет лабораторных часов — пропустите этот шаг.",
        "Seçili gruplarda laboratuvar saati yok — bu adımı geçin.",
        "Die gewählten Gruppen haben keine Laborstunden — Schritt überspringen.",
    ),
    ("djangojs", JS, "Seçilmiş qruplarda seminar saatı yoxdur — bu addımı keçin."): (
        "The selected groups have no seminar hours — skip this step.",
        "У выбранных групп нет семинарских часов — пропустите этот шаг.",
        "Seçili gruplarda seminer saati yok — bu adımı geçin.",
        "Die gewählten Gruppen haben keine Seminarstunden — Schritt überspringen.",
    ),
    ("djangojs", JS, "Sətri düzəlt"): ("Fix the row", "Исправить строку", "Satırı düzelt", "Zeile korrigieren"),
    (
        "djangojs",
        JS,
        "Sətrin %(kind)s cəmi %(total)s, bölmələrə görə isə %(need)s lazımdır — «Yoxla» addımında sətri bir kliklə düzəldə bilərsiniz.",
    ): (
        "The row's %(kind)s total is %(total)s, but the sections need %(need)s — you can fix the row with one click in the Review step.",
        "Итог строки (%(kind)s) — %(total)s, а по секциям нужно %(need)s — исправить строку можно одним кликом на шаге «Проверка».",
        "Satırın %(kind)s toplamı %(total)s, bölümlere göre ise %(need)s gerekiyor — «Kontrol» adımında satırı tek tıkla düzeltebilirsiniz.",
        "Die %(kind)s-Summe der Zeile ist %(total)s, die Abschnitte brauchen %(need)s — im Schritt „Prüfen“ mit einem Klick korrigierbar.",
    ),
    ("djangojs", JS, "Tələbə"): ("Students", "Студенты", "Öğrenci", "Studierende"),
    ("djangojs", JS, "Vakant"): ("Vacant", "Вакансия", "Boş", "Unbesetzt"),
    ("djangojs", JS, "Vakant (müəllim sonra)"): (
        "Vacant (teacher later)",
        "Вакансия (преподаватель позже)",
        "Boş (öğretmen sonra)",
        "Unbesetzt (Lehrperson später)",
    ),
    ("djangojs", JS, "Yadda saxlanmadı."): ("Not saved.", "Не сохранено.", "Kaydedilmedi.", "Nicht gespeichert."),
    ("djangojs", JS, "dəyişir"): ("changes", "меняется", "değişiyor", "ändert sich"),
    ("djangojs", JS, "lab planı %(h)s (bir lab qrupu üçün)"): (
        "lab plan %(h)s (per lab group)",
        "план лаб. %(h)s (на лаб. группу)",
        "laboratuvar planı %(h)s (laboratuvar grubu başına)",
        "Laborplan %(h)s (je Laborgruppe)",
    ),
    ("djangojs", JS, "paylanıb %(used)s / cəmi %(total)s"): (
        "allocated %(used)s / total %(total)s",
        "распределено %(used)s / всего %(total)s",
        "dağıtıldı %(used)s / toplam %(total)s",
        "verteilt %(used)s / gesamt %(total)s",
    ),
    (
        "djangojs",
        JS,
        "«%(name)s» bölməsinə %(n)s dərs bağlıdır — bu bölmə silinə bilməz. Əvvəlcə jurnalda həmin dərslərin bölməsini dəyişin.",
    ): (
        "%(n)s lessons are linked to “%(name)s” — this section cannot be removed. First change those lessons' section in the journal.",
        "К секции «%(name)s» привязано занятий: %(n)s — её нельзя удалить. Сначала измените секцию этих занятий в журнале.",
        "«%(name)s» bölümüne %(n)s ders bağlı — bu bölüm silinemez. Önce not defterinde bu derslerin bölümünü değiştirin.",
        "Mit „%(name)s“ sind %(n)s Stunden verknüpft — der Abschnitt kann nicht entfernt werden. Ändern Sie zuerst deren Abschnitt im Journal.",
    ),
    (
        "djangojs",
        JS,
        "«%(name)s» bölməsinə %(n)s dərs bağlıdır — onun tələbələri burada dəyişdirilmir (tələbəni jurnalın öz "
        "ekranında köçürün).",
    ): (
        "%(n)s lessons are linked to “%(name)s” — its students are not changed here (move a student on the journal's "
        "own screen).",
        "К секции «%(name)s» привязано занятий: %(n)s — её студенты здесь не меняются (переводите студента на "
        "экране журнала).",
        "«%(name)s» bölümüne %(n)s ders bağlı — öğrencileri burada değiştirilmez (öğrenciyi not defterinin kendi "
        "ekranında taşıyın).",
        "Mit „%(name)s“ sind %(n)s Stunden verknüpft — die Studierenden werden hier nicht geändert (im Journal selbst "
        "verschieben).",
    ),
    ("djangojs", JS, "Əlifba ilə bərabər böl"): (
        "Split evenly (alphabetical)",
        "Разделить поровну (по алфавиту)",
        "Alfabetik eşit böl",
        "Gleichmäßig teilen (alphabetisch)",
    ),
    ("djangojs", JS, "Ən azı bir qrup seçin."): (
        "Choose at least one group.",
        "Выберите хотя бы одну группу.",
        "En az bir grup seçin.",
        "Wählen Sie mindestens eine Gruppe.",
    ),
    ("djangojs", JS, "Ətraflı cədvəl"): (
        "Detailed table",
        "Подробная таблица",
        "Ayrıntılı tablo",
        "Detaillierte Tabelle",
    ),
    ("djangojs", JS, "Əvvəlcə seminarı alt qruplara bölün."): (
        "First split the seminar into subgroups.",
        "Сначала разделите семинар на подгруппы.",
        "Önce semineri alt gruplara bölün.",
        "Teilen Sie zuerst das Seminar in Untergruppen.",
    ),
    ("djangojs", JS, "— Müəllim seçilməyib —"): (
        "— No teacher chosen —",
        "— Преподаватель не выбран —",
        "— Öğretmen seçilmedi —",
        "— Keine Lehrperson gewählt —",
    ),
    ("djangojs", JS, "— seçilməyib —"): ("— not chosen —", "— не выбран —", "— seçilmedi —", "— nicht gewählt —"),
}


def main():
    for domain in ("django", "djangojs"):
        for lang in LOCALES:
            path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            po = polib.pofile(path)
            existing = {(e.msgctxt, e.msgid) for e in po}
            added = 0
            for (dom, ctx, msgid), (en, ru, tr, de) in STRINGS.items():
                if dom != domain or (ctx, msgid) in existing:
                    continue
                msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
                entry = polib.POEntry(msgid=msgid, msgstr=msgstr, flags=["python-format"] if "%(" in msgid else [])
                if ctx:
                    entry.msgctxt = ctx
                po.append(entry)
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()
