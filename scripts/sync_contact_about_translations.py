"""sync_contact_about_translations.py

Adds the new About/Contact/Footer/Navbar strings to all four locale .po
files (az, en, ru, tr) — appends entries that are not already present.

Run manually after pulling a fresh checkout, before ``compilemessages``::

    python scripts/sync_contact_about_translations.py
    python manage.py compilemessages -l az -l en -l ru -l tr

This is idempotent: re-running it will not duplicate entries.
"""

from __future__ import annotations

from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"

# Translations dictionary: source string -> {locale: translation}
TRANSLATIONS = {
    # ---------- navbar ----------
    "contact": {  # contextual: nav
        "az": "Əlaqə",
        "en": "Contact",
        "ru": "Контакт",
        "tr": "İletişim",
    },
    # ---------- about ----------
    "EMSArena ilə tanış olun": {
        "az": "EMSArena ilə tanış olun",
        "en": "Meet EMSArena",
        "ru": "Знакомьтесь, EMSArena",
        "tr": "EMSArena ile tanışın",
    },
    "təhsilin yeni nəsil arenası": {
        "az": "təhsilin yeni nəsil arenası",
        "en": "the new arena for education",
        "ru": "новая арена для образования",
        "tr": "eğitimin yeni nesil arenası",
    },
    "Universitetlər, məktəblər, kurs mərkəzləri və müəllimlər üçün modern təhsil idarəetmə, LMS və onlayn imtahan platforması. Tək məkanda kurslar, imtahanlar, qiymətləndirmə, audit və AI köməkçi.": {
        "az": "Universitetlər, məktəblər, kurs mərkəzləri və müəllimlər üçün modern təhsil idarəetmə, LMS və onlayn imtahan platforması. Tək məkanda kurslar, imtahanlar, qiymətləndirmə, audit və AI köməkçi.",
        "en": "A modern education management, LMS and online exam platform for universities, schools, training centres and teachers. Courses, exams, assessment, audit and AI assistant in one place.",
        "ru": "Современная платформа управления образованием, LMS и онлайн-экзаменов для университетов, школ, учебных центров и преподавателей. Курсы, экзамены, оценивание, аудит и ИИ-помощник в одном месте.",
        "tr": "Üniversiteler, okullar, kurs merkezleri ve öğretmenler için modern eğitim yönetimi, LMS ve çevrimiçi sınav platformu. Kurslar, sınavlar, değerlendirme, denetim ve yapay zekâ asistanı tek yerde.",
    },
    "Pulsuz başla": {"az": "Pulsuz başla", "en": "Start free", "ru": "Начать бесплатно", "tr": "Ücretsiz başla"},
    "Bizimlə əlaqə": {"az": "Bizimlə əlaqə", "en": "Contact us", "ru": "Связаться с нами", "tr": "Bize ulaşın"},
    "Dəstəklənən dil": {
        "az": "Dəstəklənən dil",
        "en": "Supported languages",
        "ru": "Поддерживаемых языков",
        "tr": "Desteklenen dil",
    },
    "İmtahan növü": {"az": "İmtahan növü", "en": "Exam types", "ru": "Типов экзаменов", "tr": "Sınav türü"},
    "Platform əlçatanlığı": {
        "az": "Platform əlçatanlığı",
        "en": "Platform availability",
        "ru": "Доступность платформы",
        "tr": "Platform erişilebilirliği",
    },
    "Tenant izolyasiyası": {
        "az": "Tenant izolyasiyası",
        "en": "Tenant isolation",
        "ru": "Изоляция арендаторов",
        "tr": "Kiracı izolasyonu",
    },
    "Missiyamız": {"az": "Missiyamız", "en": "Our mission", "ru": "Наша миссия", "tr": "Misyonumuz"},
    "Vizyonumuz": {"az": "Vizyonumuz", "en": "Our vision", "ru": "Наше видение", "tr": "Vizyonumuz"},
    "Platformanın imkanları": {
        "az": "Platformanın imkanları",
        "en": "Platform capabilities",
        "ru": "Возможности платформы",
        "tr": "Platform yetenekleri",
    },
    "Kurs və qruplar": {
        "az": "Kurs və qruplar",
        "en": "Courses and groups",
        "ru": "Курсы и группы",
        "tr": "Kurslar ve gruplar",
    },
    "Multi-tenant memarlıq": {
        "az": "Multi-tenant memarlıq",
        "en": "Multi-tenant architecture",
        "ru": "Multi-tenant архитектура",
        "tr": "Çok kiracılı mimari",
    },
    "Rol-əsaslı icazələr": {
        "az": "Rol-əsaslı icazələr",
        "en": "Role-based permissions",
        "ru": "Ролевые разрешения",
        "tr": "Rol tabanlı izinler",
    },
    "İmtahanlar və qiymətləndirmə": {
        "az": "İmtahanlar və qiymətləndirmə",
        "en": "Exams and assessment",
        "ru": "Экзамены и оценивание",
        "tr": "Sınavlar ve değerlendirme",
    },
    "Audit və təhlükəsizlik": {
        "az": "Audit və təhlükəsizlik",
        "en": "Audit and security",
        "ru": "Аудит и безопасность",
        "tr": "Denetim ve güvenlik",
    },
    "AI köməkçi": {"az": "AI köməkçi", "en": "AI assistant", "ru": "ИИ-помощник", "tr": "Yapay zekâ asistanı"},
    "Komanda": {"az": "Komanda", "en": "Team", "ru": "Команда", "tr": "Ekip"},
    "Pulsuz qeydiyyat": {
        "az": "Pulsuz qeydiyyat",
        "en": "Sign up free",
        "ru": "Бесплатная регистрация",
        "tr": "Ücretsiz kayıt",
    },
    "Demo tələb et": {"az": "Demo tələb et", "en": "Request a demo", "ru": "Запросить демо", "tr": "Demo talep et"},
    # ---------- contact ----------
    "Əlaqə": {"az": "Əlaqə", "en": "Contact", "ru": "Контакты", "tr": "İletişim"},
    "Bizimlə əlaqə saxlayın": {
        "az": "Bizimlə əlaqə saxlayın",
        "en": "Get in touch with us",
        "ru": "Свяжитесь с нами",
        "tr": "Bizimle iletişime geçin",
    },
    "Suallarınız, təklifləriniz və əməkdaşlıq istəkləriniz üçün aşağıdakı formadan və ya birbaşa əlaqə vasitələrindən istifadə edin. 24 saat ərzində cavab veririk.": {
        "az": "Suallarınız, təklifləriniz və əməkdaşlıq istəkləriniz üçün aşağıdakı formadan və ya birbaşa əlaqə vasitələrindən istifadə edin. 24 saat ərzində cavab veririk.",
        "en": "Use the form below or any of the direct channels for questions, suggestions and partnership requests. We respond within 24 hours.",
        "ru": "Используйте форму ниже или прямые каналы связи для вопросов, предложений и заявок на сотрудничество. Отвечаем в течение 24 часов.",
        "tr": "Soru, öneri ve iş birliği talepleri için aşağıdaki formu veya doğrudan iletişim kanallarını kullanın. 24 saat içinde yanıtlıyoruz.",
    },
    "Email": {"az": "Email", "en": "Email", "ru": "Email", "tr": "E-posta"},
    "info – ümumi, support – texniki dəstək": {
        "az": "info – ümumi, support – texniki dəstək",
        "en": "info – general, support – technical",
        "ru": "info – общие, support – техподдержка",
        "tr": "info – genel, support – teknik",
    },
    "Tez cavab üçün ən sürətli kanal": {
        "az": "Tez cavab üçün ən sürətli kanal",
        "en": "Fastest channel for quick replies",
        "ru": "Самый быстрый канал для ответов",
        "tr": "Hızlı yanıt için en hızlı kanal",
    },
    "Xəbərlər və yeniliklər": {
        "az": "Xəbərlər və yeniliklər",
        "en": "News and updates",
        "ru": "Новости и обновления",
        "tr": "Haberler ve güncellemeler",
    },
    "Bizi izləyin": {"az": "Bizi izləyin", "en": "Follow us", "ru": "Подписывайтесь", "tr": "Bizi takip edin"},
    "Mesajınız göndərildi!": {
        "az": "Mesajınız göndərildi!",
        "en": "Your message has been sent!",
        "ru": "Ваше сообщение отправлено!",
        "tr": "Mesajınız gönderildi!",
    },
    "Diqqətiniz üçün təşəkkür edirik. Tezliklə sizinlə əlaqə saxlayacağıq.": {
        "az": "Diqqətiniz üçün təşəkkür edirik. Tezliklə sizinlə əlaqə saxlayacağıq.",
        "en": "Thank you for reaching out. We will get back to you shortly.",
        "ru": "Спасибо за обращение. Мы свяжемся с вами в ближайшее время.",
        "tr": "İlginiz için teşekkür ederiz. Kısa süre içinde size geri döneceğiz.",
    },
    "Yeni mesaj göndər": {
        "az": "Yeni mesaj göndər",
        "en": "Send another message",
        "ru": "Отправить ещё",
        "tr": "Yeni mesaj gönder",
    },
    "Bizə yazın": {"az": "Bizə yazın", "en": "Send us a message", "ru": "Напишите нам", "tr": "Bize yazın"},
    "Formadakı bütün məlumatlar konfidensial saxlanılır.": {
        "az": "Formadakı bütün məlumatlar konfidensial saxlanılır.",
        "en": "All form data is kept confidential.",
        "ru": "Все данные формы остаются конфиденциальными.",
        "tr": "Formdaki tüm bilgiler gizli tutulur.",
    },
    "Ad Soyad": {"az": "Ad Soyad", "en": "Full name", "ru": "Имя и фамилия", "tr": "Ad Soyad"},
    "Telefon": {"az": "Telefon", "en": "Phone", "ru": "Телефон", "tr": "Telefon"},
    "Mövzu": {"az": "Mövzu", "en": "Subject", "ru": "Тема", "tr": "Konu"},
    "Mesaj": {"az": "Mesaj", "en": "Message", "ru": "Сообщение", "tr": "Mesaj"},
    "Ən azı 10, ən çoxu 5000 simvol": {
        "az": "Ən azı 10, ən çoxu 5000 simvol",
        "en": "Between 10 and 5000 characters",
        "ru": "От 10 до 5000 символов",
        "tr": "En az 10, en fazla 5000 karakter",
    },
    "Mesajı göndər": {"az": "Mesajı göndər", "en": "Send message", "ru": "Отправить", "tr": "Mesajı gönder"},
    "Tez-tez verilən suallar": {
        "az": "Tez-tez verilən suallar",
        "en": "Frequently asked questions",
        "ru": "Часто задаваемые вопросы",
        "tr": "Sıkça sorulan sorular",
    },
    # ---------- footer ----------
    "Təhsil idarəetmə və onlayn imtahan platforması. Universitetlər, məktəblər və kurs mərkəzləri üçün modern LMS həlli.": {
        "az": "Təhsil idarəetmə və onlayn imtahan platforması. Universitetlər, məktəblər və kurs mərkəzləri üçün modern LMS həlli.",
        "en": "Education management and online exam platform. A modern LMS for universities, schools and training centres.",
        "ru": "Платформа управления образованием и онлайн-экзаменов. Современная LMS для университетов, школ и учебных центров.",
        "tr": "Eğitim yönetimi ve çevrimiçi sınav platformu. Üniversiteler, okullar ve kurs merkezleri için modern LMS çözümü.",
    },
    "Sosial şəbəkələr": {
        "az": "Sosial şəbəkələr",
        "en": "Social networks",
        "ru": "Социальные сети",
        "tr": "Sosyal ağlar",
    },
    "Platforma": {"az": "Platforma", "en": "Platform", "ru": "Платформа", "tr": "Platform"},
    "Ana səhifə": {"az": "Ana səhifə", "en": "Home", "ru": "Главная", "tr": "Ana sayfa"},
    "Haqqımızda": {"az": "Haqqımızda", "en": "About", "ru": "О нас", "tr": "Hakkımızda"},
    "İmtahanlar": {"az": "İmtahanlar", "en": "Exams", "ru": "Экзамены", "tr": "Sınavlar"},
    "Resurslar": {"az": "Resurslar", "en": "Resources", "ru": "Ресурсы", "tr": "Kaynaklar"},
    "Profilim": {"az": "Profilim", "en": "My profile", "ru": "Мой профиль", "tr": "Profilim"},
    "Daxil ol": {"az": "Daxil ol", "en": "Sign in", "ru": "Войти", "tr": "Giriş yap"},
    "Qeydiyyat": {"az": "Qeydiyyat", "en": "Sign up", "ru": "Регистрация", "tr": "Kayıt ol"},
    "Texnologiya": {"az": "Texnologiya", "en": "Technology", "ru": "Технологии", "tr": "Teknoloji"},
    "Təhsil": {"az": "Təhsil", "en": "Education", "ru": "Образование", "tr": "Eğitim"},
    "Sayt xəritəsi": {"az": "Sayt xəritəsi", "en": "Sitemap", "ru": "Карта сайта", "tr": "Site haritası"},
    "Bütün hüquqlar qorunur.": {
        "az": "Bütün hüquqlar qorunur.",
        "en": "All rights reserved.",
        "ru": "Все права защищены.",
        "tr": "Tüm hakları saklıdır.",
    },
    "Hazırladı": {"az": "Hazırladı", "en": "Built by", "ru": "Создал", "tr": "Hazırlayan"},
}


def escape_po(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def append_entry(po_path: Path, msgid: str, msgstr: str) -> bool:
    """Return True if a new entry was appended, False if already present."""
    content = po_path.read_text(encoding="utf-8")
    needle = f'msgid "{escape_po(msgid)}"\nmsgstr '
    if needle in content:
        return False
    entry = f'\n#: contact/about/footer/navbar\nmsgid "{escape_po(msgid)}"\nmsgstr "{escape_po(msgstr)}"\n'
    with po_path.open("a", encoding="utf-8") as f:
        f.write(entry)
    return True


def main() -> None:
    languages = ["az", "en", "ru", "tr"]
    totals = {lang: 0 for lang in languages}
    for lang in languages:
        po = LOCALE_DIR / lang / "LC_MESSAGES" / "django.po"
        if not po.exists():
            print(f"!! Missing {po}")
            continue
        for src, by_lang in TRANSLATIONS.items():
            tr = by_lang.get(lang, "")
            if append_entry(po, src, tr):
                totals[lang] += 1
    for lang, n in totals.items():
        print(f"  {lang}: appended {n} entries")
    print("\nNow run: python manage.py compilemessages")


if __name__ == "__main__":
    main()
