"""Final imtahan demo üçün çoxdilli sual dəsti (AZ / EN / RU).

`seed_final_exam_demo` bu datadan istifadə edərək imtahana 3 dil variantı və
hər dildə eyni sualları yaradır — beləliklə giriş modalında dil seçimi
görünür və məcburidir.
"""

# Demo imtahanın dil variantları (kod → göstərilən ad).
DEMO_LANGUAGES = [
    ("az", "Azərbaycan dili"),
    ("en", "English"),
    ("ru", "Русский"),
]

# Hər sual: (order, answer_mode, {lang: (mətn, [(label, variant_mətni, düzgündür?), ...])}).
MULTILINGUAL_QUESTIONS = [
    (
        1,
        "single",
        {
            "az": (
                "Verilənlər bazasında ACID prinsipində 'A' hərfi nəyi bildirir?",
                [
                    ("A", "Availability (Əlçatanlıq)", False),
                    ("B", "Atomicity (Bölünməzlik)", True),
                    ("C", "Authorization (İcazələndirmə)", False),
                    ("D", "Aggregation (Toplama)", False),
                ],
            ),
            "en": (
                "In the ACID principle, what does the letter 'A' stand for?",
                [
                    ("A", "Availability", False),
                    ("B", "Atomicity", True),
                    ("C", "Authorization", False),
                    ("D", "Aggregation", False),
                ],
            ),
            "ru": (
                "Что означает буква «A» в принципе ACID?",
                [
                    ("A", "Доступность (Availability)", False),
                    ("B", "Атомарность (Atomicity)", True),
                    ("C", "Авторизация", False),
                    ("D", "Агрегация", False),
                ],
            ),
        },
    ),
    (
        2,
        "single",
        {
            "az": (
                "HTTP status kodu 404 nəyi ifadə edir?",
                [
                    ("A", "Server daxili xətası", False),
                    ("B", "Resurs tapılmadı", True),
                    ("C", "İcazə yoxdur", False),
                    ("D", "Uğurlu sorğu", False),
                ],
            ),
            "en": (
                "What does the HTTP status code 404 mean?",
                [
                    ("A", "Internal server error", False),
                    ("B", "Resource not found", True),
                    ("C", "Forbidden", False),
                    ("D", "Successful request", False),
                ],
            ),
            "ru": (
                "Что означает код состояния HTTP 404?",
                [
                    ("A", "Внутренняя ошибка сервера", False),
                    ("B", "Ресурс не найден", True),
                    ("C", "Доступ запрещён", False),
                    ("D", "Успешный запрос", False),
                ],
            ),
        },
    ),
    (
        3,
        "multiple",
        {
            "az": (
                "Aşağıdakılardan hansıları simmetrik şifrələmə alqoritmidir?",
                [
                    ("A", "AES", True),
                    ("B", "RSA", False),
                    ("C", "DES", True),
                    ("D", "ECDSA", False),
                ],
            ),
            "en": (
                "Which of the following are symmetric encryption algorithms?",
                [
                    ("A", "AES", True),
                    ("B", "RSA", False),
                    ("C", "DES", True),
                    ("D", "ECDSA", False),
                ],
            ),
            "ru": (
                "Какие из перечисленных являются алгоритмами симметричного шифрования?",
                [
                    ("A", "AES", True),
                    ("B", "RSA", False),
                    ("C", "DES", True),
                    ("D", "ECDSA", False),
                ],
            ),
        },
    ),
    (
        4,
        "single",
        {
            "az": (
                "Python-da len() funksiyası nə qaytarır?",
                [
                    ("A", "Obyektin növünü", False),
                    ("B", "Obyektin element/simvol sayını", True),
                    ("C", "Obyektin ünvanını", False),
                    ("D", "Obyektin dəyərini", False),
                ],
            ),
            "en": (
                "What does the len() function return in Python?",
                [
                    ("A", "The object's type", False),
                    ("B", "The number of elements/characters", True),
                    ("C", "The object's memory address", False),
                    ("D", "The object's value", False),
                ],
            ),
            "ru": (
                "Что возвращает функция len() в Python?",
                [
                    ("A", "Тип объекта", False),
                    ("B", "Количество элементов/символов", True),
                    ("C", "Адрес объекта", False),
                    ("D", "Значение объекта", False),
                ],
            ),
        },
    ),
    (
        5,
        "single",
        {
            "az": (
                "Normallaşdırmanın (normalization) əsas məqsədi nədir?",
                [
                    ("A", "Verilən təkrarlanmasını azaltmaq", True),
                    ("B", "Serveri sürətləndirmək", False),
                    ("C", "Şəbəkə trafikini artırmaq", False),
                    ("D", "Faylları şifrələmək", False),
                ],
            ),
            "en": (
                "What is the main goal of database normalization?",
                [
                    ("A", "Reduce data redundancy", True),
                    ("B", "Speed up the server", False),
                    ("C", "Increase network traffic", False),
                    ("D", "Encrypt files", False),
                ],
            ),
            "ru": (
                "Какова основная цель нормализации базы данных?",
                [
                    ("A", "Уменьшить избыточность данных", True),
                    ("B", "Ускорить сервер", False),
                    ("C", "Увеличить сетевой трафик", False),
                    ("D", "Шифровать файлы", False),
                ],
            ),
        },
    ),
    (
        6,
        "single",
        {
            "az": (
                "REST API-də hansı metod resursu YENİLƏMƏK üçün istifadə olunur?",
                [
                    ("A", "GET", False),
                    ("B", "DELETE", False),
                    ("C", "PUT/PATCH", True),
                    ("D", "OPTIONS", False),
                ],
            ),
            "en": (
                "Which method is used to UPDATE a resource in a REST API?",
                [
                    ("A", "GET", False),
                    ("B", "DELETE", False),
                    ("C", "PUT/PATCH", True),
                    ("D", "OPTIONS", False),
                ],
            ),
            "ru": (
                "Какой метод используется для ОБНОВЛЕНИЯ ресурса в REST API?",
                [
                    ("A", "GET", False),
                    ("B", "DELETE", False),
                    ("C", "PUT/PATCH", True),
                    ("D", "OPTIONS", False),
                ],
            ),
        },
    ),
]

__all__ = ["DEMO_LANGUAGES", "MULTILINGUAL_QUESTIONS"]
