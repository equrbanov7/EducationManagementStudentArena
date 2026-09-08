/* «Müəllimlər» / «Tələbələr» kataloqu — cədvəl, filtrlər, toplu seçim, əməllər.
 *
 * REDİZAYN (sahib, 2026-09-07):
 *   • sətirdə status NİŞANLARI (hesab + akademik), əlaqə linkləri, ikon-əməllər;
 *   • TOPLU SEÇİM: tələbə → «Qrupa köçür», müəllim → «Kafedraya təyin et»,
 *     hər ikisi → «Dayandır»; hədəflər ardıcıl göndərilir, nəticə toast ilə;
 *   • `window.prompt` / `alert` YOXDUR — səbəb dialoqu (ems_ui overlay) + toast;
 *   • tələbəyə «müəllim statusu ver» düyməsi HEÇ YERDƏ render olunmur.
 *
 * Müqavilə DƏYİŞMİR: list/options/action endpoint-ləri, `people:filters` və
 * `people:refresh` hadisələri, `EMSPeopleDetail.open(root, urls, id, {runAction})`
 * və tələbə idarəetmə çekməcəsinin `[data-psm-open]` düyməsi əvvəlki kimidir.
 *
 * AJAX-safe: `EMSReady` + idempotent boot (panel SPA swap-ından sonra təkrar
 * qoşulmur). Şəbəkə `EMSCore.fetchJSON` (CSRF). Inline stil/script yoxdur (CSP).
 */
