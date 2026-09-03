#!/usr/bin/env python3
"""EMSArena i18n — paylaşılan UI komponent qatının sətirləri (4 dil). İdempotent.

Əhatə (dizayn handoff Mərhələ 0):
  * `ui.status`  — `core/ui/status_catalog.py` etiketləri + «növbəti addım» mətnləri
  * `ui.filters` — filtr panelinin düymə və qeydləri
  * `ui.dialog`  — dialoq / drawer / səbəb dialoqu

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir, mövcud girişə toxunmur.
   Paralel işləyən başqa agent eyni `.po` fayllarını dəyişə bilər; ona görə
   yazma append-only-dir və mövcud (msgctxt, msgid) cütü görünəndə keçilir.

⚠️ MODUL SƏVİYYƏLİ `pgettext_lazy(_CTX, …)` ÇAĞIRIŞI GATE-Ə GÖRÜNMÜR.
   `scripts/i18n_source_scan.py` AST ilə işləyir və kontekst arqumenti dəyişən
   (`_CTX`) olduqda cütü tanımır. `core/ui/*.py` məhz bu formanı işlədir, ona
   görə həmin sətirlər burada AÇIQ sadalanır — əks halda 4 kataloqun heç
   birində olmazdılar və runtime-da tərcüməsiz qalardılar.

İstifadə:  python scripts/i18n_fill_ems_ui.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def _e(en, ru, tr):
    return {"en": en, "ru": ru, "tr": tr}


# ─────────────────────────────────────────────────────────────────────────────
# ui.status — status kataloqu (etiket + «növbəti addım»)
# ─────────────────────────────────────────────────────────────────────────────
STATUS = {
    "Naməlum": _e("Unknown", "Неизвестно", "Bilinmiyor"),
    # Ümumi şkala
    "Qaralama": _e("Draft", "Черновик", "Taslak"),
    "Təsdiq gözləyir": _e("Awaiting approval", "Ожидает утверждения", "Onay bekliyor"),
    "Təsdiqlənib": _e("Approved", "Утверждено", "Onaylandı"),
    "Düzəliş gözləyir": _e("Awaiting revision", "Ожидает доработки", "Düzeltme bekliyor"),
    "Rədd edilib": _e("Rejected", "Отклонено", "Reddedildi"),
    "Kilidlənib": _e("Locked", "Заблокировано", "Kilitlendi"),
    # Sillabus
    "Düzəliş tələb olunur": _e("Revision required", "Требуется доработка", "Düzeltme gerekli"),
    "Təqdim edilib": _e("Submitted", "Отправлено", "Gönderildi"),
    "Baxışdadır": _e("Under review", "На рассмотрении", "İnceleniyor"),
    "Arxivlənib": _e("Archived", "В архиве", "Arşivlendi"),
    "Kafedra qeydlərini nəzərə alıb yenidən göndər": _e(
        "Address the department’s notes and resubmit",
        "Учтите замечания кафедры и отправьте повторно",
        "Bölümün notlarını dikkate alıp yeniden gönderin",
    ),
    "Rədd səbəbini oxuyub yeni versiya yarat": _e(
        "Read the rejection reason and create a new version",
        "Прочитайте причину отклонения и создайте новую версию",
        "Ret gerekçesini okuyup yeni sürüm oluşturun",
    ),
    "Qaralamanı tamamlayıb təsdiqə göndər": _e(
        "Finish the draft and send it for approval",
        "Завершите черновик и отправьте на утверждение",
        "Taslağı tamamlayıp onaya gönderin",
    ),
    "Kafedra müdirinin baxışı gözlənilir": _e(
        "Awaiting the department head’s review",
        "Ожидается рассмотрение заведующим кафедрой",
        "Bölüm başkanının incelemesi bekleniyor",
    ),
    "Baxış nəticəsi gözlənilir": _e(
        "Awaiting the review outcome",
        "Ожидается результат рассмотрения",
        "İnceleme sonucu bekleniyor",
    ),
    "Əməl tələb olunmur — versiya kilidlidir": _e(
        "No action required — the version is locked",
        "Действий не требуется — версия заблокирована",
        "İşlem gerekmiyor — sürüm kilitli",
    ),
    "Arxiv qeydi — yalnız baxış": _e(
        "Archive record — view only", "Архивная запись — только просмотр", "Arşiv kaydı — yalnızca görüntüleme"
    ),
    # Dərs yükü
    "Göndərilib": _e("Sent", "Отправлено", "Gönderildi"),
    "Qaytarılıb": _e("Returned", "Возвращено", "İade edildi"),
    "Gözləyir": _e("Pending", "Ожидает", "Bekliyor"),
    "Baxılıb": _e("Reviewed", "Проверено", "İncelendi"),
    "İradlı": _e("With remarks", "С замечаниями", "İtirazlı"),
    "Normadan az (< 90%)": _e("Below norm (< 90%)", "Ниже нормы (< 90%)", "Normun altında (< %90)"),
    "Normada (90–105%)": _e("Within norm (90–105%)", "В пределах нормы (90–105%)", "Norm içinde (%90–105)"),
    "Norma üstü (105–125%)": _e("Above norm (105–125%)", "Выше нормы (105–125%)", "Normun üstünde (%105–125)"),
    "Kritik yüklü (> 125%)": _e("Critically loaded (> 125%)", "Критическая нагрузка (> 125%)", "Kritik yüklü (> %125)"),
    "normadan az": _e("below norm", "ниже нормы", "normun altında"),
    "normada": _e("within norm", "в норме", "norm içinde"),
    "normadan artıq": _e("above norm", "выше нормы", "normun üstünde"),
    "boş tutum": _e("spare capacity", "свободная ёмкость", "boş kapasite"),
    "yüklü": _e("loaded", "загружено", "dolu"),
    "risk": _e("at risk", "риск", "riskli"),
    "Saat sayı düz deyil": _e("The hour count is wrong", "Количество часов неверно", "Saat sayısı doğru değil"),
    "Qrup/tələbə sayı səhvdir": _e(
        "The group/student count is wrong", "Число групп/студентов неверно", "Grup/öğrenci sayısı hatalı"
    ),
    "Fənn ixtisasım deyil": _e(
        "The course is outside my specialisation",
        "Дисциплина вне моей специализации",
        "Ders uzmanlık alanım değil",
    ),
    "Norma həddindən artıqdır": _e("The norm is exceeded", "Норма превышена", "Norm aşılmış"),
    # Plan və semestr
    "Kafedra baxışı": _e("Department review", "Рассмотрение кафедрой", "Bölüm incelemesi"),
    "Fakültə şurası": _e("Faculty council", "Учёный совет факультета", "Fakülte kurulu"),
    "Tədris şöbəsi": _e("Teaching office", "Учебный отдел", "Öğretim dairesi"),
    "Müəllim gözləyir": _e("Awaiting a teacher", "Ожидает преподавателя", "Öğretmen bekliyor"),
    "Müəllim təyin olunub": _e("Teacher assigned", "Преподаватель назначен", "Öğretmen atandı"),
    "Jurnalı açılıb": _e("Journal opened", "Журнал открыт", "Yoklama defteri açıldı"),
    "Plandan açılış yaradıldı": _e(
        "Offerings created from the plan", "Открытия созданы из плана", "Plandan açılışlar oluşturuldu"
    ),
    "Kafedraya göndərildi": _e("Sent to the department", "Отправлено на кафедру", "Bölüme gönderildi"),
    "Müəllim təyin olundu": _e("Teachers assigned", "Преподаватели назначены", "Öğretmenler atandı"),
    "Jurnal açıldı": _e("Journal opened", "Журнал открыт", "Defter açıldı"),
    "Semestr kilidləndi": _e("Semester locked", "Семестр заблокирован", "Dönem kilitlendi"),
    # Tələbə qəbulu / reyestri
    "Uyğundur": _e("Valid", "Соответствует", "Uygun"),
    "FİN təkrarlanır — eyni şəxs iki sətirdə": _e(
        "Duplicate personal ID — the same person appears twice",
        "Дублируется ИНН — один человек в двух строках",
        "Kimlik numarası tekrar ediyor — aynı kişi iki satırda",
    ),
    "İxtisas kodu universitetdə tapılmadı": _e(
        "The programme code was not found at the university",
        "Код специальности не найден в университете",
        "Program kodu üniversitede bulunamadı",
    ),
    "Attestatın surəti yüklənməyib": _e(
        "The certificate copy has not been uploaded",
        "Копия аттестата не загружена",
        "Diploma kopyası yüklenmedi",
    ),
    "ATİS siyahısı yükləndi": _e("Admission list uploaded", "Список зачисления загружен", "Kayıt listesi yüklendi"),
    "Tədris şöbəsi yoxladı": _e(
        "The teaching office checked it", "Учебный отдел проверил", "Öğretim dairesi kontrol etti"
    ),
    "Fakültələrə paylandı": _e("Distributed to the faculties", "Распределено по факультетам", "Fakültelere dağıtıldı"),
    "Qruplara təyin edildi": _e("Assigned to groups", "Распределено по группам", "Gruplara atandı"),
    "Qrupdan qrupa köçürmə": _e("Transfer between groups", "Перевод из группы в группу", "Gruplar arası nakil"),
    "İxtisasdan ixtisasa köçürmə": _e(
        "Transfer between programmes", "Перевод между специальностями", "Programlar arası nakil"
    ),
    "Əyanidən qiyabiyə (və ya tərsi)": _e(
        "Full-time ↔ part-time change",
        "Смена очной и заочной формы",
        "Örgün ↔ açık öğretim değişikliği",
    ),
    "Akademik məzuniyyət": _e("Academic leave", "Академический отпуск", "Akademik izin"),
    "Bərpa": _e("Reinstatement", "Восстановление", "Yeniden kayıt"),
    "Xaric etmə": _e("Expulsion", "Отчисление", "Kayıt silme"),
    # Jurnal izi
    "Vaxtında yazılıb": _e("Recorded on time", "Записано вовремя", "Zamanında yazıldı"),
    "Gec yazılıb": _e("Recorded late", "Записано с опозданием", "Geç yazıldı"),
    "Jurnal boşdur": _e("The journal is empty", "Журнал пуст", "Defter boş"),
    # Autosave
    "Saxlanıldı": _e("Saved", "Сохранено", "Kaydedildi"),
    "Saxlanılır…": _e("Saving…", "Сохранение…", "Kaydediliyor…"),
    "Son dəyişiklik saxlanılmadı": _e(
        "The last change was not saved", "Последнее изменение не сохранено", "Son değişiklik kaydedilmedi"
    ),
    "İnternet bağlantısı yoxdur": _e(
        "No internet connection", "Нет подключения к интернету", "İnternet bağlantısı yok"
    ),
    "Başqa versiya ilə konflikt yarandı": _e(
        "A conflict with another version occurred",
        "Возник конфликт с другой версией",
        "Başka bir sürümle çakışma oluştu",
    ),
    "Səhifədəki məlumat köhnəlmişdir": _e(
        "The data on this page is out of date",
        "Данные на странице устарели",
        "Sayfadaki veriler güncel değil",
    ),
    # Arxiv rejimi
    "mərhələ açıqdır": _e("the stage is open", "этап открыт", "aşama açık"),
    "arxiv — yalnız oxunuş": _e("archive — read only", "архив — только чтение", "arşiv — salt okunur"),
}

# ─────────────────────────────────────────────────────────────────────────────
# ui.filters / ui.dialog — komponent şablonlarının öz mətnləri
# ─────────────────────────────────────────────────────────────────────────────
FILTERS = {
    "Tətbiq et": _e("Apply", "Применить", "Uygula"),
    "Sıfırla": _e("Reset", "Сбросить", "Temizle"),
    "Tətbiq olunmuş filtrlər": _e("Applied filters", "Применённые фильтры", "Uygulanan filtreler"),
    "%(name)s filtrini götür": _e(
        "Remove the %(name)s filter", "Убрать фильтр «%(name)s»", "%(name)s filtresini kaldır"
    ),
    "Dəyişiklik tətbiq edilməyib — «Tətbiq et» düyməsini basın.": _e(
        "The change has not been applied — press “Apply”.",
        "Изменение не применено — нажмите «Применить».",
        "Değişiklik uygulanmadı — “Uygula” düğmesine basın.",
    ),
}

DIALOG = {
    "Bağla": _e("Close", "Закрыть", "Kapat"),
    "Ləğv et": _e("Cancel", "Отмена", "İptal"),
    "Göndər": _e("Send", "Отправить", "Gönder"),
    "Səbəb": _e("Reason", "Причина", "Gerekçe"),
    "Səbəb audit jurnalına yazılır və qərar zəncirində görünür.": _e(
        "The reason is written to the audit log and shown in the decision chain.",
        "Причина записывается в журнал аудита и видна в цепочке решений.",
        "Gerekçe denetim günlüğüne yazılır ve karar zincirinde görünür.",
    ),
    "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.": _e(
        "The reason must be at least 20 characters — a short note is not enough for the audit.",
        "Причина должна содержать не менее 20 символов — короткой заметки для аудита недостаточно.",
        "Gerekçe en az 20 karakter olmalıdır — kısa bir not denetim için yeterli değildir.",
    ),
}

ENTRIES = {
    "ui.status": STATUS,
    "ui.filters": FILTERS,
    "ui.dialog": DIALOG,
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
