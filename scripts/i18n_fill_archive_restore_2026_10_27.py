#!/usr/bin/env python3
"""EMSArena i18n — «Arxivdən çıxar»: səhvən arxivlənmiş cari tələbənin hesabı (sahib 2026-10-27).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `msgfmt` / `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CTX = "accounts.archive_restore"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    CTX: {
        "Hesabı arxivdən çıxarmaq üçün icazəniz yoxdur.": t(
            "You do not have permission to restore this account from the archive.",
            "У вас нет прав восстанавливать эту учётную запись из архива.",
            "Bu hesabı arşivden çıkarma yetkiniz yok.",
            "Sie sind nicht berechtigt, dieses Konto aus dem Archiv wiederherzustellen.",
        ),
        "Başqasının adından baxış rejimində hesabı arxivdən çıxarmaq olmaz.": t(
            "An account cannot be restored from the archive while viewing as another user.",
            "Нельзя восстанавливать учётную запись из архива в режиме просмотра от имени другого пользователя.",
            "Başka bir kullanıcı adına görüntüleme modunda hesap arşivden çıkarılamaz.",
            "Im Modus „Ansicht als anderer Benutzer“ kann kein Konto aus dem Archiv wiederhergestellt werden.",
        ),
        "İstifadəçi seçilməyib.": t(
            "No user selected.", "Пользователь не выбран.", "Kullanıcı seçilmedi.", "Kein Benutzer ausgewählt."
        ),
        "İstifadəçi tapılmadı.": t(
            "User not found.", "Пользователь не найден.", "Kullanıcı bulunamadı.", "Benutzer nicht gefunden."
        ),
        "Hesab arxivdə deyil.": t(
            "The account is not archived.",
            "Учётная запись не находится в архиве.",
            "Hesap arşivde değil.",
            "Das Konto ist nicht archiviert.",
        ),
        "Hesab bloklanıb — əvvəlcə blokdan çıxarılmalıdır.": t(
            "The account is blocked — unblock it first.",
            "Учётная запись заблокирована — сначала разблокируйте её.",
            "Hesap engellendi — önce engeli kaldırılmalıdır.",
            "Das Konto ist gesperrt — heben Sie zuerst die Sperre auf.",
        ),
        "Tələbənin aktiv akademik qeydi yoxdur — arxiv düzgündür.": t(
            "The student has no active academic record — the archive status is correct.",
            "У студента нет активной академической записи — архивный статус верен.",
            "Öğrencinin aktif akademik kaydı yok — arşiv durumu doğru.",
            "Die studierende Person hat keinen aktiven Studiendatensatz — der Archivstatus ist korrekt.",
        ),
        "Tələbə «Xaric» qrupundadır — arxiv düzgündür.": t(
            "The student is in an “Expelled” group — the archive status is correct.",
            "Студент находится в группе «Отчислен» — архивный статус верен.",
            "Öğrenci «İlişiği kesilen» grubunda — arşiv durumu doğru.",
            "Die studierende Person ist in einer „Exmatrikuliert“-Gruppe — der Archivstatus ist korrekt.",
        ),
        "Hesabın bu təşkilatda bir neçə üzvlüyü var — arxivdən çıxarmaq üçün RİM ilə yoxlanmalıdır.": t(
            "The account has several memberships in this organization — check it with the Digital Development "
            "Centre before restoring.",
            "У учётной записи несколько членств в этой организации — перед восстановлением проверьте её с "
            "Центром цифрового развития.",
            "Hesabın bu kurumda birden fazla üyeliği var — arşivden çıkarmadan önce Dijital Gelişim Merkezi ile "
            "kontrol edilmelidir.",
            "Das Konto hat mehrere Mitgliedschaften in dieser Organisation — vor der Wiederherstellung mit dem "
            "Zentrum für digitale Entwicklung prüfen.",
        ),
        "Təşkilatda aktiv «Tələbə» rolu yoxdur.": t(
            "The organization has no active “Student” role.",
            "В организации нет активной роли «Студент».",
            "Kurumda aktif «Öğrenci» rolü yok.",
            "Die Organisation hat keine aktive Rolle „Studierende“.",
        ),
        "Səbəb yazılmalıdır (ən azı 3 simvol).": t(
            "Enter a reason (at least 3 characters).",
            "Укажите причину (не менее 3 символов).",
            "Bir neden yazılmalıdır (en az 3 karakter).",
            "Geben Sie einen Grund an (mindestens 3 Zeichen).",
        ),
        "Qəbul ili 2000–2100 aralığında olmalıdır.": t(
            "The admission year must be between 2000 and 2100.",
            "Год поступления должен быть в диапазоне 2000–2100.",
            "Kabul yılı 2000–2100 aralığında olmalıdır.",
            "Das Aufnahmejahr muss zwischen 2000 und 2100 liegen.",
        ),
        "Hesabı arxivdən çıxarmaq alınmadı. Yenidən cəhd edin.": t(
            "The account could not be restored from the archive. Please try again.",
            "Не удалось восстановить учётную запись из архива. Попробуйте ещё раз.",
            "Hesap arşivden çıkarılamadı. Tekrar deneyin.",
            "Das Konto konnte nicht aus dem Archiv wiederhergestellt werden. Bitte erneut versuchen.",
        ),
        "Tələbə hələ oxuyur (aktiv akademik qeyd, qrup: %(group)s), amma hesab arxivdədir — giriş və parol bərpası "
        "bağlıdır. Səhv arxivdirsə «Arxivdən çıxar».": t(
            "The student is still studying (active academic record, group: %(group)s), but the account is archived "
            "— sign-in and password reset are closed. If this is a mistake, use “Restore from archive”.",
            "Студент продолжает обучение (активная академическая запись, группа: %(group)s), но учётная запись в "
            "архиве — вход и сброс пароля закрыты. Если это ошибка, нажмите «Вернуть из архива».",
            "Öğrenci hâlâ okuyor (aktif akademik kayıt, grup: %(group)s), ama hesap arşivde — giriş ve şifre "
            "sıfırlama kapalı. Hatalıysa «Arşivden çıkar».",
            "Die studierende Person studiert noch (aktiver Studiendatensatz, Gruppe: %(group)s), aber das Konto ist "
            "archiviert — Anmeldung und Passwortzurücksetzung sind gesperrt. Falls irrtümlich: „Aus dem Archiv "
            "holen“.",
        ),
        "Bunun üçün «member.edit» icazəsi lazımdır — RİM rəhbərinə müraciət edin.": t(
            "This requires the “member.edit” permission — contact the head of the Digital Development Centre.",
            "Для этого нужно право «member.edit» — обратитесь к руководителю Центра цифрового развития.",
            "Bunun için «member.edit» yetkisi gerekir — Dijital Gelişim Merkezi yöneticisine başvurun.",
            "Dafür ist die Berechtigung „member.edit“ nötig — wenden Sie sich an die Leitung des Zentrums für "
            "digitale Entwicklung.",
        ),
        "Hesab arxivdən çıxarıldı — tələbə yenidən daxil ola bilər. Lazım olsa parolu sıfırlayın.": t(
            "The account has been restored from the archive — the student can sign in again. Reset the password "
            "if needed.",
            "Учётная запись возвращена из архива — студент снова может войти. При необходимости сбросьте пароль.",
            "Hesap arşivden çıkarıldı — öğrenci yeniden giriş yapabilir. Gerekirse şifreyi sıfırlayın.",
            "Das Konto wurde aus dem Archiv geholt — die studierende Person kann sich wieder anmelden. Setzen Sie "
            "bei Bedarf das Passwort zurück.",
        ),
        "Qəbul ili düzəldildi: %(year)s.": t(
            "Admission year corrected: %(year)s.",
            "Год поступления исправлен: %(year)s.",
            "Kabul yılı düzeltildi: %(year)s.",
            "Aufnahmejahr korrigiert: %(year)s.",
        ),
        "Arxivdən çıxar": t("Restore from archive", "Вернуть из архива", "Arşivden çıkar", "Aus dem Archiv holen"),
        "{name} ({username}) hesabı yenidən aktiv olacaq: giriş və parol sıfırlama açılır. Akademik qeyd və qrup "
        "dəyişmir.": t(
            "The account of {name} ({username}) will become active again: sign-in and password reset are reopened. "
            "The academic record and group do not change.",
            "Учётная запись {name} ({username}) снова станет активной: вход и сброс пароля откроются. Академическая "
            "запись и группа не меняются.",
            "{name} ({username}) hesabı yeniden aktif olacak: giriş ve şifre sıfırlama açılır. Akademik kayıt ve "
            "grup değişmez.",
            "Das Konto von {name} ({username}) wird wieder aktiv: Anmeldung und Passwortzurücksetzung werden "
            "geöffnet. Studiendatensatz und Gruppe bleiben unverändert.",
        ),
        "Hesab arxivdən çıxarılsın?": t(
            "Restore the account from the archive?",
            "Вернуть учётную запись из архива?",
            "Hesap arşivden çıkarılsın mı?",
            "Konto aus dem Archiv holen?",
        ),
        "Səbəb": t("Reason", "Причина", "Neden", "Grund"),
        "məs. Tələbə 131 T qrupunda oxuyur, köçürmədə səhvən məzun sayılıb": t(
            "e.g. The student studies in group 131 T and was marked as a graduate by mistake during migration",
            "напр. Студент учится в группе 131 T, при переносе ошибочно отмечен как выпускник",
            "örn. Öğrenci 131 T grubunda okuyor, aktarımda yanlışlıkla mezun sayılmış",
            "z. B. Studiert in Gruppe 131 T, wurde bei der Migration irrtümlich als Absolvent erfasst",
        ),
        "Səbəb audit jurnalına yazılır.": t(
            "The reason is saved to the audit log.",
            "Причина записывается в журнал аудита.",
            "Neden denetim günlüğüne yazılır.",
            "Der Grund wird im Audit-Protokoll gespeichert.",
        ),
        "Səbəb ən azı 3 simvol olmalıdır.": t(
            "The reason must be at least 3 characters.",
            "Причина должна содержать не менее 3 символов.",
            "Neden en az 3 karakter olmalıdır.",
            "Der Grund muss mindestens 3 Zeichen lang sein.",
        ),
        "Qəbul ili": t("Admission year", "Год поступления", "Kabul yılı", "Aufnahmejahr"),
        "(istəyə bağlı)": t("(optional)", "(необязательно)", "(isteğe bağlı)", "(optional)"),
        "məs. 2023": t("e.g. 2023", "напр. 2023", "örn. 2023", "z. B. 2023"),
        "Köçürmədə qəbul ili tapılmayıb (1950 yer-tutucusu). Bilirsinizsə yazın — boş qalsa dəyişmir.": t(
            "The admission year was not found during migration (placeholder 1950). Enter it if you know it — left "
            "empty, it stays unchanged.",
            "Год поступления не найден при переносе (заполнитель 1950). Укажите его, если знаете, — пустое поле "
            "ничего не меняет.",
            "Aktarımda kabul yılı bulunamadı (1950 yer tutucusu). Biliyorsanız yazın — boş kalırsa değişmez.",
            "Das Aufnahmejahr wurde bei der Migration nicht gefunden (Platzhalter 1950). Tragen Sie es ein, falls "
            "bekannt — leer bleibt es unverändert.",
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
