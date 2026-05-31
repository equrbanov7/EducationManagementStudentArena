#!/usr/bin/env python3
"""
EMSArena i18n — fill empty msgstr entries + add no-context msgid entries
for backend gettext() strings. Idempotent.
"""

import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


# Backend gettext source strings (msgid has NO msgctxt). msgid == AZ source.
NOCTX = {
    "Mövcud şifrə": {"az": "Mövcud şifrə", "en": "Current password", "ru": "Текущий пароль", "tr": "Mevcut şifre"},
    "Yeni şifrə": {"az": "Yeni şifrə", "en": "New password", "ru": "Новый пароль", "tr": "Yeni şifre"},
    "Yeni şifrəni təkrarla": {
        "az": "Yeni şifrəni təkrarla",
        "en": "Confirm new password",
        "ru": "Повторите новый пароль",
        "tr": "Yeni şifreyi tekrarla",
    },
}

# Empty-msgstr fills, keyed by msgid (these keys exist already but are empty in
# some locales). We provide all 4; only empty ones get filled.
FILLS = {
    "registration_completed_request_recorded": {
        "az": "Qeydiyyat tamamlandı, müraciətiniz qeydə alındı.",
        "en": "Registration completed, your request has been recorded.",
        "ru": "Регистрация завершена, ваша заявка зарегистрирована.",
        "tr": "Kayıt tamamlandı, talebiniz kaydedildi.",
    },
    "registration_completed_you_can_login_now": {
        "az": "Qeydiyyat tamamlandı, indi daxil ola bilərsiniz.",
        "en": "Registration completed, you can log in now.",
        "ru": "Регистрация завершена, теперь вы можете войти.",
        "tr": "Kayıt tamamlandı, şimdi giriş yapabilirsiniz.",
    },
    "registration_email_send_failed": {
        "az": "Qeydiyyat e-poçtu göndərilə bilmədi.",
        "en": "Failed to send the registration email.",
        "ru": "Не удалось отправить письмо о регистрации.",
        "tr": "Kayıt e-postası gönderilemedi.",
    },
    "otp_email_send_failed": {
        "az": "OTP kodu e-poçtu göndərilə bilmədi.",
        "en": "Failed to send the OTP email.",
        "ru": "Не удалось отправить письмо с OTP-кодом.",
        "tr": "OTP e-postası gönderilemedi.",
    },
    "verification_email_not_found_register_again": {
        "az": "Təsdiq e-poçtu tapılmadı, lütfən yenidən qeydiyyatdan keçin.",
        "en": "Verification email not found, please register again.",
        "ru": "Письмо для подтверждения не найдено, зарегистрируйтесь снова.",
        "tr": "Doğrulama e-postası bulunamadı, lütfen tekrar kayıt olun.",
    },
    "submission_not_allowed_attempts_or_deadline": {
        "az": "Təhvil mümkün deyil: cəhd limiti bitib və ya son tarix keçib.",
        "en": "Submission not allowed: attempt limit reached or deadline passed.",
        "ru": "Отправка невозможна: исчерпаны попытки или истёк срок.",
        "tr": "Gönderim mümkün değil: deneme hakkı doldu veya son tarih geçti.",
    },
    "user_added_to_org_with_role": {
        "az": "İstifadəçi təşkilata rol ilə əlavə edildi.",
        "en": "User added to the organization with a role.",
        "ru": "Пользователь добавлен в организацию с ролью.",
        "tr": "Kullanıcı role ile organizasyona eklendi.",
    },
    "user_did_not_select_this_org_on_signup": {
        "az": "İstifadəçi qeydiyyat zamanı bu təşkilatı seçməyib.",
        "en": "The user did not select this organization at sign-up.",
        "ru": "Пользователь не выбрал эту организацию при регистрации.",
        "tr": "Kullanıcı kayıt sırasında bu organizasyonu seçmedi.",
    },
    "grant_only_owned_or_grantable_permissions": {
        "az": "Yalnız sahib olduğunuz və ya vermə icazəniz olan icazələri verə bilərsiniz.",
        "en": "You can grant only permissions you own or are allowed to grant.",
        "ru": "Вы можете предоставлять только те разрешения, которыми владеете или вправе выдавать.",
        "tr": "Yalnızca sahip olduğunuz veya verme yetkiniz olan izinleri verebilirsiniz.",
    },
    "manage_lower_role_permissions_only": {
        "az": "Yalnız özünüzdən aşağı rolların icazələrini idarə edə bilərsiniz.",
        "en": "You can manage permissions only for roles lower than yours.",
        "ru": "Вы можете управлять разрешениями только для ролей ниже вашей.",
        "tr": "Yalnızca kendinizden düşük rollerin izinlerini yönetebilirsiniz.",
    },
    "change_lower_level_users_only": {
        "az": "Yalnız özünüzdən aşağı səviyyəli istifadəçiləri dəyişə bilərsiniz.",
        "en": "You can change only users of a lower level than yours.",
        "ru": "Вы можете изменять только пользователей уровнем ниже вашего.",
        "tr": "Yalnızca kendinizden düşük seviyedeki kullanıcıları değiştirebilirsiniz.",
    },
    "insufficient_level_for_target_user": {
        "az": "Bu istifadəçi üçün səviyyəniz kifayət etmir.",
        "en": "Your level is insufficient for this user.",
        "ru": "Вашего уровня недостаточно для этого пользователя.",
        "tr": "Bu kullanıcı için seviyeniz yetersiz.",
    },
    "student_university_or_school_required": {
        "az": "Tələbə üçün universitet və ya məktəb tələb olunur.",
        "en": "University or school is required for a student.",
        "ru": "Для студента требуется указать университет или школу.",
        "tr": "Öğrenci için üniversite veya okul gereklidir.",
    },
    "create_post_description": {
        "az": "Yeni paylaşım yaradın və kimlərin görə biləcəyini seçin.",
        "en": "Create a new post and choose who can see it.",
        "ru": "Создайте новую публикацию и выберите, кто её увидит.",
        "tr": "Yeni bir gönderi oluşturun ve kimlerin görebileceğini seçin.",
    },
    "confirmation_email_sent": {
        "az": "Təsdiq e-poçtu göndərildi.",
        "en": "A confirmation email has been sent.",
        "ru": "Письмо с подтверждением отправлено.",
        "tr": "Onay e-postası gönderildi.",
    },
}

