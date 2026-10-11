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

#: Sahib 2026-10-11: «Rolu geri al» dialoqu — bölmə və qalan rollar.
MR = "accounts.manage_roles"
_MR = [
    _t("Bölmədən çıxarılır", "Removed from unit", "Удаляется из подразделения", "Birimden çıkarılıyor"),
    _t("Qalan rollar", "Remaining roles", "Остающиеся роли", "Kalan roller"),
    _t(
        "Yalnız bu üzvlük (rol + bölmə) söndürülür; şəxsin digər rolları toxunulmadan qalır. Əməl audit jurnalına yazılır.",
        "Only this membership (role + unit) is deactivated; the person's other roles stay unchanged. "
        "The action is written to the audit log.",
        "Отключается только это членство (роль + подразделение); остальные роли человека не затрагиваются. "
        "Действие записывается в журнал аудита.",
        "Yalnızca bu üyelik (rol + birim) devre dışı bırakılır; kişinin diğer rolleri değişmeden kalır. "
        "İşlem denetim günlüğüne yazılır.",
    ),
]

#: Sahib 2026-10-11: öz «Vəzifə»ni profil redaktəsindən yazmaq (RİM redaktə hüququ ilə).
PE = "profile.edit_v2"
_PE = [
    _t("Vəzifə", "Position", "Должность", "Görev"),
    _t(
        "məs: Rəqəmsal İnkişaf Mərkəzinin müdiri",
        "e.g. Head of the Digital Development Centre",
        "напр.: руководитель Центра цифрового развития",
        "ör.: Dijital Gelişim Merkezi müdürü",
    ),
    _t(
        "Profil kartında «Vəzifə» kimi görünür; boş qalsa ən yüksək rolunuz göstərilir.",
        "Shown as “Position” on your profile card; if empty, your highest role is shown.",
        "Отображается как «Должность» в карточке профиля; если пусто — показывается ваша высшая роль.",
        "Profil kartında «Görev» olarak görünür; boş kalırsa en yüksek rolünüz gösterilir.",
    ),
]

#: Sahib 2026-10-12: «Sistem tənzimləmələri» — sillabus saatları yükdən + açar dəyişəndə təsdiq.
RS = "accounts.runtime_settings"
_RS = [
    _t(
        "Sillabus dərs saatları yükdən",
        "Syllabus hours from the teaching load",
        "Часы силлабуса из учебной нагрузки",
        "Ders izlencesi saatleri yükten",
    ),
    _t(
        "Yanılıda sillabusun mühazirə/seminar/laboratoriya saatları kafedranın paylanmış yükündən gəlir və "
        "müəllim dəyişə bilmir; yükdə olmayan dərs növü (məs. lab yoxdursa) həftəlik planda görünmür və ona "
        "saat yazılmır. Yükdə sətir yoxdursa müəllim saatı özü seçir. Söndürülüdə əvvəlki qayda: əvvəl "
        "təsdiqlənmiş tədris planı, sonra yük; artıq növlər də göstərilir.",
        "When on, the syllabus lecture/seminar/lab hours come from the chair's distributed teaching load and the "
        "teacher cannot change them; a lesson type that is not in the load (e.g. no lab) is not shown in the weekly "
        "plan and no hours can be entered for it. If the load has no row, the teacher chooses the hours. When off, "
        "the previous rule applies: the approved curriculum first, then the load; extra types are shown too.",
        "Если включено, часы лекций/семинаров/лабораторных в силлабусе берутся из распределённой нагрузки кафедры, "
        "преподаватель не может их менять; вид занятий, которого нет в нагрузке (например, нет лабораторных), не "
        "показывается в недельном плане, и часы для него не вводятся. Если в нагрузке нет строки, преподаватель "
        "выбирает часы сам. Если выключено — прежнее правило: сначала утверждённый учебный план, затем нагрузка; "
        "лишние виды тоже показываются.",
        "Açıkken izlencenin teori/seminer/laboratuvar saatleri bölümün dağıtılmış ders yükünden gelir ve öğretim "
        "elemanı değiştiremez; yükte olmayan ders türü (ör. laboratuvar yoksa) haftalık planda görünmez ve ona saat "
        "yazılamaz. Yükte satır yoksa öğretim elemanı saati kendisi seçer. Kapalıyken önceki kural: önce onaylı "
        "öğretim planı, sonra yük; fazla türler de gösterilir.",
    ),
    _t("Dəyişikliyi təsdiqləyin", "Confirm the change", "Подтвердите изменение", "Değişikliği onaylayın"),
    _t("yandırılacaq.", "will be turned on.", "будет включено.", "açılacak."),
    _t("söndürüləcək.", "will be turned off.", "будет выключено.", "kapatılacak."),
    _t(
        "Dəyişiklik «Yadda saxla» basılandan sonra bütün istifadəçilər üçün qüvvəyə minir və audit jurnalına yazılır.",
        "The change takes effect for all users after you press “Save” and is written to the audit log.",
        "Изменение вступает в силу для всех пользователей после нажатия «Сохранить» и записывается в журнал аудита.",
        "Değişiklik «Kaydet»e basıldıktan sonra tüm kullanıcılar için geçerli olur ve denetim günlüğüne yazılır.",
    ),
    _t("Ləğv et", "Cancel", "Отмена", "İptal"),
    _t("Təsdiqlə", "Confirm", "Подтвердить", "Onayla"),
]

#: Spec etiketləri `core.runtime_settings` kontekstindədir (core/runtime_settings.py `_CTX`).
CRS = "core.runtime_settings"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    CRS: {row["az"]: row for row in _RS[:2]},
    RS: {row["az"]: row for row in _RS},
    PE: {row["az"]: row for row in _PE},
    MR: {row["az"]: row for row in _MR},
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
