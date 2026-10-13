#!/usr/bin/env python3
"""EMSArena i18n — dərs yükü norması «Sistem tənzimləmələri»ndən (sahib 2026-10-14).

Əlavə olunan mətnlər:
  * `core.runtime_settings` — «Dərs yükü norması və ştat» qrupu: 1 ştat / 0,5 ştat / inzibati norma,
    ştat vahidinin ən az / ən çox həddi (etiket + izah + «ştat» vahidi);
  * `accounts.runtime_settings` — «ən az > ən çox» xətası;
  * `workload.norms` — norma qeydi (kafedra profili, yük bölgüsü, kadr analitikası) və ştat həddi xətaları;
  * `accounts.chair_profile` / `accounts.hr_analytics` — yenilənmiş izah mətnləri.

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_norms_2026_10_14.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RS = "core.runtime_settings"
RSA = "accounts.runtime_settings"
NORMS = "workload.norms"
CHAIR = "accounts.chair_profile"
HR = "accounts.hr_analytics"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    RS: {
        "Dərs yükü norması və ştat": {
            "en": "Teaching load norm and staff rate",
            "ru": "Норма учебной нагрузки и ставки",
            "tr": "Ders yükü normu ve kadro oranı",
            "de": "Lehrdeputat und Stellenanteil",
        },
        "İllik norma — 1 ştat": {
            "en": "Annual norm — 1.0 staff rate",
            "ru": "Годовая норма — 1 ставка",
            "tr": "Yıllık norm — 1 kadro",
            "de": "Jahresdeputat — 1,0 Stelle",
        },
        (
            "NK №215: bir ştat üzrə illik dərs yükü norması. 0,25 / 0,75 / 1,25 / 1,5 ştat üçün norma bu dəyərin "
            "ştat payına hasilidir (məs. 0,75 ştat → 0,75 × norma). Yük profili olmayan müəllimə də bu norma "
            "tətbiq olunur."
        ): {
            "en": (
                "Cabinet of Ministers Decision No. 215: annual teaching load norm for one full staff rate. For 0.25 / "
                "0.75 / 1.25 / 1.5 rates the norm is this value multiplied by the rate (e.g. 0.75 rate → 0.75 × "
                "norm). Teachers without a workload profile also get this norm."
            ),
            "ru": (
                "Постановление КМ №215: годовая норма учебной нагрузки на одну ставку. Для 0,25 / 0,75 / 1,25 / 1,5 "
                "ставки норма равна этому значению, умноженному на долю ставки (напр. 0,75 ставки → 0,75 × норма). "
                "Эта норма применяется и к преподавателю без профиля нагрузки."
            ),
            "tr": (
                "BK 215 sayılı karar: bir tam kadro için yıllık ders yükü normu. 0,25 / 0,75 / 1,25 / 1,5 kadro için "
                "norm bu değerin kadro oranıyla çarpımıdır (örn. 0,75 kadro → 0,75 × norm). Yük profili olmayan "
                "öğretmene de bu norm uygulanır."
            ),
            "de": (
                "Ministerratsbeschluss Nr. 215: jährliches Lehrdeputat für eine volle Stelle. Für 0,25 / 0,75 / 1,25 / "
                "1,5 Stellen ist das Deputat dieser Wert mal Stellenanteil (z. B. 0,75 Stelle → 0,75 × Deputat). "
                "Lehrkräfte ohne Lastprofil erhalten ebenfalls dieses Deputat."
            ),
        },
        "İllik norma — 0,5 ştat": {
            "en": "Annual norm — 0.5 staff rate",
            "ru": "Годовая норма — 0,5 ставки",
            "tr": "Yıllık norm — 0,5 kadro",
            "de": "Jahresdeputat — 0,5 Stelle",
        },
        "Yarım ştatda işləyən müəllimin illik norması — 1 ştat normasından avtomatik hesablanmır, ayrıca qeyd olunur.": {
            "en": (
                "Annual norm for a teacher on a half staff rate — it is not derived automatically from the full-rate "
                "norm but set separately."
            ),
            "ru": (
                "Годовая норма преподавателя на полставки — не вычисляется автоматически из нормы на 1 ставку, "
                "задаётся отдельно."
            ),
            "tr": (
                "Yarım kadroda çalışan öğretmenin yıllık normu — tam kadro normundan otomatik hesaplanmaz, ayrıca "
                "belirlenir."
            ),
            "de": (
                "Jahresdeputat einer Lehrkraft mit halber Stelle — wird nicht automatisch aus dem Deputat der vollen "
                "Stelle abgeleitet, sondern separat festgelegt."
            ),
        },
        "İllik norma — inzibati vəzifəli müəllim": {
            "en": "Annual norm — teacher with an administrative position",
            "ru": "Годовая норма — преподаватель с административной должностью",
            "tr": "Yıllık norm — idari görevli öğretmen",
            "de": "Jahresdeputat — Lehrkraft mit Verwaltungsfunktion",
        },
        (
            "Dərs deməklə yanaşı inzibati vəzifə tutan müəllim (rektor, prorektor, dekan, dekan müavini, kafedra "
            "müdiri, şöbə müdiri, mərkəz rəhbəri, tyutor və s. — müəllimlikdən başqa aktiv rolu olan) üçün illik "
            "norma; ştat payından asılı deyil."
        ): {
            "en": (
                "Annual norm for a teacher who also holds an administrative position (rector, vice-rector, dean, "
                "vice-dean, head of chair, head of department, centre head, tutor, etc. — anyone with an active role "
                "other than teaching); it does not depend on the staff rate."
            ),
            "ru": (
                "Годовая норма для преподавателя, занимающего также административную должность (ректор, проректор, "
                "декан, заместитель декана, заведующий кафедрой, начальник отдела, руководитель центра, тьютор и "
                "т. п. — с активной ролью помимо преподавательской); не зависит от доли ставки."
            ),
            "tr": (
                "Ders vermenin yanında idari görev de yürüten öğretmen (rektör, rektör yardımcısı, dekan, dekan "
                "yardımcısı, bölüm başkanı, birim müdürü, merkez müdürü, tutor vb. — öğretmenlik dışında aktif rolü "
                "olan) için yıllık norm; kadro oranına bağlı değildir."
            ),
            "de": (
                "Jahresdeputat für Lehrkräfte, die zusätzlich eine Verwaltungsfunktion ausüben (Rektor, Prorektor, "
                "Dekan, Prodekan, Lehrstuhlleiter, Abteilungsleiter, Zentrumsleiter, Tutor usw. — mit einer aktiven "
                "Rolle außer der Lehre); unabhängig vom Stellenanteil."
            ),
        },
        "Bir müəllimə ən az ştat vahidi": {
            "en": "Minimum staff rate per teacher",
            "ru": "Минимальная доля ставки на преподавателя",
            "tr": "Öğretmen başına en az kadro oranı",
            "de": "Mindeststellenanteil je Lehrkraft",
        },
        (
            "Forma 7 siyahısından və ya başqa idxaldan gələn ştat payı bundan azdırsa yük profilinə yazılmır "
            "(hesabatda göstərilir). Saathesabı müəllimə (ştatsız) aid deyil."
        ): {
            "en": (
                "A staff rate from the Form 7 list or another import below this value is not written to the workload "
                "profile (it is shown in the report). Does not apply to hourly-paid teachers (no staff rate)."
            ),
            "ru": (
                "Доля ставки из списка Формы 7 или другого импорта ниже этого значения не записывается в профиль "
                "нагрузки (показывается в отчёте). Не относится к почасовикам (без ставки)."
            ),
            "tr": (
                "Form 7 listesinden veya başka bir içe aktarımdan gelen kadro oranı bundan azsa yük profiline "
                "yazılmaz (raporda gösterilir). Saat ücretli (kadrosuz) öğretmene uygulanmaz."
            ),
            "de": (
                "Ein Stellenanteil aus der Liste Formular 7 oder einem anderen Import unter diesem Wert wird nicht "
                "ins Lastprofil geschrieben (er erscheint im Bericht). Gilt nicht für Lehrbeauftragte auf "
                "Stundenbasis (ohne Stelle)."
            ),
        },
        "ştat": {
            "en": "rate",
            "ru": "ставки",
            "tr": "kadro",
            "de": "Stelle",
        },
        "Bir müəllimə ən çox ştat vahidi": {
            "en": "Maximum staff rate per teacher",
            "ru": "Максимальная доля ставки на преподавателя",
            "tr": "Öğretmen başına en çok kadro oranı",
            "de": "Höchststellenanteil je Lehrkraft",
        },
        (
            "KQ-12: bir müəllim ən çox 1,5 ştat tuta bilər. Bundan çox ştat payı yük profilinə yazılmır "
            "(hesabatda göstərilir)."
        ): {
            "en": (
                "KQ-12: a teacher may hold at most 1.5 staff rates. A higher rate is not written to the workload "
                "profile (it is shown in the report)."
            ),
            "ru": (
                "KQ-12: преподаватель может занимать не более 1,5 ставки. Большая доля не записывается в профиль "
                "нагрузки (показывается в отчёте)."
            ),
            "tr": (
                "KQ-12: bir öğretmen en fazla 1,5 kadro tutabilir. Daha yüksek oran yük profiline yazılmaz "
                "(raporda gösterilir)."
            ),
            "de": (
                "KQ-12: Eine Lehrkraft darf höchstens 1,5 Stellen innehaben. Ein höherer Anteil wird nicht ins "
                "Lastprofil geschrieben (er erscheint im Bericht)."
            ),
        },
    },
    RSA: {
        "Ən az dəyər ən çox dəyərdən böyük ola bilməz.": {
            "en": "The minimum value cannot be greater than the maximum value.",
            "ru": "Минимальное значение не может быть больше максимального.",
            "tr": "En küçük değer en büyük değerden büyük olamaz.",
            "de": "Der Mindestwert darf nicht größer als der Höchstwert sein.",
        },
    },
    NORMS: {
        (
            "Norma: 1 ştat — %(full)s saat, 0,5 ştat — %(half)s saat, inzibati vəzifəli — %(admin)s saat; digər "
            "ştat payları 1 ştat normasına mütənasibdir. Ştat həddi %(min)s–%(max)s (Sistem tənzimləmələri)."
        ): {
            "en": (
                "Norm: 1.0 rate — %(full)s hours, 0.5 rate — %(half)s hours, administrative position — %(admin)s "
                "hours; other rates are proportional to the 1.0 norm. Staff rate limits %(min)s–%(max)s (System "
                "settings)."
            ),
            "ru": (
                "Норма: 1 ставка — %(full)s ч, 0,5 ставки — %(half)s ч, с административной должностью — %(admin)s "
                "ч; другие доли пропорциональны норме на 1 ставку. Пределы ставки %(min)s–%(max)s (Системные "
                "настройки)."
            ),
            "tr": (
                "Norm: 1 kadro — %(full)s saat, 0,5 kadro — %(half)s saat, idari görevli — %(admin)s saat; diğer "
                "kadro oranları 1 kadro normuyla orantılıdır. Kadro sınırı %(min)s–%(max)s (Sistem ayarları)."
            ),
            "de": (
                "Deputat: 1,0 Stelle — %(full)s Stunden, 0,5 Stelle — %(half)s Stunden, mit Verwaltungsfunktion — "
                "%(admin)s Stunden; andere Anteile proportional zum Deputat der vollen Stelle. Stellengrenzen "
                "%(min)s–%(max)s (Systemeinstellungen)."
            ),
        },
        "Ştat payı %(value)s icazə verilən %(min)s–%(max)s aralığından kənardır (Sistem tənzimləmələri).": {
            "en": "Staff rate %(value)s is outside the allowed range %(min)s–%(max)s (System settings).",
            "ru": "Доля ставки %(value)s вне допустимого диапазона %(min)s–%(max)s (Системные настройки).",
            "tr": "Kadro oranı %(value)s izin verilen %(min)s–%(max)s aralığının dışında (Sistem ayarları).",
            "de": "Stellenanteil %(value)s liegt außerhalb des zulässigen Bereichs %(min)s–%(max)s (Systemeinstellungen).",
        },
        "Ştat payı rəqəm olmalıdır.": {
            "en": "The staff rate must be a number.",
            "ru": "Доля ставки должна быть числом.",
            "tr": "Kadro oranı bir sayı olmalıdır.",
            "de": "Der Stellenanteil muss eine Zahl sein.",
        },
    },
    CHAIR: {
        (
            "Kafedranın ştat cədvəli, müəllim heyəti və illik yük riski. Norma ştat payına və inzibati vəzifəyə görə "
            "hesablanır."
        ): {
            "en": (
                "The chair's staffing table, teaching staff and annual load risk. The norm is calculated from the "
                "staff rate and administrative position."
            ),
            "ru": (
                "Штатное расписание кафедры, преподавательский состав и риск годовой нагрузки. Норма рассчитывается "
                "по доле ставки и административной должности."
            ),
            "tr": (
                "Bölümün kadro tablosu, öğretim kadrosu ve yıllık yük riski. Norm, kadro oranına ve idari göreve "
                "göre hesaplanır."
            ),
            "de": (
                "Stellenplan des Lehrstuhls, Lehrpersonal und Jahreslastrisiko. Das Deputat wird nach Stellenanteil "
                "und Verwaltungsfunktion berechnet."
            ),
        },
    },
    HR: {
        (
            "Yük — dərs yükü bölgüsündə (paylanmış / düzəlişli tapşırıqlar) müəllimə yazılmış illik saat; norma — "
            "ştat payına və inzibati vəzifəyə görə illik norma. Doluluq kafedra cəmindən hesablanır."
        ): {
            "en": (
                "Load — annual hours assigned to the teacher in the workload distribution (distributed / amended "
                "tasks); norm — the annual norm by staff rate and administrative position. Fill rate is computed "
                "from the chair total."
            ),
            "ru": (
                "Нагрузка — годовые часы, закреплённые за преподавателем в распределении нагрузки (распределённые / "
                "изменённые задания); норма — годовая норма по доле ставки и административной должности. "
                "Заполненность считается по итогу кафедры."
            ),
            "tr": (
                "Yük — ders yükü dağılımında (dağıtılmış / düzeltilmiş görevler) öğretmene yazılan yıllık saat; norm "
                "— kadro oranına ve idari göreve göre yıllık norm. Doluluk bölüm toplamından hesaplanır."
            ),
            "de": (
                "Last — der Lehrkraft in der Deputatsverteilung zugewiesene Jahresstunden (verteilte / geänderte "
                "Aufgaben); Deputat — Jahresdeputat nach Stellenanteil und Verwaltungsfunktion. Die Auslastung wird "
                "aus der Lehrstuhlsumme berechnet."
            ),
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