# RU entry that was left untranslated (msgstr == "Email"). Fix to RU.
RU_OVERRIDES = {
    "Email": "Эл. почта",
}


def split_entries(content):
    return content.split("\n\n")


def get_field(entry, name):
    m = re.search(r'^%s "(.*)"$' % name, entry, re.M)
    return m.group(1) if m else None


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def has_noctx(content, msgid):
    # entry with this msgid and NO msgctxt
    for e in split_entries(content):
        if "msgctxt" in e:
            continue
        if re.search(r'^msgid "%s"$' % re.escape(msgid), e, re.M):
            return True
    return False


def fill_empty_and_overrides(content, lang):
    out = []
    changed = 0
    for e in split_entries(content):
        mid = get_field(e, "msgid")
        mstr = get_field(e, "msgstr")
        if mid is not None:
            # empty msgstr fill
            if (not mstr) and mid in FILLS and "msgid_plural" not in e:
                val = FILLS[mid].get(lang, FILLS[mid]["en"])
                e = re.sub(r'^msgstr ""$', 'msgstr "%s"' % esc(val), e, count=1, flags=re.M)
                changed += 1
            # RU override
            if lang == "ru" and mid in RU_OVERRIDES and mstr == mid:
                e = re.sub(
                    r'^msgstr "%s"$' % re.escape(mid), 'msgstr "%s"' % esc(RU_OVERRIDES[mid]), e, count=1, flags=re.M
                )
                changed += 1
        out.append(e)
    return "\n\n".join(out), changed


def run():
    report = []
    for lang in LOCALES:
        p = po_path(lang)
        content = open(p, encoding="utf-8").read()
        content, changed = fill_empty_and_overrides(content, lang)
        # append no-context backend strings
        adds = []
        for mid, tr in NOCTX.items():
            if not has_noctx(content, mid):
                adds.append('\nmsgid "%s"\nmsgstr "%s"\n' % (esc(mid), esc(tr.get(lang, tr["en"]))))
        if adds:
            if not content.endswith("\n"):
                content += "\n"
            content += "".join(adds)
        open(p, "w", encoding="utf-8").write(content)
        report.append("  %s: filled=%d appended_noctx=%d" % (lang, changed, len(adds)))
    return report


if __name__ == "__main__":
    lines = run()
    open(os.path.join(BASE, "scripts", "_fill_out.txt"), "w", encoding="utf-8").write("\n".join(lines))
    print("done")
