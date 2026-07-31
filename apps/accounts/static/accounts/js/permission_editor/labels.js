/* Permission editor localized labels and permission text helpers.
 *
 * Etiketlər dil üzrə AYRI bloklarda saxlanılır (`MODULE_LABELS[uiLang]`) — yəni
 * seçilən blok onsuz da düzgün dildədir və `gettext()` sarğısına ehtiyac yoxdur.
 * Əvvəllər bəzi dəyərlər `gettext("Yapı")` kimi sarınmışdı: runtime-da bu no-op
 * idi (aktiv dil tr olanda tr mətnin özünü qaytarır), lakin türkcə/rusca
 * literalları `djangojs` kataloquna msgid kimi sızdırırdı — kataloqda mənbə
 * dilinin qarışmasının səbəblərindən biri məhz bu idi (2026-07-31 auditi).
 * 113 sarğı silindi; dəyərlər dəyişmədi.
 */
(function (ns, document) {
    "use strict";

    var CATEGORY_TO_PREFIX = {
        organization: "org",
        structure: "unit",
        members: "member",
        roles: "role",
        courses: "course",
        grading: "grade",
        exams: "exam",
        appeal: "appeal",
        analytics: "analytics",
        qa: "qa",
        audit: "audit"
    };

    var MODULE_LABELS = {
        az: {
            org: "Təşkilat",
            unit: "Struktur",
            member: "Üzvlər",
            role: "Rollar",
            course: "Kurslar",
            assignment: "Sərbəst işlər",
            project: "Kurs işləri",
            lab: "Lab işləri",
            grade: "Qiymətləndirmə",
            exam: "İmtahanlar",
            appeal: "Apellyasiya",
            analytics: "Analitika",
            qa: "Keyfiyyət",
            audit: "Audit"
        },
        en: {
            org: "Organization",
            unit: "Structure",
            member: "Members",
            role: "Roles",
            course: "Courses",
            assignment: "Assignments",
            project: "Coursework",
            lab: "Lab Work",
            grade: "Grading",
            exam: "Exams",
            appeal: "Appeals",
            analytics: "Analytics",
            qa: "Quality",
            audit: "Audit"
        },
        ru: {
            org: "Организация",
            unit: "Структура",
            member: "Участники",
            role: "Роли",
            course: "Курсы",
            assignment: "Задания",
            project: "Курсовые работы",
            lab: "Лабораторные работы",
            grade: "Оценивание",
            exam: "Экзамены",
            appeal: "Апелляции",
            analytics: "Аналитика",
            qa: "Качество",
            audit: "Аудит"
        },
        tr: {
            org: "Organizasyon",
            unit: "Yapı",
            member: "Üyeler",
            role: "Roller",
            course: "Kurslar",
            assignment: "Ödevler",
            project: "Kurs projeleri",
            lab: "Laboratuvar çalışmaları",
            grade: "Değerlendirme",
            exam: "Sınavlar",
            appeal: "İtirazlar",
            analytics: "Analitik",
            qa: "Kalite",
            audit: "Denetim"
        }
    };

    var MODULE_SUBTITLES = {
        az: {
            organization: "Təşkilat ayarları və idarəetmə əməliyyatları",
            structure: "Fakültə, şöbə və struktur vahidləri",
            members: "İstifadəçilər və üzvlüklə bağlı əməliyyatlar",
            roles: "Rol təyini və rol səviyyələri",
            courses: "Kurs yaradılması və kurs idarəetməsi",
            grading: "Qiymətləndirmə və nəticə axınları",
            exams: "İmtahan idarəetməsi və nəzarət",
            appeal: "Apellyasiya müraciətləri",
            analytics: "Analitik hesabat və göstəricilər",
            qa: "Keyfiyyət yoxlaması əməliyyatları",
            audit: "Tarixçə və audit log baxışı"
        },
        en: {
            organization: "Organization settings and management operations",
            structure: "Faculty, department and structural units",
            members: "User and membership operations",
            roles: "Role assignment and role levels",
            courses: "Course creation and course management",
            grading: "Grading and result workflows",
            exams: "Exam management and monitoring",
            appeal: "Appeal requests",
            analytics: "Analytical reports and metrics",
            qa: "Quality assurance operations",
            audit: "History and audit log access"
        },
        ru: {
            organization: "Настройки организации и управленческие действия",
            structure: "Факультеты, отделы и структурные единицы",
            members: "Операции с пользователями и участниками",
            roles: "Назначение ролей и уровни ролей",
            courses: "Создание и управление курсами",
            grading: "Оценивание и процессы результатов",
            exams: "Управление экзаменами и контроль",
            appeal: "Заявки на апелляцию",
            analytics: "Аналитические отчеты и показатели",
            qa: "Операции по контролю качества",
            audit: "История изменений и аудит-лог"
        },
        tr: {
            organization: "Organizasyon ayarları ve yönetim işlemleri",
            structure: "Fakülte, bölüm ve yapısal birimler",
            members: "Kullanıcı ve üyelik işlemleri",
            roles: "Rol atama ve rol seviyeleri",
            courses: "Kurs oluşturma ve kurs yönetimi",
            grading: "Değerlendirme ve sonuç akışları",
            exams: "Sınav yönetimi ve izleme",
            appeal: "İtiraz başvuruları",
            analytics: "Analitik raporlar ve metrikler",
            qa: "Kalite kontrol işlemleri",
            audit: "Geçmiş ve denetim logu erişimi"
        }
    };

    var ACTION_WORD_MAP = {
        az: {
            view: "Baxış",
            list: "Siyahı",
            create: "Yaratma",
            edit: "Redaktə",
            update: "Yeniləmə",
            delete: "Silmə",
            settings: "Ayarlar",
            manage: "İdarəetmə",
            assign: "Təyin etmə",
            revoke: "Geri çəkmə",
            approve: "Təsdiq",
            reject: "Rədd etmə",
            export: "İxrac",
            import: "İdxal",
            publish: "Yayımlama",
            archive: "Arxivləmə",
            permissions: "İcazələr",
            permission: "İcazə",
            members: "Üzvlər",
            role: "Rol",
            roles: "Rollar",
            grades: "Qiymətlər",
            grade: "Qiymət",
            exam: "İmtahan",
            exams: "İmtahanlar",
            analytics: "Analitika",
            audit: "Audit"
        },
        en: {
            view: "View",
            list: "List",
            create: "Create",
            edit: "Edit",
            update: "Update",
            delete: "Delete",
            settings: "Settings",
            manage: "Manage",
            assign: "Assign",
            revoke: "Revoke",
            approve: "Approve",
            reject: "Reject",
            export: "Export",
            import: "Import",
            publish: "Publish",
            archive: "Archive",
            permissions: "Permissions",
            permission: "Permission",
            members: "Members",
            role: "Role",
            roles: "Roles",
            grades: "Grades",
            grade: "Grade",
            exam: "Exam",
            exams: "Exams",
            analytics: "Analytics",
            audit: "Audit"
        },
        ru: {
            view: "Просмотр",
            list: "Список",
            create: "Создание",
            edit: "Редактирование",
            update: "Обновление",
            delete: "Удаление",
            settings: "Настройки",
            manage: "Управление",
            assign: "Назначение",
            revoke: "Отзыв",
            approve: "Подтверждение",
            reject: "Отклонение",
            export: "Экспорт",
            import: "Импорт",
            publish: "Публикация",
            archive: "Архивирование",
            permissions: "Разрешения",
            permission: "Разрешение",
            members: "Участники",
            role: "Роль",
            roles: "Роли",
            grades: "Оценки",
            grade: "Оценка",
            exam: "Экзамен",
            exams: "Экзамены",
            analytics: "Аналитика",
            audit: "Аудит"
        },
        tr: {
            view: "Görüntüleme",
            list: "Listeleme",
            create: "Oluşturma",
            edit: "Düzenleme",
            update: "Güncelleme",
            delete: "Silme",
            settings: "Ayarlar",
            manage: "Yönetim",
            assign: "Atama",
            revoke: "Geri çekme",
            approve: "Onaylama",
            reject: "Reddetme",
            export: "Dışa aktarma",
            import: "İçe aktarma",
            publish: "Yayınlama",
            archive: "Arşivleme",
            permissions: "İzinler",
            permission: "İzin",
            members: "Üyeler",
            role: "Rol",
            roles: "Roller",
            grades: "Notlar",
            grade: "Not",
            exam: "Sınav",
            exams: "Sınavlar",
            analytics: "Analitik",
            audit: "Denetim"
        }
    };

    var UI_TEXT = {
        az: {
            guideTitle: "Bu bölmə nə üçündür?",
            guideText: "Bu rola hansı funksiyaların açıq olacağını buradan idarə edirsiniz.",
            guideSteps: [
                "Bölməni açın (məs: Təşkilat, Üzvlər)",
                "“Əlavə et” ilə aktiv edin, “Sil” ilə söndürün",
                "Çoxlu seçim üçün checkbox + toplu düymələrdən istifadə edin"
            ],
            legendActive: "Aktiv: icazə açıqdır, funksiya işləyir.",
            legendInactive: "Deaktiv: icazə bağlıdır, funksiya məhduddur.",
            legendBulk: "Bulk: birdən çox icazəni eyni anda dəyişir.",
            allPermissionsBadge: "Bütün icazələr (*)",
            allPermissionsDescription: "Bu rol üçün bütün icazələr aktivdir.",
            statusActive: "Aktiv",
            statusInactive: "Deaktiv",
            actionAdd: "Əlavə et",
            actionRemove: "Sil",
            searchPlaceholder: "İcazə axtar (məs: view, edit, member)",
            searchButton: "Axtar",
            emptyResults: "Nəticə tapılmadı.",
            activeCount: "Aktiv icazələr: {count}",
            toolbarSelectAll: "Hamısını seç",
            toolbarDeselectAll: "Seçimi sıfırla",
            toolbarBulkAdd: "Seçilənləri əlavə et",
            toolbarBulkRemove: "Seçilənləri sil",
            genericAction: "əməliyyat",
            moduleSubtitleFallback: "Bu bölmə üçün icazələr"
        },
        en: {
            guideTitle: "What is this section for?",
            guideText: "Manage which features are enabled for this role.",
            guideSteps: [
                "Open a module (for example: Organization, Members)",
                "Use “Add” to enable and “Remove” to disable",
                "Use checkboxes + bulk buttons for multiple permissions"
            ],
            legendActive: "Active: permission is enabled and feature is usable.",
            legendInactive: "Inactive: permission is disabled and feature is limited.",
            legendBulk: "Bulk: changes multiple permissions at once.",
            allPermissionsBadge: "All permissions (*)",
            allPermissionsDescription: "All permissions are enabled for this role.",
            statusActive: "Active",
            statusInactive: "Inactive",
            actionAdd: "Add",
            actionRemove: "Remove",
            searchPlaceholder: "Search permission (e.g. view, edit, member)",
            searchButton: "Search",
            emptyResults: "No results found.",
            activeCount: "Active permissions: {count}",
            toolbarSelectAll: "Select all",
            toolbarDeselectAll: "Clear selection",
            toolbarBulkAdd: "Add selected",
            toolbarBulkRemove: "Remove selected",
            genericAction: "action",
            moduleSubtitleFallback: "Permissions for this module"
        },
        ru: {
            guideTitle: "Для чего этот раздел?",
            guideText: "Здесь вы управляете, какие функции открыты для этой роли.",
            guideSteps: [
                "Откройте модуль (например: Организация, Участники)",
                "Используйте «Добавить» для включения и «Удалить» для отключения",
                "Для массовых изменений используйте чекбоксы и bulk-кнопки"
            ],
            legendActive: "Активно: разрешение включено, функция работает.",
            legendInactive: "Неактивно: разрешение выключено, функция ограничена.",
            legendBulk: "Bulk: изменяет несколько разрешений сразу.",
            allPermissionsBadge: "Все разрешения (*)",
            allPermissionsDescription: "Для этой роли включены все разрешения.",
            statusActive: "Активно",
            statusInactive: "Неактивно",
            actionAdd: "Добавить",
            actionRemove: "Удалить",
            searchPlaceholder: "Поиск разрешения (например: view, edit, member)",
            searchButton: "Поиск",
            emptyResults: "Ничего не найдено.",
            activeCount: "Активные разрешения: {count}",
            toolbarSelectAll: "Выбрать все",
            toolbarDeselectAll: "Сбросить выбор",
            toolbarBulkAdd: "Добавить выбранные",
            toolbarBulkRemove: "Удалить выбранные",
            genericAction: "действие",
            moduleSubtitleFallback: "Разрешения для этого модуля"
        },
        tr: {
            guideTitle: "Bu bölüm ne içindir?",
            guideText: "Bu rol için hangi özelliklerin açık olacağını buradan yönetirsiniz.",
            guideSteps: [
                "Bir modül açın (örnek: Organizasyon, Üyeler)",
                "Etkinleştirmek için “Ekle”, kapatmak için “Sil” kullanın",
                "Çoklu işlem için checkbox + toplu butonları kullanın"
            ],
            legendActive: "Aktif: izin açık, özellik kullanılabilir.",
            legendInactive: "Pasif: izin kapalı, özellik kısıtlı.",
            legendBulk: "Bulk: birden fazla izni aynı anda değiştirir.",
            allPermissionsBadge: "Tüm izinler (*)",
            allPermissionsDescription: "Bu rol için tüm izinler aktiftir.",
            statusActive: "Aktif",
            statusInactive: "Pasif",
            actionAdd: "Ekle",
            actionRemove: "Sil",
            searchPlaceholder: "İzin ara (ör: view, edit, member)",
            searchButton: "Ara",
            emptyResults: "Sonuç bulunamadı.",
            activeCount: "Aktif izinler: {count}",
            toolbarSelectAll: "Tümünü seç",
            toolbarDeselectAll: "Seçimi temizle",
            toolbarBulkAdd: "Seçilenleri ekle",
            toolbarBulkRemove: "Seçilenleri sil",
            genericAction: "işlem",
            moduleSubtitleFallback: "Bu modül için izinler"
        }
    };

    function normalizeLang(langValue) {
        var normalized = (langValue || "").toLowerCase().trim();
        if (!normalized) {
            return "az";
        }
        var shortCode = normalized.slice(0, 2);
        return ["az", "en", "ru", "tr"].indexOf(shortCode) !== -1 ? shortCode : "az";
    }

    function titleCase(rawText) {
        return (rawText || "")
            .split(" ")
            .filter(Boolean)
            .map(function (piece) {
                return piece.charAt(0).toUpperCase() + piece.slice(1);
            })
            .join(" ");
    }

    function createContext() {
        var uiLang = normalizeLang(document.documentElement ? document.documentElement.lang : "az");
        return {
            uiLang: uiLang,
            text: UI_TEXT[uiLang] || UI_TEXT.az,
            moduleLabels: MODULE_LABELS[uiLang] || MODULE_LABELS.az,
            moduleSubtitles: MODULE_SUBTITLES[uiLang] || MODULE_SUBTITLES.az,
            actionWordMap: ACTION_WORD_MAP[uiLang] || ACTION_WORD_MAP.az
        };
    }

    function resolveModulePrefixFromCategory(categoryKey) {
        var normalizedCategory = (categoryKey || "").toLowerCase().trim();
        return CATEGORY_TO_PREFIX[normalizedCategory] || normalizedCategory;
    }

    function getModuleLabel(ctx, prefix) {
        var normalizedPrefix = (prefix || "").toLowerCase().trim();
        return ctx.moduleLabels[normalizedPrefix] || titleCase(normalizedPrefix);
    }

    function translateActionPart(ctx, part) {
        var normalized = (part || "").toLowerCase().trim();
        if (!normalized) {
            return "";
        }
        return ctx.actionWordMap[normalized] || titleCase(normalized);
    }

    function getActionLabelFromPermission(ctx, permissionKey) {
        var value = (permissionKey || "").trim();
        if (!value || value === "*") {
            return "";
        }
        var parts = value.split(".");
        var actionRaw = parts.slice(1).join(" ").replace(/_/g, " ");
        return actionRaw
            .split(" ")
            .filter(Boolean)
            .map(function (part) {
                return translateActionPart(ctx, part);
            })
            .join(" ");
    }

    function formatPermissionLabel(ctx, permissionKey) {
        var value = (permissionKey || "").trim();
        if (!value) {
            return "";
        }
        if (value === "*") {
            return ctx.text.allPermissionsBadge;
        }

        var parts = value.split(".");
        var prefix = parts[0] || "";
        var moduleLabel = getModuleLabel(ctx, prefix);
        var actionLabel = getActionLabelFromPermission(ctx, value);
        return actionLabel ? moduleLabel + " / " + actionLabel : moduleLabel;
    }

    function formatPermissionDescription(ctx, permissionKey) {
        var value = (permissionKey || "").trim();
        if (!value) {
            return "";
        }
        if (value === "*") {
            return ctx.text.allPermissionsDescription;
        }

        var parts = value.split(".");
        var prefix = parts[0] || "";
        var moduleLabel = getModuleLabel(ctx, prefix);
        var actionLabel = getActionLabelFromPermission(ctx, value) || ctx.text.genericAction;

        if (ctx.uiLang === "en") {
            return 'Allows "' + actionLabel + '" in the "' + moduleLabel + '" module.';
        }
        if (ctx.uiLang === "ru") {
            return 'Разрешает действие "' + actionLabel + '" в разделе "' + moduleLabel + '".';
        }
        if (ctx.uiLang === "tr") {
            return '"' + moduleLabel + '" bölümünde "' + actionLabel + '" işlemini yapmaya izin verir.';
        }
        return '"' + moduleLabel + '" bölməsində "' + actionLabel + '" əməliyyatını etməyə icazə verir.';
    }

    ns.labels = {
        createContext: createContext,
        formatPermissionDescription: formatPermissionDescription,
        formatPermissionLabel: formatPermissionLabel,
        getModuleLabel: getModuleLabel,
        resolveModulePrefixFromCategory: resolveModulePrefixFromCategory
    };
})(window.EMSPermissionEditor = window.EMSPermissionEditor || {}, document);
