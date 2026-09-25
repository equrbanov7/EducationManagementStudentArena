/* =========================================================================
   results_table.js — müəllim reytinqi: sıralama, «ən yüksək/ən aşağı N»,
   minimum cavab sayı, dözümlü axtarış (ı/i, ə/e, ş/s, ç/c, ğ/g, ö/o, ü/u),
   səhifələmə. Bütün sətirlər serverdədir; bu modul yalnız onları düzür/gizlədir.
   Vəziyyət URL-ə yazılır (`er_sort`, `er_view`, `er_min`, `er_tq`, `er_page`) —
   link paylaşıla bilir və filtr paneli bu açarlara toxunmur.
   Rəqəmlər `svr-rank-data` JSON adasındandır (sətir sırası indeksi ilə).
   AJAX-safe: `EMSReady` + kökdə `data-svr-rank-init`; kliklər `EMSDelegate`.
   ========================================================================= */
(function (window, document) {
    "use strict";

    var NS = (window.EMSSurveyResults = window.EMSSurveyResults || {});
    if (NS.table) {
        return;
    }

    var NUMERIC = {
        n: true,
        rate: true,
        avg_overall: true,
        likert_index: true,
        recommend_top2: true,
        delta_department_overall: true,
        delta_org_overall: true,
        question_avg: true
    };

    function fold(text) {
        return String(text || "")
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/ə/g, "e")
            .replace(/ı/g, "i");
    }

    function params() {
        try {
            return new URLSearchParams(window.location.search);
        } catch (err) {
            return null;
        }
    }

    function syncUrl(state) {
        var query = params();
        if (!query || !window.history || !window.history.replaceState) {
            return;
        }
        function put(name, value, fallback) {
            if (value === fallback || value === "" || value === null || value === undefined) {
                query.delete(name);
            } else {
                query.set(name, String(value));
            }
        }
        put("er_sort", state.sort, state.defaultSort);
        put("er_view", state.view, "all");
        put("er_min", state.min, 0);
        put("er_tq", state.q, "");
        put("er_page", state.page, 1);
        var search = query.toString();
        try {
            window.history.replaceState(window.history.state, "", window.location.pathname + (search ? "?" + search : ""));
        } catch (err) {
            /* köhnə brauzer — URL sinxronu opsionaldır */
        }
    }

    function compare(key, direction) {
        return function (a, b) {
            var va = a.data[key];
            var vb = b.data[key];
            if (key === "teacher_name") {
                return direction * String(a.data.name || "").localeCompare(String(b.data.name || ""), "az");
            }
            var aMissing = va === null || va === undefined;
            var bMissing = vb === null || vb === undefined;
            if (aMissing || bMissing) {
                return aMissing === bMissing ? a.index - b.index : aMissing ? 1 : -1;
            }
            return va === vb ? a.index - b.index : direction * (va < vb ? -1 : 1);
        };
    }

    function select(root, state) {
        var needle = fold(state.q.trim());
        var items = state.items.filter(function (item) {
            if (state.min && item.data.n < state.min) {
                return false;
            }
            return !needle || item.search.indexOf(needle) !== -1;
        });
        if (state.view === "top" || state.view === "bottom") {
            var ranked = items.filter(function (item) {
                return item.data.visible && item.data.avg_overall !== null;
            });
            ranked.sort(compare("avg_overall", state.view === "top" ? -1 : 1));
            items = ranked.slice(0, state.top);
        }
        var key = state.sort.replace(/^-/, "");
        items.sort(compare(key, state.sort.charAt(0) === "-" ? -1 : 1));
        return items;
    }

    function renderHeaders(root, state) {
        var key = state.sort.replace(/^-/, "");
        var desc = state.sort.charAt(0) === "-";
        root.querySelectorAll("th[data-svr-sort]").forEach(function (th) {
            var active = th.getAttribute("data-svr-sort") === key;
            th.setAttribute("aria-sort", active ? (desc ? "descending" : "ascending") : "none");
            var arrow = th.querySelector(".ems-sort__arrow");
            if (arrow) {
                arrow.textContent = active ? (desc ? "▼" : "▲") : "↕";
            }
        });
        root.querySelectorAll("[data-svr-rank-view]").forEach(function (button) {
            button.setAttribute("aria-pressed", button.getAttribute("data-svr-rank-view") === state.view ? "true" : "false");
        });
    }

    function renderPager(root, state, total, t) {
        var pager = root.querySelector("[data-svr-rank-pager]");
        if (!pager) {
            return;
        }
        var pages = Math.max(1, Math.ceil(total / state.size));
        pager.textContent = "";
        if (pages <= 1) {
            return;
        }
        function button(label, page, disabled) {
            var node = document.createElement("button");
            node.type = "button";
            node.className = "ems-btn ems-btn--sm";
            node.textContent = label;
            node.disabled = disabled;
            node.setAttribute("data-svr-rank-page", String(page));
            return node;
        }
        pager.appendChild(button(t.i18nPrev || "‹", state.page - 1, state.page <= 1));
        var info = document.createElement("span");
        info.textContent = (t.i18nPage || "") + " " + state.page + " / " + pages;
        pager.appendChild(info);
        pager.appendChild(button(t.i18nNext || "›", state.page + 1, state.page >= pages));
    }

    function apply(root) {
        var state = root._svrRank;
        if (!state) {
            return;
        }
        var t = (root.closest("[data-i18n-n]") || root).dataset;
        var items = select(root, state);
        var pages = Math.max(1, Math.ceil(items.length / state.size));
        state.page = Math.min(Math.max(1, state.page), pages);
        var start = (state.page - 1) * state.size;
        var shown = items.slice(start, start + state.size);
        var visible = new Set(shown.map(function (item) {
            return item.index;
        }));
        state.items.forEach(function (item) {
            item.row.hidden = !visible.has(item.index);
        });
        var tbody = state.tbody;
        items.forEach(function (item) {
            tbody.appendChild(item.row);
        });
        renderHeaders(root, state);
        renderPager(root, state, items.length, t);
        var count = root.querySelector("[data-svr-rank-count]");
        if (count) {
            count.textContent = items.length
                ? (t.i18nShown || "") + ": " + shown.length + " / " + items.length + " (" + (t.i18nOf || "") + " " + state.items.length + ")"
                : t.i18nNone || "";
        }
        syncUrl(state);
    }

    function init(root) {
        if (root.dataset.svrRankInit === "1") {
            return;
        }
        var island = document.getElementById("svr-rank-data");
        var tbody = root.querySelector("tbody");
        if (!island || !tbody) {
            return;
        }
        var data;
        try {
            data = JSON.parse(island.textContent || "[]");
        } catch (err) {
            return;
        }
        root.dataset.svrRankInit = "1";
        var rows = {};
        tbody.querySelectorAll("tr[data-svr-row]").forEach(function (row) {
            rows[row.getAttribute("data-svr-row")] = row;
        });
        var query = params();
        function get(name, fallback) {
            return query && query.get(name) !== null ? query.get(name) : fallback;
        }
        var defaultSort = root.getAttribute("data-sort") || "-avg_overall";
        root._svrRank = {
            items: data
                .map(function (entry, index) {
                    return {
                        index: index,
                        data: entry,
                        row: rows[String(index)],
                        search: fold((entry.name || "") + " " + (entry.department || ""))
                    };
                })
                .filter(function (item) {
                    return !!item.row;
                }),
            tbody: tbody,
            size: parseInt(root.getAttribute("data-page-size"), 10) || 25,
            top: parseInt(root.getAttribute("data-top"), 10) || 10,
            defaultSort: defaultSort,
            sort: get("er_sort", defaultSort),
            view: ["all", "top", "bottom"].indexOf(get("er_view", "all")) !== -1 ? get("er_view", "all") : "all",
            min: parseInt(get("er_min", "0"), 10) || 0,
            q: get("er_tq", ""),
            page: parseInt(get("er_page", "1"), 10) || 1
        };
        var state = root._svrRank;
        if (!NUMERIC[state.sort.replace(/^-/, "")] && state.sort.replace(/^-/, "") !== "teacher_name") {
            state.sort = defaultSort;
        }
        var search = root.querySelector("[data-svr-rank-search]");
        if (search) {
            search.value = state.q;
        }
        var min = root.querySelector("[data-svr-rank-min]");
        if (min) {
            min.value = String(state.min);
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(min);
            }
        }
        apply(root);
    }

    function rootOf(node) {
        return node.closest("[data-svr-rank]");
    }

    window.EMSDelegate.on("click", "[data-svr-sort-btn]", function (event, button) {
        var root = rootOf(button);
        if (!root || !root._svrRank) {
            return;
        }
        var key = button.getAttribute("data-svr-sort-btn");
        var state = root._svrRank;
        if (state.sort === "-" + key) {
            state.sort = key;
        } else if (state.sort === key) {
            state.sort = "-" + key;
        } else {
            state.sort = NUMERIC[key] ? "-" + key : key;
        }
        state.page = 1;
        apply(root);
    });

    window.EMSDelegate.on("click", "[data-svr-rank-view]", function (event, button) {
        var root = rootOf(button);
        if (!root || !root._svrRank) {
            return;
        }
        var state = root._svrRank;
        state.view = button.getAttribute("data-svr-rank-view");
        if (state.view === "top") {
            state.sort = "-avg_overall";
        } else if (state.view === "bottom") {
            state.sort = "avg_overall";
        }
        state.page = 1;
        apply(root);
    });

    window.EMSDelegate.on("click", "[data-svr-rank-page]", function (event, button) {
        var root = rootOf(button);
        if (!root || !root._svrRank || button.disabled) {
            return;
        }
        root._svrRank.page = parseInt(button.getAttribute("data-svr-rank-page"), 10) || 1;
        apply(root);
        var table = root.querySelector(".svr-rank__table");
        if (table && table.scrollIntoView) {
            table.scrollIntoView({ block: "start" });
        }
    });

    window.EMSDelegate.on("change", "[data-svr-rank-min]", function (event, select) {
        var root = rootOf(select);
        if (!root || !root._svrRank) {
            return;
        }
        root._svrRank.min = parseInt(select.value, 10) || 0;
        root._svrRank.page = 1;
        apply(root);
    });

    var timer = null;
    window.EMSDelegate.on("input", "[data-svr-rank-search]", function (event, input) {
        var root = rootOf(input);
        if (!root || !root._svrRank) {
            return;
        }
        window.clearTimeout(timer);
        timer = window.setTimeout(function () {
            root._svrRank.q = input.value || "";
            root._svrRank.page = 1;
            apply(root);
        }, 200);
    });

    window.EMSReady(function () {
        document.querySelectorAll("[data-svr-rank]").forEach(init);
    });

    NS.table = { apply: apply };
})(window, document);
