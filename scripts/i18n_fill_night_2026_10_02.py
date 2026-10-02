#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-02 gecə düzəlişləri (sahib yatarkən, «tap və düzəlt»).

Əlavə olunan mətnlər:
  * `exams.final_center.room_admin`: sıfır/yayım/multicast MAC rədd mesajı (EXAMQA R3);
  * `accounts.grades_notice`: parol bərpasından sonrakı «köçürülmüş ballar» modalı;
  * `accounts.first_login`: boş e-poçt sahəsinin nümunəsi və izahı;
  * `accounts.student_registry` / `ui.status`: reyestrdə real təhsil vəziyyəti və hesab aktivləşdirməsi.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_night_2026_10_02.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

RA = "exams.final_center.room_admin"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_MAC_SPECIAL = "Bu MAC ünvanı kompüterə aid ola bilməz (sıfır, yayım və ya multicast): %(mac)s"

GN = "accounts.grades_notice"
FL = "accounts.first_login"

# Sahib 2026-10-02: parol bərpasından sonra ilk girişdə «köçürülmüş ballar» modalı (sadə dil).
_GRADES_NOTICE = [
    _t("Vacib məlumat", "Important", "Важно", "Önemli bilgi"),
    _t(
        "Qiymətlərinizi mütləq yoxlayın",
        "Please check your grades",
        "Обязательно проверьте свои оценки",
        "Notlarınızı mutlaka kontrol edin",
    ),
    _t(
        "Əvvəlki semestrlərin balları köhnə sistemdən bu yeni sistemə köçürülüb. Köçürmə zamanı bəzi ballarda "
        "səhv ola bilər.",
        "Your scores from previous semesters were transferred from the old system to this new one. Some scores "
        "may have been transferred incorrectly.",
        "Баллы за прошлые семестры перенесены из старой системы в эту новую. При переносе в некоторых баллах "
        "могли возникнуть ошибки.",
        "Önceki dönemlerin puanları eski sistemden bu yeni sisteme aktarıldı. Aktarım sırasında bazı puanlarda "
        "hata olabilir.",
    ),
    _t("Məsələn, belə ola bilər:", "For example:", "Например:", "Örneğin:"),
    _t(
        "balınız əslində olduğundan fərqli yazılıb;",
        "a score is different from what it really is;",
        "балл указан не таким, какой он на самом деле;",
        "puanınız gerçekte olduğundan farklı yazılmış;",
    ),
    _t(
        "keçdiyiniz fənn siyahıda görünmür;",
        "a subject you passed is missing from the list;",
        "сданный вами предмет не виден в списке;",
        "geçtiğiniz ders listede görünmüyor;",
    ),
    _t(
        "fənn başqa semestrdə görünür.",
        "a subject appears in a different semester.",
        "предмет отображается в другом семестре.",
        "ders başka bir dönemde görünüyor.",
    ),
    _t("Nə etməlisiniz?", "What should you do?", "Что нужно сделать?", "Ne yapmalısınız?"),
    _t(
        "«Ümumi tədris məlumatı» bölməsində öz ballarınıza diqqətlə baxın.",
        "Look carefully at your scores in the “Overall academic information” section.",
        "Внимательно проверьте свои баллы в разделе «Общая учебная информация».",
        "«Genel öğretim bilgisi» bölümünde puanlarınızı dikkatlice kontrol edin.",
    ),
    _t(
        "Səhv görsəniz, İmtahan Mərkəzinə yaxınlaşın və balınızı dəqiqləşdirin.",
        "If you see a mistake, go to the Exam Center and have your score checked.",
        "Если заметите ошибку, обратитесь в Экзаменационный центр и уточните свой балл.",
        "Bir hata görürseniz Sınav Merkezine başvurun ve puanınızı netleştirin.",
    ),
    _t(
        "Hər şey düzdürsə, heç nə etməyinizə ehtiyac yoxdur.",
        "If everything is correct, you don't need to do anything.",
        "Если всё верно, ничего делать не нужно.",
        "Her şey doğruysa bir şey yapmanıza gerek yok.",
    ),
    _t("Başa düşdüm", "I understand", "Понятно", "Anladım"),
    _t("Ballarıma indi baxım", "Check my scores now", "Посмотреть мои баллы", "Puanlarıma şimdi bakayım"),
    _t(
        "Bu məlumat yalnız bir dəfə göstərilir.",
        "This message is shown only once.",
        "Это сообщение показывается только один раз.",
        "Bu bilgi yalnızca bir kez gösterilir.",
    ),
]

_FIRST_LOGIN = [
    _t("məs: adiniz@gmail.com", "e.g. yourname@gmail.com", "напр.: vashe_imya@gmail.com", "örn: adiniz@gmail.com"),
    _t(
        "Bu sahəni özünüz doldurun: hər gün istifadə etdiyiniz e-poçtu yazın (məs. Gmail). Təsdiq kodu ora "
        "gələcək, parolu unutsanız bərpa da bu ünvanla olacaq.",
        "Fill in this field yourself: enter the email you use every day (e.g. Gmail). The verification code will "
        "be sent there, and if you forget your password it will be recovered with this address.",
        "Заполните это поле сами: укажите почту, которой пользуетесь каждый день (например, Gmail). Туда придёт "
        "код подтверждения, и по этому же адресу можно будет восстановить пароль.",
        "Bu alanı kendiniz doldurun: her gün kullandığınız e-postayı yazın (ör. Gmail). Doğrulama kodu oraya "
        "gelecek, şifrenizi unutursanız kurtarma da bu adresle yapılacak.",
    ),
]

