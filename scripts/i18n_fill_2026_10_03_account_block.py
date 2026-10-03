#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-03: hesab dayandırma səbəbi + «blokdan çıxmaq üçün kimə yaxınlaşmalı».

Əlavə olunan mətnlər:
  * `accounts.account_block`: səbəb / müraciət kataloqu, dayandırma sahələri, «Hesabınız dayandırılıb» ekranı;
  * `accounts.student_registry`: reyestr kartında «Hesab» bloku və dayandırma dialoqu.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_03_account_block.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


AB = "accounts.account_block"
SR = "accounts.student_registry"

_BLOCK = [
    _t("Akademik məzuniyyət", "Academic leave", "Академический отпуск", "Akademik izin"),
    _t(
        "Blokdan çıxmaq üçün kimə yaxınlaşsın",
        "Whom to contact to be unblocked",
        "К кому обратиться для разблокировки",
        "Engelin kaldırılması için kime başvurmalı",
    ),
    _t(
        "Blokdan çıxmaq üçün yaxınlaşın",
        "To get unblocked, contact",
        "Для разблокировки обратитесь",
        "Engelin kaldırılması için başvurun",
    ),
    _t("Dayandırma səbəbi", "Suspension reason", "Причина приостановки", "Askıya alma nedeni"),
    _t(
        "Dayandırma səbəbini seçin.",
        "Choose the suspension reason.",
        "Выберите причину приостановки.",
        "Askıya alma nedenini seçin.",
    ),
    _t("Dayandırılma tarixi", "Suspended on", "Дата приостановки", "Askıya alma tarihi"),
    _t("Digər", "Other", "Другое", "Diğer"),
    _t("Fakültənizin dekanlığı", "Your faculty's dean's office", "Деканат вашего факультета", "Fakültenizin dekanlığı"),
    _t("Giriş müvəqqəti bağlıdır", "Sign-in temporarily closed", "Вход временно закрыт", "Giriş geçici olarak kapalı"),
    _t("Giriş səhifəsinə qayıt", "Back to sign-in", "Вернуться на страницу входа", "Giriş sayfasına dön"),
    _t(
        "Hesab açılana qədər sistemin heç bir bölməsinə daxil olmaq mümkün deyil.",
        "Until the account is reopened, no part of the system can be accessed.",
        "Пока аккаунт не будет разблокирован, доступ ко всем разделам системы закрыт.",
        "Hesap açılana kadar sistemin hiçbir bölümüne erişilemez.",
    ),
    _t(
        "Hesabın təhlükəsizliyi (şübhəli giriş)",
        "Account security (suspicious sign-in)",
        "Безопасность аккаунта (подозрительный вход)",
        "Hesap güvenliği (şüpheli giriş)",
    ),
    _t("Hesabınız dayandırılıb", "Your account is suspended", "Ваш аккаунт приостановлен", "Hesabınız askıya alındı"),
    _t(
        "Hesabınız müvəqqəti dayandırılıb",
        "Your account is temporarily suspended",
        "Ваш аккаунт временно приостановлен",
        "Hesabınız geçici olarak askıya alındı",
    ),
    _t(
        "Maliyyə şöbəsi (mühasibatlıq)",
        "Finance office (accounting)",
        "Финансовый отдел (бухгалтерия)",
        "Mali işler (muhasebe)",
    ),
    _t("Müraciət ünvanı yanlışdır.", "Invalid contact office.", "Неверное место обращения.", "Başvuru yeri geçersiz."),
    _t("Nə etməli?", "What to do?", "Что делать?", "Ne yapmalı?"),
    _t(
        "Parolunuzu heç kimə deməyin; universitet əməkdaşı onu heç vaxt soruşmur.",
        "Never share your password; university staff will never ask for it.",
        "Никому не сообщайте пароль: сотрудники университета никогда его не спрашивают.",
        "Parolanızı kimseyle paylaşmayın; üniversite personeli onu asla sormaz.",
    ),
    _t(
        "Problem həll olunandan sonra hesabınız açılacaq — eyni istifadəçi adı və parolla daxil olun.",
        "Once the issue is resolved your account will be reopened — sign in with the same username and password.",
        "После решения вопроса аккаунт откроют — входите с тем же именем пользователя и паролем.",
        "Sorun çözüldükten sonra hesabınız açılacak — aynı kullanıcı adı ve parolayla giriş yapın.",
    ),
    _t(
        "RİM — Rəqəmsal İnkişaf Mərkəzi",
        "RİM — Digital Development Centre",
        "RİM — Центр цифрового развития",
        "RİM — Dijital Gelişim Merkezi",
    ),
    _t("Səbəb", "Reason", "Причина", "Neden"),
    _t("Səbəbi seçin", "Choose a reason", "Выберите причину", "Neden seçin"),
    _t(
        "Səbəbə görə avtomatik seçilir — lazım olsa dəyişin.",
        "Chosen automatically from the reason — change it if needed.",
        "Выбирается автоматически по причине — при необходимости измените.",
        "Nedene göre otomatik seçilir — gerekirse değiştirin.",
    ),
    _t(
        "Sənədlər tam təqdim edilməyib",
        "Documents not fully submitted",
        "Документы представлены не полностью",
        "Belgeler eksik teslim edildi",
    ),
    _t("Tədris şöbəsi", "Teaching office", "Учебный отдел", "Öğrenci işleri"),
    _t("Təhsil haqqı üzrə borc", "Tuition fee debt", "Задолженность по оплате обучения", "Öğrenim ücreti borcu"),
    _t(
        "Tələbə Xidmətləri Mərkəzi", "Student Services Centre", "Центр студенческих услуг", "Öğrenci Hizmetleri Merkezi"
    ),
    _t(
        "Tələbə istifadəçi adı və parolunu yazanda səbəbi, bu ünvanı və qeydi görəcək — sistemə isə daxil ola bilməyəcək.",
        "When the student enters their username and password they will see the reason, this office and the note — but cannot enter the system.",
        "Введя имя пользователя и пароль, студент увидит причину, это место обращения и примечание — но войти в систему не сможет.",
        "Öğrenci kullanıcı adı ve parolasını yazdığında nedeni, bu adresi ve notu görecek — sisteme ise giremeyecek.",
    ),
    _t(
        "Tələbəyə qeyd (otaq, telefon, iş saatı)",
        "Note for the student (room, phone, hours)",
        "Примечание для студента (кабинет, телефон, часы)",
        "Öğrenciye not (oda, telefon, çalışma saatleri)",
    ),
    _t(
        "məs: 2-ci korpus, 105-ci otaq, 09:00–17:00",
        "e.g. Building 2, room 105, 09:00–17:00",
        "напр.: корпус 2, кабинет 105, 09:00–17:00",
        "ör.: 2. blok, 105 numaralı oda, 09:00–17:00",
    ),
    _t("səbəb qeyd olunmayıb", "no reason recorded", "причина не указана", "neden belirtilmemiş"),
    _t(
        "«Digər» seçildikdə səbəbi qısaca izah edin.",
        "When “Other” is chosen, briefly explain the reason.",
        "При выборе «Другое» кратко поясните причину.",
        "«Diğer» seçildiğinde nedeni kısaca açıklayın.",
    ),
    _t("İmtahan Mərkəzi", "Exam Centre", "Экзаменационный центр", "Sınav Merkezi"),
    _t(
        "İmtahan qaydalarının pozulması",
        "Violation of exam rules",
        "Нарушение правил экзамена",
        "Sınav kurallarının ihlali",
    ),
    _t(
        "İntizam qaydalarının pozulması",
        "Violation of disciplinary rules",
        "Нарушение правил дисциплины",
        "Disiplin kurallarının ihlali",
    ),
    _t(
        "İstifadəçi adınız və parolunuz düzgündür, amma hesabınıza giriş universitet tərəfindən müvəqqəti dayandırılıb. Məlumatlarınız, ballarınız və davamiyyətiniz silinməyib.",
        "Your username and password are correct, but the university has temporarily suspended access to your account. Your data, scores and attendance have not been deleted.",
        "Имя пользователя и пароль верны, но университет временно приостановил доступ к вашему аккаунту. Ваши данные, баллы и посещаемость не удалены.",
        "Kullanıcı adınız ve parolanız doğru, ancak üniversite hesabınıza erişimi geçici olarak askıya aldı. Verileriniz, puanlarınız ve devam kayıtlarınız silinmedi.",
    ),
    _t(
        "Şəxsi məlumatlar dəqiqləşdirilməlidir",
        "Personal data must be verified",
        "Необходимо уточнить личные данные",
        "Kişisel bilgiler doğrulanmalı",
    ),
    _t(
        "Şəxsiyyət vəsiqənizi götürüb yuxarıda göstərilən yerə yaxınlaşın.",
        "Take your ID card and go to the office shown above.",
        "Возьмите удостоверение личности и обратитесь в указанное выше место.",
        "Kimlik kartınızı alıp yukarıda gösterilen yere başvurun.",
    ),
]

