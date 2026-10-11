#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-11: «Kadr analitikası» — hesab / inzibati vəzifə / dərəcə / yük bandı filtrləri,
sütun sıralaması, qısa ştat sütunu (1 · 0,5 · s/h) və müəllimin ştat tarixçəsi («Tarixçə»).

Əlavə olunan mətnlər (`accounts.hr_analytics`): filtr etiketləri və seçimləri, tarixçə blokunun başlıq və
boş vəziyyət mətnləri, ixracın «Ştat tarixçəsi» vərəqi.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_11_hr_filters.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


HR = "accounts.hr_analytics"

_HR = [
    # ── hesab vəziyyəti filtri ────────────────────────────────────────────
    _t("Hesab vəziyyəti", "Account state", "Состояние аккаунта", "Hesap durumu"),
    _t(
        "Dayandırılıb (blok + arxiv)",
        "Suspended (blocked + archived)",
        "Приостановлен (блок + архив)",
        "Durduruldu (engelli + arşiv)",
    ),
    _t("Bloklanıb", "Blocked", "Заблокирован", "Engellendi"),
    _t("Arxivdə", "Archived", "В архиве", "Arşivde"),
    _t(
        "Aktivləşdirilməyib (ilkin parolda)",
        "Not activated (initial password)",
        "Не активирован (начальный пароль)",
        "Etkinleştirilmedi (ilk parola)",
    ),
    _t("Bu il yeni hesab", "New account this year", "Новый аккаунт в этом году", "Bu yıl yeni hesap"),
    # ── inzibati vəzifə ──────────────────────────────────────────────────
    _t("İnzibati vəzifə", "Administrative position", "Административная должность", "İdari görev"),
    _t("İnzibati vəzifələr", "Administrative positions", "Административные должности", "İdari görevler"),
    _t(
        "İnzibati vəzifəsi var",
        "Has an administrative position",
        "Есть административная должность",
        "İdari görevi var",
    ),
    _t(
        "İnzibati vəzifəsi yoxdur",
        "No administrative position",
        "Нет административной должности",
        "İdari görevi yok",
    ),
    _t(
        "İnzibati vəzifə qeyd olunmayıb.",
        "No administrative position recorded.",
        "Административная должность не указана.",
        "İdari görev kaydedilmemiş.",
    ),
    _t(
        "profildəki «Vəzifə» sahəsindən",
        "from the “Position” field of the profile",
        "из поля «Должность» в профиле",
        "profildeki «Görev» alanından",
    ),
    _t(
        "%(since)s tarixindən",
        "since %(since)s",
        "с %(since)s",
        "%(since)s tarihinden beri",
    ),
    _t(
        "%(year)s yük profilindəki vəzifə: %(position)s",
        "Position in the %(year)s workload profile: %(position)s",
        "Должность в профиле нагрузки %(year)s: %(position)s",
        "%(year)s yük profilindeki görev: %(position)s",
    ),
    _t("Vəzifə (yük profili)", "Position (workload profile)", "Должность (профиль нагрузки)", "Görev (yük profili)"),
    # ── digər filtrlər ───────────────────────────────────────────────────
    _t("Yük bandı", "Load band", "Диапазон нагрузки", "Yük aralığı"),
    _t("filtr tətbiq olunub", "filter applied", "фильтр применён", "filtre uygulandı"),
    _t(
        "Hesab kartına klik — siyahını həmin vəziyyətə görə süzür",
        "Click an account card to filter the list by that state",
        "Клик по карточке аккаунта фильтрует список по этому состоянию",
        "Hesap kartına tıklayınca liste o duruma göre süzülür",
    ),
    # ── ştat sütunu və tarixçə ───────────────────────────────────────────
    _t("s/h", "hourly", "почас.", "s/ü"),
    _t("Tarixçə", "History", "История", "Geçmiş"),
    _t("Ştat tarixçəsi", "Staffing history", "История штата", "Kadro geçmişi"),
    _t(
        "Ştat / vəzifə dəyişikliyi",
        "Staffing / position change",
        "Изменение штата / должности",
        "Kadro / görev değişikliği",
    ),
    _t(
        "Heç bir tədris ili üçün yük profili (ştat) yoxdur.",
        "No workload profile (staffing) for any academic year.",
        "Нет профиля нагрузки (штата) ни за один учебный год.",
        "Hiçbir eğitim yılı için yük profili (kadro) yok.",
    ),
    _t(
        "%(position)s · norma %(norm)s saat",
        "%(position)s · norm %(norm)s h",
        "%(position)s · норма %(norm)s ч",
        "%(position)s · norm %(norm)s saat",
    ),
    _t(
        "Əvvəlki ilə nisbətən dəyişib",
        "Changed compared with the previous year",
        "Изменилось по сравнению с предыдущим годом",
        "Önceki yıla göre değişti",
    ),
]

