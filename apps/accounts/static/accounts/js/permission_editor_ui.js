/**
 * Permission editor interactions:
 * - Multi-language user-friendly labels/descriptions (AZ/EN/RU/TR)
 * - Smooth module open/close animation
 * - Module-level select all / deselect all / bulk add / bulk remove
 * - Per-permission toggle with immediate row state update
 */
document.addEventListener("DOMContentLoaded", function () {
    var editors = document.querySelectorAll("[data-permission-editor]");
    if (!editors.length) {
        return;
    }

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

    var UI_LANG = normalizeLang(document.documentElement ? document.documentElement.lang : "az");
    var text = UI_TEXT[UI_LANG] || UI_TEXT.az;
    var moduleLabels = MODULE_LABELS[UI_LANG] || MODULE_LABELS.az;
    var moduleSubtitles = MODULE_SUBTITLES[UI_LANG] || MODULE_SUBTITLES.az;
    var actionWordMap = ACTION_WORD_MAP[UI_LANG] || ACTION_WORD_MAP.az;

    function titleCase(rawText) {
        return (rawText || "")
            .split(" ")
            .filter(Boolean)
            .map(function (piece) {
                return piece.charAt(0).toUpperCase() + piece.slice(1);
            })
            .join(" ");
    }

    function resolveModulePrefixFromCategory(categoryKey) {
        var normalizedCategory = (categoryKey || "").toLowerCase().trim();
        return CATEGORY_TO_PREFIX[normalizedCategory] || normalizedCategory;
    }

    function getModuleLabel(prefix) {
        var normalizedPrefix = (prefix || "").toLowerCase().trim();
        return moduleLabels[normalizedPrefix] || titleCase(normalizedPrefix);
    }

    function translateActionPart(part) {
        var normalized = (part || "").toLowerCase().trim();
        if (!normalized) {
            return "";
        }
        return actionWordMap[normalized] || titleCase(normalized);
    }

    function getActionLabelFromPermission(permissionKey) {
        var value = (permissionKey || "").trim();
        if (!value || value === "*") {
            return "";
        }
        var parts = value.split(".");
        var actionRaw = parts.slice(1).join(" ").replace(/_/g, " ");
        return actionRaw
            .split(" ")
            .filter(Boolean)
            .map(translateActionPart)
            .join(" ");
    }

    function formatPermissionLabel(permissionKey) {
        var value = (permissionKey || "").trim();
        if (!value) {
            return "";
        }
        if (value === "*") {
            return text.allPermissionsBadge;
        }

        var parts = value.split(".");
        var prefix = parts[0] || "";
        var moduleLabel = getModuleLabel(prefix);
        var actionLabel = getActionLabelFromPermission(value);
        return actionLabel ? moduleLabel + " / " + actionLabel : moduleLabel;
    }

    function formatPermissionDescription(permissionKey) {
        var value = (permissionKey || "").trim();
        if (!value) {
            return "";
        }
        if (value === "*") {
            return text.allPermissionsDescription;
        }

        var parts = value.split(".");
        var prefix = parts[0] || "";
        var moduleLabel = getModuleLabel(prefix);
        var actionLabel = getActionLabelFromPermission(value) || text.genericAction;

        if (UI_LANG === "en") {
            return 'Allows "' + actionLabel + '" in the "' + moduleLabel + '" module.';
        }
        if (UI_LANG === "ru") {
            return 'Разрешает действие "' + actionLabel + '" в разделе "' + moduleLabel + '".';
        }
        if (UI_LANG === "tr") {
            return '"' + moduleLabel + '" bölümünde "' + actionLabel + '" işlemini yapmaya izin verir.';
        }
        return '"' + moduleLabel + '" bölməsində "' + actionLabel + '" əməliyyatını etməyə icazə verir.';
    }

    function syncRowActiveState(row, isActive) {
        if (!row) {
            return;
        }

        row.classList.toggle("is-active", isActive);
        row.classList.toggle("is-inactive", !isActive);

        var statusBadge = row.querySelector("[data-permission-status]");
        if (statusBadge) {
            statusBadge.textContent = isActive ? text.statusActive : text.statusInactive;
            statusBadge.classList.toggle("is-active", isActive);
            statusBadge.classList.toggle("is-inactive", !isActive);
        }
    }

    function syncRowActionButton(row, isActive, options) {
        if (!row) {
            return;
        }

        row.setAttribute("data-permission-active", isActive ? "1" : "0");

        var form = row.querySelector("[data-permission-toggle-form]");
        var actionInput = form ? form.querySelector("[data-permission-action]") : null;
        var syncActionInput = !(options && options.syncActionInput === false);
        if (actionInput && syncActionInput) {
            actionInput.value = isActive ? "remove" : "add";
        }

        var actionButton = row.querySelector("[data-permission-action-btn]");
        if (!actionButton) {
            return;
        }

        actionButton.classList.toggle("permission-action-btn--remove", isActive);
        actionButton.classList.toggle("permission-action-btn--add", !isActive);
        actionButton.innerHTML = isActive
            ? '<i class="fas fa-minus-circle"></i> ' + text.actionRemove
            : '<i class="fas fa-plus-circle"></i> ' + text.actionAdd;
    }

    function bindToggleForms(root) {
        var actionButtons = root.querySelectorAll("[data-permission-action-btn]");
        actionButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                var form = button.closest("[data-permission-toggle-form]");
                var row = button.closest("[data-permission-row]");
                var wasActive = row && row.getAttribute("data-permission-active") === "1";
                var shouldEnable = !wasActive;
                var actionInput = form ? form.querySelector("[data-permission-action]") : null;
                var requestedAction = wasActive ? "remove" : "add";
                if (actionInput) {
                    actionInput.value = requestedAction;
                }

                syncRowActiveState(row, shouldEnable);
                syncRowActionButton(row, shouldEnable, { syncActionInput: false });

                if (form) {
                    button.disabled = true;
                    form.classList.add("is-loading");
                    form.submit();
                }
            });
        });
    }

    function bindPermissionLabels(root) {
        var rows = root.querySelectorAll("[data-permission-row]");
        rows.forEach(function (row) {
            var key = (row.getAttribute("data-permission-key") || "").trim();
            var label = formatPermissionLabel(key);
            var description = formatPermissionDescription(key);
            var labelNode = row.querySelector("[data-permission-label]");
            var descriptionNode = row.querySelector("[data-permission-description]");
            if (labelNode && label) {
                labelNode.textContent = label;
            }
            if (descriptionNode && description) {
                descriptionNode.textContent = description;
            }
            row.setAttribute("data-search", (key + " " + label + " " + description).toLowerCase());
        });
    }

    function bindActivePermissionBadges(root) {
        var badges = root.querySelectorAll("[data-active-permission-badge]");
        badges.forEach(function (badge) {
            var key = (badge.getAttribute("data-permission-key") || "").trim();
            if (!key) {
                return;
            }
            badge.textContent = key === "*" ? text.allPermissionsBadge : formatPermissionLabel(key);
            badge.setAttribute("title", formatPermissionDescription(key));
        });
    }

    function localizeGuide(root) {
        var titleNode = root.querySelector("[data-permission-guide-title]");
        if (titleNode) {
            titleNode.textContent = text.guideTitle;
        }

        var guideTextNode = root.querySelector("[data-permission-guide-text]");
        if (guideTextNode) {
            guideTextNode.textContent = text.guideText;
        }

        root.querySelectorAll("[data-permission-guide-step]").forEach(function (stepNode) {
            var index = parseInt(stepNode.getAttribute("data-permission-guide-step"), 10) - 1;
            if (index >= 0 && index < text.guideSteps.length) {
                stepNode.textContent = text.guideSteps[index];
            }
        });

        var legendActive = root.querySelector('[data-permission-legend="active"]');
        if (legendActive) {
            legendActive.textContent = text.legendActive;
        }
        var legendInactive = root.querySelector('[data-permission-legend="inactive"]');
        if (legendInactive) {
            legendInactive.textContent = text.legendInactive;
        }
        var legendBulk = root.querySelector('[data-permission-legend="bulk"]');
        if (legendBulk) {
            legendBulk.textContent = text.legendBulk;
        }
    }

    function localizeModuleHeaders(root) {
        var modules = root.querySelectorAll("[data-permission-module]");
        modules.forEach(function (module) {
            var category = (module.getAttribute("data-permission-category") || "").trim().toLowerCase();
            var prefix = resolveModulePrefixFromCategory(category);

            var titleNode = module.querySelector("[data-permission-module-title]");
            if (titleNode) {
                titleNode.textContent = getModuleLabel(prefix);
            }

            var subtitleNode = module.querySelector("[data-permission-module-subtitle]");
            if (subtitleNode) {
                subtitleNode.textContent = moduleSubtitles[category] || text.moduleSubtitleFallback;
            }

            var selectAllBtn = module.querySelector("[data-module-select-all]");
            var deselectAllBtn = module.querySelector("[data-module-deselect-all]");
            var bulkAddBtn = module.querySelector("[data-module-bulk-add]");
            var bulkRemoveBtn = module.querySelector("[data-module-bulk-remove]");
            if (selectAllBtn) {
                selectAllBtn.textContent = text.toolbarSelectAll;
            }
            if (deselectAllBtn) {
                deselectAllBtn.textContent = text.toolbarDeselectAll;
            }
            if (bulkAddBtn) {
                bulkAddBtn.textContent = text.toolbarBulkAdd;
            }
            if (bulkRemoveBtn) {
                bulkRemoveBtn.textContent = text.toolbarBulkRemove;
            }
        });
    }

    function localizeTopMeta(root, searchInput, searchSubmitButton, emptyState) {
        if (searchInput) {
            searchInput.placeholder = text.searchPlaceholder;
        }
        if (searchSubmitButton) {
            searchSubmitButton.innerHTML = '<i class="fas fa-search"></i> ' + text.searchButton;
        }
        if (emptyState) {
            emptyState.textContent = text.emptyResults;
        }

        var activeCountNode = root.querySelector("[data-permission-active-count]");
        if (activeCountNode) {
            var count = activeCountNode.getAttribute("data-count") || "0";
            activeCountNode.textContent = text.activeCount.replace("{count}", count);
        }
    }

    function bindModuleAccordionAnimation(modules) {
        if (!modules.length) {
            return;
        }

        var prefersReducedMotion = typeof window.matchMedia === "function"
            && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (prefersReducedMotion) {
            return;
        }

        modules.forEach(function (module) {
            var summary = module.querySelector(".permission-module-summary");
            var body = module.querySelector(".permission-module-body");
            if (!summary || !body || typeof module.animate !== "function") {
                return;
            }

            var currentAnimation = null;
            var isClosing = false;
            var isExpanding = false;

            function clearAnimationState() {
                module.style.height = "";
                module.style.overflow = "";
                currentAnimation = null;
                isClosing = false;
                isExpanding = false;
            }

            function onAnimationFinish(shouldOpen) {
                module.open = shouldOpen;
                clearAnimationState();
            }

            function onAnimationCancel() {
                clearAnimationState();
            }

            function collapse() {
                isClosing = true;
                var startHeight = module.offsetHeight + "px";
                var endHeight = summary.offsetHeight + "px";

                if (currentAnimation) {
                    currentAnimation.cancel();
                }

                module.style.overflow = "hidden";
                currentAnimation = module.animate(
                    { height: [startHeight, endHeight] },
                    { duration: 240, easing: "cubic-bezier(0.4, 0, 0.2, 1)" }
                );
                currentAnimation.onfinish = function () {
                    onAnimationFinish(false);
                };
                currentAnimation.oncancel = onAnimationCancel;
            }

            function expand() {
                isExpanding = true;
                var startHeight = module.offsetHeight + "px";
                var endHeight = summary.offsetHeight + body.offsetHeight + "px";

                if (currentAnimation) {
                    currentAnimation.cancel();
                }

                module.style.overflow = "hidden";
                currentAnimation = module.animate(
                    { height: [startHeight, endHeight] },
                    { duration: 240, easing: "cubic-bezier(0.4, 0, 0.2, 1)" }
                );
                currentAnimation.onfinish = function () {
                    onAnimationFinish(true);
                };
                currentAnimation.oncancel = onAnimationCancel;
            }

            function openModule() {
                module.style.height = module.offsetHeight + "px";
                module.open = true;
                window.requestAnimationFrame(expand);
            }

            summary.addEventListener("click", function (event) {
                event.preventDefault();
                if (isClosing || !module.open) {
                    openModule();
                } else if (isExpanding || module.open) {
                    collapse();
                }
            });
        });
    }

    editors.forEach(function (root) {
        var searchInput = root.querySelector("[data-permission-search]");
        var searchSubmitButton = root.querySelector("[data-permission-search-submit]");
        var searchClearButton = root.querySelector("[data-permission-search-clear]");
        var modules = Array.from(root.querySelectorAll("[data-permission-module]"));
        var emptyState = root.querySelector("[data-permission-empty]");

        localizeGuide(root);
        localizeModuleHeaders(root);
        localizeTopMeta(root, searchInput, searchSubmitButton, emptyState);
        bindPermissionLabels(root);
        bindActivePermissionBadges(root);
        bindToggleForms(root);
        bindModuleAccordionAnimation(modules);

        var moduleApis = modules.map(function (module) {
            var selectAllBtn = module.querySelector("[data-module-select-all]");
            var deselectAllBtn = module.querySelector("[data-module-deselect-all]");
            var bulkAddBtn = module.querySelector("[data-module-bulk-add]");
            var bulkRemoveBtn = module.querySelector("[data-module-bulk-remove]");
            var bulkForm = module.querySelector("[data-permission-bulk-form]");
            var bulkActionInput = module.querySelector("[data-permission-bulk-action]");
            var bulkValuesWrap = module.querySelector("[data-permission-bulk-values]");
            var rowNodes = Array.from(module.querySelectorAll("[data-permission-row]"));

            function allCheckboxes() {
                return Array.from(module.querySelectorAll("[data-permission-select]"));
            }

            function visibleCheckboxes() {
                return allCheckboxes().filter(function (checkbox) {
                    var row = checkbox.closest("[data-permission-row]");
                    return row && !row.hidden;
                });
            }

            function selectedCheckboxes() {
                return allCheckboxes().filter(function (checkbox) {
                    return checkbox.checked;
                });
            }

            function syncBulkButtons() {
                var hasSelection = selectedCheckboxes().length > 0;
                if (bulkAddBtn) {
                    bulkAddBtn.disabled = !hasSelection;
                }
                if (bulkRemoveBtn) {
                    bulkRemoveBtn.disabled = !hasSelection;
                }
            }

            function submitBulk(action) {
                var selected = selectedCheckboxes();
                if (!selected.length || !bulkForm || !bulkActionInput || !bulkValuesWrap) {
                    syncBulkButtons();
                    return;
                }

                bulkActionInput.value = action;
                bulkValuesWrap.innerHTML = "";

                selected.forEach(function (checkbox) {
                    var input = document.createElement("input");
                    input.type = "hidden";
                    input.name = "permissions";
                    input.value = checkbox.value;
                    bulkValuesWrap.appendChild(input);
                });

                if (bulkAddBtn) {
                    bulkAddBtn.disabled = true;
                }
                if (bulkRemoveBtn) {
                    bulkRemoveBtn.disabled = true;
                }

                bulkForm.submit();
            }

            allCheckboxes().forEach(function (checkbox) {
                checkbox.addEventListener("change", syncBulkButtons);
            });

            if (selectAllBtn) {
                selectAllBtn.addEventListener("click", function () {
                    visibleCheckboxes().forEach(function (checkbox) {
                        checkbox.checked = true;
                    });
                    syncBulkButtons();
                });
            }

            if (deselectAllBtn) {
                deselectAllBtn.addEventListener("click", function () {
                    allCheckboxes().forEach(function (checkbox) {
                        checkbox.checked = false;
                    });
                    syncBulkButtons();
                });
            }

            if (bulkAddBtn) {
                bulkAddBtn.addEventListener("click", function () {
                    submitBulk("bulk_add");
                });
            }

            if (bulkRemoveBtn) {
                bulkRemoveBtn.addEventListener("click", function () {
                    submitBulk("bulk_remove");
                });
            }

            syncBulkButtons();

            return {
                module: module,
                rows: rowNodes,
                syncBulkButtons: syncBulkButtons
            };
        });

        function runFilter() {
            var query = ((searchInput && searchInput.value) || "").trim().toLowerCase();
            var visibleModules = 0;

            moduleApis.forEach(function (api) {
                var visibleRows = 0;

                api.rows.forEach(function (row) {
                    var haystack = row.getAttribute("data-search") || "";
                    var isMatch = !query || haystack.indexOf(query) !== -1;
                    row.hidden = !isMatch;
                    if (isMatch) {
                        visibleRows += 1;
                    }
                });

                api.module.hidden = visibleRows === 0;

                if (visibleRows > 0) {
                    visibleModules += 1;
                }

                if (query) {
                    api.module.open = visibleRows > 0;
                } else {
                    api.module.open = false;
                }
                api.module.style.height = "";
                api.module.style.overflow = "";

                api.syncBulkButtons();
            });

            if (emptyState) {
                emptyState.hidden = !query || visibleModules !== 0;
            }
        }

        function syncSearchClearButton() {
            if (!searchInput || !searchClearButton) {
                return;
            }
            searchClearButton.hidden = !searchInput.value.trim();
        }

        if (searchInput) {
            searchInput.addEventListener("input", runFilter);
            searchInput.addEventListener("input", syncSearchClearButton);
            searchInput.addEventListener("keydown", function (event) {
                if (
                    event.key !== "Enter" ||
                    event.shiftKey ||
                    event.ctrlKey ||
                    event.altKey ||
                    event.metaKey ||
                    event.isComposing
                ) {
                    return;
                }
                event.preventDefault();
                runFilter();
            });
        }

        if (searchSubmitButton) {
            searchSubmitButton.addEventListener("click", function () {
                runFilter();
            });
        }

        if (searchClearButton && searchInput) {
            searchClearButton.addEventListener("click", function () {
                searchInput.value = "";
                syncSearchClearButton();
                runFilter();
                searchInput.focus();
            });
        }

        root.querySelectorAll("[data-permission-row]").forEach(function (row) {
            var isActive = row.getAttribute("data-permission-active") === "1";
            syncRowActiveState(row, isActive);
            syncRowActionButton(row, isActive);
        });

        syncSearchClearButton();
        runFilter();
    });
});
