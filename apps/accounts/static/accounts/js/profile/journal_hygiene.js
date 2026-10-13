/* «Jurnal təmizliyi» (sahib 2026-10-10) — KONTROLLER. Şablon: sections/journal_hygiene/_content.html.
 *
 * AJAX-safe: hadisələr sənəd səviyyəsində BİR DƏFƏ (EMSDelegate / EMSReady.once) qeyd olunur; panel hər
 * swap-dan sonra EMSReady ilə yenidən qurulur (vəziyyət kök elementin özündə saxlanılır).
 * Axın: sətir seç → «önizləmə» (POST action=preview, heç nə yazmır) → səbəb (≥20) → «Təsdiqlə»
 * (action=apply, önizləmə izi ilə) → siyahı + xülasə yenilənir. Tarixçədə «Bərpa et» (action=revert).
 * Şəbəkə: EMSCore.fetchJSON (CSRF avtomatik). DOM render: journal_hygiene_render.js.
 */
(function (window, document) {
    "use strict";

    if (window.EMSJournalHygiene) {
        return;
    }
    window.EMSJournalHygiene = true;

    var STATE = "__emsJournalHygiene";
    var DIALOG_ID = "jh-dialog";
    /* «not_held» — keçirilməyən fənlər (sahib 2026-10-11). */
    var TABS = ["left", "empty", "not_held", "history"];

    function R() {
        return window.EMSJournalHygieneRender;
    }

    function rootOf(node) {
        return node && node.closest ? node.closest("[data-jh-root]") : null;
    }

    function strings(root) {
        var st = state(root);
        if (!st.i18n) {
            var node = root.querySelector("#jh-i18n");
            try {
                st.i18n = node ? JSON.parse(node.textContent || "{}") : {};
            } catch (err) {
                st.i18n = {};
            }
        }
        return st.i18n;
    }

    function state(root) {
        if (!root[STATE]) {
            root[STATE] = { tab: "left", page: 1, selection: new Set(), rows: {}, request: 0, pending: null, timer: 0 };
        }
        return root[STATE];
    }

    /* Aktiv tabın cədvəl gövdəsi — gizli tabın köhnə sətirləri seçimə qarışmasın. */
    function currentBody(root) {
        return root.querySelector('[data-jh-body="' + (state(root).tab === "history" ? "history" : "rows") + '"]');
    }

    function currentBoxes(root) {
        var body = currentBody(root);
        return body ? Array.prototype.slice.call(body.querySelectorAll("[data-jh-check]:not(:disabled)")) : [];
    }

    function canApply(root) {
        return root.getAttribute("data-can-apply") === "1";
    }

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function fieldValue(root, selector) {
        var field = root.querySelector(selector);
        return field ? String(field.value || "").trim() : "";
    }

    function filters(root) {
        var tab = state(root).tab;
        var values = {
            q: fieldValue(root, "#jh-q"),
            period: fieldValue(root, "#jh-period"),
            faculty: fieldValue(root, "#jh-faculty"),
            group: fieldValue(root, "#jh-group"),
            category: fieldValue(root, '[data-jh-category="' + tab + '"]'),
        };
        if (tab === "history") {
            values.state = fieldValue(root, "#jh-state");
        }
        return values;
    }

    function applyVisibility(root) {
        var tab = state(root).tab;
        root.querySelectorAll("[data-jh-only]").forEach(function (node) {
            node.hidden = node.getAttribute("data-jh-only") !== tab;
        });
        root.querySelectorAll("[data-jh-only-rows]").forEach(function (node) {
            node.hidden = tab === "history";
        });
    }

    function syncToolbar(root) {
        var st = state(root);
        var i18n = strings(root);
        var count = st.selection.size;
        var label = root.querySelector("[data-jh-selection]");
        if (label) {
            label.textContent = count ? R().fill(i18n.selected, { n: count }) : i18n.nothing_selected;
        }
        root.querySelectorAll("[data-jh-act]").forEach(function (button) {
            button.disabled = !count || !canApply(root);
        });
        var pageBox = root.querySelector('[data-jh-table="' + (st.tab === "history" ? "history" : "rows") + '"] [data-jh-check-page]');
        if (pageBox) {
            var boxes = currentBoxes(root);
            pageBox.checked = boxes.length > 0 && boxes.every(function (box) {
                return box.checked;
            });
        }
    }

    function query(root, params) {
        var search = new URLSearchParams();
        Object.keys(params).forEach(function (key) {
            if (params[key] !== "" && params[key] !== undefined && params[key] !== null) {
                search.set(key, params[key]);
            }
        });
        return root.getAttribute("data-rows-url") + "?" + search.toString();
    }

    function render(root, data) {
        var st = state(root);
        var i18n = strings(root);
        var history = st.tab === "history";
        var tbody = currentBody(root);
        st.rows = {};
        (data.results || []).forEach(function (row) {
            st.rows[row.id] = row;
        });
        if (!tbody) {
            return;
        }
        if (!(data.results || []).length) {
            R().stateRow(tbody, i18n["empty_" + st.tab], "empty");
        } else if (history) {
            R().historyBody(tbody, data.results, { selection: st.selection, canSelect: canApply(root), i18n: i18n });
        } else {
            R().rowsBody(tbody, data.results, { selection: st.selection, canSelect: canApply(root), i18n: i18n });
        }
        var counts = data.counts || {};
        var chipBox = root.querySelector("[data-jh-chips]");
        if (chipBox) {
            chipBox.hidden = history;
            if (!history) {
                var select = root.querySelector('[data-jh-category="' + st.tab + '"]');
                var options = select
                    ? Array.prototype.slice.call(select.options).filter(function (option) {
                          return option.value;
                      }).map(function (option) {
                          return { value: option.value, label: option.textContent };
                      })
                    : [];
                R().chips(chipBox, options, counts, select ? select.value : "", i18n);
            }
        }
        var strong = root.querySelector('[data-jh-kpi="strong"]');
        if (strong && !history) {
            strong.textContent = String(counts.strong || 0);
        }
        var pager = root.querySelector("[data-jh-pager]");
        if (pager) {
            R().pager(pager, data, i18n);
        }
        syncToolbar(root);
    }

    function load(root) {
        var st = state(root);
        var token = ++st.request;
        var table = root.querySelector('[data-jh-table="' + (st.tab === "history" ? "history" : "rows") + '"]');
        if (table) {
            table.setAttribute("aria-busy", "true");
        }
        var params = Object.assign({ tab: st.tab, page: st.page, page_size: root.getAttribute("data-page-size") }, filters(root));
        window.EMSCore.fetchJSON(query(root, params))
            .then(function (data) {
                if (token === st.request) {
                    render(root, data || {});
                }
            })
            .catch(function () {
                var tbody = currentBody(root);
                if (token === st.request && tbody) {
                    R().stateRow(tbody, strings(root).load_error, "error");
                }
            })
            .then(function () {
                if (table && token === st.request) {
                    table.setAttribute("aria-busy", "false");
                }
            });
    }

    /* Üst KPI-lar və tab sayları — süzgəcsiz cəmlər (açılışda və hər yazıdan sonra). */
    function loadSummary(root) {
        TABS.forEach(function (tab) {
            window.EMSCore.fetchJSON(query(root, { tab: tab, page_size: 1 }))
                .then(function (data) {
                    var counts = (data && data.counts) || {};
                    /* Keçirilməyən fənn vahid AÇILIŞDIR — KPI və tab sayı açılışları göstərir. */
                    var total = (tab === "not_held" ? counts.offerings : counts.total) || 0;
                    var kpi = root.querySelector('[data-jh-kpi="' + tab + '"]');
                    if (kpi) {
                        kpi.textContent = String(total);
                    }
                    var badge = root.querySelector('[data-jh-tab-count="' + tab + '"]');
                    if (badge) {
                        badge.textContent = total ? String(total) : "";
                    }
                    var note = root.querySelector('[data-jh-kpi-note="' + tab + '"]');
                    if (note && tab === "history" && data && data.counts) {
                        note.textContent = strings(root).reverted + ": " + (data.counts.reverted || 0);
                    }
                    if (note && tab === "not_held") {
                        note.textContent = R().fill(strings(root).not_held_note, { n: counts.total || 0 });
                    }
                })
                .catch(function () {});
        });
    }

    function reset(root, keepPage) {
        var st = state(root);
        st.selection.clear();
        if (!keepPage) {
            st.page = 1;
        }
        load(root);
    }

    function init(root) {
        if (!root || root.getAttribute("data-jh-ready") === "1" || !R() || !window.EMSCore) {
            return;
        }
        root.setAttribute("data-jh-ready", "1");
        applyVisibility(root);
        syncToolbar(root);
        load(root);
        loadSummary(root);
    }

    window.EMSReady(function () {
        init(document.querySelector("[data-jh-root]"));
    });

    /* ── Tab, süzgəc, çip, səhifə ────────────────────────────────────────── */

    window.EMSReady.once("journal-hygiene-tab", function () {
        document.addEventListener("ems:tab", function (event) {
            var root = rootOf(event.target);
            var tab = event.detail && event.detail.tab;
            if (!root || TABS.indexOf(tab) < 0) {
                return;
            }
            state(root).tab = tab;
            applyVisibility(root);
            reset(root);
        });
    });

    window.EMSDelegate.on("change", "[data-jh-filters] select", function (event, select) {
        var root = rootOf(select);
        if (root) {
            reset(root);
        }
    });

    // 2026-10-14: vahid EMSSearchInput (1500 ms, ≥ 2 simvol, Enter dərhal, IME).
    window.EMSSearchInput.delegate("[data-jh-root] #jh-q", {
        onSearch: function (value, meta) {
            var root = rootOf(meta.input);
            if (root) {
                reset(root);
            }
        },
    });

    window.EMSDelegate.on("click", "[data-jh-root] [data-jh-chip]", function (event, chip) {
        var root = rootOf(chip);
        var select = root ? root.querySelector('[data-jh-category="' + state(root).tab + '"]') : null;
        if (!select) {
            return;
        }
        select.value = chip.getAttribute("data-jh-chip") || "";
        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.sync(select);
        }
        reset(root);
    });

    window.EMSDelegate.on("click", "[data-jh-root] [data-jh-page]", function (event, button) {
        var root = rootOf(button);
        var page = parseInt(button.getAttribute("data-jh-page") || "", 10);
        if (!root || isNaN(page) || page < 1) {
            return;
        }
        state(root).page = page;
        load(root);
    });

    /* ── Seçim ───────────────────────────────────────────────────────────── */

    window.EMSDelegate.on("change", "[data-jh-root] [data-jh-check]", function (event, box) {
        var root = rootOf(box);
        if (!root) {
            return;
        }
        var selection = state(root).selection;
        if (box.checked) {
            selection.add(box.value);
        } else {
            selection.delete(box.value);
        }
        syncToolbar(root);
    });

    window.EMSDelegate.on("change", "[data-jh-root] [data-jh-check-page]", function (event, pageBox) {
        var root = rootOf(pageBox);
        if (!root) {
            return;
        }
        var selection = state(root).selection;
        currentBoxes(root).forEach(function (box) {
            box.checked = pageBox.checked;
            if (pageBox.checked) {
                selection.add(box.value);
            } else {
                selection.delete(box.value);
            }
        });
        syncToolbar(root);
    });

    window.EMSDelegate.on("click", "[data-jh-root] [data-jh-clear]", function (event, button) {
        var root = rootOf(button);
        if (!root) {
            return;
        }
        state(root).selection.clear();
        root.querySelectorAll("[data-jh-check]").forEach(function (box) {
            box.checked = false;
        });
        syncToolbar(root);
    });

    window.EMSDelegate.on("click", "[data-jh-root] [data-jh-select-all]", function (event, button) {
        var root = rootOf(button);
        if (!root || state(root).tab === "history") {
            return;
        }
        var st = state(root);
        var params = Object.assign({ tab: st.tab, select: "all" }, filters(root));
        button.disabled = true;
        window.EMSCore.fetchJSON(query(root, params))
            .then(function (data) {
                st.selection = new Set((data && data.ids) || []);
                currentBoxes(root).forEach(function (box) {
                    box.checked = st.selection.has(box.value);
                });
                syncToolbar(root);
                toast(R().fill(strings(root).select_all_done, { n: st.selection.size }), "info");
            })
            .catch(function () {
                toast(strings(root).load_error, "error");
            })
            .then(function () {
                button.disabled = false;
            });
    });

    /* ── Önizləmə → təsdiq / bərpa dialoqu ───────────────────────────────── */

    function dialogParts(root) {
        var dialog = document.getElementById(DIALOG_ID);
        return {
            dialog: dialog,
            title: dialog && dialog.querySelector("[data-jh-dialog-title]"),
            sub: dialog && dialog.querySelector("[data-jh-dialog-sub]"),
            preview: dialog && dialog.querySelector("[data-jh-preview]"),
            error: dialog && dialog.querySelector("[data-jh-dialog-error]"),
            reason: dialog && dialog.querySelector("#jh-reason"),
            confirm: dialog && dialog.querySelector("[data-jh-confirm]"),
            repreview: dialog && dialog.querySelector("[data-jh-repreview]"),
            min: parseInt(root.getAttribute("data-min-reason") || "20", 10) || 20,
        };
    }

    function syncConfirm(root) {
        var parts = dialogParts(root);
        var pending = state(root).pending;
        if (!parts.confirm) {
            return;
        }
        var reasonOk = parts.reason && parts.reason.value.trim().length >= parts.min;
        var ready = Boolean(pending && !pending.busy && !pending.blocked && (pending.action === "revert" || pending.digest));
        parts.confirm.disabled = !(reasonOk && ready);
        parts.confirm.setAttribute("aria-disabled", parts.confirm.disabled ? "true" : "false");
    }

    function showError(root, message) {
        var parts = dialogParts(root);
        if (parts.error) {
            parts.error.textContent = message || "";
            parts.error.hidden = !message;
        }
    }

    function post(root, payload) {
        return window.EMSCore.fetchJSON(root.getAttribute("data-action-url"), { method: "POST", data: payload });
    }

    function runPreview(root) {
        var st = state(root);
        var parts = dialogParts(root);
        var pending = st.pending;
        pending.digest = "";
        pending.blocked = false;
        pending.busy = true;
        showError(root, "");
        if (parts.repreview) {
            parts.repreview.hidden = true;
        }
        if (parts.preview) {
            parts.preview.textContent = strings(root).loading;
        }
        syncConfirm(root);
        post(root, { action: "preview", tab: st.tab, ids: pending.ids, target: pending.target })
            .then(function (data) {
                pending.digest = data.digest || "";
                pending.blocked = !data.can_apply;
                if (parts.preview) {
                    R().preview(parts.preview, data, strings(root));
                }
            })
            .catch(function (err) {
                showError(root, ((err && err.payload) || {}).message || strings(root).load_error);
            })
            .then(function () {
                pending.busy = false;
                syncConfirm(root);
            });
    }

    function openDialog(root, pending) {
        var i18n = strings(root);
        var parts = dialogParts(root);
        if (!parts.dialog || !window.EMSOverlay) {
            return;
        }
        var key = pending.action === "revert" ? "revert" : pending.target;
        state(root).pending = pending;
        parts.title.textContent = i18n["title_" + key] || "";
        parts.sub.textContent = i18n["sub_" + key] || "";
        if (parts.reason) {
            parts.reason.value = "";
        }
        showError(root, "");
        window.EMSOverlay.open(DIALOG_ID);
        if (pending.action === "revert") {
            if (parts.repreview) {
                parts.repreview.hidden = true;
            }
            parts.preview.textContent = R().fill(i18n.revert_count, { n: pending.ids.length });
            syncConfirm(root);
        } else {
            runPreview(root);
        }
    }

    window.EMSDelegate.on("click", "[data-jh-root] [data-jh-act]", function (event, button) {
        var root = rootOf(button);
        if (!root || !canApply(root)) {
            return;
        }
        var ids = Array.from(state(root).selection);
        if (!ids.length) {
            return;
        }
        var action = button.getAttribute("data-jh-act") === "revert" ? "revert" : "apply";
        openDialog(root, { action: action, target: button.getAttribute("data-jh-target") || "", ids: ids });
    });

    window.EMSDelegate.on("click", "[data-jh-root] [data-jh-repreview]", function (event, button) {
        var root = rootOf(button);
        if (root && state(root).pending) {
            runPreview(root);
        }
    });

    window.EMSDelegate.on("input", "[data-jh-root] #jh-reason", function (event, field) {
        var root = rootOf(field);
        if (root) {
            syncConfirm(root);
        }
    });

    window.EMSDelegate.on("click", "[data-jh-root] [data-jh-confirm]", function (event, button) {
        var root = rootOf(button);
        var st = root ? state(root) : null;
        var pending = st && st.pending;
        var parts = root ? dialogParts(root) : null;
        if (!pending || !parts || !parts.reason) {
            return;
        }
        var reason = parts.reason.value.trim();
        if (reason.length < parts.min) {
            return;
        }
        var payload =
            pending.action === "revert"
                ? { action: "revert", ids: pending.ids, reason: reason }
                : { action: "apply", tab: st.tab, ids: pending.ids, target: pending.target, reason: reason, digest: pending.digest };
        pending.busy = true;
        syncConfirm(root);
        post(root, payload)
            .then(function (data) {
                toast(data && data.message, "success");
                st.pending = null;
                window.EMSOverlay.close(DIALOG_ID);
                reset(root, true);
                loadSummary(root);
            })
            .catch(function (err) {
                var data = (err && err.payload) || {};
                showError(root, data.message || strings(root).load_error);
                if (data.error === "drift" && pending.action !== "revert") {
                    pending.digest = "";
                    if (parts.repreview) {
                        parts.repreview.hidden = false;
                    }
                }
            })
            .then(function () {
                if (st.pending === pending) {
                    pending.busy = false;
                    syncConfirm(root);
                }
            });
    });
})(window, document);