_REGISTRY = [
    _t("Aktiv — sistemə daxil ola bilir", "Active — can sign in", "Активен — может войти", "Aktif — giriş yapabilir"),
    _t(
        "Arxiv (məzun / xaric) — giriş bağlıdır",
        "Archive (graduate / expelled) — sign-in closed",
        "Архив (выпускник / отчислен) — вход закрыт",
        "Arşiv (mezun / ilişiği kesilmiş) — giriş kapalı",
    ),
    _t("Bağla", "Close", "Закрыть", "Kapat"),
    _t("Blokdan çıxar", "Unblock", "Разблокировать", "Engeli kaldır"),
    _t("Blokdan çıxmaq üçün", "To be unblocked", "Для разблокировки", "Engelin kaldırılması için"),
    _t(
        "Dayandırılıb — sistemə daxil ola bilmir",
        "Suspended — cannot sign in",
        "Приостановлен — не может войти",
        "Askıya alındı — giriş yapamaz",
    ),
    _t(
        "Hesab bərpa edilsin? Tələbə yenidən sistemə daxil ola biləcək.",
        "Restore the account? The student will be able to sign in again.",
        "Восстановить аккаунт? Студент снова сможет войти в систему.",
        "Hesap geri açılsın mı? Öğrenci yeniden giriş yapabilecek.",
    ),
    _t("Hesabı dayandır", "Suspend account", "Приостановить аккаунт", "Hesabı askıya al"),
    _t("Ləğv et", "Cancel", "Отмена", "İptal"),
    _t("Silinib", "Deleted", "Удалён", "Silindi"),
    _t("Səbəb", "Reason", "Причина", "Neden"),
    _t("Tarix", "Date", "Дата", "Tarih"),
    _t("Tələbəyə qeyd", "Note for the student", "Примечание для студента", "Öğrenciye not"),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    AB: {row["az"]: row for row in _BLOCK},
    SR: {row["az"]: row for row in _REGISTRY},
}

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
