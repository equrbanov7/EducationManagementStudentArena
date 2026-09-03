#!/usr/bin/env python3
"""EMSArena i18n — «Fənn təhvili» bölməsinin sətirləri (4 dil). İdempotent.

Yeni bölmənin (teaching-handover) bütün UI mətnləri, bloker/xəta etiketləri,
sidebar adı, `journal.reassign` icazə etiketi, jurnaldakı yalnız-oxu zolağı və
model meta adları doldurulur.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silə bilir) — skript
yalnız ƏLAVƏ edir və mövcud girişə toxunmur.

⚠️ ŞABLON DIRNAQ TƏLƏSİ. Şablonlarda `{% trans "X" context "Y" %}` və
`{% trans 'X' context 'Y' %}` — HƏR İKİ forma işlənir. Buradakı ENTRIES xəritəsi
mətnləri AÇIQ sadaladığı üçün dırnaq forması nəticəyə TƏSİR ETMİR; yoxlama
(`probe`) isə .po-nun öz formatındadır (həmişə cüt dırnaq). 2026-08-30-da 286
mətnin tərcüməsiz qalmasının səbəbi məhz tək-dırnaqlı formanın skan olunmaması
idi — ona görə bu skript skan yox, açıq siyahı işlədir.

İstifadə:  python scripts/i18n_fill_teaching_handover.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    # ── İcazə etiketi (permission-editor + RİM «səlahiyyətləriniz» paneli) ──
    "organizations.permission.label": {
        "Fənni başqa müəllimə təhvil vermək": {
            "en": "Hand a subject over to another teacher",
            "ru": "Передать предмет другому преподавателю",
            "tr": "Dersi başka bir öğretim elemanına devretme",
        },
    },
    # ── Sidebar ─────────────────────────────────────────────────────────────
    "profile.sidebar": {
        "Fənn təhvili": {"en": "Subject handover", "ru": "Передача предмета", "tr": "Ders devri"},
    },
    # ── Jurnal səhifəsindəki yalnız-oxu zolağı ──────────────────────────────
    "registrar.handover": {
        (
            "Bu fənn başqa müəllimə təhvil verilib — jurnal sizin üçün yalnız-oxu rejimindədir. "
            "Yazdığınız bal və davamiyyət olduğu kimi qalır."
        ): {
            "en": (
                "This subject has been handed over to another teacher — the journal is read-only for you. "
                "The marks and attendance you recorded stay exactly as they are."
            ),
            "ru": (
                "Этот предмет передан другому преподавателю — журнал доступен вам только для чтения. "
                "Выставленные вами баллы и посещаемость сохраняются без изменений."
            ),
            "tr": (
                "Bu ders başka bir öğretim elemanına devredildi — günlük sizin için salt okunur. "
                "Girdiğiniz notlar ve devam kayıtları olduğu gibi kalır."
            ),
        },
    },
    # ── Model meta adları (admin + verbose_name) ────────────────────────────
    # msgid QƏSDƏN AZ-dır: ingilis msgid olsaydı EN tərcüməsi msgid-in eynisi
    # olardı və i18n qapısı bunu «identity borcu» kimi sayardı.
    "registrar.model.handover.meta": {
        "fənn təhvili qeydi": {
            "en": "teaching handover",
            "ru": "передача преподавания",
            "tr": "ders devri kaydı",
        },
        "fənn təhvili qeydləri": {
            "en": "teaching handovers",
            "ru": "передачи преподавания",
            "tr": "ders devri kayıtları",
        },
    },
    # ── Bölmənin öz mətnləri ────────────────────────────────────────────────
    "accounts.handover": {
        # başlıq + çərçivə
        "Fənn təhvili": {"en": "Subject handover", "ru": "Передача предмета", "tr": "Ders devri"},
        "Fənn təhvili bölmələri": {
            "en": "Subject handover sections",
            "ru": "Разделы передачи предмета",
            "tr": "Ders devri bölümleri",
        },
        (
            "Müəllim işdən çıxdıqda və ya dərs yükü dəyişdikdə fənnin elektron jurnalını başqa müəllimə verin. "
            "Yazılmış bal və davamiyyət olduğu kimi qalır — yalnız jurnalın sahibi dəyişir."
        ): {
            "en": (
                "When a teacher leaves or the teaching load changes, hand the subject's electronic journal to "
                "another teacher. Recorded marks and attendance stay untouched — only the journal's owner changes."
            ),
            "ru": (
                "Когда преподаватель уходит или меняется учебная нагрузка, передайте электронный журнал предмета "
                "другому преподавателю. Выставленные баллы и посещаемость не меняются — меняется только владелец "
                "журнала."
            ),
            "tr": (
                "Bir öğretim elemanı ayrıldığında veya ders yükü değiştiğinde dersin elektronik günlüğünü başka "
                "bir öğretim elemanına devredin. Girilen notlar ve devam kayıtları değişmez — yalnızca günlüğün "
                "sahibi değişir."
            ),
        },
        "Səlahiyyət sahəniz": {"en": "Your authority scope", "ru": "Ваша зона полномочий", "tr": "Yetki alanınız"},
        "Bütün universitet": {"en": "Entire university", "ru": "Весь университет", "tr": "Tüm üniversite"},
        "Yalnız öz struktur bölmələriniz": {
            "en": "Only your own structural units",
            "ru": "Только ваши структурные подразделения",
            "tr": "Yalnızca kendi yapısal biriminiz",
        },
        "Fənn təhvili üçün icazəniz yoxdur — bu bölmə yalnız səlahiyyətli rollar üçündür.": {
            "en": "You do not have permission for subject handover — this section is for authorised roles only.",
            "ru": "У вас нет прав на передачу предмета — раздел доступен только уполномоченным ролям.",
            "tr": "Ders devri için yetkiniz yok — bu bölüm yalnızca yetkili roller içindir.",
        },
        # tablar + addımlar
        "Təhvil": {"en": "Handover", "ru": "Передача", "tr": "Devir"},
        "Tarixçə": {"en": "History", "ru": "История", "tr": "Geçmiş"},
        "Hansı müəllimin fənləri?": {
            "en": "Whose subjects?",
            "ru": "Предметы какого преподавателя?",
            "tr": "Hangi öğretim elemanının dersleri?",
        },
        "Boş buraxsanız səlahiyyət sahənizdəki bütün fənlər göstərilir.": {
            "en": "Leave empty to list every subject within your authority scope.",
            "ru": "Оставьте пустым, чтобы показать все предметы в вашей зоне полномочий.",
            "tr": "Boş bırakırsanız yetki alanınızdaki tüm dersler listelenir.",
        },
        "Təhvil veriləcək fənləri seçin": {
            "en": "Select the subjects to hand over",
            "ru": "Выберите предметы для передачи",
            "tr": "Devredilecek dersleri seçin",
        },
        "Yeni müəllimi təyin edin": {
            "en": "Assign the new teacher",
            "ru": "Назначьте нового преподавателя",
            "tr": "Yeni öğretim elemanını atayın",
        },
        (
            "Seçilmiş fənlərin hamısına eyni müəllimi tətbiq edə, yaxud cədvəldə hər sətir üçün ayrıca müəllim "
            "seçə bilərsiniz."
        ): {
            "en": (
                "Apply one teacher to every selected subject, or pick a different teacher for each row in the table."
            ),
            "ru": (
                "Примените одного преподавателя ко всем выбранным предметам или выберите отдельного преподавателя "
                "для каждой строки таблицы."
            ),
            "tr": (
                "Seçili tüm derslere aynı öğretim elemanını uygulayın ya da tablodaki her satır için ayrı bir "
                "öğretim elemanı seçin."
            ),
        },
        # süzgəclər + cədvəl
        "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama"},
        "fənn adı, kodu və ya qrup": {
            "en": "subject name, code or group",
            "ru": "название предмета, код или группа",
            "tr": "ders adı, kodu veya grup",
        },
        "Semestr": {"en": "Semester", "ru": "Семестр", "tr": "Dönem"},
        "Fakültə": {"en": "Faculty", "ru": "Факультет", "tr": "Fakülte"},
        "Kafedra": {"en": "Department", "ru": "Кафедра", "tr": "Bölüm"},
        "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
        "Yalnız təhvil oluna bilənlər": {
            "en": "Only those that can be handed over",
            "ru": "Только те, что можно передать",
            "tr": "Yalnızca devredilebilenler",
        },
        "Səlahiyyət sahənizdəki dərs açılışları": {
            "en": "Course offerings within your authority scope",
            "ru": "Учебные назначения в вашей зоне полномочий",
            "tr": "Yetki alanınızdaki ders açılışları",
        },
        "Hamısını seç": {"en": "Select all", "ru": "Выбрать все", "tr": "Tümünü seç"},
        "Fənn": {"en": "Subject", "ru": "Предмет", "tr": "Ders"},
        "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup"},
        "Təsir": {"en": "Impact", "ru": "Влияние", "tr": "Etki"},
        "Cari müəllim": {"en": "Current teacher", "ru": "Текущий преподаватель", "tr": "Mevcut öğretim elemanı"},
        "Yeni müəllim": {"en": "New teacher", "ru": "Новый преподаватель", "tr": "Yeni öğretim elemanı"},
        "Müəllim təyin edilməyib": {
            "en": "No teacher assigned",
            "ru": "Преподаватель не назначен",
            "tr": "Öğretim elemanı atanmamış",
        },
        "Müəllim seç": {"en": "Choose teacher", "ru": "Выбрать преподавателя", "tr": "Öğretim elemanı seç"},
        "Dəyiş": {"en": "Change", "ru": "Изменить", "tr": "Değiştir"},
        "Təhvil mümkün deyil": {"en": "Handover not possible", "ru": "Передача невозможна", "tr": "Devir mümkün değil"},
        "tələbə": {"en": "students", "ru": "студентов", "tr": "öğrenci"},
        "dərs": {"en": "lessons", "ru": "занятий", "tr": "ders"},
        "bal xanası": {"en": "mark cells", "ru": "ячеек баллов", "tr": "not hücresi"},
        "Bu süzgəclərə uyğun fənn tapılmadı.": {
            "en": "No subject matches these filters.",
            "ru": "Нет предметов, соответствующих этим фильтрам.",
            "tr": "Bu filtrelere uyan ders bulunamadı.",
        },
        "Hələ təhvil qeydi yoxdur.": {
            "en": "No handover records yet.",
            "ru": "Записей о передаче пока нет.",
            "tr": "Henüz devir kaydı yok.",
        },
        "Yüklənir…": {"en": "Loading…", "ru": "Загрузка…", "tr": "Yükleniyor…"},
        # seçicilər
        "Müəllim adı və ya istifadəçi adı": {
            "en": "Teacher name or username",
            "ru": "Имя преподавателя или логин",
            "tr": "Öğretim elemanı adı veya kullanıcı adı",
        },
        "Müəllim axtarın": {
            "en": "Search for a teacher",
            "ru": "Найдите преподавателя",
            "tr": "Öğretim elemanı arayın",
        },
        "Uyğun müəllim tapılmadı.": {
            "en": "No matching teacher found.",
            "ru": "Подходящий преподаватель не найден.",
            "tr": "Eşleşen öğretim elemanı bulunamadı.",
        },
        "Təmizlə": {"en": "Clear", "ru": "Очистить", "tr": "Temizle"},
        "Seçilənlərə tətbiq et": {
            "en": "Apply to selected",
            "ru": "Применить к выбранным",
            "tr": "Seçilenlere uygula",
        },
        # TR-də «Seç» msgid-in eynisi olardı (identity borcu) — daha dəqiq
        # «öğretim elemanını seç» variantı seçilib.
        "Seç": {"en": "Select", "ru": "Выбрать", "tr": "Öğretim elemanını seç"},
        "Yeni müəllim seçin": {
            "en": "Choose the new teacher",
            "ru": "Выберите нового преподавателя",
            "tr": "Yeni öğretim elemanını seçin",
        },
        # əməl zolağı + təsdiq
        "fənn seçilib": {"en": "subject(s) selected", "ru": "предмет(ов) выбрано", "tr": "ders seçildi"},
        "Seçilmiş sətirlərin hamısına yeni müəllim təyin edin.": {
            "en": "Assign a new teacher to every selected row.",
            "ru": "Назначьте нового преподавателя каждой выбранной строке.",
            "tr": "Seçili her satıra yeni bir öğretim elemanı atayın.",
        },
        "Təhvil ver": {"en": "Hand over", "ru": "Передать", "tr": "Devret"},
        "Təhvili təsdiqləyin": {
            "en": "Confirm the handover",
            "ru": "Подтвердите передачу",
            "tr": "Devri onaylayın",
        },
        "Təhvili geri qaytarın": {
            "en": "Revert the handover",
            "ru": "Отменить передачу",
            "tr": "Devri geri alın",
        },
        (
            "Yazılmış bal, davamiyyət və keçmiş dərslərin müəllimi DƏYİŞMİR. Köhnə müəllim jurnalı yalnız-oxu "
            "rejimində görməyə davam edir, amma bal yaza bilməz."
        ): {
            "en": (
                "Recorded marks, attendance and the instructor of past lessons DO NOT change. The previous teacher "
                "keeps read-only access to the journal but can no longer enter marks."
            ),
            "ru": (
                "Выставленные баллы, посещаемость и преподаватель прошедших занятий НЕ меняются. Прежний "
                "преподаватель сохраняет доступ к журналу только для чтения, но больше не может выставлять баллы."
            ),
            "tr": (
                "Girilen notlar, devam kayıtları ve geçmiş derslerin öğretim elemanı DEĞİŞMEZ. Önceki öğretim "
                "elemanı günlüğü salt okunur görmeye devam eder, ancak not giremez."
            ),
        },
        "Səbəb (məcburi)": {"en": "Reason (required)", "ru": "Причина (обязательно)", "tr": "Gerekçe (zorunlu)"},
        "Səbəb": {"en": "Reason", "ru": "Причина", "tr": "Gerekçe"},
        "məs. müəllim işdən çıxdı; dərs yükü yenidən bölündü": {
            "en": "e.g. the teacher left; the teaching load was redistributed",
            "ru": "напр. преподаватель уволился; нагрузка перераспределена",
            "tr": "örn. öğretim elemanı ayrıldı; ders yükü yeniden dağıtıldı",
        },
        "Səbəb çox qısadır.": {
            "en": "The reason is too short.",
            "ru": "Причина слишком короткая.",
            "tr": "Gerekçe çok kısa.",
        },
        "İmtina": {"en": "Cancel", "ru": "Отмена", "tr": "Vazgeç"},
        "Təsdiqlə": {"en": "Confirm", "ru": "Подтвердить", "tr": "Onayla"},
        "Təhvil tamamlandı.": {"en": "Handover completed.", "ru": "Передача завершена.", "tr": "Devir tamamlandı."},
        "Təhvil geri qaytarıldı.": {
            "en": "Handover reverted.",
            "ru": "Передача отменена.",
            "tr": "Devir geri alındı.",
        },
        # tarixçə
        "Kim, nə vaxt, hansı fənni kimdən kimə verib. Səhv təyinat geri qaytarıla bilər.": {
            "en": "Who handed which subject from whom to whom, and when. A wrong assignment can be reverted.",
            "ru": "Кто, когда и какой предмет передал от кого кому. Ошибочное назначение можно отменить.",
            "tr": "Kim, ne zaman, hangi dersi kimden kime devretti. Yanlış atama geri alınabilir.",
        },
        "Tarix": {"en": "Date", "ru": "Дата", "tr": "Tarih"},
        "Kimdən → kimə": {"en": "From → to", "ru": "От → кому", "tr": "Kimden → kime"},
        "Kimdən": {"en": "From", "ru": "От", "tr": "Kimden"},
        "Kimə": {"en": "To", "ru": "Кому", "tr": "Kime"},
        "Əməliyyat": {"en": "Action", "ru": "Действие", "tr": "İşlem"},
        "Geri qaytar": {"en": "Revert", "ru": "Отменить", "tr": "Geri al"},
        "Geri qaytarılıb": {"en": "Reverted", "ru": "Отменено", "tr": "Geri alındı"},
        # səhifələmə
        "Səhifələmə": {"en": "Pagination", "ru": "Постраничная навигация", "tr": "Sayfalama"},
        "Səhifə": {"en": "Page", "ru": "Страница", "tr": "Sayfa"},
        "Əvvəlki": {"en": "Previous", "ru": "Предыдущая", "tr": "Önceki"},
        "Növbəti": {"en": "Next", "ru": "Следующая", "tr": "Sonraki"},
        # blokerlər
        "Bu fənn sizin səlahiyyət sahənizə düşmür": {
            "en": "This subject is outside your authority scope",
            "ru": "Этот предмет вне вашей зоны полномочий",
            "tr": "Bu ders yetki alanınızın dışında",
        },
        "Jurnal bağlanıb — bağlı semestrin müəllimi dəyişdirilmir": {
            "en": "The journal is closed — the teacher of a closed semester is not changed",
            "ru": "Журнал закрыт — преподаватель закрытого семестра не меняется",
            "tr": "Günlük kapatıldı — kapalı dönemin öğretim elemanı değiştirilmez",
        },
        "Semestr başa çatıb — tarixi jurnal toxunulmazdır": {
            "en": "The semester has ended — a historical journal is untouchable",
            "ru": "Семестр завершён — исторический журнал неприкосновенен",
            "tr": "Dönem sona erdi — geçmiş günlük dokunulmazdır",
        },
        "Dərs açılışı aktiv deyil": {
            "en": "The course offering is not active",
            "ru": "Учебное назначение неактивно",
            "tr": "Ders açılışı aktif değil",
        },
        "Fənn onsuz da bu müəllimdədir": {
            "en": "The subject already belongs to this teacher",
            "ru": "Предмет уже закреплён за этим преподавателем",
            "tr": "Ders zaten bu öğretim elemanında",
        },
        "Seçilmiş müəllim bal yazma səlahiyyətinə malik deyil": {
            "en": "The selected teacher has no mark-entry authority",
            "ru": "У выбранного преподавателя нет права выставлять баллы",
            "tr": "Seçilen öğretim elemanının not girme yetkisi yok",
        },
        "Öz fənninizi özünüz təhvil verə bilməzsiniz": {
            "en": "You cannot hand over your own subject yourself",
            "ru": "Вы не можете передать собственный предмет сами",
            "tr": "Kendi dersinizi kendiniz devredemezsiniz",
        },
        "Yeni müəllim seçilməyib": {
            "en": "No new teacher selected",
            "ru": "Новый преподаватель не выбран",
            "tr": "Yeni öğretim elemanı seçilmedi",
        },
        # xəta mesajları (servis kodları)
        "Təhvil üçün səbəb yazılmalıdır.": {
            "en": "A reason must be given for the handover.",
            "ru": "Для передачи необходимо указать причину.",
            "tr": "Devir için bir gerekçe yazılmalıdır.",
        },
        "Heç bir fənn seçilməyib.": {
            "en": "No subject has been selected.",
            "ru": "Не выбран ни один предмет.",
            "tr": "Hiçbir ders seçilmedi.",
        },
        "Bir dəfəyə çox sayda fənn seçilib — seçimi azaldın.": {
            "en": "Too many subjects selected at once — reduce the selection.",
            "ru": "Выбрано слишком много предметов — сократите выбор.",
            "tr": "Aynı anda çok fazla ders seçildi — seçimi azaltın.",
        },
        "Dərs açılışı tapılmadı.": {
            "en": "Course offering not found.",
            "ru": "Учебное назначение не найдено.",
            "tr": "Ders açılışı bulunamadı.",
        },
        "Təhvil qeydi tapılmadı.": {
            "en": "Handover record not found.",
            "ru": "Запись о передаче не найдена.",
            "tr": "Devir kaydı bulunamadı.",
        },
        "Bu təhvil artıq geri qaytarılıb.": {
            "en": "This handover has already been reverted.",
            "ru": "Эта передача уже отменена.",
            "tr": "Bu devir zaten geri alındı.",
        },
        "Fənn təhvildən sonra yenidən başqasına verilib — əvvəlcə sonuncu təhvili geri qaytarın.": {
            "en": "The subject was handed over again afterwards — revert the latest handover first.",
            "ru": "После этого предмет был передан ещё раз — сначала отмените последнюю передачу.",
            "tr": "Ders sonrasında yeniden devredildi — önce en son devri geri alın.",
        },
        "Bu fənnin müəllimi az öncə dəyişdirilib — səhifəni yeniləyin.": {
            "en": "This subject's teacher was changed a moment ago — refresh the page.",
            "ru": "Преподаватель этого предмета только что изменён — обновите страницу.",
            "tr": "Bu dersin öğretim elemanı az önce değiştirildi — sayfayı yenileyin.",
        },
        "Seçilmiş müəllim bal yazma səlahiyyətinə malik deyil.": {
            "en": "The selected teacher has no mark-entry authority.",
            "ru": "У выбранного преподавателя нет права выставлять баллы.",
            "tr": "Seçilen öğretim elemanının not girme yetkisi yok.",
        },
        "Jurnal bağlanıb — əvvəlcə RİM jurnalı açmalıdır.": {
            "en": "The journal is closed — the registry office must reopen it first.",
            "ru": "Журнал закрыт — сначала его должен открыть центр цифрового развития.",
            "tr": "Günlük kapatıldı — önce dijital gelişim merkezi açmalıdır.",
        },
        "Bu əməliyyat üçün icazəniz yoxdur.": {
            "en": "You do not have permission for this operation.",
            "ru": "У вас нет прав на эту операцию.",
            "tr": "Bu işlem için yetkiniz yok.",
        },
        "Naməlum əməliyyat.": {"en": "Unknown operation.", "ru": "Неизвестная операция.", "tr": "Bilinmeyen işlem."},
        "Əməliyyat yerinə yetirilmədi.": {
            "en": "The operation was not completed.",
            "ru": "Операция не выполнена.",
            "tr": "İşlem tamamlanmadı.",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
