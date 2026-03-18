from django.utils.translation import get_language


DEFAULT_CATEGORY_TRANSLATIONS = {
    "technology": {
        "az": "Texnologiya",
        "en": "Technology",
        "ru": "Технологии",
        "tr": "Teknoloji",
    },
    "programming": {
        "az": "Proqramlaşdırma",
        "en": "Programming",
        "ru": "Программирование",
        "tr": "Programlama",
    },
    "web-development": {
        "az": "Veb inkişafı",
        "en": "Web Development",
        "ru": "Веб-разработка",
        "tr": "Web geliştirme",
    },
    "data-ai": {
        "az": "Məlumat və süni intellekt",
        "en": "Data & AI",
        "ru": "Данные и ИИ",
        "tr": "Veri ve yapay zeka",
    },
    "cybersecurity": {
        "az": "Kibertəhlükəsizlik",
        "en": "Cybersecurity",
        "ru": "Кибербезопасность",
        "tr": "Siber güvenlik",
    },
    "cloud-devops": {
        "az": "Bulud və DevOps",
        "en": "Cloud & DevOps",
        "ru": "Облако и DevOps",
        "tr": "Bulut ve DevOps",
    },
    "education": {
        "az": "Təhsil",
        "en": "Education",
        "ru": "Образование",
        "tr": "Eğitim",
    },
    "study-tips": {
        "az": "Oxu məsləhətləri",
        "en": "Study Tips",
        "ru": "Советы по учебе",
        "tr": "Çalışma ipuçları",
    },
    "online-learning": {
        "az": "Onlayn öyrənmə",
        "en": "Online Learning",
        "ru": "Онлайн-обучение",
        "tr": "Çevrimiçi öğrenme",
    },
    "career-development": {
        "az": "Karyera inkişafı",
        "en": "Career Development",
        "ru": "Развитие карьеры",
        "tr": "Kariyer gelişimi",
    },
    "language-learning": {
        "az": "Dil öyrənilməsi",
        "en": "Language Learning",
        "ru": "Изучение языков",
        "tr": "Dil öğrenimi",
    },
    "business": {
        "az": "Biznes",
        "en": "Business",
        "ru": "Бизнес",
        "tr": "İş dünyası",
    },
    "entrepreneurship": {
        "az": "Sahibkarlıq",
        "en": "Entrepreneurship",
        "ru": "Предпринимательство",
        "tr": "Girişimcilik",
    },
    "marketing": {
        "az": "Marketinq",
        "en": "Marketing",
        "ru": "Маркетинг",
        "tr": "Pazarlama",
    },
    "finance": {
        "az": "Maliyyə",
        "en": "Finance",
        "ru": "Финансы",
        "tr": "Finans",
    },
    "management": {
        "az": "İdarəetmə",
        "en": "Management",
        "ru": "Управление",
        "tr": "Yönetim",
    },
    "science": {
        "az": "Elm",
        "en": "Science",
        "ru": "Наука",
        "tr": "Bilim",
    },
    "mathematics": {
        "az": "Riyaziyyat",
        "en": "Mathematics",
        "ru": "Математика",
        "tr": "Matematik",
    },
    "physics": {
        "az": "Fizika",
        "en": "Physics",
        "ru": "Физика",
        "tr": "Fizik",
    },
    "biology": {
        "az": "Biologiya",
        "en": "Biology",
        "ru": "Биология",
        "tr": "Biyoloji",
    },
    "research": {
        "az": "Tədqiqat",
        "en": "Research",
        "ru": "Исследования",
        "tr": "Araştırma",
    },
    "lifestyle": {
        "az": "Həyat tərzi",
        "en": "Lifestyle",
        "ru": "Лайфстайл",
        "tr": "Yaşam tarzı",
    },
    "productivity": {
        "az": "Produktivlik",
        "en": "Productivity",
        "ru": "Продуктивность",
        "tr": "Verimlilik",
    },
    "health-wellness": {
        "az": "Sağlamlıq və rifah",
        "en": "Health & Wellness",
        "ru": "Здоровье и благополучие",
        "tr": "Sağlık ve iyi yaşam",
    },
    "travel": {
        "az": "Səyahət",
        "en": "Travel",
        "ru": "Путешествия",
        "tr": "Seyahat",
    },
    "food": {
        "az": "Qida",
        "en": "Food",
        "ru": "Еда",
        "tr": "Yemek",
    },
    "creative": {
        "az": "Yaradıcılıq",
        "en": "Creative",
        "ru": "Креатив",
        "tr": "Yaratıcılık",
    },
    "design": {
        "az": "Dizayn",
        "en": "Design",
        "ru": "Дизайн",
        "tr": "Tasarım",
    },
    "writing": {
        "az": "Yazı",
        "en": "Writing",
        "ru": "Письмо",
        "tr": "Yazı",
    },
    "photography": {
        "az": "Fotoqrafiya",
        "en": "Photography",
        "ru": "Фотография",
        "tr": "Fotoğrafçılık",
    },
    "video-audio": {
        "az": "Video və audio",
        "en": "Video & Audio",
        "ru": "Видео и аудио",
        "tr": "Video ve ses",
    },
}


DEFAULT_CATEGORY_PLACEHOLDERS = {
    "technology": "images/placeholders/category-technology.svg",
    "education": "images/placeholders/category-education.svg",
    "business": "images/placeholders/category-business.svg",
    "science": "images/placeholders/category-science.svg",
    "lifestyle": "images/placeholders/category-lifestyle.svg",
    "creative": "images/placeholders/category-creative.svg",
}


def get_localized_category_name(slug, fallback):
    language = (get_language() or "az").split("-")[0].lower()
    translations = DEFAULT_CATEGORY_TRANSLATIONS.get(slug, {})
    return translations.get(language) or translations.get("en") or fallback


def get_category_placeholder_static_path(category_slug, *, fallback="images/tech-placeholder.svg"):
    return DEFAULT_CATEGORY_PLACEHOLDERS.get(category_slug, fallback)
