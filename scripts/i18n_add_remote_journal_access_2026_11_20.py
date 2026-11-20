#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-20: «Kənardan jurnal girişi» (Sistem tənzimləmələri → kabinetdən şəbəkə istisnası).

Sahib: «sistem tənzimləmələri yerində olsun, ordan mən bunları əlavə edib çıxara bilim». ``django`` kataloquna
(``accounts.remote_journal_access`` + ``profile.section``) beş dildə əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_remote_journal_access_2026_11_20.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_C = "accounts.remote_journal_access"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", "profile.section", "Kənardan jurnal girişi"): (
        "Remote journal access",
        "Доступ к журналу извне",
        "Dışarıdan yoklama defteri erişimi",
        "Journalzugriff von außen",
    ),
    ("django", _C, "Hesab tapılmadı və ya aktiv deyil."): (
        "Account not found or inactive.",
        "Учётная запись не найдена или неактивна.",
        "Hesap bulunamadı veya aktif değil.",
        "Konto nicht gefunden oder inaktiv.",
    ),
    ("django", _C, "Bu hesaba kənardan jurnal girişi verilə bilməz (tələbə və ya üzvlüyü yoxdur)."): (
        "Remote journal access cannot be granted to this account (student or no membership).",
        "Этой учётной записи нельзя дать доступ к журналу извне (студент или нет членства).",
        "Bu hesaba dışarıdan defter erişimi verilemez (öğrenci veya üyeliği yok).",
        "Diesem Konto kann kein Journalzugriff von außen gewährt werden (Studierende oder keine Mitgliedschaft).",
    ),
    ("django", _C, "Bu hesab artıq siyahıdadır."): (
        "This account is already on the list.",
        "Эта учётная запись уже в списке.",
        "Bu hesap zaten listede.",
        "Dieses Konto steht bereits auf der Liste.",
    ),
    ("django", _C, "Bu icazə artıq geri alınıb."): (
        "This access has already been revoked.",
        "Этот доступ уже отозван.",
        "Bu izin zaten geri alındı.",
        "Dieser Zugriff wurde bereits entzogen.",
    ),
    ("django", _C, "Bu əməl yalnız RİM rəhbəri üçündür."): (
        "This action is only for the head of the RIM.",
        "Это действие доступно только руководителю РИМ.",
        "Bu işlem yalnızca RİM başkanı içindir.",
        "Diese Aktion ist nur für die RIM-Leitung.",
    ),
    ("django", _C, "Kənardan jurnal girişi yalnız RİM rəhbəri üçündür."): (
        "Remote journal access is only for the head of the RIM.",
        "Доступ к журналу извне управляется только руководителем РИМ.",
        "Dışarıdan defter erişimi yalnızca RİM başkanı içindir.",
        "Journalzugriff von außen ist nur für die RIM-Leitung.",
    ),
    ("django", _C, "%(name)s universitet şəbəkəsindən kənarda da jurnala girə biləcək. Digər icazələri dəyişmir."): (
        "%(name)s will be able to open the journal outside the university network too. Other permissions stay the same.",
        "%(name)s сможет открывать журнал и вне сети университета. Остальные права не меняются.",
        "%(name)s üniversite ağı dışında da deftere girebilecek. Diğer izinler değişmez.",
        "%(name)s kann das Journal auch außerhalb des Universitätsnetzes öffnen. Andere Rechte bleiben gleich.",
    ),
    ("django", _C, "%(name)s jurnala yalnız universitet şəbəkəsindən girə biləcək."): (
        "%(name)s will be able to open the journal only from the university network.",
        "%(name)s сможет открывать журнал только из сети университета.",
        "%(name)s deftere yalnızca üniversite ağından girebilecek.",
        "%(name)s kann das Journal nur noch aus dem Universitätsnetz öffnen.",
    ),
    ("django", _C, "artıq siyahıdadır"): (
        "already on the list",
        "уже в списке",
        "zaten listede",
        "bereits auf der Liste",
    ),
    ("django", _C, "%(name)s kənardan jurnala girə bilər."): (
        "%(name)s can now open the journal remotely.",
        "%(name)s теперь может открывать журнал извне.",
        "%(name)s artık deftere dışarıdan girebilir.",
        "%(name)s kann das Journal jetzt von außen öffnen.",
    ),
    ("django", _C, "%(name)s üçün kənardan jurnal girişi geri alındı."): (
        "Remote journal access was revoked for %(name)s.",
        "Доступ к журналу извне для %(name)s отозван.",
        "%(name)s için dışarıdan defter erişimi geri alındı.",
        "Journalzugriff von außen für %(name)s wurde entzogen.",
    ),
    ("django", _C, "Naməlum əməl."): (
        "Unknown action.",
        "Неизвестное действие.",
        "Bilinmeyen işlem.",
        "Unbekannte Aktion.",
    ),
    ("django", _C, "Əməl alınmadı. Bir azdan yenidən cəhd edin."): (
        "The action failed. Please try again shortly.",
        "Действие не выполнено. Попробуйте ещё раз чуть позже.",
        "İşlem başarısız oldu. Biraz sonra tekrar deneyin.",
        "Die Aktion ist fehlgeschlagen. Bitte gleich erneut versuchen.",
    ),
    ("django", _C, "Kənardan jurnal girişi verilsin?"): (
        "Grant remote journal access?",
        "Дать доступ к журналу извне?",
        "Dışarıdan defter erişimi verilsin mi?",
        "Journalzugriff von außen gewähren?",
    ),
    ("django", _C, "Əlavə et"): ("Add", "Добавить", "Ekle", "Hinzufügen"),
    ("django", _C, "Kənardan jurnal girişi geri alınsın?"): (
        "Revoke remote journal access?",
        "Отозвать доступ к журналу извне?",
        "Dışarıdan defter erişimi geri alınsın mı?",
        "Journalzugriff von außen entziehen?",
    ),
    ("django", _C, "Geri al"): ("Revoke", "Отозвать", "İzni kaldır", "Entziehen"),
    ("django", _C, "Universitet şəbəkəsindən kənarda jurnala yalnız bu siyahıdakı hesablar girə bilər."): (
        "Outside the university network, only the accounts on this list can open the journal.",
        "Вне сети университета журнал могут открывать только учётные записи из этого списка.",
        "Üniversite ağı dışında deftere yalnızca bu listedeki hesaplar girebilir.",
        "Außerhalb des Universitätsnetzes können nur die Konten auf dieser Liste das Journal öffnen.",
    ),
    ("django", _C, "Hesab əlavə et"): ("Add an account", "Добавить учётную запись", "Hesap ekle", "Konto hinzufügen"),
    ("django", _C, "Şəxs"): ("Person", "Сотрудник", "Kişi", "Person"),
    ("django", _C, "Uyğun hesab tapılmadı."): (
        "No matching account found.",
        "Подходящая учётная запись не найдена.",
        "Uygun hesap bulunamadı.",
        "Kein passendes Konto gefunden.",
    ),
    ("django", _C, "Ad, soyad və ya istifadəçi adı üzrə axtar"): (
        "Search by first name, last name or username",
        "Поиск по имени, фамилии или имени пользователя",
        "Ad, soyad veya kullanıcı adına göre ara",
        "Nach Vorname, Nachname oder Benutzername suchen",
    ),
    ("django", _C, "Qeyd"): ("Note", "Примечание", "Not", "Notiz"),
    ("django", _C, "(istəyə bağlı)"): ("(optional)", "(необязательно)", "(isteğe bağlı)", "(optional)"),
    ("django", _C, "Məs.: kafedra müdiri, evdən jurnal yazır"): (
        "E.g.: head of department, fills in the journal from home",
        "Напр.: заведующий кафедрой, ведёт журнал из дома",
        "Örn.: bölüm başkanı, defteri evden dolduruyor",
        "Z. B.: Lehrstuhlleitung, führt das Journal von zu Hause",
    ),
    (
        "django",
        _C,
        "Yalnız jurnal (və imtahan balının daxil edilməsi) kənardan açılır; hesabın rolu və digər icazələri dəyişmir. "
        "İnzibati (admin) hesablar üçün iki mərhələli təsdiq yenə tələb olunur.",
    ): (
        "Only the journal (and exam score entry) opens remotely; the account's role and other permissions do not "
        "change. Administrative (admin) accounts still need two-step verification.",
        "Извне открывается только журнал (и ввод экзаменационных баллов); роль и остальные права учётной записи не "
        "меняются. Для административных (admin) учётных записей двухэтапная проверка по-прежнему обязательна.",
        "Dışarıdan yalnızca defter (ve sınav puanı girişi) açılır; hesabın rolü ve diğer izinleri değişmez. Yönetici "
        "(admin) hesapları için iki adımlı doğrulama yine gereklidir.",
        "Von außen öffnet sich nur das Journal (und die Eingabe der Prüfungsnoten); Rolle und andere Rechte des Kontos "
        "bleiben gleich. Für Verwaltungskonten (Admin) ist die Zwei-Schritt-Bestätigung weiterhin erforderlich.",
    ),
    ("django", _C, "Vəzifə / bölmə"): (
        "Position / unit",
        "Должность / подразделение",
        "Görev / birim",
        "Funktion / Einheit",
    ),
    ("django", _C, "Kim verib"): ("Granted by", "Кто выдал", "Veren", "Gewährt von"),
    ("django", _C, "Əməl"): ("Action", "Действие", "İşlem", "Aktion"),
    ("django", _C, "İki mərhələli təsdiq"): (
        "Two-step verification",
        "Двухэтапная проверка",
        "İki adımlı doğrulama",
        "Zwei-Schritt-Bestätigung",
    ),
    ("django", _C, "Server tənzimləməsi"): ("Server setting", "Настройка сервера", "Sunucu ayarı", "Servereinstellung"),
    ("django", _C, "Buradan dəyişmir"): (
        "Not editable here",
        "Здесь не меняется",
        "Buradan değiştirilemez",
        "Hier nicht änderbar",
    ),
    ("django", _C, "Siyahı boşdur"): ("The list is empty", "Список пуст", "Liste boş", "Die Liste ist leer"),
    ("django", _C, "Kənardan jurnala heç kim girə bilmir. Yuxarıdan hesab əlavə edin."): (
        "Nobody can open the journal remotely. Add an account above.",
        "Никто не может открывать журнал извне. Добавьте учётную запись выше.",
        "Kimse deftere dışarıdan giremiyor. Yukarıdan hesap ekleyin.",
        "Niemand kann das Journal von außen öffnen. Fügen Sie oben ein Konto hinzu.",
    ),
}


def main():
    for domain in ("django",):
        for lang in LOCALES:
            path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            po = polib.pofile(path)
            existing = {(e.msgctxt, e.msgid) for e in po}
            added = 0
            for (dom, ctx, msgid), (en, ru, tr, de) in STRINGS.items():
                if dom != domain or (ctx, msgid) in existing:
                    continue
                msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
                entry = polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr)
                if "%(" in msgid:
                    entry.flags.append("python-format")
                po.append(entry)
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()
