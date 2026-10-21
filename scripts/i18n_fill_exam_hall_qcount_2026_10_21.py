#!/usr/bin/env python3
"""EMSArena i18n — zal kompüteri yoxlaması açarı + kateqoriyaya görə sual sayı (sahib 2026-10-21).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RS = "core.runtime_settings"
FORM_HELP = "exams.form.exam.help"
ENTRY = "exams.final_center.entry"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


AZ_OVERRIDES = {}

ENTRIES = {
    RS: {
        "Zal kompüteri yoxlaması (MAC/IP)": t(
            "Exam hall computer check (MAC/IP)",
            "Проверка компьютера экзаменационного зала (MAC/IP)",
            "Sınav salonu bilgisayar kontrolü (MAC/IP)",
            "Prüfungssaal-Computerprüfung (MAC/IP)",
        ),
        "Yandırılıbsa (defolt) final və midterm girişində zal kompüteri yoxlanır: harada konfiqurasiya "
        "olunubsa qeydli zal kompüterləri, ARP agenti ilə MAC ünvanı və IP siyahısı tələb olunur. "
        "Söndürüləndə kompüter/MAC/IP tələbi YOXDUR — tələbə universitet şəbəkəsindəki istənilən "
        "kompüterdən daxil ola bilər. Universitet şəbəkəsi qaydası, istifadəçi adı + PIN və cəhdin ilk "
        "cihaza bağlanması hər iki halda qalır.": t(
            "When on (default), the exam hall computer is checked at final and midterm entry: wherever "
            "configured, registered hall computers, the MAC address via the ARP agent and the IP list are "
            "required. When off, there is NO computer/MAC/IP requirement — the student can sign in from any "
            "computer on the university network. The university network rule, username + PIN and binding the "
            "attempt to its first device stay in both cases.",
            "Если включено (по умолчанию), при входе на итоговый и промежуточный экзамен проверяется компьютер "
            "зала: там, где это настроено, требуются зарегистрированные компьютеры зала, MAC-адрес через "
            "ARP-агент и список IP. Если выключено, требования к компьютеру/MAC/IP НЕТ — студент может войти с "
            "любого компьютера в сети университета. Правило сети университета, логин + PIN и привязка попытки "
            "к первому устройству сохраняются в обоих случаях.",
            "Açıksa (varsayılan) final ve ara sınav girişinde salon bilgisayarı kontrol edilir: yapılandırıldığı "
            "yerlerde kayıtlı salon bilgisayarları, ARP ajanı ile MAC adresi ve IP listesi gerekir. Kapalıysa "
            "bilgisayar/MAC/IP şartı YOKTUR — öğrenci üniversite ağındaki herhangi bir bilgisayardan giriş "
            "yapabilir. Üniversite ağı kuralı, kullanıcı adı + PIN ve denemenin ilk cihaza bağlanması her iki "
            "durumda da geçerlidir.",
            "Wenn aktiviert (Standard), wird beim Zugang zur Abschluss- und Zwischenprüfung der Saalcomputer "
            "geprüft: Wo konfiguriert, sind registrierte Saalcomputer, die MAC-Adresse über den ARP-Agenten "
            "und die IP-Liste erforderlich. Wenn deaktiviert, gibt es KEINE Computer-/MAC-/IP-Anforderung — "
            "Studierende können sich von jedem Computer im Universitätsnetz anmelden. Die Regel für das "
            "Universitätsnetz, Benutzername + PIN und die Bindung des Versuchs an das erste Gerät bleiben in "
            "beiden Fällen bestehen.",
        ),
        "Final imtahanında sual sayı": t(
            "Number of questions in the final exam",
            "Количество вопросов на итоговом экзамене",
            "Final sınavındaki soru sayısı",
            "Anzahl der Fragen in der Abschlussprüfung",
        ),
        "Yeni imtahanda «Final» kateqoriyası seçiləndə sual sayı avtomatik bu dəyərə qoyulur. "
        "Müəllif sayı əl ilə dəyişə bilər; mövcud imtahanların sayı dəyişmir.": t(
            "When the «Final» category is chosen for a new exam, the number of questions is set to this value "
            "automatically. The author can change it by hand; existing exams keep their count.",
            "При выборе категории «Итоговый» для нового экзамена количество вопросов автоматически "
            "устанавливается на это значение. Автор может изменить его вручную; у существующих экзаменов "
            "количество не меняется.",
            "Yeni sınavda «Final» kategorisi seçildiğinde soru sayısı otomatik olarak bu değere ayarlanır. "
            "Yazar sayıyı elle değiştirebilir; mevcut sınavların sayısı değişmez.",
            "Wird für eine neue Prüfung die Kategorie «Final» gewählt, wird die Fragenanzahl automatisch auf "
            "diesen Wert gesetzt. Die Autorin bzw. der Autor kann sie manuell ändern; bestehende Prüfungen "
            "behalten ihre Anzahl.",
        ),
        "Midterm imtahanında sual sayı": t(
            "Number of questions in the midterm exam",
            "Количество вопросов на промежуточном экзамене",
            "Ara sınavdaki soru sayısı",
            "Anzahl der Fragen in der Zwischenprüfung",
        ),
        "Yeni imtahanda «Midterm» kateqoriyası seçiləndə sual sayı avtomatik bu dəyərə qoyulur. "
        "Müəllif sayı əl ilə dəyişə bilər; mövcud imtahanların sayı dəyişmir.": t(
            "When the «Midterm» category is chosen for a new exam, the number of questions is set to this value "
            "automatically. The author can change it by hand; existing exams keep their count.",
            "При выборе категории «Промежуточный» для нового экзамена количество вопросов автоматически "
            "устанавливается на это значение. Автор может изменить его вручную; у существующих экзаменов "
            "количество не меняется.",
            "Yeni sınavda «Ara sınav» kategorisi seçildiğinde soru sayısı otomatik olarak bu değere ayarlanır. "
            "Yazar sayıyı elle değiştirebilir; mevcut sınavların sayısı değişmez.",
            "Wird für eine neue Prüfung die Kategorie «Zwischenprüfung» gewählt, wird die Fragenanzahl "
            "automatisch auf diesen Wert gesetzt. Die Autorin bzw. der Autor kann sie manuell ändern; "
            "bestehende Prüfungen behalten ihre Anzahl.",
        ),
        "sual": t("questions", "вопросов", "soru", "Fragen"),
    },
    FORM_HELP: {
        "Midterm üçün %(count)s sual (Sistem tənzimləmələri)": t(
            "%(count)s questions for a midterm (System settings)",
            "%(count)s вопросов для промежуточного экзамена (Системные настройки)",
            "Ara sınav için %(count)s soru (Sistem ayarları)",
            "%(count)s Fragen für eine Zwischenprüfung (Systemeinstellungen)",
        ),
        "Final üçün %(count)s sual (Sistem tənzimləmələri)": t(
            "%(count)s questions for a final (System settings)",
            "%(count)s вопросов для итогового экзамена (Системные настройки)",
            "Final için %(count)s soru (Sistem ayarları)",
            "%(count)s Fragen für eine Abschlussprüfung (Systemeinstellungen)",
        ),
    },
    ENTRY: {
        "Zal müəyyən edilmədi — imtahan zalının nəzarətçisinə müraciət edin.": t(
            "The exam hall could not be determined — please contact the hall invigilator.",
            "Не удалось определить экзаменационный зал — обратитесь к наблюдателю зала.",
            "Sınav salonu belirlenemedi — lütfen salon gözetmenine başvurun.",
            "Der Prüfungssaal konnte nicht ermittelt werden — bitte wenden Sie sich an die Saalaufsicht.",
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
            if lang == "az":
                msgstr = AZ_OVERRIDES.get((ctx, msgid), msgid)
            else:
                msgstr = translations.get(lang) or msgid
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
