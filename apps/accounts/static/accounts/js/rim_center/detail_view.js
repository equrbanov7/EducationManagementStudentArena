/* RİM mərkəzi — istifadəçi detal kartı (sahib 2026-11-04: «RİM hər özəllik olsun, modern UX/UI»).
 *
 * Bölmələr: Əsas məlumatlar · Vəzifə və bölmə (fakültə → kafedra) · Rollar · Status və təhlükəsizlik.
 * Bütün server datası `ns.escape`-dən keçir. Düymələrin görünməsi UI rahatlığıdır — qapı serverdədir.
 * Hadisələr `detail_events.js`-dədir (EMSDelegate, AJAX-safe).
 */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCenter = window.EMSRimCenter || {});
    var view = (ns.detailView = {});
    var esc = ns.escape;
    var OTHER = "__other__";

    function t(key) {
        return ns.t(key);
    }

    function section(icon, titleKey, body, extraClass) {
        return (
            '<section class="rim-sec' + (extraClass ? " " + extraClass : "") + '">' +
            '<h4 class="rim-sec__title"><i class="fas ' + icon + '" aria-hidden="true"></i> ' + esc(t(titleKey)) + "</h4>" +
            body +
            "</section>"
        );
    }

    function readItem(labelKey, value) {
        return (
            '<div class="rim-detail-item"><span class="rim-detail-key">' + esc(t(labelKey)) +
            '</span><span class="rim-detail-value">' + esc(value || "—") + "</span></div>"
        );
    }

    function selectShell(inner, attrs) {
        return (
            '<div class="bootstrap-single-select bootstrap-single-select--ems">' +
            '<select class="ems-select bootstrap-single-select__native" data-bootstrap-select data-live-search="true"' +
            ' data-live-search-placeholder="' + esc(t("search_placeholder")) + '"' +
            ' data-live-search-empty="' + esc(t("search_empty")) + '"' + attrs + ">" + inner + "</select></div>"
        );
    }

    /* ── Başlıq: status + bayraqlar + idarə olunmama səbəbi ─────────────── */

    function summary(user) {
        var html = '<div class="rim-summary">' + ns.render.statusBadge(user) + ns.render.flags(user) + "</div>";
        if (!user.manageable && user.not_manageable_message) {
            html += '<p class="rim-warning" role="note"><i class="fas fa-lock" aria-hidden="true"></i> ' +
                esc(user.not_manageable_message) + "</p>";
        }
        if (user.status === "archived" && user.archive_kind === "staff") {
            html += '<p class="rim-warning" data-rim-archive-note><i class="fas fa-box-archive" aria-hidden="true"></i> ' +
                esc(t("archived_staff_note")) + "</p>";
        } else if (user.archive_restore && user.archive_restore.note) {
            html += '<p class="' + (user.archive_restore.eligible ? "rim-warning" : "rim-note") + '" data-rim-archive-note>' +
                '<i class="fas fa-box-archive" aria-hidden="true"></i> ' + esc(user.archive_restore.note) + "</p>";
        }
        return html;
    }

    /* ── Əsas məlumatlar ─────────────────────────────────────────────────── */

    var BASIC_FIELDS = ["username", "first_name", "last_name", "patronymic", "email", "phone", "fin"];

    function basics(user) {
        if (!(user.actions && user.actions.edit)) {
            return section("fa-id-card", "sec_basics",
                '<div class="rim-detail-grid">' +
                readItem("username", user.username) + readItem("full_name", user.full_name) +
                readItem("email", user.email) + readItem("fin", user.fin) + readItem("phone", user.phone) +
                "</div>");
        }
        var fields = BASIC_FIELDS.map(function (name) {
            if (name === "phone") {
                return '<div class="rim-field" data-rim-field="phone"><label class="rim-field-label" for="rim-edit-phone">' +
                    esc(t(name)) + '</label><div data-rim-phone-slot></div>' +
                    '<p class="rim-field-error" data-rim-field-error="phone" hidden></p></div>';
            }
            var attrs = name === "email" ? ' type="email" autocomplete="off"' : ' type="text" autocomplete="off"';
            if (name === "fin") {
                attrs += ' maxlength="7" class="rim-input rim-input--mono"';
            } else {
                attrs += ' class="rim-input"';
            }
            return '<div class="rim-field" data-rim-field="' + esc(name) + '"><label class="rim-field-label" for="rim-edit-' +
                esc(name) + '">' + esc(t(name)) + '</label><input id="rim-edit-' + esc(name) + '"' + attrs +
                ' data-rim-edit-field="' + esc(name) + '" data-initial="' + esc(user[name] || "") + '" value="' +
                esc(user[name] || "") + '" aria-describedby="rim-edit-' + esc(name) + '-err">' +
                '<p class="rim-field-error" id="rim-edit-' + esc(name) + '-err" data-rim-field-error="' + esc(name) +
                '" hidden></p></div>';
        }).join("");
        return section("fa-id-card", "sec_basics",
            '<div class="rim-form-grid" data-rim-edit-form>' + fields + "</div>" +
            '<p class="rim-error" data-rim-edit-error role="alert" hidden></p>' +
            '<div class="rim-sec__foot"><span class="rim-sec__hint" data-rim-edit-dirty hidden>' + esc(t("unsaved")) +
            '</span><button type="button" class="rim-btn rim-btn--primary" data-rim-edit-save disabled>' +
            '<i class="fas fa-floppy-disk" aria-hidden="true"></i> ' + esc(t("save")) + "</button></div>");
    }

    /* ── Vəzifə (standart siyahı + «Digər») ──────────────────────────────── */

    function positionBlock(user) {
        var current = user.staff_position || "";
        if (!user.can_edit_position) {
            return '<div class="rim-detail-grid">' + readItem("staff_position", current) + "</div>";
        }
        var known = false;
        var options = (user.position_options || []).map(function (opt) {
            var selected = opt.value === current;
            known = known || selected;
            return '<option value="' + esc(opt.value) + '"' + (selected ? " selected" : "") + ">" + esc(opt.label) + "</option>";
        }).join("");
        var custom = current && !known
            ? '<option value="' + esc(current) + '" selected data-subtext="' + esc(t("position_custom")) + '">' + esc(current) + "</option>"
            : "";
        return (
            '<div class="rim-position" data-rim-position data-initial="' + esc(current) + '">' +
            '<label class="rim-field-label" for="rim-position-select">' + esc(t("staff_position")) + "</label>" +
            '<div class="rim-position__row">' +
            selectShell('<option value="">' + esc(t("position_none")) + "</option>" + custom + options +
                '<option value="' + OTHER + '">' + esc(t("position_other")) + "</option>",
                ' id="rim-position-select" data-rim-position-select') +
            '<input type="text" class="rim-input" maxlength="255" data-rim-position-other hidden' +
            ' placeholder="' + esc(t("position_other_placeholder")) + '" aria-label="' + esc(t("position_other")) + '">' +
            '<button type="button" class="rim-btn rim-btn--primary" data-rim-position-save disabled>' + esc(t("save")) + "</button>" +
            "</div>" +
            '<p class="rim-field-error" data-rim-position-error role="alert" hidden></p>' +
            "</div>"
        );
    }

    /* ── Bölmə: fakültə → kafedra ────────────────────────────────────────── */

    function whereLabel(row) {
        if (!row.unit_id) {
            return '<span class="rim-pill rim-pill--warn"><i class="fas fa-circle-exclamation" aria-hidden="true"></i> ' +
                esc(t("unit_unassigned")) + "</span>";
        }
        return '<span class="rim-place__where">' +
            (row.faculty_name ? esc(row.faculty_name) + ' <i class="fas fa-angle-right" aria-hidden="true"></i> ' : "") +
            "<strong>" + esc(row.unit_name) + "</strong></span>";
    }

    function placementRow(row, card) {
        var head = '<div class="rim-place__head"><span class="rim-place__role">' + esc(row.role_label) + "</span>" +
            whereLabel(row) + "</div>";
        if (!row.editable) {
            return '<div class="rim-place is-locked">' + head + '<p class="rim-note rim-place__lock"><i class="fas fa-lock" aria-hidden="true"></i> ' +
                esc(row.locked_reason) + "</p></div>";
        }
        var units = (card.units || []).filter(function (unit) {
            return (" " + unit.kinds + " ").indexOf(" " + row.kind + " ") !== -1;
        });
        var facultyIds = {};
        units.forEach(function (unit) {
            if (unit.faculty_id) {
                facultyIds[unit.faculty_id] = true;
            }
        });
        var faculties = (card.faculties || []).filter(function (faculty) {
            return facultyIds[faculty.id];
        });
        var facultyOptions = '<option value="">' + esc(t("all_faculties")) + "</option>" + faculties.map(function (faculty) {
            return '<option value="' + esc(faculty.id) + '"' + (faculty.id === row.faculty_id ? " selected" : "") + ">" +
                esc(faculty.name) + "</option>";
        }).join("");
        var unitOptions = '<option value="">' + esc(t("unit_placeholder")) + "</option>" + units.map(function (unit) {
            return '<option value="' + esc(unit.id) + '" data-faculty="' + esc(unit.faculty_id) + '"' +
                (unit.faculty ? ' data-subtext="' + esc(unit.faculty) + '"' : "") +
                ' data-search="' + esc((unit.code || "") + " " + (unit.faculty || "")) + '"' +
                (unit.id === row.unit_id ? " selected" : "") + ">" + esc(unit.name) + "</option>";
        }).join("");
        var hint = row.kind === "teacher" ? '<p class="rim-sec__hint">' + esc(t("placement_hint_teacher")) + "</p>" : "";
        return (
            '<div class="rim-place" data-rim-place="' + esc(row.id) + '" data-current-unit="' + esc(row.unit_id) + '">' + head +
            '<div class="rim-place__grid">' +
            '<div><label class="rim-field-label">' + esc(t("faculty")) + "</label>" +
            selectShell(facultyOptions, ' data-rim-place-faculty aria-label="' + esc(t("faculty")) + '"') + "</div>" +
            '<div><label class="rim-field-label">' + esc(t("unit")) + "</label>" +
            selectShell(unitOptions, ' data-rim-place-unit aria-label="' + esc(t("unit")) + '"') + "</div>" +
            "</div>" + hint +
            '<p class="rim-field-error" data-rim-place-error role="alert" hidden></p>' +
            '<div class="rim-sec__foot"><button type="button" class="rim-btn rim-btn--primary" data-rim-place-save disabled>' +
            '<i class="fas fa-sitemap" aria-hidden="true"></i> ' + esc(t("save_unit")) + "</button></div></div>"
        );
    }

    function academicBlock(card) {
        var records = card.records || [];
        if (!records.length) {
            return '<p class="rim-note">' + esc(card.disabled_reason || t("no_academic_record")) + "</p>";
        }
        return '<div class="rim-detail-grid">' + records.map(function (record) {
            return '<div class="rim-detail-item"><span class="rim-detail-key">' + esc(t("academic_record")) + "</span>" +
                '<span class="rim-detail-value">' + esc([record.group, record.program].filter(Boolean).join(" · ") || "—") +
                '</span><span class="rim-pill rim-pill--' + esc(record.status) + '">' + esc(record.status_label) + "</span></div>";
        }).join("") + "</div>";
    }

    function positionSection(user) {
        if (user.graduation) {
            return section("fa-graduation-cap", "sec_academic", academicBlock(user.graduation));
        }
        var body = positionBlock(user);
        var card = user.placement;
        if (card) {
            var rows = card.memberships || [];
            body += '<p class="rim-sec__subtitle">' + esc(t("placement_title")) + "</p>";
            body += rows.length
                ? rows.map(function (row) { return placementRow(row, card); }).join("")
                : '<p class="rim-note">' + esc(t("placement_empty")) + "</p>";
        }
        return section("fa-sitemap", "sec_position", body);
    }

    /* ── Rollar ──────────────────────────────────────────────────────────── */

    function rolesSection(user) {
        var cfg = ns.config() || {};
        return section("fa-user-shield", "roles",
            '<div class="rim-card-roles">' + ns.render.roleChips(user) + "</div>" +
            '<div class="rim-sec__foot"><a class="rim-btn rim-btn--ghost rim-btn--sm" href="' +
            esc(user.role_assignment_url || cfg.roleAssignmentUrl || "#") + '">' +
            '<i class="fas fa-arrow-up-right-from-square" aria-hidden="true"></i> ' + esc(t("manage_roles")) + "</a></div>");
    }

    /* ── Status və təhlükəsizlik — əməl kartları ─────────────────────────── */

    function tile(icon, tone, titleKey, descKey, button, disabledReason) {
        return (
            '<div class="rim-tile rim-tile--' + tone + (button ? "" : " is-disabled") + '">' +
            '<span class="rim-tile__icon" aria-hidden="true"><i class="fas ' + icon + '"></i></span>' +
            '<div class="rim-tile__body"><p class="rim-tile__title">' + esc(t(titleKey)) + "</p>" +
            '<p class="rim-tile__desc">' + esc(disabledReason || t(descKey)) + "</p></div>" +
            '<div class="rim-tile__action">' + (button || "") + "</div></div>"
        );
    }

    function actButton(action, tone, labelKey) {
        return '<button type="button" class="rim-btn rim-btn--' + tone + ' rim-btn--sm" data-rim-act="' + action + '">' +
            esc(t(labelKey)) + "</button>";
    }

    function statusSection(user) {
        var a = user.actions || {};
        var tiles = [];
        if (a.set_password) {
            tiles.push(tile("fa-key", "primary", "set_password", "tile_password_desc", actButton("set_password", "primary", "set_password")));
        }
        if (a.block) {
            tiles.push(tile("fa-ban", "warning", "block", "tile_block_desc", actButton("block", "warning", "block")));
        }
        if (a.unblock) {
            tiles.push(tile("fa-unlock", "primary", "unblock", "tile_unblock_desc", actButton("unblock", "ghost", "unblock")));
        }
        var grad = user.graduation;
        if (grad) {
            tiles.push(tile("fa-graduation-cap", "primary", "graduate", "tile_graduate_desc",
                a.graduate ? '<button type="button" class="rim-btn rim-btn--primary rim-btn--sm" data-rim-graduate-open>' +
                    esc(t("graduate")) + "</button>" : "",
                a.graduate ? "" : grad.disabled_reason));
        }
        var arch = user.staff_archive;
        if (arch && !arch.archived) {
            tiles.push(tile("fa-box-archive", "warning", "archive_staff", "tile_archive_desc",
                a.archive_staff ? actButton("archive_staff", "warning", "archive_staff") : "",
                a.archive_staff ? "" : arch.disabled_reason));
        }
        if (arch && arch.archived) {
            tiles.push(tile("fa-box-open", "primary", "unarchive_staff", "tile_unarchive_desc",
                a.unarchive_staff ? actButton("unarchive_staff", "primary", "unarchive_staff") : "",
                a.unarchive_staff ? "" : arch.disabled_reason));
        }
        if (a.archive_restore && document.querySelector("[data-rim-root] [data-archive-restore]")) {
            var archive = user.archive_restore || {};
            tiles.push(tile("fa-box-open", "primary", "archive_restore", "tile_archive_restore_desc",
                '<button type="button" class="rim-btn rim-btn--primary rim-btn--sm" data-archive-restore-open data-source="rim"' +
                ' data-user-id="' + esc(user.id) + '" data-name="' + esc(user.full_name || "") +
                '" data-username="' + esc(user.username) + '" data-needs-year="' + (archive.needs_admission_year ? "1" : "0") + '">' +
                esc(t("archive_restore")) + "</button>"));
        }
        if (a.soft_delete) {
            tiles.push(tile("fa-user-slash", "danger", "soft_delete", "tile_soft_delete_desc", actButton("soft_delete", "danger", "soft_delete")));
        }
        if (a.restore) {
            tiles.push(tile("fa-rotate-left", "primary", "restore", "tile_restore_desc", actButton("restore", "primary", "restore")));
        }
        var body = tiles.length
            ? '<div class="rim-tiles">' + tiles.join("") + "</div>"
            : '<p class="rim-note">' + esc(t("no_actions")) + "</p>";
        return section("fa-shield-halved", "sec_status", body);
    }

    /* ── Kaskad: fakültə seçimi kafedra variantlarını süzür ──────────────── */

    view.filterUnits = function filterUnits(host) {
        var faculty = host.querySelector("select[data-rim-place-faculty]");
        var unit = host.querySelector("select[data-rim-place-unit]");
        if (!faculty || !unit) {
            return;
        }
        var wanted = faculty.value;
        Array.prototype.forEach.call(unit.options, function (option) {
            if (!option.value) {
                return;
            }
            option.hidden = Boolean(wanted) && option.getAttribute("data-faculty") !== wanted;
        });
        var current = unit.options[unit.selectedIndex];
        if (current && current.hidden) {
            unit.value = "";
        }
        if (window.EMSBootstrapSelect && window.EMSBootstrapSelect.refresh) {
            window.EMSBootstrapSelect.refresh(unit);
        }
    };

    view.render = function render(user) {
        var titleEl = document.querySelector("[data-rim-detail-title]");
        var bodyEl = document.querySelector("[data-rim-detail-body]");
        if (!titleEl || !bodyEl) {
            return;
        }
        titleEl.textContent = user.full_name || user.username;
        bodyEl.innerHTML = summary(user) + basics(user) + positionSection(user) + rolesSection(user) + statusSection(user);
        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.init(bodyEl);
        }
        ns.render.mountPhone(bodyEl, user);
        // «Dəyişiklik varmı» müqayisəsi üçün ilkin dəyər (telefon xanası JS-lə qurulduğuna görə sonradan yazılır).
        Array.prototype.forEach.call(bodyEl.querySelectorAll("[data-rim-edit-field]"), function (input) {
            if (!input.hasAttribute("data-initial")) {
                input.setAttribute("data-initial", input.value || "");
            }
        });
        Array.prototype.forEach.call(bodyEl.querySelectorAll("[data-rim-place]"), view.filterUnits);
    };

    view.OTHER = OTHER;
})(window, document);
