#!/usr/bin/env python3
"""EMSArena i18n — imtahan zalı giriş / gözləmə otağı redizaynı (sahib 2026-10-21).

Yeni sətirlər: gözləmə otağında «Tələbə» sahəsi və «Səhifəni bağlamayın …» təlimatı
(apps/exams/templates/exams/student/final_waiting.html); sərt zal rejiminin xəbərdarlıq səhifəsi
(hall_computer_blocked.html, views/student/_final_device.py) və «Sistem tənzimləmələri»ndə açarın yeni izahı
(core/runtime_settings_exam_center.py). Qalan bütün mətnlər mövcud msgid-lərdir.
msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

WAITING = "exams.template.final_waiting"
HALL = "exams.final_center.hall_computer"
RS = "core.runtime_settings"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


AZ_OVERRIDES = {}

ENTRIES = {
    WAITING: {
        "Tələbə": t("Student", "Студент", "Öğrenci", "Studierende"),
        "Səhifəni bağlamayın — nəzarətçi imtahanı başladanda imtahan avtomatik açılacaq.": t(
            "Do not close this page — the exam opens automatically when the invigilator starts it.",
            "Не закрывайте страницу — экзамен откроется автоматически, когда наблюдатель его начнёт.",
            "Bu sayfayı kapatmayın — gözetmen sınavı başlattığında sınav otomatik olarak açılacaktır.",
            "Schließen Sie diese Seite nicht — die Prüfung öffnet sich automatisch, sobald die Aufsicht sie startet.",
        ),
    },
    HALL: {
        "Bu kompüter imtahan zalı kompüteri kimi qeydiyyatdan keçməyib. Final və midterm imtahanlarına yalnız "
        "imtahan zalındakı qeydiyyatlı kompüterlərdən daxil olmaq olar.": t(
            "This computer is not registered as an exam hall computer. Final and midterm exams can only be "
            "entered from the registered computers in the exam hall.",
            "Этот компьютер не зарегистрирован как компьютер экзаменационного зала. Войти на итоговый и "
            "промежуточный экзамены можно только с зарегистрированных компьютеров экзаменационного зала.",
            "Bu bilgisayar sınav salonu bilgisayarı olarak kayıtlı değil. Final ve ara sınavlara yalnızca sınav "
            "salonundaki kayıtlı bilgisayarlardan girilebilir.",
            "Dieser Computer ist nicht als Prüfungssaal-Computer registriert. Abschluss- und Zwischenprüfungen "
            "können nur über die registrierten Computer im Prüfungssaal aufgerufen werden.",
        ),
        "Qeydiyyatsız kompüter": t(
            "Unregistered computer",
            "Незарегистрированный компьютер",
            "Kayıtsız bilgisayar",
            "Nicht registrierter Computer",
        ),
        "Bu kompüterin ünvanı": t(
            "This computer's address",
            "Адрес этого компьютера",
            "Bu bilgisayarın adresi",
            "Adresse dieses Computers",
        ),
        "oxunmadı": t("not detected", "не определён", "okunamadı", "nicht erkannt"),
        "Kompüterin qeydiyyatı üçün bu ünvanı imtahan mərkəzinə və ya zal nəzarətçisinə bildirin.": t(
            "To register the computer, give this address to the exam centre or the hall invigilator.",
            "Чтобы зарегистрировать компьютер, сообщите этот адрес экзаменационному центру или наблюдателю зала.",
            "Bilgisayarın kaydı için bu adresi sınav merkezine veya salon gözetmenine bildirin.",
            "Um den Computer zu registrieren, teilen Sie diese Adresse dem Prüfungszentrum oder der Saalaufsicht mit.",
        ),
    },
    RS: {
        "Yandırılıbsa (defolt) final və midterm səhifələrini YALNIZ imtahan zalının qeydiyyatlı "
        "kompüterləri (MAC ünvanı ARP agenti ilə, əks halda IP) aça bilər; qeydiyyatsız kompüterdə giriş "
        "forması əvəzinə xəbərdarlıq və həmin kompüterin ünvanı göstərilir. Heç bir kompüter qeydiyyatda "
        "deyilsə, heç kim daxil ola bilmir. Söndürüləndə kompüter tələbi YOXDUR — universitet şəbəkəsindəki "
        "istənilən kompüterdən daxil olmaq olar. Universitet şəbəkəsi qaydası, istifadəçi adı + PIN və "
        "cəhdin ilk cihaza bağlanması hər iki halda qalır.": t(
            "When on (default), the final and midterm pages can ONLY be opened from the registered exam hall "
            "computers (MAC address via the ARP agent, otherwise IP); an unregistered computer sees a warning and "
            "its own address instead of the sign-in form. If no computer is registered, nobody can sign in. When "
            "off, there is NO computer requirement — any computer on the university network can be used. The "
            "university network rule, username + PIN and binding the attempt to its first device stay in both "
            "cases.",
            "Если включено (по умолчанию), страницы итогового и промежуточного экзаменов открываются ТОЛЬКО с "
            "зарегистрированных компьютеров экзаменационного зала (MAC-адрес через ARP-агент, иначе IP); на "
            "незарегистрированном компьютере вместо формы входа показываются предупреждение и адрес этого "
            "компьютера. Если ни один компьютер не зарегистрирован, войти не может никто. Если выключено, "
            "требования к компьютеру НЕТ — можно войти с любого компьютера в сети университета. Правило сети "
            "университета, логин + PIN и привязка попытки к первому устройству сохраняются в обоих случаях.",
            "Açıksa (varsayılan) final ve ara sınav sayfaları YALNIZCA sınav salonunun kayıtlı bilgisayarlarından "
            "(ARP ajanı ile MAC adresi, aksi halde IP) açılabilir; kayıtsız bilgisayarda giriş formu yerine uyarı "
            "ve o bilgisayarın adresi gösterilir. Hiçbir bilgisayar kayıtlı değilse kimse giriş yapamaz. "
            "Kapalıysa bilgisayar şartı YOKTUR — üniversite ağındaki herhangi bir bilgisayardan girilebilir. "
            "Üniversite ağı kuralı, kullanıcı adı + PIN ve denemenin ilk cihaza bağlanması her iki durumda da "
            "geçerlidir.",
            "Wenn aktiviert (Standard), können die Seiten der Abschluss- und Zwischenprüfung NUR von den "
            "registrierten Computern des Prüfungssaals geöffnet werden (MAC-Adresse über den ARP-Agenten, sonst "
            "IP); ein nicht registrierter Computer sieht statt des Anmeldeformulars eine Warnung und seine eigene "
            "Adresse. Ist kein Computer registriert, kann sich niemand anmelden. Wenn deaktiviert, gibt es KEINE "
            "Computer-Anforderung — jeder Computer im Universitätsnetz kann verwendet werden. Die Regel für das "
            "Universitätsnetz, Benutzername + PIN und die Bindung des Versuchs an das erste Gerät bleiben in "
            "beiden Fällen bestehen.",
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