#: Sahib 2026-10-11: rektordan yuxarı «Qəyyumlar Şurasının sədri» rolu (organizations 0059).
ROLES = "roles.org_display_name"
_ROLES = [
    _t(
        "Qəyyumlar Şurasının sədri",
        "Chair of the Board of Trustees",
        "Председатель Попечительского совета",
        "Mütevelli Heyeti Başkanı",
    ),
]

#: Sahib 2026-10-11: RİM mərkəzi — ilk açılışda siyahı, hesab növü / vəziyyət / sıralama filtrləri.
RIM = "profile.rim"
_RIM = [
    _t("Hesab növü", "Account type", "Тип аккаунта", "Hesap türü"),
    _t("Hamısı", "All", "Все", "Tümü"),
    _t("Tələbələr", "Students", "Студенты", "Öğrenciler"),
    _t("Müəllimlər", "Teachers", "Преподаватели", "Öğretim elemanları"),
    _t("Heyət (inzibati)", "Staff (administrative)", "Персонал (административный)", "Personel (idari)"),
    _t("Rolu olmayanlar", "Without a role", "Без роли", "Rolü olmayanlar"),
    _t("Vəziyyət", "State", "Состояние", "Durum"),
    _t("İlk giriş gözlənilir", "Awaiting first sign-in", "Ожидается первый вход", "İlk giriş bekleniyor"),
    _t("Heç daxil olmayıb", "Never signed in", "Ни разу не входил", "Hiç giriş yapmadı"),
    _t("Email təsdiqlənməyib", "Email not verified", "Email не подтверждён", "E-posta doğrulanmadı"),
    _t("Sıralama", "Sort", "Сортировка", "Sıralama ölçütü"),
    _t("Avtomatik", "Automatic", "Автоматически", "Otomatik"),
    _t("Ən yeni hesablar", "Newest accounts", "Новые аккаунты", "En yeni hesaplar"),
    _t("Soyad (A→Z)", "Surname (A→Z)", "Фамилия (А→Я)", "Soyadı (A→Z)"),
    _t("Son giriş", "Last sign-in", "Последний вход", "Son oturum açma"),
    _t("Filtrləri sıfırla", "Reset filters", "Сбросить фильтры", "Filtreleri sıfırla"),
    _t("Yüklənir…", "Loading…", "Загрузка…", "Yükleniyor…"),
    _t(
        "Ən son yaradılan hesablar göstərilir — ad, soyad, email və ya FİN yazaraq axtarın.",
        "Showing the most recently created accounts — search by name, surname, email or FIN.",
        "Показаны последние созданные аккаунты — ищите по имени, фамилии, email или FIN.",
        "En son oluşturulan hesaplar gösteriliyor — ad, soyad, e-posta veya FİN ile arayın.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    HR: {row["az"]: row for row in _HR},
    ROLES: {row["az"]: row for row in _ROLES},
    RIM: {row["az"]: row for row in _RIM},
}

#: «Yük bandı» türkcədə əvvəl az ilə eyni yazılmışdı (i18n gate: identity borcu).
FORCE = {(HR, "Yük bandı")}


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
