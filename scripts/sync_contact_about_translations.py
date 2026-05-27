"""sync_contact_about_translations.py

Adds the new About/Contact/Footer/Navbar strings to all four locale .po
files (az, en, ru, tr) — appends entries that are not already present.

Run manually after pulling a fresh checkout, before ``compilemessages``::

    python scripts/sync_contact_about_translations.py
    python manage.py compilemessages -l az -l en -l ru -l tr

This is idempotent: re-running it will not duplicate entries.
"""

from __future__ import annotations

import ast
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

TRANSLATIONS.update(
    {
        # ---------- about: remaining visible/SEO strings ----------
        "EMSArena loqo": {
            "az": "EMSArena loqo",
            "en": "EMSArena logo",
            "ru": "Логотип EMSArena",
            "tr": "EMSArena logosu",
        },
        "EMSArena platform xüsusiyyətləri": {
            "az": "EMSArena platform xüsusiyyətləri",
            "en": "EMSArena platform features",
            "ru": "Возможности платформы EMSArena",
            "tr": "EMSArena platform özellikleri",
        },
        "Missiya və Vizyon": {
            "az": "Missiya və Vizyon",
            "en": "Mission and vision",
            "ru": "Миссия и видение",
            "tr": "Misyon ve vizyon",
        },
        "Təhsil müəssisələrini bürokratiyadan azad edib müəllim-tələbə qarşılıqlı əlaqəsinə diqqət yetirməyə imkan vermək. Tək, etibarlı və ölçəklənən platforma ilə tədrisi sadələşdirmək.": {
            "az": "Təhsil müəssisələrini bürokratiyadan azad edib müəllim-tələbə qarşılıqlı əlaqəsinə diqqət yetirməyə imkan vermək. Tək, etibarlı və ölçəklənən platforma ilə tədrisi sadələşdirmək.",
            "en": "Free educational institutions from bureaucracy and help them focus on teacher-student interaction. Simplify teaching with one reliable and scalable platform.",
            "ru": "Освободить образовательные организации от бюрократии и помочь им сосредоточиться на взаимодействии преподавателей и студентов. Упростить обучение с помощью единой надежной и масштабируемой платформы.",
            "tr": "Eğitim kurumlarını bürokrasiden kurtarıp öğretmen-öğrenci etkileşimine odaklanmalarını sağlamak. Tek, güvenilir ve ölçeklenebilir bir platformla öğretimi sadeleştirmek.",
        },
        "Azərbaycan və regionun ən çox seçilən təhsil texnologiyaları platforması olmaq — AI dəstəkli, multi-tenant, təhlükəsiz və hər ölçüdə təşkilat üçün uyğun.": {
            "az": "Azərbaycan və regionun ən çox seçilən təhsil texnologiyaları platforması olmaq — AI dəstəkli, multi-tenant, təhlükəsiz və hər ölçüdə təşkilat üçün uyğun.",
            "en": "To become the preferred education technology platform in Azerbaijan and the region: AI-assisted, multi-tenant, secure and suitable for organizations of every size.",
            "ru": "Стать самой востребованной образовательной технологической платформой в Азербайджане и регионе: с поддержкой ИИ, multi-tenant архитектурой, безопасной и подходящей для организаций любого размера.",
            "tr": "Azerbaycan ve bölgede en çok tercih edilen eğitim teknolojileri platformu olmak: yapay zekâ destekli, çok kiracılı, güvenli ve her ölçekte kuruma uygun.",
        },
        "Bir abunəlikdə kursdan imtahana, qiymətləndirmədən analitikaya qədər lazım olan hər şey.": {
            "az": "Bir abunəlikdə kursdan imtahana, qiymətləndirmədən analitikaya qədər lazım olan hər şey.",
            "en": "Everything you need from courses to exams, assessment and analytics in one subscription.",
            "ru": "Все необходимое от курсов и экзаменов до оценивания и аналитики в одной подписке.",
            "tr": "Kurslardan sınavlara, değerlendirmeden analitiğe kadar ihtiyacınız olan her şey tek abonelikte.",
        },
        "Mövzular, dərslər, materiallar və qrup idarəçiliyi tək yerdə. Müəllim üçün sadə, tələbə üçün aydın.": {
            "az": "Mövzular, dərslər, materiallar və qrup idarəçiliyi tək yerdə. Müəllim üçün sadə, tələbə üçün aydın.",
            "en": "Topics, lessons, materials and group management in one place. Simple for teachers, clear for students.",
            "ru": "Темы, уроки, материалы и управление группами в одном месте. Просто для преподавателя и понятно для студента.",
            "tr": "Konular, dersler, materyaller ve grup yönetimi tek yerde. Öğretmen için sade, öğrenci için anlaşılır.",
        },
        "Hər təşkilat tam izolyasiya olunmuş məkana sahibdir. Məlumatlar bir-birinə qarışmır, RBAC ciddi tətbiq olunur.": {
            "az": "Hər təşkilat tam izolyasiya olunmuş məkana sahibdir. Məlumatlar bir-birinə qarışmır, RBAC ciddi tətbiq olunur.",
            "en": "Every organization gets a fully isolated workspace. Data never mixes, and RBAC is enforced strictly.",
            "ru": "Каждая организация получает полностью изолированное пространство. Данные не смешиваются, а RBAC применяется строго.",
            "tr": "Her kurum tamamen izole edilmiş bir alana sahiptir. Veriler birbirine karışmaz, RBAC sıkı şekilde uygulanır.",
        },
        "Superadmin, təşkilat sahibi, müəllim, tələbə və işçi rolları — hər kəs yalnız ona icazə verilən məlumatı görür.": {
            "az": "Superadmin, təşkilat sahibi, müəllim, tələbə və işçi rolları — hər kəs yalnız ona icazə verilən məlumatı görür.",
            "en": "Superadmin, organization owner, teacher, student and staff roles: everyone sees only the data they are allowed to access.",
            "ru": "Роли суперадмина, владельца организации, преподавателя, студента и сотрудника: каждый видит только разрешенные ему данные.",
            "tr": "Superadmin, kurum sahibi, öğretmen, öğrenci ve personel rolleri: herkes yalnızca izin verilen verileri görür.",
        },
        "Test, yazılı, praktik və canlı imtahanlar. Avtomatik qiymətləndirmə, analitika və anti-cheat parametrləri.": {
            "az": "Test, yazılı, praktik və canlı imtahanlar. Avtomatik qiymətləndirmə, analitika və anti-cheat parametrləri.",
            "en": "Test, written, practical and live exams with automatic grading, analytics and anti-cheat settings.",
            "ru": "Тестовые, письменные, практические и live-экзамены с автоматическим оцениванием, аналитикой и античит-настройками.",
            "tr": "Test, yazılı, uygulamalı ve canlı sınavlar; otomatik değerlendirme, analitik ve anti-cheat ayarları.",
        },
        "Hər kritik əməliyyat audit log-a yazılır. Daxili təhlükəsizlik testləri və CSP siyasətləri ilə qorunan.": {
            "az": "Hər kritik əməliyyat audit log-a yazılır. Daxili təhlükəsizlik testləri və CSP siyasətləri ilə qorunan.",
            "en": "Every critical action is written to the audit log and protected with internal security tests and CSP policies.",
            "ru": "Каждое критическое действие записывается в audit log и защищается внутренними проверками безопасности и CSP-политиками.",
            "tr": "Her kritik işlem audit log'a yazılır; dahili güvenlik testleri ve CSP politikalarıyla korunur.",
        },
        "İstifadəçinin icazəsi çərçivəsində suallarını cavablandıran, naviqasiyaya kömək edən ağıllı assistent.": {
            "az": "İstifadəçinin icazəsi çərçivəsində suallarını cavablandıran, naviqasiyaya kömək edən ağıllı assistent.",
            "en": "A smart assistant that answers questions and helps navigation within the user's permissions.",
            "ru": "Умный ассистент, который отвечает на вопросы и помогает с навигацией в рамках прав пользователя.",
            "tr": "Kullanıcının izinleri kapsamında soruları yanıtlayan ve gezinmeye yardımcı olan akıllı asistan.",
        },
        "EMSArena təcrübəli mühəndis və pedaqoqların məhsuludur. İstifadəçi yönümlü dizayn və etibarlı texnologiya əsas prioritetlərimizdir.": {
            "az": "EMSArena təcrübəli mühəndis və pedaqoqların məhsuludur. İstifadəçi yönümlü dizayn və etibarlı texnologiya əsas prioritetlərimizdir.",
            "en": "EMSArena is built by experienced engineers and educators. User-centered design and reliable technology are our main priorities.",
            "ru": "EMSArena создана опытными инженерами и педагогами. Пользовательский дизайн и надежные технологии — наши главные приоритеты.",
            "tr": "EMSArena deneyimli mühendisler ve eğitimciler tarafından geliştirilmiştir. Kullanıcı odaklı tasarım ve güvenilir teknoloji temel önceliklerimizdir.",
        },
        "Founder · Full-stack Engineer": {
            "az": "Təsisçi · Full-stack mühəndis",
            "en": "Founder · Full-stack Engineer",
            "ru": "Основатель · Full-stack инженер",
            "tr": "Kurucu · Full-stack mühendis",
        },
        "EMSArena-nın baş memarı və əsas mühəndisi. Django, React və paylaşılan sistemlər sahəsində mütəxəssis.": {
            "az": "EMSArena-nın baş memarı və əsas mühəndisi. Django, React və paylaşılan sistemlər sahəsində mütəxəssis.",
            "en": "The lead architect and core engineer of EMSArena, specializing in Django, React and shared systems.",
            "ru": "Главный архитектор и ведущий инженер EMSArena, специалист по Django, React и распределенным системам.",
            "tr": "EMSArena'nın baş mimarı ve ana mühendisi; Django, React ve paylaşımlı sistemler konusunda uzmandır.",
        },
        "Mühəndislik komandası": {
            "az": "Mühəndislik komandası",
            "en": "Engineering team",
            "ru": "Инженерная команда",
            "tr": "Mühendislik ekibi",
        },
        "Backend · Frontend · DevOps": {
            "az": "Backend · Frontend · DevOps",
            "en": "Backend · Frontend · DevOps",
            "ru": "Backend · Frontend · DevOps",
            "tr": "Backend · Frontend · DevOps",
        },
        "Performans, etibarlılıq və təhlükəsizliyi öz üzərinə götürən təcrübəli mühəndislər.": {
            "az": "Performans, etibarlılıq və təhlükəsizliyi öz üzərinə götürən təcrübəli mühəndislər.",
            "en": "Experienced engineers focused on performance, reliability and security.",
            "ru": "Опытные инженеры, отвечающие за производительность, надежность и безопасность.",
            "tr": "Performans, güvenilirlik ve güvenliği üstlenen deneyimli mühendisler.",
        },
        "Pedaqoji məsləhətçilər": {
            "az": "Pedaqoji məsləhətçilər",
            "en": "Education advisors",
            "ru": "Педагогические консультанты",
            "tr": "Pedagojik danışmanlar",
        },
        "Təhsil eksperti · Metodoloq": {
            "az": "Təhsil eksperti · Metodoloq",
            "en": "Education expert · Methodologist",
            "ru": "Эксперт по образованию · Методолог",
            "tr": "Eğitim uzmanı · Metodolog",
        },
        "Müəllim və universitet təcrübəsinə malik mütəxəssislər platformanın pedaqoji düzgünlüyünü təmin edirlər.": {
            "az": "Müəllim və universitet təcrübəsinə malik mütəxəssislər platformanın pedaqoji düzgünlüyünü təmin edirlər.",
            "en": "Specialists with teaching and university experience ensure the platform's pedagogical quality.",
            "ru": "Специалисты с преподавательским и университетским опытом обеспечивают педагогическую корректность платформы.",
            "tr": "Öğretmenlik ve üniversite deneyimine sahip uzmanlar platformanın pedagojik doğruluğunu sağlar.",
        },
        "Təhsilinizi növbəti səviyyəyə qaldıraq": {
            "az": "Təhsilinizi növbəti səviyyəyə qaldıraq",
            "en": "Let's take your education to the next level",
            "ru": "Давайте выведем ваше обучение на новый уровень",
            "tr": "Eğitiminizi bir sonraki seviyeye taşıyalım",
        },
        "Bir abunəlikdə kurs, imtahan, audit və AI — hamısı bir yerdə.": {
            "az": "Bir abunəlikdə kurs, imtahan, audit və AI — hamısı bir yerdə.",
            "en": "Courses, exams, audit and AI in one subscription and one place.",
            "ru": "Курсы, экзамены, аудит и ИИ в одной подписке и в одном месте.",
            "tr": "Kurs, sınav, denetim ve yapay zekâ tek abonelikte, tek yerde.",
        },
        "Haqqımızda – EMSArena": {
            "az": "Haqqımızda – EMSArena",
            "en": "About us – EMSArena",
            "ru": "О нас – EMSArena",
            "tr": "Hakkımızda – EMSArena",
        },
        "EMSArena təhsil idarəetmə, LMS və onlayn imtahan platformasıdır. Komandamız, missiyamız və platformanın imkanları haqqında məlumat.": {
            "az": "EMSArena təhsil idarəetmə, LMS və onlayn imtahan platformasıdır. Komandamız, missiyamız və platformanın imkanları haqqında məlumat.",
            "en": "EMSArena is an education management, LMS and online exam platform. Learn about our team, mission and platform capabilities.",
            "ru": "EMSArena — платформа управления образованием, LMS и онлайн-экзаменов. Узнайте о нашей команде, миссии и возможностях платформы.",
            "tr": "EMSArena bir eğitim yönetimi, LMS ve çevrimiçi sınav platformudur. Ekibimiz, misyonumuz ve platform özelliklerimiz hakkında bilgi alın.",
        },
        # ---------- contact page/form/model/admin/email ----------
        "Adınız və soyadınız": {
            "az": "Adınız və soyadınız",
            "en": "Your full name",
            "ru": "Ваше имя и фамилия",
            "tr": "Adınız ve soyadınız",
        },
        "Mesajınızı yazın...": {
            "az": "Mesajınızı yazın...",
            "en": "Write your message...",
            "ru": "Напишите ваше сообщение...",
            "tr": "Mesajınızı yazın...",
        },
        "Ad ən azı 2 simvol olmalıdır.": {
            "az": "Ad ən azı 2 simvol olmalıdır.",
            "en": "Name must be at least 2 characters.",
            "ru": "Имя должно содержать минимум 2 символа.",
            "tr": "Ad en az 2 karakter olmalıdır.",
        },
        "Ad daxilində link ola bilməz.": {
            "az": "Ad daxilində link ola bilməz.",
            "en": "The name cannot contain a link.",
            "ru": "Имя не может содержать ссылку.",
            "tr": "Ad içinde bağlantı olamaz.",
        },
        "Telefon nömrəsi yalnız rəqəm və +, -, (, ) simvollarından ibarət ola bilər.": {
            "az": "Telefon nömrəsi yalnız rəqəm və +, -, (, ) simvollarından ibarət ola bilər.",
            "en": "Phone number can contain only digits and +, -, (, ) symbols.",
            "ru": "Номер телефона может содержать только цифры и символы +, -, (, ).",
            "tr": "Telefon numarası yalnızca rakam ve +, -, (, ) karakterlerinden oluşabilir.",
        },
        "Mesaj ən azı 10 simvol olmalıdır.": {
            "az": "Mesaj ən azı 10 simvol olmalıdır.",
            "en": "Message must be at least 10 characters.",
            "ru": "Сообщение должно содержать минимум 10 символов.",
            "tr": "Mesaj en az 10 karakter olmalıdır.",
        },
        "Mesajda çox sayda link aşkar edildi.": {
            "az": "Mesajda çox sayda link aşkar edildi.",
            "en": "Too many links were detected in the message.",
            "ru": "В сообщении обнаружено слишком много ссылок.",
            "tr": "Mesajda çok sayıda bağlantı tespit edildi.",
        },
        "Forma doğrulanmadı.": {
            "az": "Forma doğrulanmadı.",
            "en": "The form could not be verified.",
            "ru": "Форма не прошла проверку.",
            "tr": "Form doğrulanamadı.",
        },
        "Ümumi sual": {"az": "Ümumi sual", "en": "General question", "ru": "Общий вопрос", "tr": "Genel soru"},
        "Satış / Demo": {"az": "Satış / Demo", "en": "Sales / Demo", "ru": "Продажи / Демо", "tr": "Satış / Demo"},
        "Texniki dəstək": {
            "az": "Texniki dəstək",
            "en": "Technical support",
            "ru": "Техническая поддержка",
            "tr": "Teknik destek",
        },
        "Əməkdaşlıq": {"az": "Əməkdaşlıq", "en": "Partnership", "ru": "Партнерство", "tr": "İş birliği"},
        "Rəy və təklif": {
            "az": "Rəy və təklif",
            "en": "Feedback and suggestion",
            "ru": "Отзыв и предложение",
            "tr": "Geri bildirim ve öneri",
        },
        "Digər": {"az": "Digər", "en": "Other", "ru": "Другое", "tr": "Diğer"},
        "Göndərilir": {"az": "Göndərilir", "en": "Sending", "ru": "Отправляется", "tr": "Gönderiliyor"},
        "Göndərildi": {"az": "Göndərildi", "en": "Sent", "ru": "Отправлено", "tr": "Gönderildi"},
        "Göndərilmədi": {"az": "Göndərilmədi", "en": "Not sent", "ru": "Не отправлено", "tr": "Gönderilemedi"},
        "Qeyd edildi": {"az": "Qeyd edildi", "en": "Recorded", "ru": "Записано", "tr": "Kaydedildi"},
        "IP ünvan": {"az": "IP ünvan", "en": "IP address", "ru": "IP-адрес", "tr": "IP adresi"},
        "User-Agent": {"az": "User-Agent", "en": "User-Agent", "ru": "User-Agent", "tr": "User-Agent"},
        "Cavablandırılıb": {"az": "Cavablandırılıb", "en": "Handled", "ru": "Обработано", "tr": "Yanıtlandı"},
        "Göndərilmə tarixi": {
            "az": "Göndərilmə tarixi",
            "en": "Submission date",
            "ru": "Дата отправки",
            "tr": "Gönderim tarihi",
        },
        "Cavab tarixi": {"az": "Cavab tarixi", "en": "Reply date", "ru": "Дата ответа", "tr": "Yanıt tarihi"},
        "Cavab mətni": {"az": "Cavab mətni", "en": "Reply text", "ru": "Текст ответа", "tr": "Yanıt metni"},
        "Hansı maildən": {
            "az": "Hansı maildən",
            "en": "From mailbox",
            "ru": "С какого email",
            "tr": "Hangi e-postadan",
        },
        "Cavab email statusu": {
            "az": "Cavab email statusu",
            "en": "Reply email status",
            "ru": "Статус email-ответа",
            "tr": "Yanıt e-posta durumu",
        },
        "Cavab email xətası": {
            "az": "Cavab email xətası",
            "en": "Reply email error",
            "ru": "Ошибка email-ответа",
            "tr": "Yanıt e-posta hatası",
        },
        "Cavab göndərilmə tarixi": {
            "az": "Cavab göndərilmə tarixi",
            "en": "Reply sent date",
            "ru": "Дата отправки ответа",
            "tr": "Yanıt gönderim tarihi",
        },
        "Cavab verən admin": {
            "az": "Cavab verən admin",
            "en": "Replying admin",
            "ru": "Ответивший администратор",
            "tr": "Yanıtlayan admin",
        },
        "Əlaqə mesajı": {
            "az": "Əlaqə mesajı",
            "en": "Contact message",
            "ru": "Сообщение контакта",
            "tr": "İletişim mesajı",
        },
        "Əlaqə mesajları": {
            "az": "Əlaqə mesajları",
            "en": "Contact messages",
            "ru": "Сообщения контактов",
            "tr": "İletişim mesajları",
        },
        "Əlaqə – EMSArena": {
            "az": "Əlaqə – EMSArena",
            "en": "Contact – EMSArena",
            "ru": "Контакты – EMSArena",
            "tr": "İletişim – EMSArena",
        },
        "EMSArena ilə əlaqə saxlayın. Suallarınız, təklifləriniz və əməkdaşlıq istəkləriniz üçün bizə yazın.": {
            "az": "EMSArena ilə əlaqə saxlayın. Suallarınız, təklifləriniz və əməkdaşlıq istəkləriniz üçün bizə yazın.",
            "en": "Contact EMSArena. Write to us with your questions, suggestions and partnership requests.",
            "ru": "Свяжитесь с EMSArena. Пишите нам с вопросами, предложениями и заявками на сотрудничество.",
            "tr": "EMSArena ile iletişime geçin. Sorularınız, önerileriniz ve iş birliği talepleriniz için bize yazın.",
        },
        "Çox sayda mesaj göndərilib. Zəhmət olmasa bir az gözləyin.": {
            "az": "Çox sayda mesaj göndərilib. Zəhmət olmasa bir az gözləyin.",
            "en": "Too many messages have been sent. Please wait a little.",
            "ru": "Отправлено слишком много сообщений. Пожалуйста, немного подождите.",
            "tr": "Çok sayıda mesaj gönderildi. Lütfen biraz bekleyin.",
        },
        "Bu email ünvanından çox sayda mesaj göndərilib. Sabah yenidən cəhd edin.": {
            "az": "Bu email ünvanından çox sayda mesaj göndərilib. Sabah yenidən cəhd edin.",
            "en": "Too many messages have been sent from this email address. Try again tomorrow.",
            "ru": "С этого email-адреса отправлено слишком много сообщений. Попробуйте снова завтра.",
            "tr": "Bu e-posta adresinden çok sayıda mesaj gönderildi. Yarın tekrar deneyin.",
        },
        "Mesajınızı qəbul edə bilmədik. Zəhmət olmasa daha sonra cəhd edin.": {
            "az": "Mesajınızı qəbul edə bilmədik. Zəhmət olmasa daha sonra cəhd edin.",
            "en": "We could not accept your message. Please try again later.",
            "ru": "Мы не смогли принять ваше сообщение. Пожалуйста, попробуйте позже.",
            "tr": "Mesajınızı alamadık. Lütfen daha sonra tekrar deneyin.",
        },
        "Mesajınız uğurla qəbul edildi. Tezliklə sizinlə əlaqə saxlayacağıq.": {
            "az": "Mesajınız uğurla qəbul edildi. Tezliklə sizinlə əlaqə saxlayacağıq.",
            "en": "Your message was received successfully. We will contact you soon.",
            "ru": "Ваше сообщение успешно принято. Мы скоро свяжемся с вами.",
            "tr": "Mesajınız başarıyla alındı. Kısa süre içinde sizinle iletişime geçeceğiz.",
        },
        "EMSArena hansı təşkilatlar üçün uyğundur?": {
            "az": "EMSArena hansı təşkilatlar üçün uyğundur?",
            "en": "Which organizations is EMSArena suitable for?",
            "ru": "Для каких организаций подходит EMSArena?",
            "tr": "EMSArena hangi kurumlar için uygundur?",
        },
        "Universitetlər, məktəblər, kurs mərkəzləri, korporativ təlim şöbələri və fərdi müəllimlər üçün uyğundur. Multi-tenant strukturu sayəsində hər təşkilat öz məkanını idarə edir.": {
            "az": "Universitetlər, məktəblər, kurs mərkəzləri, korporativ təlim şöbələri və fərdi müəllimlər üçün uyğundur. Multi-tenant strukturu sayəsində hər təşkilat öz məkanını idarə edir.",
            "en": "It is suitable for universities, schools, training centers, corporate training departments and individual teachers. With the multi-tenant structure, each organization manages its own workspace.",
            "ru": "Подходит для университетов, школ, учебных центров, корпоративных отделов обучения и индивидуальных преподавателей. Благодаря multi-tenant структуре каждая организация управляет своим пространством.",
            "tr": "Üniversiteler, okullar, kurs merkezleri, kurumsal eğitim birimleri ve bireysel öğretmenler için uygundur. Çok kiracılı yapı sayesinde her kurum kendi alanını yönetir.",
        },
        "Demo və ya pulsuz sınaq müddəti var?": {
            "az": "Demo və ya pulsuz sınaq müddəti var?",
            "en": "Is there a demo or free trial?",
            "ru": "Есть ли демо или бесплатный пробный период?",
            "tr": "Demo veya ücretsiz deneme var mı?",
        },
        "Bəli, satış komandamızla əlaqə saxlayaraq pulsuz demo təşkil edə bilərsiniz. Formada 'Satış / Demo' mövzusunu seçin.": {
            "az": "Bəli, satış komandamızla əlaqə saxlayaraq pulsuz demo təşkil edə bilərsiniz. Formada 'Satış / Demo' mövzusunu seçin.",
            "en": "Yes. Contact our sales team to arrange a free demo. Select 'Sales / Demo' as the subject in the form.",
            "ru": "Да. Свяжитесь с нашей командой продаж, чтобы организовать бесплатную демо-версию. В форме выберите тему «Продажи / Демо».",
            "tr": "Evet. Satış ekibimizle iletişime geçerek ücretsiz demo düzenleyebilirsiniz. Formda 'Satış / Demo' konusunu seçin.",
        },
        "Texniki dəstək necə alınır?": {
            "az": "Texniki dəstək necə alınır?",
            "en": "How do I get technical support?",
            "ru": "Как получить техническую поддержку?",
            "tr": "Teknik destek nasıl alınır?",
        },
        "Mövcud müştərilərimiz hesab daxilindən bilet aça bilər. Yeni gələnlər forma vasitəsilə 'Texniki dəstək' mövzusunu seçərək yaza bilər.": {
            "az": "Mövcud müştərilərimiz hesab daxilindən bilet aça bilər. Yeni gələnlər forma vasitəsilə 'Texniki dəstək' mövzusunu seçərək yaza bilər.",
            "en": "Existing customers can open a ticket from inside their account. New visitors can write through the form by selecting 'Technical support'.",
            "ru": "Действующие клиенты могут открыть тикет из своего аккаунта. Новые посетители могут написать через форму, выбрав тему «Техническая поддержка».",
            "tr": "Mevcut müşterilerimiz hesap içinden talep oluşturabilir. Yeni gelenler formda 'Teknik destek' konusunu seçerek yazabilir.",
        },
        "Məlumatlarım təhlükəsizdir?": {
            "az": "Məlumatlarım təhlükəsizdir?",
            "en": "Is my data secure?",
            "ru": "Мои данные в безопасности?",
            "tr": "Verilerim güvende mi?",
        },
        "Bəli. Multi-tenant izolyasiya, rol-əsaslı icazə sistemi (RBAC), şifrəli saxlama və audit log sayəsində məlumatlar maksimum səviyyədə qorunur.": {
            "az": "Bəli. Multi-tenant izolyasiya, rol-əsaslı icazə sistemi (RBAC), şifrəli saxlama və audit log sayəsində məlumatlar maksimum səviyyədə qorunur.",
            "en": "Yes. Data is strongly protected through multi-tenant isolation, role-based access control (RBAC), encrypted storage and audit logs.",
            "ru": "Да. Данные надежно защищены благодаря multi-tenant изоляции, ролевой системе доступа (RBAC), зашифрованному хранению и audit log.",
            "tr": "Evet. Çok kiracılı izolasyon, rol tabanlı izin sistemi (RBAC), şifreli saklama ve audit log sayesinde veriler güçlü şekilde korunur.",
        },
        "AI köməkçi necə işləyir?": {
            "az": "AI köməkçi necə işləyir?",
            "en": "How does the AI assistant work?",
            "ru": "Как работает ИИ-помощник?",
            "tr": "Yapay zekâ asistanı nasıl çalışır?",
        },
        "AI köməkçi yalnız sizin icazəniz olan məlumatları görür. Tələbə yalnız öz kursları, müəllim yalnız öz qrupları, admin isə öz təşkilatı haqqında suallar verə bilər.": {
            "az": "AI köməkçi yalnız sizin icazəniz olan məlumatları görür. Tələbə yalnız öz kursları, müəllim yalnız öz qrupları, admin isə öz təşkilatı haqqında suallar verə bilər.",
            "en": "The AI assistant sees only data you are allowed to access. A student can ask about their courses, a teacher about their groups, and an admin about their organization.",
            "ru": "ИИ-помощник видит только данные, к которым у вас есть доступ. Студент может спрашивать о своих курсах, преподаватель — о своих группах, администратор — о своей организации.",
            "tr": "Yapay zekâ asistanı yalnızca izinli olduğunuz verileri görür. Öğrenci kendi kursları, öğretmen kendi grupları, admin ise kendi kurumu hakkında soru sorabilir.",
        },
        "EMSArena – Cavab": {
            "az": "EMSArena – Cavab",
            "en": "EMSArena – Reply",
            "ru": "EMSArena – Ответ",
            "tr": "EMSArena – Yanıt",
        },
        "Mesajınıza cavab": {
            "az": "Mesajınıza cavab",
            "en": "Reply to your message",
            "ru": "Ответ на ваше сообщение",
            "tr": "Mesajınıza yanıt",
        },
        "Salam": {"az": "Salam", "en": "Hello", "ru": "Здравствуйте", "tr": "Merhaba"},
        "EMSArena saytındakı mesajınız üçün təşəkkür edirik. Aşağıda cavabımızı tapa bilərsiniz.": {
            "az": "EMSArena saytındakı mesajınız üçün təşəkkür edirik. Aşağıda cavabımızı tapa bilərsiniz.",
            "en": "Thank you for your message on the EMSArena website. You can find our reply below.",
            "ru": "Спасибо за ваше сообщение на сайте EMSArena. Ниже вы найдете наш ответ.",
            "tr": "EMSArena sitesindeki mesajınız için teşekkür ederiz. Yanıtımızı aşağıda bulabilirsiniz.",
        },
        "Sizin orijinal mesajınız:": {
            "az": "Sizin orijinal mesajınız:",
            "en": "Your original message:",
            "ru": "Ваше исходное сообщение:",
            "tr": "Orijinal mesajınız:",
        },
        "Bu mesaja birbaşa cavab verə bilərsiniz — yenidən komandamıza gələcək.": {
            "az": "Bu mesaja birbaşa cavab verə bilərsiniz — yenidən komandamıza gələcək.",
            "en": "You can reply directly to this message. It will come back to our team.",
            "ru": "Вы можете ответить прямо на это сообщение, и оно снова попадет нашей команде.",
            "tr": "Bu mesaja doğrudan yanıt verebilirsiniz; yanıtınız ekibimize geri gelecektir.",
        },
        "Təhsil idarəetmə platforması": {
            "az": "Təhsil idarəetmə platforması",
            "en": "Education management platform",
            "ru": "Платформа управления образованием",
            "tr": "Eğitim yönetimi platformu",
        },
        "EMSArena – Yeni əlaqə mesajı": {
            "az": "EMSArena – Yeni əlaqə mesajı",
            "en": "EMSArena – New contact message",
            "ru": "EMSArena – Новое сообщение контакта",
            "tr": "EMSArena – Yeni iletişim mesajı",
        },
        "Yeni əlaqə mesajı": {
            "az": "Yeni əlaqə mesajı",
            "en": "New contact message",
            "ru": "Новое сообщение контакта",
            "tr": "Yeni iletişim mesajı",
        },
        "EMSArena saytındakı əlaqə formasından yeni bir mesaj göndərildi. Mesaj saxlanılıb və admin panelindən baxa bilərsiniz.": {
            "az": "EMSArena saytındakı əlaqə formasından yeni bir mesaj göndərildi. Mesaj saxlanılıb və admin panelindən baxa bilərsiniz.",
            "en": "A new message was submitted from the EMSArena contact form. The message has been saved and can be viewed from the admin panel.",
            "ru": "Из контактной формы EMSArena отправлено новое сообщение. Сообщение сохранено и доступно в админ-панели.",
            "tr": "EMSArena iletişim formundan yeni bir mesaj gönderildi. Mesaj kaydedildi ve admin panelinden görüntülenebilir.",
        },
        "Tarix": {"az": "Tarix", "en": "Date", "ru": "Дата", "tr": "Tarih"},
        "Admin paneldə cavablandır": {
            "az": "Admin paneldə cavablandır",
            "en": "Reply in admin panel",
            "ru": "Ответить в админ-панели",
            "tr": "Admin panelde yanıtla",
        },
        "Mesaj detalları": {
            "az": "Mesaj detalları",
            "en": "Message details",
            "ru": "Детали сообщения",
            "tr": "Mesaj detayları",
        },
        "Cavab müştəriyə <strong>info@</strong> və ya <strong>support@emsarena.com</strong>-dan gedəcək — şəxsi Gmail-iniz görünməyəcək.": {
            "az": "Cavab müştəriyə <strong>info@</strong> və ya <strong>support@emsarena.com</strong>-dan gedəcək — şəxsi Gmail-iniz görünməyəcək.",
            "en": "The reply will go to the customer from <strong>info@</strong> or <strong>support@emsarena.com</strong>; your personal Gmail will not be visible.",
            "ru": "Ответ клиенту будет отправлен с <strong>info@</strong> или <strong>support@emsarena.com</strong>; ваш личный Gmail не будет виден.",
            "tr": "Yanıt müşteriye <strong>info@</strong> veya <strong>support@emsarena.com</strong> üzerinden gidecek; kişisel Gmail adresiniz görünmeyecek.",
        },
        "Bu mesaja cavab vermək üçün EMSArena admin panelinə keçin.": {
            "az": "Bu mesaja cavab vermək üçün EMSArena admin panelinə keçin.",
            "en": "Go to the EMSArena admin panel to reply to this message.",
            "ru": "Перейдите в админ-панель EMSArena, чтобы ответить на это сообщение.",
            "tr": "Bu mesaja yanıt vermek için EMSArena admin paneline gidin.",
        },
        "Avtomatik göndərilmiş bildiriş": {
            "az": "Avtomatik göndərilmiş bildiriş",
            "en": "Automatically sent notification",
            "ru": "Автоматически отправленное уведомление",
            "tr": "Otomatik gönderilmiş bildirim",
        },
        "[EMSArena Contact] %(subject)s — %(name)s": {
            "az": "[EMSArena Əlaqə] %(subject)s — %(name)s",
            "en": "[EMSArena Contact] %(subject)s — %(name)s",
            "ru": "[EMSArena Контакты] %(subject)s — %(name)s",
            "tr": "[EMSArena İletişim] %(subject)s — %(name)s",
        },
        "Re: [EMSArena] %(subject)s": {
            "az": "Re: [EMSArena] %(subject)s",
            "en": "Re: [EMSArena] %(subject)s",
            "ru": "Re: [EMSArena] %(subject)s",
            "tr": "Re: [EMSArena] %(subject)s",
        },
        "Göndərən": {"az": "Göndərən", "en": "Sender", "ru": "Отправитель", "tr": "Gönderen"},
        "Cavab": {"az": "Cavab", "en": "Reply", "ru": "Ответ", "tr": "Yanıt"},
        "Status": {"az": "Status", "en": "Status", "ru": "Статус", "tr": "Durum"},
        "Metadata": {"az": "Metadata", "en": "Metadata", "ru": "Метаданные", "tr": "Metadata"},
        "✓ Cavablandı": {"az": "✓ Cavablandı", "en": "✓ Replied", "ru": "✓ Ответ отправлен", "tr": "✓ Yanıtlandı"},
        "Cavabsız bağlandı": {
            "az": "Cavabsız bağlandı",
            "en": "Closed without reply",
            "ru": "Закрыто без ответа",
            "tr": "Yanıtsız kapatıldı",
        },
        "✓ Cavablandı — yenidən göndər": {
            "az": "✓ Cavablandı — yenidən göndər",
            "en": "✓ Replied — send again",
            "ru": "✓ Ответ отправлен — отправить снова",
            "tr": "✓ Yanıtlandı — yeniden gönder",
        },
        "Yenidən cəhd et": {"az": "Yenidən cəhd et", "en": "Try again", "ru": "Попробовать снова", "tr": "Tekrar dene"},
        "Göndərişi təsdiqlə": {
            "az": "Göndərişi təsdiqlə",
            "en": "Confirm delivery",
            "ru": "Подтвердить отправку",
            "tr": "Gönderimi onayla",
        },
        "✉ Müştəriyə cavablandır": {
            "az": "✉ Müştəriyə cavablandır",
            "en": "✉ Reply to customer",
            "ru": "✉ Ответить клиенту",
            "tr": "✉ Müşteriye yanıtla",
        },
        "Cavablandırılmış kimi işarələ": {
            "az": "Cavablandırılmış kimi işarələ",
            "en": "Mark as handled",
            "ru": "Отметить как обработанное",
            "tr": "Yanıtlanmış olarak işaretle",
        },
        "Hansı maildən cavab göndərilsin": {
            "az": "Hansı maildən cavab göndərilsin",
            "en": "Which mailbox should send the reply",
            "ru": "С какого email отправить ответ",
            "tr": "Yanıt hangi e-postadan gönderilsin",
        },
        "Müştəriyə göndəriləcək cavab. Markdown dəstəklənmir; sadə mətn olaraq görünəcək.": {
            "az": "Müştəriyə göndəriləcək cavab. Markdown dəstəklənmir; sadə mətn olaraq görünəcək.",
            "en": "The reply that will be sent to the customer. Markdown is not supported; it will appear as plain text.",
            "ru": "Ответ, который будет отправлен клиенту. Markdown не поддерживается; текст будет показан как обычный.",
            "tr": "Müşteriye gönderilecek yanıt. Markdown desteklenmez; düz metin olarak görünür.",
        },
        "Cavab qeyd edildi və %(email)s ünvanına göndərilməyə çalışılır.": {
            "az": "Cavab qeyd edildi və %(email)s ünvanına göndərilməyə çalışılır.",
            "en": "The reply was saved and delivery to %(email)s is being attempted.",
            "ru": "Ответ сохранен, выполняется попытка отправки на %(email)s.",
            "tr": "Yanıt kaydedildi ve %(email)s adresine gönderilmeye çalışılıyor.",
        },
        "Cavablandır: %(name)s": {
            "az": "Cavablandır: %(name)s",
            "en": "Reply to: %(name)s",
            "ru": "Ответить: %(name)s",
            "tr": "Yanıtla: %(name)s",
        },
        "Cavablandır": {"az": "Cavablandır", "en": "Reply", "ru": "Ответить", "tr": "Yanıtla"},
        "Müştəri mesajı": {
            "az": "Müştəri mesajı",
            "en": "Customer message",
            "ru": "Сообщение клиента",
            "tr": "Müşteri mesajı",
        },
        "Ad": {"az": "Ad", "en": "Name", "ru": "Имя", "tr": "Ad"},
        "Yenidən cavab göndər": {
            "az": "Yenidən cavab göndər",
            "en": "Send reply again",
            "ru": "Отправить ответ снова",
            "tr": "Yanıtı yeniden gönder",
        },
        "Yenidən göndər": {"az": "Yenidən göndər", "en": "Send again", "ru": "Отправить снова", "tr": "Yeniden gönder"},
        "Cavab yaz və göndər": {
            "az": "Cavab yaz və göndər",
            "en": "Write and send reply",
            "ru": "Написать и отправить ответ",
            "tr": "Yanıt yaz ve gönder",
        },
        "Müştəri bu ünvandan cavab gəldiyini görəcək. Onun cavabı da bu inboxa qayıdacaq.": {
            "az": "Müştəri bu ünvandan cavab gəldiyini görəcək. Onun cavabı da bu inboxa qayıdacaq.",
            "en": "The customer will see that the reply came from this address. Their response will return to this inbox.",
            "ru": "Клиент увидит, что ответ пришел с этого адреса. Его ответ также вернется в этот inbox.",
            "tr": "Müşteri yanıtın bu adresten geldiğini görecek. Onun yanıtı da bu gelen kutusuna dönecek.",
        },
        "Cavabı göndər": {"az": "Cavabı göndər", "en": "Send reply", "ru": "Отправить ответ", "tr": "Yanıtı gönder"},
        "Ləğv et": {"az": "Ləğv et", "en": "Cancel", "ru": "Отмена", "tr": "İptal et"},
        "Son cavab cəhdi": {
            "az": "Son cavab cəhdi",
            "en": "Last reply attempt",
            "ru": "Последняя попытка ответа",
            "tr": "Son yanıt denemesi",
        },
        # ---------- profile contact inbox ----------
        "Superadmin inbox": {
            "az": "Superadmin gələnlər qutusu",
            "en": "Superadmin inbox",
            "ru": "Входящие суперадмина",
            "tr": "Superadmin gelen kutusu",
        },
        "Customer contact inbox": {
            "az": "Müştəri əlaqə mesajları",
            "en": "Customer contact inbox",
            "ru": "Входящие сообщений клиентов",
            "tr": "Müşteri iletişim gelen kutusu",
        },
        "Review public contact form messages and reply from the official EMSArena mailboxes.": {
            "az": "İctimai əlaqə formasından gələn mesajlara baxın və rəsmi EMSArena poçtlarından cavab verin.",
            "en": "Review public contact form messages and reply from the official EMSArena mailboxes.",
            "ru": "Просматривайте сообщения из публичной контактной формы и отвечайте с официальных почтовых ящиков EMSArena.",
            "tr": "Herkese açık iletişim formu mesajlarını inceleyin ve resmi EMSArena posta kutularından yanıtlayın.",
        },
        "Back to inbox": {
            "az": "Gələnlərə qayıt",
            "en": "Back to inbox",
            "ru": "Назад во входящие",
            "tr": "Gelen kutusuna dön",
        },
        "Sent": {"az": "Göndərildi", "en": "Sent", "ru": "Отправлено", "tr": "Gönderildi"},
        "Sending": {"az": "Göndərilir", "en": "Sending", "ru": "Отправляется", "tr": "Gönderiliyor"},
        "Failed": {"az": "Uğursuz", "en": "Failed", "ru": "Ошибка", "tr": "Başarısız"},
        "Saved": {"az": "Saxlanıldı", "en": "Saved", "ru": "Сохранено", "tr": "Kaydedildi"},
        "New": {"az": "Yeni", "en": "New", "ru": "Новое", "tr": "Yeni"},
        "Customer message": {
            "az": "Müştəri mesajı",
            "en": "Customer message",
            "ru": "Сообщение клиента",
            "tr": "Müşteri mesajı",
        },
        "Email was not delivered.": {
            "az": "Email çatdırılmadı.",
            "en": "Email was not delivered.",
            "ru": "Email не был доставлен.",
            "tr": "E-posta teslim edilmedi.",
        },
        "Email delivery is still pending.": {
            "az": "Email göndərişi hələ tamamlanmayıb.",
            "en": "Email delivery is still pending.",
            "ru": "Доставка email все еще ожидается.",
            "tr": "E-posta teslimi hâlâ beklemede.",
        },
        "Refresh shortly to see the final status.": {
            "az": "Yekun statusu görmək üçün bir az sonra yeniləyin.",
            "en": "Refresh shortly to see the final status.",
            "ru": "Обновите страницу чуть позже, чтобы увидеть итоговый статус.",
            "tr": "Son durumu görmek için kısa süre sonra yenileyin.",
        },
        "Reply is saved, but delivery was not confirmed.": {
            "az": "Cavab saxlanılıb, amma çatdırılma təsdiqlənməyib.",
            "en": "Reply is saved, but delivery was not confirmed.",
            "ru": "Ответ сохранен, но доставка не подтверждена.",
            "tr": "Yanıt kaydedildi, ancak teslimat doğrulanmadı.",
        },
        "Send it again to get a fresh delivery status.": {
            "az": "Yeni çatdırılma statusu almaq üçün yenidən göndərin.",
            "en": "Send it again to get a fresh delivery status.",
            "ru": "Отправьте снова, чтобы получить новый статус доставки.",
            "tr": "Güncel teslimat durumu almak için yeniden gönderin.",
        },
        "Send from": {"az": "Göndərən poçt", "en": "Send from", "ru": "Отправить с", "tr": "Gönderen posta"},
        "Mailbox": {"az": "Poçt qutusu", "en": "Mailbox", "ru": "Почтовый ящик", "tr": "Posta kutusu"},
        "Reply": {"az": "Cavab", "en": "Reply", "ru": "Ответ", "tr": "Yanıt"},
        "Write your reply...": {
            "az": "Cavabınızı yazın...",
            "en": "Write your reply...",
            "ru": "Напишите ответ...",
            "tr": "Yanıtınızı yazın...",
        },
        "Plain text. Min 10, max 10000 characters.": {
            "az": "Sadə mətn. Minimum 10, maksimum 10000 simvol.",
            "en": "Plain text. Min 10, max 10000 characters.",
            "ru": "Обычный текст. Минимум 10, максимум 10000 символов.",
            "tr": "Düz metin. En az 10, en fazla 10000 karakter.",
        },
        "Send Reply": {"az": "Cavabı göndər", "en": "Send Reply", "ru": "Отправить ответ", "tr": "Yanıt gönder"},
        "Cancel": {"az": "Ləğv et", "en": "Cancel", "ru": "Отмена", "tr": "İptal"},
        "Last reply attempt": {
            "az": "Son cavab cəhdi",
            "en": "Last reply attempt",
            "ru": "Последняя попытка ответа",
            "tr": "Son yanıt denemesi",
        },
        "From": {"az": "Kimdən", "en": "From", "ru": "От", "tr": "Kimden"},
        "Total": {"az": "Cəmi", "en": "Total", "ru": "Всего", "tr": "Toplam"},
        "Search name, email, message...": {
            "az": "Ad, email, mesaj axtar...",
            "en": "Search name, email, message...",
            "ru": "Поиск по имени, email, сообщению...",
            "tr": "Ad, e-posta, mesaj ara...",
        },
        "No contact messages yet.": {
            "az": "Hələ əlaqə mesajı yoxdur.",
            "en": "No contact messages yet.",
            "ru": "Сообщений контакта пока нет.",
            "tr": "Henüz iletişim mesajı yok.",
        },
        "Contact Messages": {
            "az": "Əlaqə mesajları",
            "en": "Contact Messages",
            "ru": "Сообщения контакта",
            "tr": "İletişim mesajları",
        },
        "Create category": {
            "az": "Kateqoriya yarat",
            "en": "Create category",
            "ru": "Создать категорию",
            "tr": "Kategori oluştur",
        },
        "Categories": {
            "az": "Kateqoriyalar",
            "en": "Categories",
            "ru": "Категории",
            "tr": "Kategoriler",
        },
    }
)