SR = "accounts.student_registry"
US = "ui.status"

# Sahib 2026-10-02: reyestrdə real təhsil vəziyyəti + hesab aktivləşdirməsi.
_REGISTRY = [
    _t("OXUYUR", "STUDYING", "ОБУЧАЕТСЯ", "OKUYOR"),
    _t("Oxu müddəti bitməyib", "Study period not over", "Срок обучения не истёк", "Öğrenim süresi bitmedi"),
    _t("OXU MÜDDƏTİ BİTİB", "STUDY PERIOD ENDED", "СРОК ОБУЧЕНИЯ ИСТЁК", "ÖĞRENİM SÜRESİ BİTTİ"),
    _t(
        "Çox güman məzundur — rəsmiləşdirin",
        "Most likely a graduate — make it official",
        "Скорее всего выпускник — оформите официально",
        "Büyük olasılıkla mezun — resmileştirin",
    ),
    _t(
        "ARXİV: MƏZUN / XARİC",
        "ARCHIVE: GRADUATE / EXPELLED",
        "АРХИВ: ВЫПУСКНИК / ОТЧИСЛЕН",
        "ARŞİV: MEZUN / İLİŞİĞİ KESİLMİŞ",
    ),
    _t(
        "Köhnə sistemdə «azad edilib»",
        "Marked as “released” in the old system",
        "В старой системе отмечен как «освобождён»",
        "Eski sistemde «serbest bırakıldı»",
    ),
    _t("QƏBUL İLİ BİLİNMİR", "ADMISSION YEAR UNKNOWN", "ГОД ПОСТУПЛЕНИЯ НЕИЗВЕСТЕН", "KABUL YILI BİLİNMİYOR"),
    _t(
        "Köçürmədə il tapılmayıb",
        "The year was not found during migration",
        "Год не найден при переносе данных",
        "Aktarımda yıl bulunamadı",
    ),
    _t(
        "PAROLUNU QURUB / BƏRPA EDİB",
        "SET / RECOVERED PASSWORD",
        "ЗАДАЛ / ВОССТАНОВИЛ ПАРОЛЬ",
        "ŞİFRESİNİ KURDU / KURTARDI",
    ),
    _t(
        "Öz parolu + təsdiqli e-poçt",
        "Own password + verified email",
        "Свой пароль + подтверждённая почта",
        "Kendi şifresi + doğrulanmış e-posta",
    ),
    _t("HƏLƏ İLKİN PAROLDA", "STILL ON INITIAL PASSWORD", "ВСЁ ЕЩЁ С НАЧАЛЬНЫМ ПАРОЛЕМ", "HÂLÂ İLK ŞİFREDE"),
    _t(
        "Daxil olub parolunu dəyişməyib",
        "Has not signed in and changed the password",
        "Не вошёл и не сменил пароль",
        "Giriş yapıp şifresini değiştirmedi",
    ),
    _t("Vəziyyət", "Study state", "Состояние", "Durum"),
    _t("Hesab", "Account", "Учётная запись", "Hesap"),
    _t(
        "Parolunu qurub / bərpa edib",
        "Set / recovered password",
        "Задал / восстановил пароль",
        "Şifresini kurdu / kurtardı",
    ),
    _t("Hələ ilkin parolda", "Still on initial password", "Всё ещё с начальным паролем", "Hâlâ ilk şifrede"),
    _t("Rəsmi status", "Official status", "Официальный статус", "Resmî durum"),
]

_STUDY_STATE = [
    _t("Oxuyur", "Studying", "Обучается", "Okuyor"),
    _t("Oxu müddəti bitib", "Study period ended", "Срок обучения истёк", "Öğrenim süresi bitti"),
    _t(
        "Çox güman məzundur — rəsmi statusu (məzun) qeyd edilməlidir.",
        "Most likely a graduate — the official status (graduated) should be recorded.",
        "Скорее всего выпускник — нужно оформить официальный статус (выпускник).",
        "Büyük olasılıkla mezun — resmî durum (mezun) kaydedilmeli.",
    ),
    _t("Qəbul ili bilinmir", "Admission year unknown", "Год поступления неизвестен", "Kabul yılı bilinmiyor"),
    _t(
        "Arxiv: məzun və ya xaric",
        "Archive: graduate or expelled",
        "Архив: выпускник или отчислен",
        "Arşiv: mezun veya ilişiği kesilmiş",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    SR: {row["az"]: row for row in _REGISTRY},
    US: {row["az"]: row for row in _STUDY_STATE},
    GN: {row["az"]: row for row in _GRADES_NOTICE},
    FL: {row["az"]: row for row in _FIRST_LOGIN},
    RA: {
        _MAC_SPECIAL: _t(
            _MAC_SPECIAL,
            "This MAC address cannot belong to a computer (zero, broadcast or multicast): %(mac)s",
            "Этот MAC-адрес не может принадлежать компьютеру (нулевой, широковещательный или multicast): %(mac)s",
            "Bu MAC adresi bir bilgisayara ait olamaz (sıfır, yayın veya multicast): %(mac)s",
        ),
    },
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
