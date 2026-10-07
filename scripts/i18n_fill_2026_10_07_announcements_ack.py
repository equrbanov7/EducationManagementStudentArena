#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-07: «Elanlar» məcburi elan (təsdiq) + forma aydınlığı.

Yeni mətnlər: popup rejimi (radio kartlar), «Kim görəcək» xülasəsi, məcburi popup / detal
banneri («Elanı oxudum və tanış oldum», «Təsdiq edirəm»), kabinetdə «Məcburi» çipi və
«Təsdiq gözləyənlər» filtri, menecerin «Təsdiq edən: X / Y» statistikası və alıcı siyahısı.

Kontekstlər: `announcements.{api,cabinet,manage,model,popup}`. Cəm formalı iki mətn
(«%(n)s nəfər», «Kim görəcək: … — təxminən %(n)s nəfər») ``msgid_plural`` ilə yazılır.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları `msgfmt` ilə yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_07_announcements_ack.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

# (kontekst, az) → (en, ru, tr)
ROWS = {
    "announcements.api": {
        "Bu elan təsdiq tələb etmir.": (
            "This announcement does not require confirmation.",
            "Это объявление не требует подтверждения.",
            "Bu duyuru onay gerektirmiyor.",
        ),
        "Əvvəlcə «Elanı oxudum və tanış oldum» qutusunu işarələyin.": (
            "First tick “I have read and understood the announcement”.",
            "Сначала отметьте «Я прочитал(а) объявление и ознакомлен(а)».",
            "Önce “Duyuruyu okudum ve bilgi edindim” kutusunu işaretleyin.",
        ),
    },
    "announcements.cabinet": {
        "Bu elan məcburidir": (
            "This announcement is mandatory",
            "Это обязательное объявление",
            "Bu duyuru zorunludur",
        ),
        "Elanla tanış olduğunuzu %(day)s tarixində təsdiq etmisiniz.": (
            "You confirmed that you read this announcement on %(day)s.",
            "Вы подтвердили ознакомление с объявлением %(day)s.",
            "Duyuruyu okuduğunuzu %(day)s tarihinde onayladınız.",
        ),
        "Elanla tanış olun və təsdiq edin. Təsdiq edənədək elan hər səhifədə popup kimi açılacaq.": (
            "Read the announcement and confirm. Until you confirm, it will open as a popup on every page.",
            "Ознакомьтесь с объявлением и подтвердите. До подтверждения оно будет открываться "
            "всплывающим окном на каждой странице.",
            "Duyuruyu okuyun ve onaylayın. Onaylayana kadar duyuru her sayfada açılır pencere olarak gösterilecek.",
        ),
        "Elanı oxudum və tanış oldum": (
            "I have read and understood the announcement",
            "Я прочитал(а) объявление и ознакомлен(а)",
            "Duyuruyu okudum ve bilgi edindim",
        ),
        "Məcburi": ("Mandatory", "Обязательно", "Zorunlu"),
        "Məcburi elan: istifadəçi burada «Elanı oxudum və tanış oldum» təsdiqini verəcək; təsdiq edənədək "
        "elan hər səhifədə popup kimi açılır.": (
            "Mandatory announcement: the user will confirm “I have read and understood the announcement” here; "
            "until then it opens as a popup on every page.",
            "Обязательное объявление: здесь пользователь подтвердит «Я прочитал(а) объявление и ознакомлен(а)»; "
            "до подтверждения оно открывается всплывающим окном на каждой странице.",
            "Zorunlu duyuru: kullanıcı burada “Duyuruyu okudum ve bilgi edindim” onayını verecek; "
            "onaylayana kadar duyuru her sayfada açılır pencere olarak gösterilir.",
        ),
        "Məcburi elan — baxış rejimində təsdiq yazılmır.": (
            "Mandatory announcement — confirmations are not recorded in view-as mode.",
            "Обязательное объявление — в режиме просмотра подтверждение не записывается.",
            "Zorunlu duyuru — görüntüleme modunda onay kaydedilmez.",
        ),
        "Sizə ünvanlanmış bütün məcburi elanları təsdiq etmisiniz.": (
            "You have confirmed all mandatory announcements addressed to you.",
            "Вы подтвердили все адресованные вам обязательные объявления.",
            "Size gönderilen tüm zorunlu duyuruları onayladınız.",
        ),
        "Təsdiq edildi": ("Confirmed", "Подтверждено", "Onaylandı"),
        "Təsdiq edildi %(day)s": ("Confirmed %(day)s", "Подтверждено %(day)s", "Onaylandı %(day)s"),
        "Təsdiq edirəm": ("I confirm", "Подтверждаю", "Onaylıyorum"),
        "Təsdiq gözləyir": ("Awaiting confirmation", "Ожидает подтверждения", "Onay bekliyor"),
        "Təsdiq gözləyən elan yoxdur": (
            "No announcements awaiting confirmation",
            "Нет объявлений, ожидающих подтверждения",
            "Onay bekleyen duyuru yok",
        ),
        "Təsdiq gözləyənlər": ("Awaiting confirmation", "Ожидают подтверждения", "Onay bekleyenler"),
        "Təsdiq göndərilmədi. Bir az sonra yenidən cəhd edin.": (
            "The confirmation was not sent. Please try again a little later.",
            "Подтверждение не отправлено. Повторите попытку чуть позже.",
            "Onay gönderilemedi. Biraz sonra tekrar deneyin.",
        ),
    },
    "announcements.manage": {
        "Ad, soyad və ya login…": (
            "Name, surname or login…",
            "Имя, фамилия или логин…",
            "Ad, soyad veya kullanıcı adı…",
        ),
        "Alıcı filtrləri": ("Recipient filters", "Фильтры получателей", "Alıcı filtreleri"),
        "Alıcılarda axtar": ("Search recipients", "Поиск среди получателей", "Alıcılarda ara"),
        "Axtarışa uyğun alıcı tapılmadı": (
            "No recipients match the search",
            "Получатели по запросу не найдены",
            "Aramaya uygun alıcı bulunamadı",
        ),
        "Bir dəfəlik popup": ("One-time popup", "Однократное всплывающее окно", "Tek seferlik açılır pencere"),
        "Elan yalnız «Elanlar» bölməsində və sayğacda görünür.": (
            "The announcement only appears in the “Announcements” section and the counter.",
            "Объявление видно только в разделе «Объявления» и в счётчике.",
            "Duyuru yalnızca “Duyurular” bölümünde ve sayaçta görünür.",
        ),
        "Girişdə necə göstərilsin": (
            "How to show it at sign-in",
            "Как показывать при входе",
            "Girişte nasıl gösterilsin",
        ),
        "Gözləyənlər": ("Pending", "Ожидают", "Bekleyenler"),
        "Hədəf auditoriyada heç kim yoxdur": (
            "Nobody is in the target audience",
            "В целевой аудитории никого нет",
            "Hedef kitlede kimse yok",
        ),
        "Hədəf auditoriyanın hamısı təsdiq edib": (
            "Everyone in the target audience has confirmed",
            "Все из целевой аудитории подтвердили",
            "Hedef kitlenin tamamı onayladı",
        ),
        "Hələ heç kim təsdiq etməyib": (
            "Nobody has confirmed yet",
            "Пока никто не подтвердил",
            "Henüz kimse onaylamadı",
        ),
        "Kim görəcək: hesablanır…": (
            "Who will see it: calculating…",
            "Кто увидит: подсчёт…",
            "Kim görecek: hesaplanıyor…",
        ),
        "Kim görəcək: say hesablanmadı — bir az sonra yenidən yoxlayın.": (
            "Who will see it: the count could not be calculated — check again a little later.",
            "Кто увидит: не удалось посчитать — проверьте чуть позже.",
            "Kim görecek: sayı hesaplanamadı — biraz sonra tekrar kontrol edin.",
        ),
        "Kim görəcək: əvvəlcə auditoriyanı seçin.": (
            "Who will see it: choose the audience first.",
            "Кто увидит: сначала выберите аудиторию.",
            "Kim görecek: önce hedef kitleyi seçin.",
        ),
        "Məcburi elan — təsdiq": (
            "Mandatory announcement — confirmations",
            "Обязательное объявление — подтверждения",
            "Zorunlu duyuru — onaylar",
        ),
        "Məcburi popup": ("Mandatory popup", "Обязательное всплывающее окно", "Zorunlu açılır pencere"),
        "Növbəti girişdə bir dəfə açılır — istifadəçi bağlaya bilər, sonra bir daha çıxmır.": (
            "Opens once at the next visit — the user can close it and it will not appear again.",
            "Открывается один раз при следующем входе — пользователь может закрыть его, и оно больше не появится.",
            "Bir sonraki girişte bir kez açılır — kullanıcı kapatabilir, sonra bir daha çıkmaz.",
        ),
        "Oxuyub, təsdiq gözləyir": (
            "Has read, awaiting confirmation",
            "Прочитал(а), ожидает подтверждения",
            "Okudu, onay bekliyor",
        ),
        "Popup və təsdiq": ("Popup and confirmation", "Всплывающее окно и подтверждение", "Açılır pencere ve onay"),
        "Popup yoxdur": ("No popup", "Без всплывающего окна", "Açılır pencere yok"),
        "Siyahını yükləmək alınmadı. Bir az sonra yenidən cəhd edin.": (
            "Could not load the list. Please try again a little later.",
            "Не удалось загрузить список. Повторите попытку чуть позже.",
            "Liste yüklenemedi. Biraz sonra tekrar deneyin.",
        ),
        "Təsdiq": ("Confirmed", "Подтвердили", "Onay"),
        "Təsdiq edib: %(day)s": ("Confirmed: %(day)s", "Подтвердил(а): %(day)s", "Onayladı: %(day)s"),
        "Təsdiq edən": ("Confirmed", "Подтвердили", "Onaylayan"),
        "Təsdiq edən: <strong>%(acked)s</strong> / %(total)s (hədəf)": (
            "Confirmed: <strong>%(acked)s</strong> / %(total)s (target)",
            "Подтвердили: <strong>%(acked)s</strong> / %(total)s (цель)",
            "Onaylayan: <strong>%(acked)s</strong> / %(total)s (hedef)",
        ),
        "Təsdiq edənlər": ("Confirmed", "Подтвердившие", "Onaylayanlar"),
        "Təsdiq edənlərin payı": ("Share of confirmations", "Доля подтвердивших", "Onaylayanların oranı"),
        "Təsdiq vəziyyəti": ("Confirmation status", "Статус подтверждения", "Onay durumu"),
        "bütün təşkilat": ("the whole organization", "вся организация", "tüm kurum"),
        "və daha %(n)s": ("and %(n)s more", "и ещё %(n)s", "ve %(n)s tane daha"),
        "İmtahan səhifələrində popup göstərilmir. Məcburi elanı kimin təsdiq etdiyini redaktə səhifəsində "
        "izləyə bilərsiniz.": (
            "Popups are never shown on exam pages. You can track who confirmed a mandatory announcement "
            "on its edit page.",
            "Всплывающие окна не показываются на страницах экзаменов. Кто подтвердил обязательное "
            "объявление, видно на странице редактирования.",
            "Sınav sayfalarında açılır pencere gösterilmez. Zorunlu duyuruyu kimin onayladığını düzenleme "
            "sayfasında takip edebilirsiniz.",
        ),
        "İstifadəçi «Tanış oldum» təsdiqi vermədən bağlaya bilməz — təsdiq edənədək hər səhifədə açılır.": (
            "The user cannot close it without confirming “I have read it” — it opens on every page until confirmed.",
            "Пользователь не сможет закрыть его без подтверждения «Ознакомлен(а)» — до подтверждения оно "
            "открывается на каждой странице.",
            "Kullanıcı “Bilgi edindim” onayı vermeden kapatamaz — onaylayana kadar her sayfada açılır.",
        ),
    },
    "announcements.model": {
        "Bir dəfəlik popup": ("One-time popup", "Однократное всплывающее окно", "Tek seferlik açılır pencere"),
        "Məcburi popup": ("Mandatory popup", "Обязательное всплывающее окно", "Zorunlu açılır pencere"),
        "Popup yoxdur": ("No popup", "Без всплывающего окна", "Açılır pencere yok"),
    },
    "announcements.popup": {
        "Bu elan məcburidir: oxuyun və tanış olduğunuzu təsdiq edin. Təsdiq edənədək pəncərə bağlanmır.": (
            "This announcement is mandatory: read it and confirm. The window cannot be closed until you confirm.",
            "Это обязательное объявление: прочитайте и подтвердите ознакомление. До подтверждения окно не закроется.",
            "Bu duyuru zorunludur: okuyun ve bilgi edindiğinizi onaylayın. Onaylayana kadar pencere kapanmaz.",
        ),
        "Elanı oxudum və tanış oldum": (
            "I have read and understood the announcement",
            "Я прочитал(а) объявление и ознакомлен(а)",
            "Duyuruyu okudum ve bilgi edindim",
        ),
        "Təsdiq edirəm": ("I confirm", "Подтверждаю", "Onaylıyorum"),
        "Təsdiq göndərilmədi. Bir az sonra yenidən cəhd edin.": (
            "The confirmation was not sent. Please try again a little later.",
            "Подтверждение не отправлено. Повторите попытку чуть позже.",
            "Onay gönderilemedi. Biraz sonra tekrar deneyin.",
        ),
        "Təsdiq tələb olunur": ("Confirmation required", "Требуется подтверждение", "Onay gerekli"),
    },
}

