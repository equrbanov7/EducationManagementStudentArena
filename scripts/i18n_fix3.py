#!/usr/bin/env python3
"""EMSArena i18n — phase 3 catalog appends (category_management + exam monitor JS)."""

import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


CATALOG = {
    # ---- profile.category_management ----
    ("profile.category_management", "eyebrow"): {
        "az": "İdarəetmə",
        "en": "Manage",
        "ru": "Управление",
        "tr": "Yönetim",
    },
    ("profile.category_management", "title"): {
        "az": "Kateqoriyaları idarə et",
        "en": "Manage categories",
        "ru": "Управление категориями",
        "tr": "Kategorileri yönet",
    },
    ("profile.category_management", "subtitle"): {
        "az": "Standart kateqoriyalar, yeni yaradılanlar və alt kateqoriyalar burada görünür.",
        "en": "Default categories, newly created ones and subcategories appear here.",
        "ru": "Здесь отображаются категории по умолчанию, новые и подкатегории.",
        "tr": "Varsayılan kategoriler, yeni oluşturulanlar ve alt kategoriler burada görünür.",
    },
    ("profile.category_management", "root_categories"): {
        "az": "əsas kateqoriya",
        "en": "root categories",
        "ru": "основных категорий",
        "tr": "ana kategori",
    },
    ("profile.category_management", "create_new"): {
        "az": "Yeni kateqoriya yarat",
        "en": "Create new category",
        "ru": "Создать новую категорию",
        "tr": "Yeni kategori oluştur",
    },
    ("profile.category_management", "search_ph_names"): {
        "az": "AZ, EN, RU, TR adlarına görə axtar",
        "en": "Search by AZ, EN, RU, TR names",
        "ru": "Поиск по названиям AZ, EN, RU, TR",
        "tr": "AZ, EN, RU, TR adlarına göre ara",
    },
    ("profile.category_management", "search"): {"az": "Axtar", "en": "Search", "ru": "Поиск", "tr": "Ara"},
    ("profile.category_management", "reset"): {"az": "Sıfırla", "en": "Reset", "ru": "Сбросить", "tr": "Sıfırla"},
    ("profile.category_management", "root_category"): {
        "az": "Əsas kateqoriya",
        "en": "Root category",
        "ru": "Основная категория",
        "tr": "Ana kategori",
    },
    ("profile.category_management", "default"): {
        "az": "Standart",
        "en": "Default",
        "ru": "По умолчанию",
        "tr": "Varsayılan",
    },
    ("profile.category_management", "edit"): {"az": "Düzəliş et", "en": "Edit", "ru": "Редактировать", "tr": "Düzenle"},
    ("profile.category_management", "delete"): {"az": "Sil", "en": "Delete", "ru": "Удалить", "tr": "Sil"},
    ("profile.category_management", "type_category"): {
        "az": "kateqoriyanı",
        "en": "the category",
        "ru": "категорию",
        "tr": "kategoriyi",
    },
    ("profile.category_management", "type_subcategory"): {
        "az": "alt kateqoriyanı",
        "en": "the subcategory",
        "ru": "подкатегорию",
        "tr": "alt kategoriyi",
    },
    ("profile.category_management", "direct_posts"): {
        "az": "birbaşa paylaşım",
        "en": "direct posts",
        "ru": "прямых публикаций",
        "tr": "doğrudan gönderi",
    },
    ("profile.category_management", "show_subcategories"): {
        "az": "Alt kateqoriyaları göstər",
        "en": "Show subcategories",
        "ru": "Показать подкатегории",
        "tr": "Alt kategorileri göster",
    },
    ("profile.category_management", "hide_subcategories"): {
        "az": "Alt kateqoriyaları gizlət",
        "en": "Hide subcategories",
        "ru": "Скрыть подкатегории",
        "tr": "Alt kategorileri gizle",
    },
    ("profile.category_management", "subcategories_count"): {
        "az": "alt kateqoriya",
        "en": "subcategories",
        "ru": "подкатегорий",
        "tr": "alt kategori",
    },
    ("profile.category_management", "showing_filtered"): {
        "az": "Filtrlənənləri göstərir",
        "en": "Showing filtered results",
        "ru": "Показаны отфильтрованные",
        "tr": "Filtrelenenleri gösteriyor",
    },
    ("profile.category_management", "clear_before_delete"): {
        "az": "Silmək üçün əvvəlcə bağlı paylaşımları və ya alt kateqoriyaları təmizləyin.",
        "en": "To delete, first clear linked posts or subcategories.",
        "ru": "Чтобы удалить, сначала очистите связанные публикации или подкатегории.",
        "tr": "Silmek için önce bağlı gönderileri veya alt kategorileri temizleyin.",
    },
    ("profile.category_management", "zero_subcategories"): {
        "az": "0 alt kateqoriya",
        "en": "0 subcategories",
        "ru": "0 подкатегорий",
        "tr": "0 alt kategori",
    },
    ("profile.category_management", "subcategory"): {
        "az": "Alt kateqoriya",
        "en": "Subcategory",
        "ru": "Подкатегория",
        "tr": "Alt kategori",
    },
    ("profile.category_management", "parent"): {
        "az": "Üst kateqoriya",
        "en": "Parent",
        "ru": "Родитель",
        "tr": "Üst kategori",
    },
    ("profile.category_management", "subcategory_has_posts"): {
        "az": "Bu alt kateqoriyaya bağlı paylaşımlar var.",
        "en": "This subcategory has linked posts.",
        "ru": "К этой подкатегории привязаны публикации.",
        "tr": "Bu alt kategoriye bağlı gönderiler var.",
    },
    ("profile.category_management", "no_search_match"): {
        "az": "Axtarışa uyğun kateqoriya tapılmadı.",
        "en": "No categories match your search.",
        "ru": "Категории по запросу не найдены.",
        "tr": "Aramayla eşleşen kategori bulunamadı.",
    },
    ("profile.category_management", "empty"): {
        "az": "Hələ heç bir kateqoriya yoxdur.",
        "en": "No categories yet.",
        "ru": "Категорий пока нет.",
        "tr": "Henüz kategori yok.",
    },
    ("profile.category_management", "edit_modal_title_named"): {
        "az": "Kateqoriyanı redaktə et:",
        "en": "Edit category:",
        "ru": "Редактировать категорию:",
        "tr": "Kategoriyi düzenle:",
    },
    ("profile.category_management", "edit_modal_title"): {
        "az": "Kateqoriyanı redaktə et",
        "en": "Edit category",
        "ru": "Редактировать категорию",
        "tr": "Kategoriyi düzenle",
    },
    ("profile.category_management", "close"): {"az": "Bağla", "en": "Close", "ru": "Закрыть", "tr": "Kapat"},
    ("profile.category_management", "cancel"): {"az": "Ləğv et", "en": "Cancel", "ru": "Отмена", "tr": "İptal"},
    ("profile.category_management", "save"): {"az": "Yadda saxla", "en": "Save", "ru": "Сохранить", "tr": "Kaydet"},
    ("profile.category_management", "delete_modal_title"): {
        "az": "Kateqoriyanı sil",
        "en": "Delete category",
        "ru": "Удалить категорию",
        "tr": "Kategoriyi sil",
    },
    ("profile.category_management", "delete_confirm"): {
        "az": "Bu kateqoriyanı silmək istədiyinizə əminsiniz?",
        "en": "Are you sure you want to delete this category?",
        "ru": "Вы уверены, что хотите удалить эту категорию?",
        "tr": "Bu kategoriyi silmek istediğinizden emin misiniz?",
    },
    # ---- exam live monitor JS strings (context already used by template) ----
    ("exams.template.exam_live_monitor", "js_anonymous"): {
        "az": "Anonim",
        "en": "Anonymous",
        "ru": "Аноним",
        "tr": "Anonim",
    },
    ("exams.template.exam_live_monitor", "js_no_students"): {
        "az": "Hələ tələbə qoşulmayıb.",
        "en": "No students have joined yet.",
        "ru": "Студенты ещё не подключились.",
        "tr": "Henüz öğrenci katılmadı.",
    },
    ("exams.template.exam_live_monitor", "js_load_error"): {
        "az": "Məlumat yüklənə bilmədi.",
        "en": "Failed to load data.",
        "ru": "Не удалось загрузить данные.",
        "tr": "Veriler yüklenemedi.",
    },
    ("exams.template.exam_live_monitor", "js_status_active"): {
        "az": "Aktiv",
        "en": "Active",
        "ru": "Активен",
        "tr": "Aktif",
    },
    ("exams.template.exam_live_monitor", "js_status_submitted"): {
        "az": "Təhvil verilib",
        "en": "Submitted",
        "ru": "Отправлено",
        "tr": "Teslim edildi",
    },
    ("exams.template.exam_live_monitor", "js_status_expired"): {
        "az": "Vaxt bitib",
        "en": "Expired",
        "ru": "Время истекло",
        "tr": "Süre doldu",
    },
    ("exams.template.exam_live_monitor", "js_status_blocked"): {
        "az": "Bloklanıb",
        "en": "Blocked",
        "ru": "Заблокирован",
        "tr": "Engellendi",
    },
    ("exams.template.exam_live_monitor", "js_status_unknown"): {
        "az": "Naməlum",
        "en": "Unknown",
        "ru": "Неизвестно",
        "tr": "Bilinmiyor",
    },
}


def po_has_entry(content, ctx, key):
    return bool(re.search(r'msgctxt "%s"\nmsgid "%s"\n' % (re.escape(ctx), re.escape(key)), content))


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def run():
    report = []
    for lang in LOCALES:
        p = po_path(lang)
        content = open(p, encoding="utf-8").read()
        adds = []
        for (ctx, key), tr in CATALOG.items():
            if po_has_entry(content, ctx, key):
                continue
            adds.append('\nmsgctxt "%s"\nmsgid "%s"\nmsgstr "%s"\n' % (esc(ctx), esc(key), esc(tr.get(lang, tr["en"]))))
        if adds:
            if not content.endswith("\n"):
                content += "\n"
            content += "".join(adds)
            open(p, "w", encoding="utf-8").write(content)
        report.append("  %s: appended %d" % (lang, len(adds)))
    return report


if __name__ == "__main__":
    print("\n".join(run()))
