/**
 * «Fənn təhvili» bölməsi — dərs açılışının başqa müəllimə verilməsi.
 *
 * AJAX-safe (docs/frontend/AJAX_SAFE_JS_PATTERN.md): `window.EMSReady` sarğısı,
 * null-safe element axtarışları, idempotent init (kök elementə bayraq qoyulur).
 * Bölmə SPA panelidir — swap-dan sonra init təzə kök üzərində yenidən işə düşür.
 *
 * Server müqaviləsi: `apps/accounts/views/handover/api.py` + `actions.py`.
 * Bütün dinamik dəyərlər `data-*` atributlarından oxunur (CSP: inline JS yoxdur).
 *
 * DİZAYN QƏRARI — sətir-səviyyəli hədəf PAYLAŞILAN modal seçici ilə verilir.
 * 25 sətir × 25 ayrı `EMSSearchableSelect` həm ağır olardı, həm də klaviatura
 * naviqasiyasını dolaşdırardı. Toplu tətbiq («seçilənlərə tətbiq et») eyni
 * məlumat modelini yazır — iki yol bir-birini əvəz edir, ayrılmır.
 *
 * Saf render funksiyaları `teaching_handover_render.js`-dədir.
 */
(function () {
    "use strict";

    function init() {
        var root = document.querySelector("[data-thx-root]");
        var R = window.EMSHandoverRender;
        if (!root || root._thxReady || !R) {
            return;
        }
        root._thxReady = true;

        var i18nNode = root.querySelector("[data-thx-i18n]");
        var D = i18nNode ? i18nNode.dataset : {};
        var labels = {
            students: D.students || "",
            lessons: D.lessons || "",
            marks: D.marks || "",
            noInstructor: D.noInstructor || "—",
            choose: D.choose || "",
            change: D.change || "",
            blocked: D.blocked || "",
            revert: D.revert || "",
            reverted: D.reverted || "",
            revertBlocked: D.revertBlocked || "",
            prev: D.prev || "",
            next: D.next || "",
            page: D.page || ""
        };

        var rowsBody = root.querySelector("[data-thx-rows]");
        var historyBody = root.querySelector("[data-thx-history]");
        var pagerHost = root.querySelector("[data-thx-pager]");
        var historyPagerHost = root.querySelector("[data-thx-history-pager]");
        var bar = root.querySelector("[data-thx-bar]");
        var barText = root.querySelector("[data-thx-bar-text]");
        var submitBtn = root.querySelector("[data-thx-submit]");
        var applyAllBtn = root.querySelector("[data-thx-apply-all]");
        var checkAll = root.querySelector("[data-thx-check-all]");
        var pickerDialog = root.querySelector("[data-thx-picker]");
        var confirmDialog = root.querySelector("[data-thx-dialog]");

        // Seçim və hədəflər SƏHİFƏLƏR ARASI saxlanılır: 2-ci səhifəyə keçib
        // qayıdanda seçimin itməsi toplu təhvildə ən əsəb pozucu haldır.
        var targets = {};
        var selected = {};
        var pageRows = {};
        var state = { page: 1, historyPage: 1, source: "", pickerRow: "", pending: null, lastFocus: null };

        function fetchJSON(url, options) {
            if (window.EMSCore && window.EMSCore.fetchJSON) {
                return window.EMSCore.fetchJSON(url, options);
            }
            return fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } }).then(function (response) {
                return response.json();
            });
        }

        function toast(text) {
            if (window.EMSToast && window.EMSToast.show) {
                window.EMSToast.show(text, "success");
            }
        }

        // ── Süzgəclər ───────────────────────────────────────────────────────
        function filterParams() {
            var form = root.querySelector("[data-thx-filters]");
            var params = new URLSearchParams();
            if (form) {
                var search = form.querySelector('input[name="q"]');
                if (search && search.value.trim()) {
                    params.set("q", search.value.trim());
                }
                ["period", "faculty", "kafedra"].forEach(function (name) {
                    var node = form.querySelector('[name="' + name + '"]');
                    if (node && node.value) {
                        params.set(name, node.value);
                    }
                });
                var onlyOpen = form.querySelector("[data-thx-only-open]");
                if (onlyOpen && onlyOpen.checked) {
                    params.set("scope", "open");
                }
            }
            if (state.source) {
                params.set("teacher", state.source);
            }
            params.set("page", String(state.page));
            params.set("page_size", root.dataset.pageSize || "25");
            return params;
        }

        // ── Cədvəl ──────────────────────────────────────────────────────────
        function loadOfferings() {
            if (!rowsBody) {
                return;
            }
            R.skeleton(rowsBody, 7);
            fetchJSON(root.dataset.offeringsUrl + "?" + filterParams().toString())
                .then(function (data) {
                    if (!data || !data.has_access) {
                        R.message(rowsBody, 7, D.empty);
                        R.pager(pagerHost, null, labels, function () {});
                        return;
                    }
                    renderRows(data.results || []);
                    R.pager(pagerHost, data, labels, function (page) {
                        state.page = page;
                        loadOfferings();
                    });
                })
                .catch(function () {
                    R.message(rowsBody, 7, D.error);
                });
        }

        function renderRows(rows) {
            pageRows = {};
            rowsBody.innerHTML = "";
            if (!rows.length) {
                R.message(rowsBody, 7, D.empty);
                syncBar();
                return;
            }
            rows.forEach(function (row) {
                pageRows[row.id] = row;
                rowsBody.appendChild(
                    R.offeringRow(row, { labels: labels, isSelected: !!selected[row.id], chosen: targets[row.id] })
                );
            });
            syncCheckAll();
            syncBar();
        }

        function refreshTargetCell(id) {
            var row = pageRows[id];
            var tr = rowsBody ? rowsBody.querySelector('[data-thx-row="' + id + '"]') : null;
            if (row && tr && tr.lastElementChild) {
                tr.replaceChild(R.targetCell(row, targets[id], labels), tr.lastElementChild);
            }
        }

        // ── Seçim vəziyyəti ─────────────────────────────────────────────────
        function selectedIds() {
            return Object.keys(selected).filter(function (id) {
                return selected[id];
            });
        }

        function setRowSelected(id, on) {
            if (on) {
                selected[id] = true;
            } else {
                delete selected[id];
            }
            var tr = rowsBody ? rowsBody.querySelector('[data-thx-row="' + id + '"]') : null;
            if (tr && !tr.classList.contains("is-blocked")) {
                tr.classList.toggle("is-selected", !!on);
            }
        }

        function syncCheckAll() {
            if (!checkAll || !rowsBody) {
                return;
            }
            var boxes = rowsBody.querySelectorAll("[data-thx-check]:not(:disabled)");
            var checked = rowsBody.querySelectorAll("[data-thx-check]:not(:disabled):checked");
            checkAll.checked = boxes.length > 0 && boxes.length === checked.length;
            checkAll.indeterminate = checked.length > 0 && checked.length < boxes.length;
        }

        function syncBar() {
            var ids = selectedIds();
            var missingTarget = ids.some(function (id) {
                return !targets[id];
            });
            if (bar) {
                bar.hidden = ids.length === 0;
            }
            if (barText) {
                // Xəbərdarlıq MƏTNLƏ verilir — düymənin sönük olması tək izah deyil.
                barText.textContent =
                    ids.length + " " + (D.selectedOne || "") + (missingTarget ? " · " + (D.needsTarget || "") : "");
            }
            if (applyAllBtn) {
                applyAllBtn.disabled = ids.length === 0;
            }
            if (submitBtn) {
                submitBtn.disabled = ids.length === 0 || missingTarget;
            }
        }

        // ── Seçicilər (axtarışlı, debounce-lu, lazy səhifələnən) ────────────
        function makePicker(hook, role, onChange) {
            var host = root.querySelector(".js-" + hook);
            if (!host || !window.EMSSearchableSelect) {
                return null;
            }
            return window.EMSSearchableSelect.create(host, {
                url: root.dataset.teachersUrl + "?role=" + role,
                multi: false,
                skeleton: true,
                emptyText: D.pickerEmpty || "",
                onChange: onChange || function () {}
            });
        }

        var sourcePicker = makePicker("thx-source", "source", function () {
            state.source = sourcePicker ? sourcePicker.value() : "";
            state.page = 1;
            loadOfferings();
        });
        var bulkPicker = makePicker("thx-bulk", "target");
        var rowPicker = makePicker("thx-row", "target");

        // ── Modal idarəsi ───────────────────────────────────────────────────
        function openDialog(node) {
            if (!node) {
                return;
            }
            state.lastFocus = document.activeElement;
            node.hidden = false;
            var focusable = node.querySelector("button, textarea, input");
            if (focusable) {
                focusable.focus();
            }
        }

        function closeDialog(node) {
            if (!node) {
                return;
            }
            node.hidden = true;
            if (state.lastFocus && typeof state.lastFocus.focus === "function") {
                state.lastFocus.focus();
            }
        }

        function openRowPicker(id) {
            var row = pageRows[id];
            if (!row) {
                return;
            }
            state.pickerRow = id;
            var subject = root.querySelector("[data-thx-picker-subject]");
            if (subject) {
                subject.textContent = (row.subject_name || row.subject_code || "") + " · " + (row.group || "");
            }
            if (rowPicker) {
                rowPicker.reset();
            }
            openDialog(pickerDialog);
        }

        function confirmRowPicker() {
            if (!rowPicker || !state.pickerRow) {
                return;
            }
            var id = rowPicker.value();
            if (!id) {
                return;
            }
            targets[state.pickerRow] = { id: id, name: rowPicker.text() };
            setRowSelected(state.pickerRow, true);
            var box = rowsBody.querySelector('[data-thx-check="' + state.pickerRow + '"]');
            if (box) {
                box.checked = true;
            }
            refreshTargetCell(state.pickerRow);
            syncCheckAll();
            syncBar();
            closeDialog(pickerDialog);
        }

        function applyBulkTarget() {
            if (!bulkPicker) {
                return;
            }
            var id = bulkPicker.value();
            if (!id) {
                return;
            }
            selectedIds().forEach(function (offeringId) {
                targets[offeringId] = { id: id, name: bulkPicker.text() };
                refreshTargetCell(offeringId);
            });
            syncBar();
        }

        // ── Təsdiq + göndərmə ───────────────────────────────────────────────
        function openConfirm(intent) {
            if (!intent || !intent.summary.length) {
                return;
            }
            state.pending = intent;
            var title = root.querySelector("[data-thx-dialog-title]");
            var reason = root.querySelector("[data-thx-reason]");
            var error = root.querySelector("[data-thx-dialog-error]");
            if (title) {
                title.textContent = intent.title;
            }
            R.summaryCards(root.querySelector("[data-thx-dialog-body]"), intent.summary);
            if (reason) {
                reason.value = "";
            }
            if (error) {
                error.hidden = true;
            }
            openDialog(confirmDialog);
        }

        function transferIntent() {
            var ids = selectedIds().filter(function (id) {
                return targets[id];
            });
            return {
                title: D.confirmTitle || "",
                summary: ids.map(function (id) {
                    var row = pageRows[id] || {};
                    var from = (row.instructor && row.instructor.name) || labels.noInstructor;
                    return {
                        head: (row.subject_name || row.subject_code || "") + " · " + (row.group || ""),
                        meta:
                            (row.period || "") +
                            " · " +
                            (row.students || 0) +
                            " " +
                            labels.students +
                            " · " +
                            (row.marks || 0) +
                            " " +
                            labels.marks,
                        move: from + "  →  " + targets[id].name
                    };
                }),
                payload: {
                    action: "reassign",
                    items: ids.map(function (id) {
                        return { offering_id: id, new_instructor_id: targets[id].id };
                    })
                },
                done: D.done || ""
            };
        }

        function submitPending() {
            if (!state.pending) {
                return;
            }
            var reason = root.querySelector("[data-thx-reason]");
            var error = root.querySelector("[data-thx-dialog-error]");
            var confirmBtn = root.querySelector("[data-thx-dialog-confirm]");
            var text = reason ? reason.value.trim() : "";
            if (text.length < Number(root.dataset.minReason || 3)) {
                showDialogError(error, D.reasonShort);
                if (reason) {
                    reason.focus();
                }
                return;
            }
            if (confirmBtn) {
                confirmBtn.disabled = true;
            }
            var done = state.pending.done;
            var payload = Object.assign({}, state.pending.payload, { reason: text });
            fetchJSON(root.dataset.actionUrl, { method: "POST", data: payload })
                .then(function () {
                    closeDialog(confirmDialog);
                    toast(done);
                    targets = {};
                    selected = {};
                    state.pending = null;
                    loadOfferings();
                    loadHistory();
                })
                .catch(function (err) {
                    var body = err && err.payload;
                    showDialogError(error, (body && body.message) || D.error);
                })
                .finally(function () {
                    if (confirmBtn) {
                        confirmBtn.disabled = false;
                    }
                });
        }

        function showDialogError(node, text) {
            if (node) {
                node.textContent = text || "";
                node.hidden = false;
            }
        }

        // ── Tarixçə ─────────────────────────────────────────────────────────
        function loadHistory() {
            if (!historyBody) {
                return;
            }
            R.skeleton(historyBody, 5, 3);
            fetchJSON(root.dataset.historyUrl + "?page=" + state.historyPage)
                .then(function (data) {
                    if (!data || !data.has_access || !(data.results || []).length) {
                        R.message(historyBody, 5, D.emptyHistory);
                        R.pager(historyPagerHost, null, labels, function () {});
                        return;
                    }
                    historyBody.innerHTML = "";
                    data.results.forEach(function (row) {
                        historyBody.appendChild(R.historyRow(row, labels));
                    });
                    R.pager(historyPagerHost, data, labels, function (page) {
                        state.historyPage = page;
                        loadHistory();
                    });
                })
                .catch(function () {
                    R.message(historyBody, 5, D.error);
                });
        }

        // ── Tablar ──────────────────────────────────────────────────────────
        function switchTab(name, focus) {
            Array.prototype.forEach.call(root.querySelectorAll("[data-thx-tab]"), function (button) {
                var on = button.dataset.thxTab === name;
                button.classList.toggle("is-active", on);
                button.setAttribute("aria-selected", on ? "true" : "false");
                button.tabIndex = on ? 0 : -1;
                if (on && focus) {
                    button.focus();
                }
            });
            Array.prototype.forEach.call(root.querySelectorAll("[data-thx-panel]"), function (panel) {
                panel.hidden = panel.dataset.thxPanel !== name;
            });
            if (name === "history") {
                loadHistory();
            }
        }

        // ── Hadisələr ───────────────────────────────────────────────────────
        root.addEventListener("click", function (event) {
            var target = event.target;
            var tab = target.closest("[data-thx-tab]");
            if (tab) {
                switchTab(tab.dataset.thxTab);
                return;
            }
            if (target.closest("[data-thx-clear-source]")) {
                if (sourcePicker) {
                    sourcePicker.reset();
                }
                state.source = "";
                state.page = 1;
                loadOfferings();
                return;
            }
            if (target.closest("[data-thx-apply-all]")) {
                applyBulkTarget();
                return;
            }
            var pick = target.closest("[data-thx-pick]");
            if (pick) {
                openRowPicker(pick.dataset.thxPick);
                return;
            }
            if (target.closest("[data-thx-picker-confirm]")) {
                confirmRowPicker();
                return;
            }
            if (target.closest("[data-thx-picker-close]")) {
                closeDialog(pickerDialog);
                return;
            }
            if (target.closest("[data-thx-dialog-close]")) {
                state.pending = null;
                closeDialog(confirmDialog);
                return;
            }
            if (target.closest("[data-thx-dialog-confirm]")) {
                submitPending();
                return;
            }
            if (target.closest("[data-thx-submit]")) {
                openConfirm(transferIntent());
                return;
            }
            var revert = target.closest("[data-thx-revert]");
            if (revert) {
                openConfirm({
                    title: D.revertTitle || "",
                    summary: [
                        { head: revert.dataset.thxRevertLabel || "", meta: "", move: revert.dataset.thxRevertMove || "" }
                    ],
                    payload: { action: "revert", handover_id: revert.dataset.thxRevert },
                    done: D.revertDone || ""
                });
            }
        });

        root.addEventListener("change", function (event) {
            var box = event.target.closest("[data-thx-check]");
            if (box) {
                setRowSelected(box.dataset.thxCheck, box.checked);
                syncCheckAll();
                syncBar();
                return;
            }
            if (event.target === checkAll && rowsBody) {
                Array.prototype.forEach.call(
                    rowsBody.querySelectorAll("[data-thx-check]:not(:disabled)"),
                    function (node) {
                        node.checked = checkAll.checked;
                        setRowSelected(node.dataset.thxCheck, checkAll.checked);
                    }
                );
                syncBar();
                return;
            }
            if (event.target.closest("[data-thx-filters]")) {
                state.page = 1;
                loadOfferings();
            }
        });

        var searchTimer = null;
        root.addEventListener("input", function (event) {
            if (!event.target.matches('[data-thx-filters] input[name="q"]')) {
                return;
            }
            window.clearTimeout(searchTimer);
            searchTimer = window.setTimeout(function () {
                state.page = 1;
                loadOfferings();
            }, 300);
        });

        root.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                if (pickerDialog && !pickerDialog.hidden) {
                    closeDialog(pickerDialog);
                } else if (confirmDialog && !confirmDialog.hidden) {
                    state.pending = null;
                    closeDialog(confirmDialog);
                }
                return;
            }
            var tab = event.target.closest("[data-thx-tab]");
            if (tab && (event.key === "ArrowRight" || event.key === "ArrowLeft")) {
                event.preventDefault();
                switchTab(tab.dataset.thxTab === "transfer" ? "history" : "transfer", true);
            }
        });

        // ── Süzgəc açılışları + ilk yükləmə ─────────────────────────────────
        fetchJSON(root.dataset.optionsUrl)
            .then(function (data) {
                if (!data || !data.has_access) {
                    return;
                }
                [
                    ["periods", data.periods],
                    ["faculties", data.faculties],
                    ["kafedras", data.kafedras]
                ].forEach(function (pair) {
                    var select = root.querySelector('[data-thx-option="' + pair[0] + '"]');
                    if (!select) {
                        return;
                    }
                    (pair[1] || []).forEach(function (option) {
                        var node = document.createElement("option");
                        node.value = option.id;
                        node.textContent = option.label;
                        select.appendChild(node);
                    });
                });
            })
            .catch(function () {});

        loadOfferings();
    }

    window.EMSReady(init);
})();