def escape_po(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _po_literal(value: str) -> str:
    return ast.literal_eval(value.strip())


def _entry_value(entry: str, token: str) -> str:
    lines = entry.splitlines()
    chunks: list[str] = []
    collecting = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{token} "):
            collecting = True
            chunks.append(_po_literal(stripped[len(token) :]))
            continue
        if collecting:
            if stripped.startswith('"'):
                chunks.append(_po_literal(stripped))
                continue
            break
    return "".join(chunks)


def _serialize_entry(msgid: str, msgstr: str) -> str:
    return "#: contact/about/footer/navbar\n" f'msgid "{escape_po(msgid)}"\n' f'msgstr "{escape_po(msgstr)}"'


def upsert_plain_entry(po_path: Path, msgid: str, msgstr: str) -> str:
    """Insert or update a plain (non-msgctxt) entry.

    Contextual entries with the same msgid are intentionally ignored because
    Django treats them as separate translation keys.
    """
    content = po_path.read_text(encoding="utf-8")
    trailing_newline = "\n" if content.endswith("\n") else ""
    entries = content.strip("\n").split("\n\n") if content.strip() else []
    serialized = _serialize_entry(msgid, msgstr)

    for index, entry in enumerate(entries):
        if _entry_value(entry, "msgctxt"):
            continue
        if _entry_value(entry, "msgid") == msgid:
            if _entry_value(entry, "msgstr") == msgstr:
                return "unchanged"
            entries[index] = serialized
            po_path.write_text("\n\n".join(entries) + trailing_newline, encoding="utf-8")
            return "updated"

    entries.append(serialized)
    po_path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")
    return "appended"


def main() -> None:
    languages = ["az", "en", "ru", "tr"]
    totals = {lang: {"appended": 0, "updated": 0, "unchanged": 0} for lang in languages}
    for lang in languages:
        po = LOCALE_DIR / lang / "LC_MESSAGES" / "django.po"
        if not po.exists():
            print(f"!! Missing {po}")
            continue
        for src, by_lang in TRANSLATIONS.items():
            tr = by_lang.get(lang, "")
            status = upsert_plain_entry(po, src, tr)
            totals[lang][status] += 1
    for lang, counts in totals.items():
        print(
            f"  {lang}: appended {counts['appended']}, " f"updated {counts['updated']}, unchanged {counts['unchanged']}"
        )
    print("\nNow run: python manage.py compilemessages")


if __name__ == "__main__":
    main()