(function () {
    "use strict";

    var DEBOUNCE_MS = 250;

    /* ---- kiçik köməkçilər ------------------------------------------------ */

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null && text !== "") {
            node.textContent = String(text);
        }
        return node;
    }

    function icon(name) {
        var i = el("i", "fas " + name);
        i.setAttribute("aria-hidden", "true");
        return i;
    }

    function toast(message, level) {
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, level || "success");
        }
    }

    function fmt(template, values) {
        return String(template || "").replace(/%[abcd]/g, function (key) {
            var value = values[key.charAt(1)];
            return value === undefined || value === null ? "" : String(value);
        });
    }

    function messageOf(error, fallback) {
        var payload = error && error.payload;
        return (payload && payload.message) || fallback || "";
    }

    function readDetailI18n(root) {
        var block = document.getElementById("people-detail-i18n-" + (root.dataset.kind || ""));
        if (!block) {
            return {};
        }
        try {
            return JSON.parse(block.textContent || "{}");
        } catch (err) {
            return {};
        }
    }

    function badge(labels, tones, value, fallbackTone) {
        var text = (labels && labels[value]) || value || "—";
        var tone = (tones && tones[value]) || fallbackTone || "neutral";
        return el("span", "ems-badge ems-badge--" + tone, text);
    }

    /* ---- hüceyrələr ----------------------------------------------------- */

    function textCell(row, value, className) {
        var cell = el("td", className);
        cell.textContent = value || "—";
        if (!value) {
            cell.classList.add("is-muted");
        }
        row.appendChild(cell);
        return cell;
    }

    function personCell(row, person, ctx) {
        var cell = el("td", "people__cell-person");

        var avatar = el("span", "people__avatar");
        if (person.avatar_url) {
            var img = document.createElement("img");
            img.src = person.avatar_url;
            img.alt = "";
            img.loading = "lazy";
            avatar.appendChild(img);
        } else {
            // Şəkil FAYLLARI köhnə sistemdən köçmür — baş hərflər fallback-dir.
            avatar.classList.add("people__avatar--initials");
            avatar.textContent = person.initials || "?";
        }

        var name = el("button", "people__name");
        name.type = "button";
        name.dataset.peopleOpen = person.id;
        name.title = ctx.t("openCard");
        name.textContent = [person.full_name, person.patronymic].filter(Boolean).join(" ") || person.username;

        var sub = el("span", "people__username", "@" + person.username);
        var stack = el("span", "people__name-stack");
        stack.appendChild(name);
        stack.appendChild(sub);
        if (person.kind === "student" && person.admission_year) {
            stack.appendChild(el("span", "people__meta", ctx.t("admission") + " " + person.admission_year));
        }

        cell.appendChild(avatar);
        cell.appendChild(stack);
        row.appendChild(cell);
    }

    function contactCell(row, person) {
        var cell = el("td", "people__cell-contact");
        var any = false;
        if (person.email) {
            var mail = el("a", "people__contact", person.email);
            mail.href = "mailto:" + person.email;
            mail.prepend(icon("fa-envelope"));
            cell.appendChild(mail);
            any = true;
        }
        if (person.phone) {
            var tel = el("a", "people__contact", person.phone);
            tel.href = "tel:" + String(person.phone).replace(/\s+/g, "");
            tel.prepend(icon("fa-phone"));
            cell.appendChild(tel);
            any = true;
        }
        if (!any) {
            cell.textContent = "—";
            cell.classList.add("is-muted");
        }
        row.appendChild(cell);
    }

    function statusCell(row, person, ctx) {
        var cell = el("td", "people__cell-status");
        cell.appendChild(badge(ctx.i18n.status, ctx.i18n.status_tone, person.status, "neutral"));
        if (person.kind === "student" && person.academic_status) {
            cell.appendChild(badge(ctx.i18n.academic_status, ctx.i18n.academic_status_tone, person.academic_status, "info"));
        }
        row.appendChild(cell);
    }

    function actionButton(className, iconName, label, attrs, iconOnly) {
        var button = el("button", "people__action " + (className || ""));
        button.type = "button";
        button.appendChild(icon(iconName));
        if (iconOnly) {
            button.classList.add("people__action--icon");
            button.title = label;
            button.setAttribute("aria-label", label);
        } else {
            button.appendChild(el("span", "", label));
        }
        Object.keys(attrs || {}).forEach(function (key) {
            button.dataset[key] = attrs[key];
        });
        return button;
    }

    function actionsCell(row, person, ctx) {
        var cell = el("td", "people__cell-actions");
        var flags = ctx.flags;
        /* «İdarə et» — tələbə idarəetmə çekməcəsini açır (people_academic.js).
         * Burada YALNIZ düymə qoyulur: bu modul çekməcədən xəbərsizdir, o modul
         * isə düyməni sənəd səviyyəsində delegasiya ilə tutur. */
        if (flags.canManageAcademic && person.kind === "student") {
            var manage = actionButton("people__action--manage", "fa-id-card", ctx.t("manage"), { psmOpen: person.id });
            cell.appendChild(manage);
            if (person.record_id) {
                cell.appendChild(
                    actionButton("", "fa-people-arrows", ctx.t("changeGroup"), { peopleAction: "transfer_group", peopleTarget: person.id })
                );
            }
        }
        if (flags.canManageTeacherRole && person.kind === "teacher") {
            cell.appendChild(
                actionButton("", "fa-building-columns", ctx.t("assignUnit"), { peopleAction: "assign_unit", peopleTarget: person.id })
            );
            cell.appendChild(
                actionButton("people__action--danger", "fa-user-minus", ctx.t("revokeTeacher"), { peopleAction: "revoke_teacher", peopleTarget: person.id }, true)
            );
        }
        if (flags.canManageStatus && person.status === "active") {
            cell.appendChild(
                actionButton("people__action--danger", "fa-user-slash", ctx.t("block"), { peopleAction: "block", peopleTarget: person.id }, true)
            );
        }
        if (flags.canManageStatus && person.status === "blocked") {
            cell.appendChild(
                actionButton("people__action--ok", "fa-user-check", ctx.t("unblock"), { peopleAction: "unblock", peopleTarget: person.id }, true)
            );
        }
        row.appendChild(cell);
    }

    /* QA 2026-09-05 (UX-17): "Şəxs"/"Kafedra"/"Qrup" başlıqları `data-people-sort-*`
     * ilə mövcud "Sıralama" select-inin (name="sort") dəyərlərinə bağlanır. */
    function initSortHeaders(root, form) {
        var sortSelect = form && form.querySelector('select[name="sort"]');
        var headers = root.querySelectorAll("[data-people-sort-asc]");
        if (!sortSelect || !headers.length) {
            return;
        }

        function refresh() {
            Array.prototype.forEach.call(headers, function (th) {
                var asc = th.dataset.peopleSortAsc;
                var desc = th.dataset.peopleSortDesc;
                if (sortSelect.value === asc) {
                    th.setAttribute("aria-sort", "ascending");
                } else if (desc && sortSelect.value === desc) {
                    th.setAttribute("aria-sort", "descending");
                } else {
                    th.setAttribute("aria-sort", "none");
                }
            });
        }

        Array.prototype.forEach.call(headers, function (th) {
            var button = th.querySelector(".people__th-sort");
            if (!button) {
                return;
            }
            button.addEventListener("click", function () {
                var asc = th.dataset.peopleSortAsc;
                var desc = th.dataset.peopleSortDesc;
                var next = sortSelect.value === asc && desc ? desc : asc;
                sortSelect.value = next;
                sortSelect.dispatchEvent(new Event("change", { bubbles: true }));
                refresh();
            });
        });

        sortSelect.addEventListener("change", refresh);
        refresh();
    }

    /* ---- boot ----------------------------------------------------------- */

    function boot() {
        var roots = document.querySelectorAll("[data-people-root]");
        Array.prototype.forEach.call(roots, function (root) {
            if (root.dataset.peopleInit === "1") {
                return;
            }
            root.dataset.peopleInit = "1";
            setup(root);
        });
    }

    function setup(root) {
        var kind = root.dataset.kind;
        var urls = {
            list: root.dataset.listUrl,
            options: root.dataset.optionsUrl,
            action: root.dataset.actionUrl,
            detail: root.dataset.detailUrlTemplate,
            groups: root.dataset.groupsUrl || "",
        };
        var flags = {
            canViewContacts: root.dataset.canViewContacts === "1",
            canViewDemographics: root.dataset.canViewDemographics === "1",
            canManageStatus: root.dataset.canManageStatus === "1",
            canManageTeacherRole: root.dataset.canManageTeacherRole === "1",
            canManageAcademic: root.dataset.canManageAcademic === "1",
        };
        var ctx = {
            root: root,
            kind: kind,
            urls: urls,
            flags: flags,
            i18n: readDetailI18n(root),
            minReason: parseInt(root.dataset.minReasonLength || "3", 10),
            t: function (key) {
                return root.dataset["i18n" + key.charAt(0).toUpperCase() + key.slice(1)] || "";
            },
        };
        var form = root.querySelector("[data-people-filters]");
        var tbody = root.querySelector("[data-people-rows]");
        var empty = root.querySelector("[data-people-empty]");
        var totalEl = root.querySelector("[data-people-total]");
        var pageInfo = root.querySelector("[data-people-page-info]");
        var pagerInfo = root.querySelector("[data-people-pager-info]");
        var coverage = root.querySelector("[data-people-coverage]");
        var selectAll = root.querySelector("[data-people-select-all]");
        var moreBadge = root.querySelector("[data-people-filters-badge]");
        var state = { page: 1, total: 0, numPages: 1, rows: {}, selected: {} };
        var timer = null;
        var canSelect = !!selectAll;

        function params() {
            var data = new URLSearchParams();
            if (form) {
                Array.prototype.forEach.call(form.elements, function (field) {
                    if (!field.name) {
                        return;
                    }
                    if (field.type === "checkbox") {
                        if (field.checked) {
                            data.set(field.name, field.value);
                        }
                        return;
                    }
                    if (field.value) {
                        data.set(field.name, field.value);
                    }
                });
            }
            data.set("page", String(state.page));
            return data;
        }

        /* Analitika ilə EYNİ filtr dəsti — `page` XARİC. */
        function publishFilters() {
            var data = params();
            data.delete("page");
            var query = data.toString();
            if (root.dataset.peopleFilterQuery === query) {
                return;
            }
            root.dataset.peopleFilterQuery = query;
            root.dispatchEvent(new CustomEvent("people:filters", { detail: { query: query } }));
        }

        /* «Əlavə filtrlər» bağlı ikən içindəki aktiv filtr sayı görünsün. */
        function syncMoreBadge() {
            if (!moreBadge || !form) {
                return;
            }
            var more = form.querySelector("[data-people-filters-more]");
            var count = 0;
            if (more) {
                Array.prototype.forEach.call(more.querySelectorAll("[name]"), function (field) {
                    if (field.name === "sort") {
                        return;
                    }
                    if (field.type === "checkbox" ? field.checked : field.value) {
                        count += 1;
                    }
                });
            }
            moreBadge.textContent = count ? String(count) : "";
            moreBadge.hidden = !count;
        }

        function fillSelect(select, options) {
            if (!select) {
                return;
            }
            var current = select.value;
            while (select.options.length > 1) {
                select.remove(1);
            }
            (options || []).forEach(function (option) {
                var node = document.createElement("option");
                node.value = option.id;
                node.textContent = option.text;
                select.appendChild(node);
            });
            select.value = current;
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.refresh(select);
            }
        }

        var allOptionsLoaded = false;

        /* Dialoqdakı seçicilər (`data-people-option-all`) filtrdən ASILI OLMAYAN
         * tam siyahını alır — kafedra təyinatı cari fakültə süzgəci ilə daralmasın. */
        function loadAllOptions() {
            var targets = root.querySelectorAll("[data-people-option][data-people-option-all]");
            if (!targets.length || allOptionsLoaded) {
                return;
            }
            allOptionsLoaded = true;
            window.EMSCore.fetchJSON(urls.options)
                .then(function (payload) {
                    if (!payload || !payload.has_access) {
                        return;
                    }
                    Array.prototype.forEach.call(targets, function (select) {
                        fillSelect(select, payload[select.dataset.peopleOption]);
                    });
                })
                .catch(function () {
                    allOptionsLoaded = false;
                });
        }

        function loadOptions() {
            loadAllOptions();
            window.EMSCore.fetchJSON(urls.options + "?" + params().toString())
                .then(function (payload) {
                    if (!payload || !payload.has_access) {
                        return;
                    }
                    Array.prototype.forEach.call(root.querySelectorAll("[data-people-option]:not([data-people-option-all])"), function (select) {
                        fillSelect(select, payload[select.dataset.peopleOption]);
                    });
                    if (coverage && payload.demographics_coverage) {
                        var cov = payload.demographics_coverage;
                        coverage.textContent = cov.total
                            ? fmt(ctx.t("demographics"), { a: cov.gender_known, b: cov.birth_date_known, c: cov.total })
                            : "";
                    }
                })
                .catch(function () {
                    /* açılışlar boş qalır — cədvəl yenə işləyir */
                });
        }

        /* ---- seçim ------------------------------------------------------- */

        function selectedIds() {
            return Object.keys(state.selected);
        }

        function syncBulk() {
            var bar = root.querySelector("[data-people-bulkbar]");
            var ids = selectedIds();
            if (bar) {
                bar.hidden = ids.length === 0;
                var count = bar.querySelector("[data-people-bulk-count]");
                if (count) {
                    count.textContent = fmt(ctx.t("selected"), { d: ids.length }).replace("%d", String(ids.length));
                }
            }
            if (selectAll) {
                var boxes = tbody.querySelectorAll("[data-people-check]");
                var checked = tbody.querySelectorAll("[data-people-check]:checked").length;
                selectAll.checked = boxes.length > 0 && checked === boxes.length;
                selectAll.indeterminate = checked > 0 && checked < boxes.length;
            }
            Array.prototype.forEach.call(tbody.querySelectorAll("tr[data-people-row]"), function (tr) {
                tr.classList.toggle("is-selected", !!state.selected[tr.dataset.peopleRow]);
            });
        }

        function clearSelection() {
            state.selected = {};
            Array.prototype.forEach.call(tbody.querySelectorAll("[data-people-check]"), function (box) {
                box.checked = false;
            });
            syncBulk();
        }

        /* ---- render ------------------------------------------------------- */

        function render(payload) {
            tbody.textContent = "";
            state.rows = {};
            (payload.results || []).forEach(function (person) {
                state.rows[String(person.id)] = person;
                var row = el("tr");
                row.dataset.peopleRow = person.id;
                if (canSelect) {
                    var checkCell = el("td", "people__cell-check");
                    var box = document.createElement("input");
                    box.type = "checkbox";
                    box.dataset.peopleCheck = person.id;
                    box.checked = !!state.selected[String(person.id)];
                    box.setAttribute("aria-label", ctx.t("selectRow"));
                    checkCell.appendChild(box);
                    row.appendChild(checkCell);
                }
                personCell(row, person, ctx);
                if (kind === "teachers") {
                    textCell(row, person.title || person.role_label);
                    textCell(row, person.kafedra_name || person.unit_name);
                } else {
                    var groupCell = textCell(row, person.group_name, "people__cell-group");
                    if (!person.group_name) {
                        groupCell.textContent = "";
                        groupCell.appendChild(el("span", "ems-badge ems-badge--warning", ctx.t("noGroup")));
                    }
                    textCell(row, person.program_label || person.program_name);
                }
                textCell(row, person.faculty_name);
                if (flags.canViewContacts) {
                    contactCell(row, person);
                }
                if (flags.canViewDemographics) {
                    var demo = [];
                    if (person.gender && person.gender !== "unspecified") {
                        demo.push(person.gender === "male" ? ctx.t("male") : ctx.t("female"));
                    }
                    if (person.age !== null && person.age !== undefined) {
                        demo.push(person.age + " " + ctx.t("age"));
                    }
                    textCell(row, demo.join(", "));
                }
                statusCell(row, person, ctx);
                if (flags.canManageStatus || flags.canManageTeacherRole || flags.canManageAcademic) {
                    actionsCell(row, person, ctx);
                }
                tbody.appendChild(row);
            });
            state.total = payload.total || 0;
            state.numPages = payload.num_pages || 1;
            state.page = payload.page || 1;
            if (empty) {
                empty.hidden = state.total > 0;
            }
            if (totalEl) {
                totalEl.textContent = fmt(ctx.t("total"), { d: state.total }).replace("%d", String(state.total));
            }
            var pageText = fmt(ctx.t("page"), { a: state.page, b: state.numPages });
            if (pageInfo) {
                pageInfo.textContent = state.total ? pageText : "";
            }
            if (pagerInfo) {
                pagerInfo.textContent = pageText;
            }
            var prev = root.querySelector("[data-people-prev]");
            var next = root.querySelector("[data-people-next]");
            if (prev) {
                prev.disabled = state.page <= 1;
            }
            if (next) {
                next.disabled = state.page >= state.numPages;
            }
            var pager = root.querySelector("[data-people-pager]");
            if (pager) {
                pager.hidden = state.numPages <= 1;
            }
            syncBulk();
        }

        // Yüklənərkən cədvəl `aria-busy` olur və skelet sətirlər yerini tutur.
        function setBusy(busy) {
            var table = tbody.closest("table") || tbody.parentElement;
            if (table) {
                table.setAttribute("aria-busy", busy ? "true" : "false");
            }
            if (!busy) {
                return;
            }
            if (empty) {
                empty.hidden = true;
            }
            var columns = (table && table.querySelectorAll("thead th").length) || 1;
            var html = "";
            for (var r = 0; r < 6; r += 1) {
                html += '<tr class="people__row--skeleton" aria-hidden="true">';
                for (var c = 0; c < columns; c += 1) {
                    html += '<td><span class="skeleton skeleton-line skeleton-line--sm"></span></td>';
                }
                html += "</tr>";
            }
            tbody.innerHTML = html;
        }

        function load() {
            publishFilters();
            syncMoreBadge();
            setBusy(true);
            window.EMSCore.fetchJSON(urls.list + "?" + params().toString())
                .then(function (payload) {
                    setBusy(false);
                    if (!payload || !payload.has_access) {
                        tbody.textContent = "";
                        if (empty) {
                            empty.hidden = false;
                        }
                        return;
                    }
                    render(payload);
                })
                .catch(function () {
                    setBusy(false);
                    tbody.textContent = "";
                });
        }

        function reload(resetPage) {
            if (resetPage) {
                state.page = 1;
            }
            window.clearTimeout(timer);
            timer = window.setTimeout(load, DEBOUNCE_MS);
        }

        if (form) {
            form.addEventListener("input", function () {
                reload(true);
            });
            form.addEventListener("change", function (event) {
                if (event.target && event.target.name === "faculty") {
                    loadOptions();
                }
                reload(true);
            });
            form.addEventListener("submit", function (event) {
                event.preventDefault();
                reload(true);
            });
            form.addEventListener("reset", function () {
                window.setTimeout(function () {
                    Array.prototype.forEach.call(form.querySelectorAll("select"), function (select) {
                        if (window.EMSBootstrapSelect) {
                            window.EMSBootstrapSelect.sync(select);
                        }
                    });
                    reload(true);
                }, 0);
            });
        }

        var prevBtn = root.querySelector("[data-people-prev]");
        var nextBtn = root.querySelector("[data-people-next]");
        if (prevBtn) {
            prevBtn.addEventListener("click", function () {
                if (state.page > 1) {
                    state.page -= 1;
                    load();
                }
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener("click", function () {
                if (state.page < state.numPages) {
                    state.page += 1;
                    load();
                }
            });
        }
        if (selectAll) {
            selectAll.addEventListener("change", function () {
                Array.prototype.forEach.call(tbody.querySelectorAll("[data-people-check]"), function (box) {
                    box.checked = selectAll.checked;
                    if (selectAll.checked) {
                        state.selected[box.dataset.peopleCheck] = true;
                    } else {
                        delete state.selected[box.dataset.peopleCheck];
                    }
                });
                syncBulk();
            });
        }

        root.addEventListener("change", function (event) {
            var box = event.target.closest ? event.target.closest("[data-people-check]") : null;
            if (!box) {
                return;
            }
            if (box.checked) {
                state.selected[box.dataset.peopleCheck] = true;
            } else {
                delete state.selected[box.dataset.peopleCheck];
            }
            syncBulk();
        });

        root.addEventListener("click", function (event) {
            var opener = event.target.closest("[data-people-open]");
            if (opener) {
                openDetail(ctx, opener.dataset.peopleOpen, load);
                return;
            }
            var action = event.target.closest("[data-people-action]");
            if (action) {
                runAction(ctx, action.dataset.peopleAction, [action.dataset.peopleTarget], load);
                return;
            }
            var bulk = event.target.closest("[data-people-bulk]");
            if (bulk) {
                var ids = selectedIds();
                if (ids.length) {
                    runAction(ctx, bulk.dataset.peopleBulk, ids, function () {
                        clearSelection();
                        load();
                    });
                }
                return;
            }
            if (event.target.closest("[data-people-bulk-clear]")) {
                clearSelection();
                return;
            }
            if (event.target.closest("[data-people-empty-reset]") && form) {
                form.reset();
            }
        });

        /* Xarici modul (tələbə idarəetməsi) əməli tamamlayanda cədvəl yerində yenilənsin. */
        root.addEventListener("people:refresh", function () {
            load();
        });

        ctx.state = state;
        initSortHeaders(root, form);
        loadOptions();
        load();
    }

    /* ---- şəxs kartı --------------------------------------------------------- */

    function openDetail(ctx, userId, reloadList) {
        if (window.EMSPeopleDetail && typeof window.EMSPeopleDetail.open === "function") {
            window.EMSPeopleDetail.open(ctx.root, ctx.urls, userId, {
                runAction: function (action, id, onDone) {
                    runAction(ctx, action, [id], function () {
                        ctx.root.dispatchEvent(new CustomEvent("people:refresh"));
                        onDone();
                    });
                },
            });
            return;
        }
        reloadList();
    }

    /* ---- əməllər (dialoq + ardıcıl POST) ------------------------------------ */

    function dialogOf(ctx, kind) {
        return ctx.root.querySelector('[data-people-dialog="' + kind + '"]');
    }

    function renderTargets(dialog, ctx, ids) {
        var box = dialog.querySelector("[data-people-dialog-targets]");
        if (!box) {
            return;
        }
        box.textContent = "";
        var list = el("ul", "people-dialog__list");
        ids.slice(0, 8).forEach(function (id) {
            var person = ctx.state.rows[String(id)] || {};
            var item = el("li", "people-dialog__item");
            item.appendChild(el("span", "people-dialog__avatar", person.initials || "?"));
            var name = el("span", "people-dialog__name", [person.full_name, person.patronymic].filter(Boolean).join(" ") || person.username || id);
            item.appendChild(name);
            var meta = person.kind === "student" ? person.group_name || ctx.t("noGroup") : person.kafedra_name || person.unit_name || "";
            if (meta) {
                item.appendChild(el("span", "people-dialog__meta", meta));
            }
            list.appendChild(item);
        });
        if (ids.length > 8) {
            list.appendChild(el("li", "people-dialog__item people-dialog__item--more", "+" + (ids.length - 8)));
        }
        box.appendChild(list);
    }

    function showDialogError(dialog, message) {
        var box = dialog.querySelector("[data-people-dialog-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
    }

    function openOverlay(dialog) {
        if (window.EMSOverlay && typeof window.EMSOverlay.open === "function") {
            window.EMSOverlay.open(dialog);
        } else {
            dialog.hidden = false;
        }
    }

    function closeOverlay(dialog) {
        if (window.EMSOverlay && typeof window.EMSOverlay.close === "function") {
            window.EMSOverlay.close(dialog);
        } else {
            dialog.hidden = true;
        }
    }

    /** Hədəfləri ARDICIL göndərir; nəticə toast ilə, ilk xəta dialoqda qalır. */
    function runSequential(ctx, dialog, ids, buildPayload, onDone) {
        var submit = dialog.querySelector("[data-people-dialog-submit]");
        if (submit) {
            submit.disabled = true;
        }
        var ok = 0;
        var firstError = "";
        var chain = Promise.resolve();
        ids.forEach(function (id) {
            chain = chain.then(function () {
                var payload = buildPayload(id);
                if (!payload) {
                    return null;
                }
                return window.EMSCore.fetchJSON(ctx.urls.action, { method: "POST", data: payload })
                    .then(function () {
                        ok += 1;
                    })
                    .catch(function (error) {
                        if (!firstError) {
                            firstError = messageOf(error, ctx.t("failed"));
                        }
                    });
            });
        });
        chain.then(function () {
            if (submit) {
                submit.disabled = false;
            }
            if (ok > 0) {
                toast(fmt(ctx.t("done"), { a: ok, b: ids.length }), firstError ? "warning" : "success");
            }
            if (firstError && ok === 0) {
                showDialogError(dialog, firstError);
                return;
            }
            if (firstError) {
                toast(firstError, "error");
            }
            closeOverlay(dialog);
            onDone();
        });
    }

    function bindDialogSubmit(dialog, handler) {
        var form = dialog.querySelector("[data-people-dialog-form]");
        if (!form) {
            return;
        }
        form.onsubmit = function (event) {
            event.preventDefault();
            handler(form);
        };
    }

    function reasonFrom(form, ctx, required) {
        var field = form.querySelector('[name="reason"]');
        var reason = field ? String(field.value || "").trim() : "";
        if (required && reason.length < ctx.minReason) {
            return null;
        }
        return reason;
    }

    /* Səbəb / təsdiq dialoqu — block, unblock, revoke_teacher (tək və toplu). */
    function openReasonDialog(ctx, action, ids, onDone) {
        var dialog = dialogOf(ctx, "reason");
        if (!dialog) {
            return;
        }
        var meta = {
            block: { title: ctx.t("block"), sub: ctx.t("confirmBlock"), required: true, tone: "ems-btn--danger" },
            unblock: { title: ctx.t("unblock"), sub: ctx.t("confirmUnblock"), required: false, tone: "ems-btn--primary" },
            revoke_teacher: { title: ctx.t("revokeTeacher"), sub: ctx.t("confirmRevoke"), required: true, tone: "ems-btn--danger" },
        }[action];
        if (!meta) {
            return;
        }
        var title = dialog.querySelector("[data-people-dialog-title]");
        var sub = dialog.querySelector("[data-people-dialog-sub]");
        var submit = dialog.querySelector("[data-people-dialog-submit]");
        var req = dialog.querySelector("[data-people-dialog-req]");
        var hint = dialog.querySelector("[data-people-dialog-hint]");
        var form = dialog.querySelector("[data-people-dialog-form]");
        if (title) {
            title.textContent = meta.title;
        }
        if (sub) {
            sub.textContent = meta.sub;
        }
        if (submit) {
            submit.textContent = meta.title;
            submit.className = "ems-btn " + meta.tone;
        }
        if (req) {
            req.hidden = !meta.required;
        }
        if (hint) {
            hint.textContent = meta.required ? fmt(ctx.t("reasonRequired"), { d: ctx.minReason }).replace("%d", String(ctx.minReason)) : "";
        }
        if (form) {
            form.reset();
        }
        showDialogError(dialog, "");
        renderTargets(dialog, ctx, ids);
        bindDialogSubmit(dialog, function (frm) {
            var reason = reasonFrom(frm, ctx, meta.required);
            if (reason === null) {
                showDialogError(dialog, fmt(ctx.t("reasonRequired"), { d: ctx.minReason }).replace("%d", String(ctx.minReason)));
                return;
            }
            runSequential(ctx, dialog, ids, function (id) {
                return { action: action, user_id: id, reason: reason };
            }, onDone);
        });
        openOverlay(dialog);
    }

    /* Kafedraya təyin et — müəllimlər (tək və toplu). */
    function openUnitDialog(ctx, ids, onDone) {
        var dialog = dialogOf(ctx, "unit");
        if (!dialog) {
            return;
        }
        var form = dialog.querySelector("[data-people-dialog-form]");
        if (form) {
            form.reset();
            var select = form.querySelector('[name="unit_id"]');
            if (select && ids.length === 1) {
                var person = ctx.state.rows[String(ids[0])] || {};
                select.value = person.unit_id || "";
            }
            if (select && window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(select);
            }
        }
        showDialogError(dialog, "");
        renderTargets(dialog, ctx, ids);
        bindDialogSubmit(dialog, function (frm) {
            var unitField = frm.querySelector('[name="unit_id"]');
            var unitId = unitField ? unitField.value : "";
            if (!unitId) {
                showDialogError(dialog, ctx.t("pickUnit"));
                return;
            }
            var reason = reasonFrom(frm, ctx, false) || "";
            runSequential(ctx, dialog, ids, function (id) {
                return { action: "assign_unit", user_id: id, unit_id: unitId, reason: reason };
            }, onDone);
        });
        openOverlay(dialog);
    }

    /* Qrupa köçür — tələbələr (tək və toplu); hədəf QEYD id-si sətirdən gəlir. */
    function openGroupDialog(ctx, ids, onDone) {
        var dialog = dialogOf(ctx, "group");
        if (!dialog) {
            return;
        }
        var recordIds = ids
            .map(function (id) {
                var person = ctx.state.rows[String(id)] || {};
                return person.record_id || "";
            })
            .filter(Boolean);
        if (!recordIds.length) {
            toast(ctx.t("noRecord"), "error");
            return;
        }
        var form = dialog.querySelector("[data-people-dialog-form]");
        var hidden = form ? form.querySelector('[name="group_id"]') : null;
        if (form) {
            form.reset();
        }
        if (hidden) {
            hidden.value = "";
        }
        var hint = dialog.querySelector("[data-people-dialog-hint]");
        if (hint) {
            hint.textContent = fmt(ctx.t("reasonRequired"), { d: ctx.minReason }).replace("%d", String(ctx.minReason));
        }
        var host = dialog.querySelector("[data-people-group-picker]");
        var pickerRoot = host ? host.querySelector(".js-people-group-picker") : null;
        if (pickerRoot && window.EMSSearchableSelect && ctx.urls.groups) {
            var picker = window.EMSSearchableSelect.create(pickerRoot, {
                url: ctx.urls.groups,
                multi: false,
                skeleton: true,
                emptyText: host.getAttribute("data-empty") || "",
                onChange: function () {
                    if (hidden) {
                        hidden.value = picker ? picker.value() : "";
                    }
                },
            });
            if (picker) {
                picker.reset();
            }
        }
        showDialogError(dialog, "");
        renderTargets(dialog, ctx, ids);
        bindDialogSubmit(dialog, function (frm) {
            var groupId = hidden ? hidden.value : "";
            if (!groupId) {
                showDialogError(dialog, ctx.t("pickGroup"));
                return;
            }
            var reason = reasonFrom(frm, ctx, true);
            if (reason === null) {
                showDialogError(dialog, fmt(ctx.t("reasonRequired"), { d: ctx.minReason }).replace("%d", String(ctx.minReason)));
                return;
            }
            runSequential(ctx, dialog, recordIds, function (recordId) {
                return { action: "transfer_group", record_id: recordId, group_id: groupId, reason: reason };
            }, onDone);
        });
        openOverlay(dialog);
        window.setTimeout(function () {
            var input = pickerRoot ? pickerRoot.querySelector("input") : null;
            if (input) {
                input.focus();
            }
        }, 30);
    }

    function runAction(ctx, action, ids, onDone) {
        ids = (ids || []).map(String).filter(Boolean);
        if (!ids.length) {
            return;
        }
        if (action === "assign_unit") {
            openUnitDialog(ctx, ids, onDone);
            return;
        }
        if (action === "transfer_group") {
            openGroupDialog(ctx, ids, onDone);
            return;
        }
        if (action === "grant_teacher") {
            // Sahib (2026-09-07): tələbəyə müəllim statusu verilmir — bu səthdə düymə yoxdur.
            return;
        }
        openReasonDialog(ctx, action, ids, onDone);
    }

    if (window.EMSReady) {
        window.EMSReady(boot);
    } else {
        document.addEventListener("DOMContentLoaded", boot);
    }
})();
