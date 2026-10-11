#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-11 (WP13): «Hesabı dayandır» dialoqu hədəfin statusuna görə + «Digər» səbəb sahəsi.

Əlavə olunan mətnlər (`accounts.account_block`):
  * müəllim/əməkdaş üçün səbəb və ünvanlar («İşdən ayrılıb / müqavilə bitib», «Kadrlar şöbəsi», «Kafedra müdiri»);
  * «Digər» üçün məcburi «Səbəbi yazın» sahəsi və onun ipucları;
  * «Müəllimə qeyd …» / «İstifadəçiyə qeyd …» etiketləri və ipucları; blok səhifəsinin neytral mətni.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_11_wp13roster.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


AB = "accounts.account_block"

_BLOCK = [
    _t(
        "Kadrlar şöbəsi (İnsan resursları)",
        "HR department (Human resources)",
        "Отдел кадров (человеческие ресурсы)",
        "Personel birimi (İnsan kaynakları)",
    ),
    _t("Kafedra müdiri", "Head of department", "Заведующий кафедрой", "Bölüm başkanı"),
    _t(
        "İşdən ayrılıb / müqavilə bitib",
        "Left the job / contract ended",
        "Уволился / контракт завершён",
        "İşten ayrıldı / sözleşmesi sona erdi",
    ),
    _t(
        "«Digər» seçilib — səbəbi «Səbəbi yazın» sahəsinə yazın (ən azı 3 simvol).",
        "“Other” is selected — write the reason in the “Write the reason” field (at least 3 characters).",
        "Выбрано «Другое» — укажите причину в поле «Напишите причину» (не менее 3 символов).",
        "«Diğer» seçildi — nedeni «Nedeni yazın» alanına yazın (en az 3 karakter).",
    ),
    _t("Səbəbi yazın", "Write the reason", "Напишите причину", "Nedeni yazın"),
    _t(
        "məs: hesab sahibinin yazılı müraciəti ilə",
        "e.g. at the account holder's written request",
        "напр.: по письменному заявлению владельца аккаунта",
        "ör.: hesap sahibinin yazılı talebiyle",
    ),
    _t(
        "«Digər» seçilib — səbəbi bu sahəyə yazın (məcburi). Tələbə girişdə məhz bu mətni görəcək.",
        "“Other” is selected — write the reason here (required). The student will see exactly this text when signing in.",
        "Выбрано «Другое» — укажите причину здесь (обязательно). Студент увидит именно этот текст при входе.",
        "«Diğer» seçildi — nedeni buraya yazın (zorunlu). Öğrenci girişte tam olarak bu metni görecek.",
    ),
    _t(
        "«Digər» seçilib — səbəbi bu sahəyə yazın (məcburi). Müəllim girişdə məhz bu mətni görəcək.",
        "“Other” is selected — write the reason here (required). The teacher will see exactly this text when signing in.",
        "Выбрано «Другое» — укажите причину здесь (обязательно). Преподаватель увидит именно этот текст при входе.",
        "«Diğer» seçildi — nedeni buraya yazın (zorunlu). Öğretim elemanı girişte tam olarak bu metni görecek.",
    ),
    _t(
        "«Digər» seçilib — səbəbi bu sahəyə yazın (məcburi). İstifadəçi girişdə məhz bu mətni görəcək.",
        "“Other” is selected — write the reason here (required). The user will see exactly this text when signing in.",
        "Выбрано «Другое» — укажите причину здесь (обязательно). Пользователь увидит именно этот текст при входе.",
        "«Diğer» seçildi — nedeni buraya yazın (zorunlu). Kullanıcı girişte tam olarak bu metni görecek.",
    ),
    _t(
        "Müəllimə qeyd (otaq, telefon, iş saatı)",
        "Note for the teacher (room, phone, hours)",
        "Примечание для преподавателя (кабинет, телефон, часы)",
        "Öğretim elemanına not (oda, telefon, çalışma saatleri)",
    ),
    _t(
        "İstifadəçiyə qeyd (otaq, telefon, iş saatı)",
        "Note for the user (room, phone, hours)",
        "Примечание для пользователя (кабинет, телефон, часы)",
        "Kullanıcıya not (oda, telefon, çalışma saatleri)",
    ),
    _t("(istəyə bağlı)", "(optional)", "(необязательно)", "(isteğe bağlı)"),
    _t(
        "Müəllim istifadəçi adı və parolunu yazanda səbəbi, bu ünvanı və qeydi görəcək — sistemə isə daxil ola bilməyəcək.",
        "When the teacher enters their username and password they will see the reason, this contact and the note — but will not be able to sign in.",
        "Введя имя пользователя и пароль, преподаватель увидит причину, это место обращения и примечание, но войти в систему не сможет.",
        "Öğretim elemanı kullanıcı adını ve parolasını girdiğinde nedeni, bu başvuru yerini ve notu görecek — ancak sisteme giriş yapamayacak.",
    ),
    _t(
        "İstifadəçi adı və parol yazılanda səbəb, bu ünvan və qeyd göstəriləcək — sistemə isə daxil olmaq mümkün olmayacaq.",
        "When the username and password are entered, the reason, this contact and the note will be shown — but signing in will not be possible.",
        "При вводе имени пользователя и пароля будут показаны причина, это место обращения и примечание, но войти в систему будет невозможно.",
        "Kullanıcı adı ve parola girildiğinde neden, bu başvuru yeri ve not gösterilecek — ancak sisteme giriş yapılamayacak.",
    ),
    _t(
        "İstifadəçi adınız və parolunuz düzgündür, amma hesabınıza giriş universitet tərəfindən müvəqqəti dayandırılıb. Hesabınızdakı məlumatlar silinməyib.",
        "Your username and password are correct, but the university has temporarily suspended access to your account. The data in your account has not been deleted.",
        "Имя пользователя и пароль верны, но университет временно приостановил доступ к вашему аккаунту. Данные в аккаунте не удалены.",
        "Kullanıcı adınız ve parolanız doğru, ancak üniversite hesabınıza erişimi geçici olarak askıya aldı. Hesabınızdaki veriler silinmedi.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {AB: {row["az"]: row for row in _BLOCK}}

FORCE = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