_SUMMARY = "Kim görəcək: %(who)s · %(where)s — təxminən %(n)s nəfər"

# Cəm formaları: (kontekst, tək, cəm) → dil → [forma0, forma1, ...]
PLURALS = {
    ("announcements.manage", "%(n)s nəfər", "%(n)s nəfər"): {
        "az": ["%(n)s nəfər", "%(n)s nəfər"],
        "en": ["%(n)s person", "%(n)s people"],
        "ru": ["%(n)s человек", "%(n)s человека", "%(n)s человек", "%(n)s человека"],
        "tr": ["%(n)s kişi", "%(n)s kişi"],
    },
    ("announcements.manage", _SUMMARY, _SUMMARY): {
        "az": [_SUMMARY, _SUMMARY],
        "en": [
            "Who will see it: %(who)s · %(where)s — about %(n)s person",
            "Who will see it: %(who)s · %(where)s — about %(n)s people",
        ],
        "ru": [
            "Кто увидит: %(who)s · %(where)s — примерно %(n)s человек",
            "Кто увидит: %(who)s · %(where)s — примерно %(n)s человека",
            "Кто увидит: %(who)s · %(where)s — примерно %(n)s человек",
            "Кто увидит: %(who)s · %(where)s — примерно %(n)s человека",
        ],
        "tr": [
            "Kim görecek: %(who)s · %(where)s — yaklaşık %(n)s kişi",
            "Kim görecek: %(who)s · %(where)s — yaklaşık %(n)s kişi",
        ],
    },
}


#: Bu skriptin öz mətnləri — dəyər həmişə buradakı ilə sinxronlanır (identity düzəlişləri).
FORCE = {"announcements.cabinet", "announcements.manage", "announcements.model", "announcements.popup"}


def _value(lang, az, row):
    return az if lang == "az" else row[LANGS.index(lang) - 1]


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ROWS.items():
        for msgid, row in items.items():
            want = _value(lang, msgid, row)
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=want))
                added += 1
            elif entry.msgstr != want and (
                not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete or ctx in FORCE
            ):
                entry.msgstr, entry.obsolete = want, False
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                changed += 1
    nplurals = 4 if lang == "ru" else 2
    for (ctx, singular, plural), forms in PLURALS.items():
        entry = index.get((ctx, singular))
        values = {i: form for i, form in enumerate(forms[lang][:nplurals])}
        if entry is None:
            po.append(polib.POEntry(msgctxt=ctx, msgid=singular, msgid_plural=plural, msgstr_plural=values))
            added += 1
        elif entry.msgstr_plural != values:
            entry.msgstr_plural = values
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
