/* «Müəllimlər» / «Tələbələr» kataloqu — 3/3: `setup(root)` + `boot`.
 * people_directory.js və people_directory_actions.js-dən SONRA yüklənir
 * (köməkçilər və əməllər `window.EMSPeopleDirectory`-dən oxunur; əməllər
 * klik anında həll olunur). AJAX-safe: `EMSReady` + idempotent boot
 * (`data-people-init`). Bölgü: 2026-09-21 (modul ölçü büdcəsi).
 */
(function () {
    "use strict";

    var DEBOUNCE_MS = 250;

    var P = (window.EMSPeopleDirectory = window.EMSPeopleDirectory || {});
    var el = P.el;
    var fmt = P.fmt;
    var readDetailI18n = P.readDetailI18n;
    var textCell = P.textCell;
    var personCell = P.personCell;
    var contactCell = P.contactCell;
    var statusCell = P.statusCell;
    var actionsCell = P.actionsCell;
    var initSortHeaders = P.initSortHeaders;

    function openDetail(ctx, userId, reloadList) {
        return P.openDetail(ctx, userId, reloadList);
    }

    function runAction(ctx, action, ids, onDone) {
        return P.runAction(ctx, action, ids, onDone);
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

    if (window.EMSReady) {
        window.EMSReady(boot);
    } else {
        document.addEventListener("DOMContentLoaded", boot);
    }
})();
