#!/usr/bin/env python3
"""EMSArena i18n — «Əmək müqavilələri» (2026-10-19): HR bölməsi «Əmək müqavilələri», işçinin «Müqavilələrim»
bölməsi, bitmə xatırlatmaları / «müqavilə göndərildi» / «işçi təsdiqlədi» bildirişləri, `hr.contracts_*` açarları,
«Sistem tənzimləmələri» → «Əmək müqavilələri» qrupu.

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`. ⚠️ `makemessages` İŞLƏDİLMİR.
İstifadə:  python scripts/i18n_fill_hr_contracts_2026_10_19.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

HRC = "hr_contracts"
EMAIL = "hr_contracts.email"
RS = "core.runtime_settings"
PERM = "organizations.permission.label"
SIDEBAR = "profile.sidebar"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    SIDEBAR: {
        "Əmək müqavilələri": t("Employment contracts", "Трудовые договоры", "İş sözleşmeleri", "Arbeitsverträge"),
        "Müqavilələrim": t("My contracts", "Мои договоры", "Sözleşmelerim", "Meine Verträge"),
    },
    PERM: {
        "Əmək müqavilələrinə baxmaq (siyahı, fayl, tarixçə, ixrac)": t(
            "View employment contracts (list, file, history, export)",
            "Просмотр трудовых договоров (список, файл, история, экспорт)",
            "İş sözleşmelerini görüntüleme (liste, dosya, geçmiş, dışa aktarma)",
            "Arbeitsverträge einsehen (Liste, Datei, Verlauf, Export)",
        ),
        "Əmək müqavilələrini idarə etmək (əlavə, yeniləmə, göndərmə, xitam; bitmə xatırlatmaları)": t(
            "Manage employment contracts (add, renew, send, terminate; expiry reminders)",
            "Управление трудовыми договорами (добавление, продление, отправка, расторжение; напоминания об окончании)",
            "İş sözleşmelerini yönetme (ekleme, yenileme, gönderme, fesih; bitiş hatırlatmaları)",
            "Arbeitsverträge verwalten (hinzufügen, verlängern, senden, kündigen; Ablauferinnerungen)",
        ),
    },
    RS: {
        "Əmək müqavilələri": t("Employment contracts", "Трудовые договоры", "İş sözleşmeleri", "Arbeitsverträge"),
        "Bitmə xatırlatmalarının günləri": t(
            "Expiry reminder days",
            "Дни напоминаний об окончании",
            "Bitiş hatırlatma günleri",
            "Tage für Ablauferinnerungen",
        ),
        "Müqavilənin bitməsinə bu qədər gün qalanda işçiyə və Kadrlar şöbəsinə (HR) bildiriş gedir — hər hədd bir "
        "dəfə. Müddəti bitən müqavilə üçün əlavə olaraq bir dəfə «müddəti bitdi» bildirişi göndərilir. Yenilənmiş "
        "və ya xitam verilmiş müqavilələrə xatırlatma getmir.": t(
            "When this many days remain until a contract ends, the employee and the HR department are notified — once "
            "per threshold. An expired contract additionally gets a single “expired” notice. Renewed or terminated "
            "contracts get no reminders.",
            "Когда до окончания договора остаётся столько дней, сотрудник и отдел кадров (HR) получают уведомление — "
            "один раз на каждый порог. Для истёкшего договора дополнительно один раз отправляется уведомление «срок "
            "истёк». Продлённые и расторгнутые договоры напоминаний не получают.",
            "Sözleşmenin bitmesine bu kadar gün kaldığında çalışana ve İnsan Kaynakları birimine (HR) bildirim gider — "
            "her eşik için bir kez. Süresi dolan sözleşme için ayrıca bir kez «süresi doldu» bildirimi gönderilir. "
            "Yenilenen veya feshedilen sözleşmelere hatırlatma gitmez.",
            "Wenn bis zum Vertragsende noch so viele Tage verbleiben, werden die beschäftigte Person und die "
            "Personalabteilung (HR) benachrichtigt — einmal pro Schwelle. Für einen abgelaufenen Vertrag geht "
            "zusätzlich einmal eine Meldung „abgelaufen“ hinaus. Verlängerte oder gekündigte Verträge erhalten keine "
            "Erinnerungen.",
        ),
        "«Bitmək üzrədir» pəncərəsi": t(
            "“Expiring soon” window", "Окно «скоро истекает»", "«Bitmek üzere» aralığı", "Zeitfenster „läuft bald ab“"
        ),
        "HR siyahısında müqavilə bitməsinə bu qədər gün (və ya daha az) qalanda «Bitmək üzrədir» kimi işarələnir və "
        "yuxarıdakı sayğacda göstərilir.": t(
            "In the HR list a contract is marked “Expiring soon” and counted in the tile above when this many days "
            "(or fewer) remain until it ends.",
            "В списке HR договор отмечается как «Скоро истекает» и учитывается в счётчике сверху, когда до его "
            "окончания остаётся столько дней (или меньше).",
            "HR listesinde sözleşmenin bitmesine bu kadar (veya daha az) gün kaldığında «Bitmek üzere» olarak "
            "işaretlenir ve üstteki sayaçta gösterilir.",
            "In der HR-Liste wird ein Vertrag als „läuft bald ab“ markiert und oben gezählt, wenn bis zu seinem Ende "
            "noch so viele Tage (oder weniger) verbleiben.",
        ),
        "Müqavilə bildirişləri e-poçtla da getsin": t(
            "Also send contract notifications by e-mail",
            "Отправлять уведомления о договорах также по e-mail",
            "Sözleşme bildirimleri e-postayla da gönderilsin",
            "Vertragsbenachrichtigungen auch per E-Mail senden",
        ),
        "Yandırılıbsa bitmə xatırlatması, «müqavilə göndərildi» və «işçi təsdiqlədi» bildirişləri kabinetdən əlavə "
        "istifadəçinin e-poçtuna da gedir. Söndürüləndə yalnız kabinet bildirişi qalır.": t(
            "When on, expiry reminders and the “contract sent” and “employee confirmed” notices are also e-mailed to "
            "the user in addition to the cabinet. When off, only the cabinet notification remains.",
            "Если включено, напоминания об окончании и уведомления «договор отправлен» и «сотрудник подтвердил» "
            "приходят не только в кабинет, но и на e-mail пользователя. Если выключено, остаётся только уведомление "
            "в кабинете.",
            "Açıksa bitiş hatırlatmaları ile «sözleşme gönderildi» ve «çalışan onayladı» bildirimleri kabinete ek "
            "olarak kullanıcının e-postasına da gider. Kapalıyken yalnızca kabinet bildirimi kalır.",
            "Wenn aktiviert, gehen Ablauferinnerungen sowie die Meldungen „Vertrag gesendet“ und „Mitarbeiter hat "
            "bestätigt“ zusätzlich zum Kabinett auch per E-Mail an die Person. Wenn deaktiviert, bleibt nur die "
            "Kabinett-Benachrichtigung.",
        ),
    },
    EMAIL: {
        "Hörmətli": t("Dear", "Уважаемый(ая)", "Sayın", "Sehr geehrte/r"),
        "Kabinetə keç": t("Open your cabinet", "Перейти в кабинет", "Kabinete git", "Zum Kabinett"),
    },
    HRC: {
        # ── Növlər / vəziyyətlər / hadisələr ──────────────────────────────────
        "Müddətli": t("Fixed-term", "Срочный", "Belirli süreli", "Befristet"),
        "Müddətsiz": t("Indefinite", "Бессрочный", "Belirsiz süreli", "Unbefristet"),
        "Əvəzçilik": t("Secondary employment", "Совместительство", "Ek görev (yarı zamanlı)", "Nebentätigkeit"),
        "Saathesabı": t("Hourly", "Почасовой", "Saat ücretli", "Stundenbasis"),
        "Digər": t("Other", "Другое", "Diğer", "Sonstige"),
        "Qaralama": t("Draft", "Черновик", "Taslak", "Entwurf"),
        "Qüvvədədir": t("In force", "Действует", "Yürürlükte", "In Kraft"),
        "Xitam verilib": t("Terminated", "Расторгнут", "Feshedildi", "Gekündigt"),
        "Yenilənib": t("Renewed", "Продлён", "Yenilendi", "Verlängert"),
        "Bitmək üzrədir": t("Expiring soon", "Скоро истекает", "Bitmek üzere", "Läuft bald ab"),
        "Müddəti bitib": t("Expired", "Срок истёк", "Süresi doldu", "Abgelaufen"),
        "Qeydə alındı": t("Registered", "Зарегистрирован", "Kaydedildi", "Erfasst"),
        "Redaktə olundu": t("Edited", "Изменён", "Düzenlendi", "Bearbeitet"),
        "Qüvvəyə mindi": t("Took effect", "Вступил в силу", "Yürürlüğe girdi", "In Kraft getreten"),
        "Fayl yeniləndi": t("File replaced", "Файл заменён", "Dosya değiştirildi", "Datei ersetzt"),
        "İşçiyə göndərildi": t(
            "Sent to employee", "Отправлен сотруднику", "Çalışana gönderildi", "An Mitarbeiter gesendet"
        ),
        "İşçi təsdiqlədi": t(
            "Employee confirmed", "Сотрудник подтвердил", "Çalışan onayladı", "Mitarbeiter hat bestätigt"
        ),
        "Bitmə xatırlatması göndərildi": t(
            "Expiry reminder sent",
            "Отправлено напоминание об окончании",
            "Bitiş hatırlatması gönderildi",
            "Ablauferinnerung gesendet",
        ),
        "Müddəti bitdi bildirişi göndərildi": t(
            "Expiry notice sent",
            "Отправлено уведомление об истечении срока",
            "Süre doldu bildirimi gönderildi",
            "Ablaufmeldung gesendet",
        ),
        "Xitam verildi": t("Terminated", "Договор расторгнут", "Fesih yapıldı", "Kündigung erfasst"),
        "Yeni müqavilə ilə yeniləndi": t(
            "Renewed by a new contract",
            "Продлён новым договором",
            "Yeni sözleşmeyle yenilendi",
            "Durch neuen Vertrag verlängert",
        ),
        # ── HR paneli ─────────────────────────────────────────────────────────
        "Bu bölmə Kadrlar şöbəsi (HR) üçündür — əmək müqavilələrinə baxmaq icazəniz yoxdur.": t(
            "This section is for the HR department — you are not allowed to view employment contracts.",
            "Этот раздел предназначен для отдела кадров (HR) — у вас нет права просматривать трудовые договоры.",
            "Bu bölüm İnsan Kaynakları (HR) içindir — iş sözleşmelerini görüntüleme yetkiniz yok.",
            "Dieser Bereich ist für die Personalabteilung (HR) — Sie dürfen keine Arbeitsverträge einsehen.",
        ),
        "Əməl yerinə yetirilmədi — icazənizi yoxlayın və ya səhifəni yeniləyin.": t(
            "The action failed — check your permission or reload the page.",
            "Действие не выполнено — проверьте права доступа или обновите страницу.",
            "İşlem yapılamadı — yetkinizi kontrol edin veya sayfayı yenileyin.",
            "Aktion fehlgeschlagen — prüfen Sie Ihre Berechtigung oder laden Sie die Seite neu.",
        ),
        "Əməl yerinə yetirilmədi — səhifəni yeniləyib yenidən cəhd edin.": t(
            "The action failed — reload the page and try again.",
            "Действие не выполнено — обновите страницу и попробуйте ещё раз.",
            "İşlem yapılamadı — sayfayı yenileyip tekrar deneyin.",
            "Aktion fehlgeschlagen — laden Sie die Seite neu und versuchen Sie es erneut.",
        ),
        "Bütün əməkdaşların (müəllim, inzibati və texniki heyət) əmək müqavilələri: müddət, sənəd, göndərilmə və "
        "işçinin təsdiqi. Bitməsinə az qalan müqavilələr üçün HR və işçiyə avtomatik bildiriş gedir.": t(
            "Employment contracts of all staff (teaching, administrative and technical): term, document, sending and "
            "the employee's confirmation. HR and the employee are notified automatically when a contract is about to "
            "end.",
            "Трудовые договоры всех сотрудников (преподаватели, административный и технический персонал): срок, "
            "документ, отправка и подтверждение сотрудника. О скором окончании договора HR и сотрудник уведомляются "
            "автоматически.",
            "Tüm çalışanların (öğretim, idari ve teknik personel) iş sözleşmeleri: süre, belge, gönderim ve çalışanın "
            "onayı. Bitmesine az kalan sözleşmeler için HR ve çalışana otomatik bildirim gider.",
            "Arbeitsverträge aller Beschäftigten (Lehr-, Verwaltungs- und technisches Personal): Laufzeit, Dokument, "
            "Versand und Bestätigung. HR und die beschäftigte Person werden automatisch benachrichtigt, wenn ein "
            "Vertrag bald endet.",
        ),
        "Baxış rejimi: dəyişiklik etmək və ixrac bağlıdır.": t(
            "View mode: changes and export are disabled.",
            "Режим просмотра: изменения и экспорт недоступны.",
            "Görüntüleme modu: değişiklik ve dışa aktarma kapalı.",
            "Ansichtsmodus: Änderungen und Export sind gesperrt.",
        ),
        "Nəticə: %(n)s": t("Results: %(n)s", "Результатов: %(n)s", "Sonuç: %(n)s", "Ergebnisse: %(n)s"),
        "İşçi": t("Employee", "Сотрудник", "Çalışan", "Mitarbeiter/in"),
        "Müqavilə": t("Contract", "Договор", "Sözleşme", "Vertrag"),
        "Müddət": t("Term", "Срок", "Süre", "Laufzeit"),
        "Qalan": t("Left", "Осталось", "Kalan", "Verbleibend"),
        "Vəziyyət": t("Status", "Состояние", "Durum", "Status"),
        "Göndərilmə": t("Sending", "Отправка", "Gönderim", "Versand"),
        "Əməllər": t("Actions", "Действия", "İşlemler", "Aktionen"),
        "Səhifələmə": t("Pagination", "Пагинация", "Sayfalama", "Seitennavigation"),
        "Əvvəlki səhifə": t("Previous page", "Предыдущая страница", "Önceki sayfa", "Vorherige Seite"),
        "Növbəti səhifə": t("Next page", "Следующая страница", "Sonraki sayfa", "Nächste Seite"),
        "Bu filtrə uyğun müqavilə yoxdur.": t(
            "No contracts match this filter.",
            "Нет договоров по этому фильтру.",
            "Bu filtreye uygun sözleşme yok.",
            "Keine Verträge für diesen Filter.",
        ),
        "«Müqavilə əlavə et» düyməsi ilə ilk müqaviləni qeydə alın.": t(
            "Register the first contract with the “Add contract” button.",
            "Зарегистрируйте первый договор кнопкой «Добавить договор».",
            "İlk sözleşmeyi «Sözleşme ekle» düğmesiyle kaydedin.",
            "Erfassen Sie den ersten Vertrag mit der Schaltfläche „Vertrag hinzufügen“.",
        ),
        "Müqavilə əlavə et": t("Add contract", "Добавить договор", "Sözleşme ekle", "Vertrag hinzufügen"),
        "Excel ixracı": t("Excel export", "Экспорт в Excel", "Excel dışa aktarımı", "Excel-Export"),
        "ştat": t("staff rate", "ставка", "kadro", "Stellenanteil"),
        "saat/həftə": t("h/week", "ч/нед.", "saat/hafta", "Std./Woche"),
        "Fayl": t("File", "Файл", "Dosya", "Datei"),
        "müddətsiz": t("indefinite", "бессрочно", "süresiz", "unbefristet"),
        "Sınaq:": t("Probation:", "Испытательный срок:", "Deneme:", "Probezeit:"),
        "%(n)s gün keçib": t(
            "%(n)s days overdue", "просрочен на %(n)s дн.", "%(n)s gün geçti", "seit %(n)s Tagen abgelaufen"
        ),
        "bu gün bitir": t("ends today", "истекает сегодня", "bugün bitiyor", "endet heute"),
        "%(n)s gün": t("%(n)s days", "%(n)s дн.", "%(n)s gün kaldı", "%(n)s Tage"),
        "Yeni:": t("New:", "Новый:", "Yeni sözleşme:", "Neu:"),
        "Təsdiqlənib": t("Confirmed", "Подтверждён", "Onaylandı", "Bestätigt"),
        "Təsdiq gözləyir": t(
            "Awaiting confirmation", "Ожидает подтверждения", "Onay bekliyor", "Wartet auf Bestätigung"
        ),
        "Göndərilib:": t("Sent:", "Отправлен:", "Gönderildi:", "Gesendet:"),
        "Göndərilməyib": t("Not sent", "Не отправлен", "Gönderilmedi", "Nicht gesendet"),
        "Yenidən göndərildi": t("Sent again", "Отправлен повторно", "Yeniden gönderildi", "Erneut gesendet"),
        "Müqavilə göndərildi": t("Contract sent", "Договор отправлен", "Sözleşme gönderildi", "Vertrag gesendet"),
        "Redaktə": t("Edit", "Изменить", "Düzenle", "Bearbeiten"),
        "Yenilə": t("Renew", "Продлить", "Yenile", "Verlängern"),
        "Tarixçə": t("History", "История", "Geçmiş", "Verlauf"),
        "Xitam": t("Terminate", "Расторгнуть", "Feshet", "Kündigen"),
        # ── Dialoqlar ─────────────────────────────────────────────────────────
        "Yadda saxla": t("Save", "Сохранить", "Kaydet", "Speichern"),
        "Müqavilə işçiyə göndərildi": t(
            "Contract sent to the employee",
            "Договор отправлен сотруднику",
            "Sözleşme çalışana gönderildi",
            "Vertrag an Mitarbeiter gesendet",
        ),
        "Müqaviləni işçinin e-poçtuna göndərdiyinizi qeyd edin — işçiyə sistemə daxil olub təsdiqləməsi üçün "
        "bildiriş gedəcək.": t(
            "Record that you e-mailed the contract to the employee — they will be notified to sign in and confirm it.",
            "Отметьте, что вы отправили договор на e-mail сотрудника, — он получит уведомление войти в систему и "
            "подтвердить его.",
            "Sözleşmeyi çalışanın e-postasına gönderdiğinizi kaydedin — çalışana sisteme girip onaylaması için "
            "bildirim gidecek.",
            "Vermerken Sie, dass Sie den Vertrag per E-Mail gesendet haben — die Person wird benachrichtigt, sich "
            "anzumelden und ihn zu bestätigen.",
        ),
        "Qeyd et və bildir": t(
            "Record and notify", "Отметить и уведомить", "Kaydet ve bildir", "Vermerken und benachrichtigen"
        ),
        "Müqaviləyə xitam ver": t("Terminate contract", "Расторгнуть договор", "Sözleşmeyi feshet", "Vertrag kündigen"),
        "Xitam geri alınmır: müqavilə bağlanır, xatırlatmalar dayanır, səbəb tarixçədə qalır.": t(
            "Termination cannot be undone: the contract is closed, reminders stop and the reason stays in the history.",
            "Расторжение необратимо: договор закрывается, напоминания прекращаются, причина остаётся в истории.",
            "Fesih geri alınamaz: sözleşme kapanır, hatırlatmalar durur, gerekçe geçmişte kalır.",
            "Die Kündigung ist endgültig: Der Vertrag wird geschlossen, Erinnerungen enden, der Grund bleibt im Verlauf.",
        ),
        "Xitam ver": t("Terminate", "Расторгнуть", "Feshet", "Kündigen"),
        "Xitamın səbəbi": t("Reason for termination", "Причина расторжения", "Fesih gerekçesi", "Kündigungsgrund"),
        "Səbəb ən azı %(n)s simvol olmalıdır.": t(
            "The reason must be at least %(n)s characters.",
            "Причина должна содержать не менее %(n)s символов.",
            "Gerekçe en az %(n)s karakter olmalıdır.",
            "Der Grund muss mindestens %(n)s Zeichen lang sein.",
        ),
        "İşçi bildirişdə belə mətn görəcək: «Yeni əmək müqaviləniz e-poçtunuza göndərilib. Sistemə daxil olub "
        "tanış olduğunuzu təsdiqləyin.»": t(
            "The employee will see: “Your new employment contract has been sent to your e-mail. Sign in to the "
            "system and confirm that you have read it.”",
            "Сотрудник увидит: «Ваш новый трудовой договор отправлен на ваш e-mail. Войдите в систему и "
            "подтвердите, что ознакомились с ним.»",
            "Çalışan bildirimde şunu görecek: «Yeni iş sözleşmeniz e-postanıza gönderildi. Sisteme girip okuduğunuzu "
            "onaylayın.»",
            "Die Person sieht: „Ihr neuer Arbeitsvertrag wurde an Ihre E-Mail gesendet. Melden Sie sich an und "
            "bestätigen Sie, dass Sie ihn gelesen haben.“",
        ),
        "İşçiyə qeyd": t("Note to the employee", "Примечание для сотрудника", "Çalışana not", "Hinweis an Mitarbeiter"),
        "(istəyə bağlı)": t("(optional)", "(необязательно)", "(isteğe bağlı)", "(optional)"),
        "Məs.: yeni müqavilə 1 noyabrdan qüvvəyə minir.": t(
            "E.g.: the new contract takes effect on 1 November.",
            "Напр.: новый договор вступает в силу с 1 ноября.",
            "Örn.: yeni sözleşme 1 Kasım'dan itibaren yürürlüğe girer.",
            "Z. B.: Der neue Vertrag gilt ab dem 1. November.",
        ),
        "Xitam tarixi": t("Termination date", "Дата расторжения", "Fesih tarihi", "Kündigungsdatum"),
        "Yeni müqavilə əvvəlkinin davamı kimi qeydə alınır: köhnə müqavilə «Yenilənib» statusuna keçir və onun üçün "
        "xatırlatmalar dayanır.": t(
            "The new contract is registered as a continuation of the previous one: the old contract becomes “Renewed” "
            "and its reminders stop.",
            "Новый договор регистрируется как продолжение предыдущего: старый получает статус «Продлён», напоминания "
            "по нему прекращаются.",
            "Yeni sözleşme öncekinin devamı olarak kaydedilir: eski sözleşme «Yenilendi» durumuna geçer ve onun "
            "hatırlatmaları durur.",
            "Der neue Vertrag wird als Fortsetzung des vorherigen erfasst: Der alte erhält den Status „Verlängert“, "
            "seine Erinnerungen enden.",
        ),
        "Ad, soyad və ya istifadəçi adı": t(
            "First name, last name or username",
            "Имя, фамилия или логин",
            "Ad, soyad veya kullanıcı adı",
            "Vorname, Nachname oder Benutzername",
        ),
        "Yalnız aktiv əməkdaşlar (müəllim, inzibati və texniki heyət) — tələbələr siyahıda yoxdur.": t(
            "Active staff only (teaching, administrative and technical) — students are not listed.",
            "Только действующие сотрудники (преподаватели, административный и технический персонал) — студентов "
            "в списке нет.",
            "Yalnızca aktif çalışanlar (öğretim, idari ve teknik personel) — öğrenciler listede yok.",
            "Nur aktive Beschäftigte (Lehr-, Verwaltungs- und technisches Personal) — Studierende sind nicht "
            "aufgeführt.",
        ),
        "Müqavilə №": t("Contract No.", "№ договора", "Sözleşme No.", "Vertrags-Nr."),
        "Növ": t("Type", "Вид", "Tür", "Art"),
        "Vəzifə": t("Position", "Должность", "Pozisyon", "Position"),
        "Məs.: baş müəllim, mühasib, laborant": t(
            "E.g.: senior lecturer, accountant, lab assistant",
            "Напр.: старший преподаватель, бухгалтер, лаборант",
            "Örn.: kıdemli öğretim görevlisi, muhasebeci, laborant",
            "Z. B.: Oberassistent, Buchhalter, Laborant",
        ),
        "Bölmə": t("Unit", "Подразделение", "Birim", "Einheit"),
        "Axtar…": t("Search…", "Поиск…", "Ara…", "Suchen…"),
        "Uyğun bölmə yoxdur": t(
            "No matching unit", "Нет подходящего подразделения", "Uygun birim yok", "Keine passende Einheit"
        ),
        "— İşçinin əsas bölməsi —": t(
            "— Employee's primary unit —",
            "— Основное подразделение сотрудника —",
            "— Çalışanın ana birimi —",
            "— Haupteinheit der Person —",
        ),
        "Boş qalsa işçinin əsas üzvlüyündəki bölmə götürülür. Xatırlatmalar bu bölməni əhatə edən HR əməkdaşlarına "
        "gedir.": t(
            "If left empty, the unit of the employee's primary membership is used. Reminders go to HR staff whose "
            "scope covers this unit.",
            "Если оставить пустым, берётся подразделение основного членства сотрудника. Напоминания получают "
            "сотрудники HR, чья зона охватывает это подразделение.",
            "Boş bırakılırsa çalışanın ana üyeliğindeki birim alınır. Hatırlatmalar bu birimi kapsayan HR "
            "çalışanlarına gider.",
            "Leer gelassen, wird die Einheit der Hauptmitgliedschaft verwendet. Erinnerungen gehen an HR-Personal, "
            "dessen Zuständigkeit diese Einheit umfasst.",
        ),
        "Başlama tarixi": t("Start date", "Дата начала", "Başlangıç tarihi", "Beginndatum"),
        "Bitmə tarixi": t("End date", "Дата окончания", "Bitiş tarihi", "Enddatum"),
        "Müddətsiz müqavilənin bitmə tarixi olmur.": t(
            "An indefinite contract has no end date.",
            "У бессрочного договора нет даты окончания.",
            "Belirsiz süreli sözleşmenin bitiş tarihi olmaz.",
            "Ein unbefristeter Vertrag hat kein Enddatum.",
        ),
        "Sınaq müddəti bitir": t(
            "Probation ends", "Окончание испытательного срока", "Deneme süresi bitişi", "Probezeit endet"
        ),
        "Həftəlik saat": t("Weekly hours", "Часов в неделю", "Haftalık saat", "Wochenstunden"),
        "Ştat vahidi": t("Staff rate", "Ставка", "Kadro oranı", "Stellenanteil"),
        "Qaralama (hələ qüvvədə deyil)": t(
            "Draft (not in force yet)",
            "Черновик (ещё не действует)",
            "Taslak (henüz yürürlükte değil)",
            "Entwurf (noch nicht in Kraft)",
        ),
        "Müqavilənin faylı": t("Contract file", "Файл договора", "Sözleşme dosyası", "Vertragsdatei"),
        "PDF, JPG və ya PNG · ən çox 10 MB": t(
            "PDF, JPG or PNG · up to 10 MB",
            "PDF, JPG или PNG · не более 10 МБ",
            "PDF, JPG veya PNG · en fazla 10 MB",
            "PDF, JPG oder PNG · max. 10 MB",
        ),
        "Cari fayl:": t("Current file:", "Текущий файл:", "Mevcut dosya:", "Aktuelle Datei:"),
        "yeni fayl seçsəniz əvəz olunacaq": t(
            "it will be replaced if you choose a new file",
            "будет заменён, если выбрать новый файл",
            "yeni dosya seçerseniz değiştirilecek",
            "wird ersetzt, wenn Sie eine neue Datei wählen",
        ),
        "Qeyd": t("Note", "Примечание", "Not", "Notiz"),
        "Müqaviləni redaktə et": t("Edit contract", "Изменить договор", "Sözleşmeyi düzenle", "Vertrag bearbeiten"),
        "Müqaviləni yenilə": t("Renew contract", "Продлить договор", "Sözleşmeyi yenile", "Vertrag verlängern"),
        "İşçini seçin.": t(
            "Select the employee.", "Выберите сотрудника.", "Çalışanı seçin.", "Wählen Sie die Person aus."
        ),
        "Müqavilənin tarixçəsi": t("Contract history", "История договора", "Sözleşme geçmişi", "Vertragsverlauf"),
        "Bağla": t("Close", "Закрыть", "Kapat", "Schließen"),
        "Yüklənir…": t("Loading…", "Загрузка…", "Yükleniyor…", "Wird geladen…"),
        "%(n)s günlük hədd": t("%(n)s-day threshold", "порог %(n)s дн.", "%(n)s günlük eşik", "%(n)s-Tage-Schwelle"),
        "sistem": t("system", "система", "sistem tarafından", "System"),
        "Hadisə yoxdur.": t("No events.", "Событий нет.", "Olay yok.", "Keine Ereignisse."),
        # ── İşçi paneli ───────────────────────────────────────────────────────
        "Kadrlar şöbəsində qeydə alınmış əmək müqavilələriniz: müddət, sənəd və təsdiq.": t(
            "Your employment contracts registered by the HR department: term, document and confirmation.",
            "Ваши трудовые договоры, зарегистрированные отделом кадров: срок, документ и подтверждение.",
            "İnsan Kaynaklarında kayıtlı iş sözleşmeleriniz: süre, belge ve onay.",
            "Ihre von der Personalabteilung erfassten Arbeitsverträge: Laufzeit, Dokument und Bestätigung.",
        ),
        "Yeni müqaviləniz e-poçtunuza göndərilib. Tanış olub təsdiqləyin": t(
            "Your new contract has been sent to your e-mail. Read it and confirm",
            "Ваш новый договор отправлен на ваш e-mail. Ознакомьтесь и подтвердите",
            "Yeni sözleşmeniz e-postanıza gönderildi. Okuyup onaylayın",
            "Ihr neuer Vertrag wurde an Ihre E-Mail gesendet. Lesen und bestätigen Sie ihn",
        ),
        "Müqaviləyə sistemdə bax": t(
            "View the contract in the system",
            "Открыть договор в системе",
            "Sözleşmeyi sistemde görüntüle",
            "Vertrag im System ansehen",
        ),
        "Baxış rejimində təsdiq vermək olmaz.": t(
            "You cannot confirm in view mode.",
            "В режиме просмотра подтверждать нельзя.",
            "Görüntüleme modunda onay verilemez.",
            "Im Ansichtsmodus ist keine Bestätigung möglich.",
        ),
        "Tanış oldum, təsdiqləyirəm": t(
            "I have read it and confirm",
            "Ознакомлен(а), подтверждаю",
            "Okudum, onaylıyorum",
            "Gelesen, ich bestätige",
        ),
        "Təsdiq geri alınmır və Kadrlar şöbəsinə bildirilir.": t(
            "The confirmation cannot be withdrawn and is reported to the HR department.",
            "Подтверждение нельзя отозвать, о нём сообщается в отдел кадров.",
            "Onay geri alınamaz ve İnsan Kaynaklarına bildirilir.",
            "Die Bestätigung kann nicht zurückgenommen werden und wird der Personalabteilung gemeldet.",
        ),
        "Cari müqavilə": t("Current contract", "Текущий договор", "Geçerli sözleşme", "Aktueller Vertrag"),
        "gün əvvəl bitib": t("days ago it ended", "дн. назад истёк", "gün önce bitti", "Tage seit Ablauf"),
        "gün qalıb": t("days left", "дн. осталось", "gün kaldı", "Tage verbleibend"),
        "Sınaq müddəti": t("Probation period", "Испытательный срок", "Deneme süresi", "Probezeit"),
        "Təsdiqləmisiniz": t("You confirmed", "Вы подтвердили", "Onayladınız", "Von Ihnen bestätigt"),
        "Müqaviləni aç": t("Open contract", "Открыть договор", "Sözleşmeyi aç", "Vertrag öffnen"),
        "Digər müqavilələr": t("Other contracts", "Другие договоры", "Diğer sözleşmeler", "Weitere Verträge"),
        "Sizin üçün qeydə alınmış əmək müqaviləsi yoxdur.": t(
            "No employment contract is registered for you.",
            "Для вас не зарегистрировано трудовых договоров.",
            "Sizin için kayıtlı iş sözleşmesi yok.",
            "Für Sie ist kein Arbeitsvertrag erfasst.",
        ),
        "Müqaviləniz sistemə əlavə olunanda burada görünəcək.": t(
            "It will appear here once your contract is added to the system.",
            "Договор появится здесь после добавления в систему.",
            "Sözleşmeniz sisteme eklendiğinde burada görünecek.",
            "Ihr Vertrag erscheint hier, sobald er im System erfasst ist.",
        ),
        # ── Şəxs səhifəsi ─────────────────────────────────────────────────────
        "Əmək müqaviləsi": t("Employment contract", "Трудовой договор", "İş sözleşmesi", "Arbeitsvertrag"),
        "Qeydə alınmış müqavilə yoxdur.": t(
            "No contract registered.", "Договоры не зарегистрированы.", "Kayıtlı sözleşme yok.", "Kein Vertrag erfasst."
        ),
        "Bütün müqavilələr": t("All contracts", "Все договоры", "Tüm sözleşmeler", "Alle Verträge"),
        # ── Filtr / KPI / ixrac ───────────────────────────────────────────────
        "Qüvvədə": t("In force", "Действуют", "Yürürlükte olan", "In Kraft"),
        "{n} gün ərzində bitir": t(
            "Ending within {n} days", "Истекают в течение {n} дн.", "{n} gün içinde bitiyor", "Enden in {n} Tagen"
        ),
        "30 gün ərzində bitir": t(
            "Ending within 30 days", "Истекают в течение 30 дн.", "30 gün içinde bitiyor", "Enden in 30 Tagen"
        ),
        "60 gün ərzində bitir": t(
            "Ending within 60 days", "Истекают в течение 60 дн.", "60 gün içinde bitiyor", "Enden in 60 Tagen"
        ),
        "90 gün ərzində bitir": t(
            "Ending within 90 days", "Истекают в течение 90 дн.", "90 gün içinde bitiyor", "Enden in 90 Tagen"
        ),
        "Axtarış": t("Search", "Поиск", "Arama", "Suche"),
        "Ad, soyad, vəzifə və ya müqavilə №": t(
            "Name, surname, position or contract No.",
            "Имя, фамилия, должность или № договора",
            "Ad, soyad, pozisyon veya sözleşme No.",
            "Name, Nachname, Position oder Vertrags-Nr.",
        ),
        "Bütün bölmələr": t("All units", "Все подразделения", "Tüm birimler", "Alle Einheiten"),
        "Bütün növlər": t("All types", "Все виды", "Tüm türler", "Alle Arten"),
        "Bütün vəziyyətlər": t("All statuses", "Все состояния", "Tüm durumlar", "Alle Status"),
        "Bitmə müddəti": t("Ends within", "Окончание", "Bitiş süresi", "Endet innerhalb"),
        "İstənilən": t("Any", "Любой", "Herhangi", "Beliebig"),
        "İstifadəçi adı": t("Username", "Логин", "Kullanıcı adı", "Benutzername"),
        "Başlama": t("Start", "Начало", "Başlangıç", "Beginn"),
        "Bitmə": t("End", "Окончание", "Bitiş", "Ende"),
        "Qalan gün": t("Days left", "Осталось дней", "Kalan gün", "Verbleibende Tage"),
        "Ştat": t("Staff rate", "Ставка", "Kadro", "Stellenanteil"),
        "Göndərilib": t("Sent", "Отправлен", "Gönderildi", "Gesendet"),
        "Müqavilələr": t("Contracts", "Договоры", "Sözleşmeler", "Verträge"),
        "Əmək müqavilələri ixracı": t(
            "Employment contracts export",
            "Экспорт трудовых договоров",
            "İş sözleşmeleri dışa aktarımı",
            "Export der Arbeitsverträge",
        ),
        # ── Servis xətaları və cavablar ───────────────────────────────────────
        "Aktiv təşkilat konteksti yoxdur.": t(
            "No active organization context.",
            "Нет контекста активной организации.",
            "Etkin kurum bağlamı yok.",
            "Kein aktiver Organisationskontext.",
        ),
        "Bu əməl üçün icazəniz yoxdur.": t(
            "You are not allowed to do this.",
            "У вас нет права на это действие.",
            "Bu işlem için yetkiniz yok.",
            "Sie sind dazu nicht berechtigt.",
        ),
        "Müqavilə tapılmadı.": t(
            "Contract not found.", "Договор не найден.", "Sözleşme bulunamadı.", "Vertrag nicht gefunden."
        ),
        "Baxış rejimində dəyişiklik etmək olmaz.": t(
            "Changes are not allowed in view mode.",
            "В режиме просмотра изменения запрещены.",
            "Görüntüleme modunda değişiklik yapılamaz.",
            "Im Ansichtsmodus sind Änderungen nicht erlaubt.",
        ),
        "Baxış rejimində ixrac bağlıdır.": t(
            "Export is disabled in view mode.",
            "В режиме просмотра экспорт недоступен.",
            "Görüntüleme modunda dışa aktarma kapalı.",
            "Im Ansichtsmodus ist der Export gesperrt.",
        ),
        "Bu sahə məcburidir.": t(
            "This field is required.", "Это поле обязательно.", "Bu alan zorunludur.", "Pflichtfeld."
        ),
        "Tarix düzgün deyil.": t("Invalid date.", "Неверная дата.", "Geçersiz tarih.", "Ungültiges Datum."),
        "Rəqəm düzgün deyil.": t("Invalid number.", "Неверное число.", "Geçersiz sayı.", "Ungültige Zahl."),
        "Dəyər 0-dan böyük və {max}-dən kiçik olmalıdır.": t(
            "The value must be greater than 0 and not exceed {max}.",
            "Значение должно быть больше 0 и не превышать {max}.",
            "Değer 0'dan büyük ve en fazla {max} olmalıdır.",
            "Der Wert muss größer als 0 und höchstens {max} sein.",
        ),
        "Bölmə tapılmadı.": t(
            "Unit not found.", "Подразделение не найдено.", "Birim bulunamadı.", "Einheit nicht gefunden."
        ),
        "Müqavilə nömrəsini yazın.": t(
            "Enter the contract number.",
            "Укажите номер договора.",
            "Sözleşme numarasını girin.",
            "Geben Sie die Vertragsnummer ein.",
        ),
        "Müqavilə növünü seçin.": t(
            "Select the contract type.",
            "Выберите вид договора.",
            "Sözleşme türünü seçin.",
            "Wählen Sie die Vertragsart.",
        ),
        "Müddətli müqavilədə bitmə tarixi məcburidir.": t(
            "A fixed-term contract requires an end date.",
            "Для срочного договора дата окончания обязательна.",
            "Belirli süreli sözleşmede bitiş tarihi zorunludur.",
            "Ein befristeter Vertrag braucht ein Enddatum.",
        ),
        "Bitmə tarixi başlama tarixindən əvvəl ola bilməz.": t(
            "The end date cannot be before the start date.",
            "Дата окончания не может быть раньше даты начала.",
            "Bitiş tarihi başlangıç tarihinden önce olamaz.",
            "Das Enddatum darf nicht vor dem Beginn liegen.",
        ),
        "Sınaq müddəti müqavilə müddətinin içində olmalıdır.": t(
            "The probation period must fall within the contract term.",
            "Испытательный срок должен быть в пределах срока договора.",
            "Deneme süresi sözleşme süresi içinde olmalıdır.",
            "Die Probezeit muss innerhalb der Vertragslaufzeit liegen.",
        ),
        "Öz əhatənizdəki bölməni seçin.": t(
            "Select a unit within your scope.",
            "Выберите подразделение в пределах вашей зоны.",
            "Kapsamınızdaki birimi seçin.",
            "Wählen Sie eine Einheit in Ihrem Zuständigkeitsbereich.",
        ),
        "Bu bölmə sizin əhatənizdən kənardadır.": t(
            "This unit is outside your scope.",
            "Это подразделение вне вашей зоны.",
            "Bu birim kapsamınızın dışında.",
            "Diese Einheit liegt außerhalb Ihres Bereichs.",
        ),
        "Bu nömrəli müqavilə artıq qeydə alınıb.": t(
            "A contract with this number is already registered.",
            "Договор с таким номером уже зарегистрирован.",
            "Bu numaralı sözleşme zaten kayıtlı.",
            "Ein Vertrag mit dieser Nummer ist bereits erfasst.",
        ),
        "Seçilmiş şəxs bu təşkilatın aktiv əməkdaşı deyil (tələbəyə əmək müqaviləsi bağlanmır).": t(
            "The selected person is not an active staff member of this organization (students cannot have an "
            "employment contract).",
            "Выбранное лицо не является действующим сотрудником этой организации (со студентом трудовой договор не "
            "заключается).",
            "Seçilen kişi bu kurumun aktif çalışanı değil (öğrenciyle iş sözleşmesi yapılmaz).",
            "Die gewählte Person ist keine aktive Beschäftigte dieser Organisation (mit Studierenden wird kein "
            "Arbeitsvertrag geschlossen).",
        ),
        "Bu müqavilə artıq yenilənib və ya xitam verilib.": t(
            "This contract has already been renewed or terminated.",
            "Этот договор уже продлён или расторгнут.",
            "Bu sözleşme zaten yenilendi veya feshedildi.",
            "Dieser Vertrag wurde bereits verlängert oder gekündigt.",
        ),
        "Yeni müqavilə əvvəlkindən sonra başlamalıdır.": t(
            "The new contract must start after the previous one.",
            "Новый договор должен начинаться после предыдущего.",
            "Yeni sözleşme öncekinden sonra başlamalıdır.",
            "Der neue Vertrag muss nach dem vorherigen beginnen.",
        ),
        "Xitam verilmiş və ya yenilənmiş müqavilə redaktə olunmur.": t(
            "A terminated or renewed contract cannot be edited.",
            "Расторгнутый или продлённый договор нельзя изменить.",
            "Feshedilmiş veya yenilenmiş sözleşme düzenlenemez.",
            "Ein gekündigter oder verlängerter Vertrag ist nicht " "bearbeitbar.",
        ),
        "Bu müqavilə artıq bağlanıb.": t(
            "This contract is already closed.",
            "Этот договор уже закрыт.",
            "Bu sözleşme zaten kapandı.",
            "Dieser Vertrag ist bereits geschlossen.",
        ),
        "İşçi bu müqaviləni artıq təsdiqləyib.": t(
            "The employee has already confirmed this contract.",
            "Сотрудник уже подтвердил этот договор.",
            "Çalışan bu sözleşmeyi zaten onayladı.",
            "Die Person hat diesen Vertrag bereits bestätigt.",
        ),
        "Xitamın səbəbini yazın (ən azı {n} simvol).": t(
            "Enter the reason for termination (at least {n} characters).",
            "Укажите причину расторжения (не менее {n} символов).",
            "Fesih gerekçesini yazın (en az {n} karakter).",
            "Geben Sie den Kündigungsgrund an (mindestens {n} Zeichen).",
        ),
        "Xitam tarixi müqavilənin başlanğıcından əvvəl ola bilməz.": t(
            "The termination date cannot be before the contract start.",
            "Дата расторжения не может быть раньше начала договора.",
            "Fesih tarihi sözleşmenin başlangıcından önce olamaz.",
            "Das Kündigungsdatum darf nicht vor Vertragsbeginn liegen.",
        ),
        "Siz bu müqaviləni artıq təsdiqləmisiniz.": t(
            "You have already confirmed this contract.",
            "Вы уже подтвердили этот договор.",
            "Bu sözleşmeyi zaten onayladınız.",
            "Sie haben diesen Vertrag bereits bestätigt.",
        ),
        "Müqavilə qeydə alındı.": t(
            "Contract registered.", "Договор зарегистрирован.", "Sözleşme kaydedildi.", "Vertrag erfasst."
        ),
        "Dəyişikliklər yadda saxlanıldı.": t(
            "Changes saved.", "Изменения сохранены.", "Değişiklikler kaydedildi.", "Änderungen gespeichert."
        ),
        "İşçiyə bildiriş göndərildi.": t(
            "The employee has been notified.",
            "Сотруднику отправлено уведомление.",
            "Çalışana bildirim gönderildi.",
            "Die Person wurde benachrichtigt.",
        ),
        "Müqaviləyə xitam verildi.": t(
            "The contract has been terminated.",
            "Договор расторгнут.",
            "Sözleşme feshedildi.",
            "Der Vertrag wurde gekündigt.",
        ),
        "Təşəkkürlər — təsdiqiniz qeydə alındı.": t(
            "Thank you — your confirmation has been recorded.",
            "Спасибо — ваше подтверждение зарегистрировано.",
            "Teşekkürler — onayınız kaydedildi.",
            "Danke — Ihre Bestätigung wurde gespeichert.",
        ),
        # ── Rəy düzəlişləri (A1–A7, 2026-10-19) ──────────────────────────────
        "Ləğv edilib": t("Discarded", "Аннулирован", "İptal edildi", "Verworfen"),
        "Dəyişdi — yenidən göndərilməlidir": t(
            "Changed — must be sent again",
            "Изменён — нужно отправить повторно",
            "Değişti — yeniden gönderilmeli",
            "Geändert — muss erneut gesendet werden",
        ),
        "Qaralama ləğv edildi": t(
            "Draft discarded", "Черновик аннулирован", "Taslak iptal edildi", "Entwurf verworfen"
        ),
        "Qaralama ləğv edildi.": t(
            "The draft has been discarded.",
            "Черновик аннулирован.",
            "Taslak iptal edildi.",
            "Der Entwurf wurde verworfen.",
        ),
        "Qaralamanı ləğv et": t("Discard draft", "Аннулировать черновик", "Taslağı iptal et", "Entwurf verwerfen"),
        "Ləğv et": t("Discard", "Аннулировать", "İptal et", "Verwerfen"),
        "Qaralama işçiyə heç vaxt göstərilmir; sətir və tarixçə saxlanılır, nömrəni yenidən istifadə etmək olar.": t(
            "The draft is never shown to the employee; the record and its history are kept and the number can be reused.",
            "Черновик никогда не показывается сотруднику; запись и история сохраняются, номер можно использовать снова.",
            "Taslak çalışana hiçbir zaman gösterilmez; kayıt ve geçmiş saklanır, numara yeniden kullanılabilir.",
            "Der Entwurf wird der Person nie angezeigt; Datensatz und Verlauf bleiben, die Nummer ist wiederverwendbar.",
        ),
        "Qaralama «göndərildi» qeyd olunanda avtomatik qüvvəyə minir.": t(
            "A draft takes effect automatically when it is marked as sent.",
            "Черновик автоматически вступает в силу, когда отмечается как отправленный.",
            "Taslak «gönderildi» olarak işaretlendiğinde otomatik olarak yürürlüğe girer.",
            "Ein Entwurf tritt automatisch in Kraft, sobald er als gesendet vermerkt wird.",
        ),
        "Qaralamaya xitam verilmir — «Qaralamanı ləğv et» əməlindən istifadə edin.": t(
            "A draft cannot be terminated — use “Discard draft”.",
            "Черновик нельзя расторгнуть — используйте «Аннулировать черновик».",
            "Taslak feshedilemez — «Taslağı iptal et» işlemini kullanın.",
            "Ein Entwurf kann nicht gekündigt werden — verwenden Sie „Entwurf verwerfen“.",
        ),
        "Yalnız qaralama ləğv edilə bilər.": t(
            "Only a draft can be discarded.",
            "Аннулировать можно только черновик.",
            "Yalnızca taslak iptal edilebilir.",
            "Nur ein Entwurf kann verworfen werden.",
        ),
        "Təsdiqlənmiş müqavilə dəyişdirilə bilməz — «Yenilə» ilə yeni müqavilə yaradın.": t(
            "A confirmed contract cannot be changed — create a new one with “Renew”.",
            "Подтверждённый договор нельзя изменить — создайте новый через «Продлить».",
            "Onaylanmış sözleşme değiştirilemez — «Yenile» ile yeni sözleşme oluşturun.",
            "Ein bestätigter Vertrag kann nicht geändert werden — legen Sie mit „Verlängern“ einen neuen an.",
        ),
        "Təsdiqlənmiş müqavilədə yalnız qeyd dəyişdirilə bilər": t(
            "Only the note can be changed on a confirmed contract",
            "В подтверждённом договоре можно изменить только примечание",
            "Onaylanmış sözleşmede yalnızca not değiştirilebilir",
            "Bei einem bestätigten Vertrag kann nur die Notiz geändert werden",
        ),
        "Məlumat ziddiyyətlidir — səhifəni yeniləyib yenidən cəhd edin.": t(
            "The data conflicts — reload the page and try again.",
            "Данные противоречат друг другу — обновите страницу и попробуйте ещё раз.",
            "Veriler çelişiyor — sayfayı yenileyip tekrar deneyin.",
            "Die Daten widersprechen sich — laden Sie die Seite neu und versuchen Sie es erneut.",
        ),
        "İşçi tapılmadı.": t(
            "Employee not found.", "Сотрудник не найден.", "Çalışan bulunamadı.", "Person nicht gefunden."
        ),
        "bitmə tarixi": t("end date", "дата окончания", "bitiş tarihi", "Enddatum"),
        # ── Bildirişlər ───────────────────────────────────────────────────────
        "Yeni əmək müqaviləniz göndərildi": t(
            "Your new employment contract has been sent",
            "Ваш новый трудовой договор отправлен",
            "Yeni iş sözleşmeniz gönderildi",
            "Ihr neuer Arbeitsvertrag wurde gesendet",
        ),
        "Yeni əmək müqaviləniz e-poçtunuza göndərilib. Sistemə daxil olub tanış olduğunuzu təsdiqləyin.": t(
            "Your new employment contract has been sent to your e-mail. Sign in to the system and confirm that you "
            "have read it.",
            "Ваш новый трудовой договор отправлен на ваш e-mail. Войдите в систему и подтвердите, что ознакомились "
            "с ним.",
            "Yeni iş sözleşmeniz e-postanıza gönderildi. Sisteme girip okuduğunuzu onaylayın.",
            "Ihr neuer Arbeitsvertrag wurde an Ihre E-Mail gesendet. Melden Sie sich an und bestätigen Sie, dass Sie "
            "ihn gelesen haben.",
        ),
        "Müqavilə № {number} · {position}": t(
            "Contract No. {number} · {position}",
            "Договор № {number} · {position}",
            "Sözleşme No. {number} · {position}",
            "Vertrag Nr. {number} · {position}",
        ),
        "Müqavilə təsdiqləndi: {name}": t(
            "Contract confirmed: {name}",
            "Договор подтверждён: {name}",
            "Sözleşme onaylandı: {name}",
            "Vertrag bestätigt: {name}",
        ),
        "{name} № {number} əmək müqaviləsi ilə tanış olduğunu təsdiqlədi.": t(
            "{name} confirmed having read employment contract No. {number}.",
            "{name} подтвердил(а) ознакомление с трудовым договором № {number}.",
            "{name}, {number} numaralı iş sözleşmesini okuduğunu onayladı.",
            "{name} hat die Kenntnisnahme des Arbeitsvertrags Nr. {number} bestätigt.",
        ),
        "bitməsinə {days} gün qalıb": t(
            "ends in {days} days", "истекает через {days} дн.", "bitmesine {days} gün kaldı", "endet in {days} Tagen"
        ),
        "Əmək müqavilənizin müddəti bitir": t(
            "Your employment contract is ending",
            "Срок вашего трудового договора истекает",
            "İş sözleşmenizin süresi doluyor",
            "Ihr Arbeitsvertrag läuft aus",
        ),
        "№ {number} əmək müqavilənizin {when} (bitmə tarixi: {end}). Ətraflı məlumat üçün Kadrlar şöbəsinə "
        "müraciət edin.": t(
            "Your employment contract No. {number}: {when} (end date: {end}). Contact the HR department for details.",
            "Ваш трудовой договор № {number}: {when} (дата окончания: {end}). За подробностями обратитесь в отдел "
            "кадров.",
            "{number} numaralı iş sözleşmeniz: {when} (bitiş tarihi: {end}). Ayrıntılar için İnsan Kaynaklarına "
            "başvurun.",
            "Ihr Arbeitsvertrag Nr. {number}: {when} (Enddatum: {end}). Wenden Sie sich für Details an die "
            "Personalabteilung.",
        ),
        "Müqavilə müddəti bitir: {name}": t(
            "Contract ending: {name}",
            "Срок договора истекает: {name}",
            "Sözleşme süresi doluyor: {name}",
            "Vertrag läuft aus: {name}",
        ),
        "{name} — «{position}», № {number}: {when} (bitmə tarixi: {end}).": t(
            "{name} — “{position}”, No. {number}: {when} (end date: {end}).",
            "{name} — «{position}», № {number}: {when} (дата окончания: {end}).",
            "{name} — «{position}», No. {number}: {when} (bitiş tarihi: {end}).",
            "{name} — „{position}“, Nr. {number}: {when} (Enddatum: {end}).",
        ),
        "Əmək müqavilənizin müddəti bitdi": t(
            "Your employment contract has expired",
            "Срок вашего трудового договора истёк",
            "İş sözleşmenizin süresi doldu",
            "Ihr Arbeitsvertrag ist abgelaufen",
        ),
        "№ {number} əmək müqavilənizin müddəti {end} tarixində bitib. Kadrlar şöbəsinə müraciət edin.": t(
            "Your employment contract No. {number} expired on {end}. Please contact the HR department.",
            "Срок вашего трудового договора № {number} истёк {end}. Обратитесь в отдел кадров.",
            "{number} numaralı iş sözleşmenizin süresi {end} tarihinde doldu. İnsan Kaynaklarına başvurun.",
            "Ihr Arbeitsvertrag Nr. {number} ist am {end} abgelaufen. Bitte wenden Sie sich an die Personalabteilung.",
        ),
        "Müqavilənin müddəti bitdi: {name}": t(
            "Contract expired: {name}",
            "Срок договора истёк: {name}",
            "Sözleşmenin süresi doldu: {name}",
            "Vertrag abgelaufen: {name}",
        ),
        "{name} — «{position}», № {number}: müddəti {end} tarixində bitib, yenilənməyib.": t(
            "{name} — “{position}”, No. {number}: expired on {end} and has not been renewed.",
            "{name} — «{position}», № {number}: срок истёк {end}, договор не продлён.",
            "{name} — «{position}», No. {number}: süresi {end} tarihinde doldu, yenilenmedi.",
            "{name} — „{position}“, Nr. {number}: am {end} abgelaufen, nicht verlängert.",
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
