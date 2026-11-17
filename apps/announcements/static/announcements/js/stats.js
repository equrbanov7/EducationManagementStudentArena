/* «Elan statistikası» (2026-11-18) — tənbəl yükləmə + filtrlər.
 *   * səhifə açılan kimi bölgü (`data-summary-url`) və şəxs siyahısı (`data-people-url`) AYRI JSON uçlarından gəlir;
 *   * elan seçimi dəyişəndə tam keçid (rol variantları elandan asılıdır);
 *   * bölgü / rol / bölmə dəyişəndə hər ikisi yenilənir, URL və «Excel-ə yüklə» keçidi sinxronlaşır;
 *   * bölgü sətrinə klik: bölmə filtri həmin bölməyə daralır (fakültə → ixtisas → qrup), rol sətri — rol filtri;
 *   * şəxslər: vəziyyət tabları, axtarış (vahid EMSSearchInput), səhifələmə.
 * AJAX-safe: hadisələr `EMSDelegate` ilə document səviyyəsində, ilk yükləmə `EMSReady` ilə (idempotent).
 */
(function () {
    "use strict";

    if (window.__emsAnnouncementStats) {
        return;
    }
    window.__emsAnnouncementStats = true;

    var FILTERS = ["elan", "dim", "role", "unit"];

    function rootOf(node) {
        return node && node.closest ? node.closest("[data-annst-root]") : null;
    }

    function filterParams(root) {
        var form = root.querySelector("[data-annst-filters]");
        var data = new URLSearchParams();
        if (!form) { return data; }
        FILTERS.forEach(function (name) {
            var field = form.elements.namedItem(name);
            if (field && (field.value || "").trim()) { data.set(name, field.value.trim()); }
        });
        return data;
    }

    function peopleParams(root, page) {
        var data = filterParams(root);
        var form = root.querySelector("[data-annst-people-filters]");
        var status = form && form.querySelector("[data-annst-status]:checked");
        var search = form && form.querySelector("[data-annst-search]");
        if (status && status.value !== "all") { data.set("status", status.value); }
        if (search && search.value.trim()) { data.set("q", search.value.trim()); }
        if (page && page > 1) { data.set("page", String(page)); }
        return data;
    }

    function syncUrl(root) {
        var data = peopleParams(root, 0);
        var exportLink = root.querySelector("[data-annst-export]");
        var exportUrl = root.getAttribute("data-export-url");
        if (exportLink && exportUrl) {
            exportLink.setAttribute("href", exportUrl + "?" + data.toString());
        }
        if (!window.history || typeof window.history.replaceState !== "function") { return; }
        try {
            window.history.replaceState(window.history.state, "", window.location.pathname + "?" + data.toString());
        } catch (e) { /* köhnə brauzer — URL sinxronu vacib deyil */ }
    }

    function showError(root, target) {
        var source = root.querySelector("[data-annst-error]");
        var message = document.createElement("p");
        message.className = "ann-error";
        message.setAttribute("role", "alert");
        message.textContent = source ? source.textContent : "Error";
        target.replaceChildren(message);
    }

    function fetchInto(root, key, url, data, target) {
        if (!target || !url || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") { return; }
        var slot = "__annst" + key;
        if (root[slot]) {
            try { root[slot].abort(); } catch (e) { /* ignore */ }
        }
        var controller = typeof AbortController === "function" ? new AbortController() : null;
        root[slot] = controller;
        target.setAttribute("aria-busy", "true");
        target.classList.add("ems-search-pending");
        window.EMSCore.fetchJSON(url + "?" + data.toString(), { signal: controller ? controller.signal : undefined })
            .then(function (payload) {
                if (root[slot] !== controller) { return; }
                target.innerHTML = payload && payload.html ? payload.html : "";
            })
            .catch(function (error) {
                if (error && error.name === "AbortError") { return; }
                showError(root, target);
            })
            .then(function () {
                if (root[slot] === controller) {
                    target.setAttribute("aria-busy", "false");
                    target.classList.remove("ems-search-pending");
                    root[slot] = null;
                }
            });
    }

    function loadSummary(root) {
        fetchInto(root, "Summary", root.getAttribute("data-summary-url"), filterParams(root),
            root.querySelector("[data-annst-summary]"));
    }

    function loadPeople(root, page) {
        fetchInto(root, "People", root.getAttribute("data-people-url"), peopleParams(root, page),
            root.querySelector("[data-annst-people]"));
        if (page && page > 1) {
            var section = root.querySelector("[data-annst-people]");
            try { section.scrollIntoView({ block: "start", behavior: "smooth" }); } catch (e) { /* ignore */ }
        }
    }

    function reloadAll(root) {
        syncUrl(root);
        loadSummary(root);
        loadPeople(root, 1);
    }

    function setSelect(select, value, label) {
        if (!select) { return; }
        if (value && !Array.prototype.some.call(select.options, function (o) { return o.value === value; })) {
            var option = document.createElement("option");
            option.value = value;
            option.textContent = label || value;
            select.appendChild(option);
        }
        select.value = value;
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
    }

    window.EMSReady(function () {
        document.querySelectorAll("[data-annst-root]").forEach(function (root) {
            if (root.__annstReady || !root.querySelector("[data-annst-summary]")) { return; }
            root.__annstReady = true;
            loadSummary(root);
            loadPeople(root, 1);
        });
    });

    window.EMSDelegate.on("change", "[data-annst-root] [data-annst-elan]", function (event, select) {
        if (!select.value) { return; }
        var url = new URL(window.location.href);
        url.search = "";
        url.searchParams.set("elan", select.value);
        window.location.assign(url.pathname + "?" + url.searchParams.toString());
    });

    window.EMSDelegate.on("change", "[data-annst-root] [data-annst-field]", function (event, select) {
        var root = rootOf(select);
        if (root) { reloadAll(root); }
    });

    window.EMSDelegate.on("submit", "[data-annst-root] [data-annst-filters]", function (event, form) {
        event.preventDefault();
        var root = rootOf(form);
        if (root) { reloadAll(root); }
    });

    window.EMSDelegate.on("click", "[data-annst-root] [data-annst-drill-unit]", function (event, button) {
        var root = rootOf(button);
        if (!root) { return; }
        var form = root.querySelector("[data-annst-filters]");
        setSelect(form.querySelector("[data-annst-unit]"), button.getAttribute("data-annst-drill-unit"),
            button.getAttribute("data-annst-drill-label"));
        setSelect(form.elements.namedItem("dim"), button.getAttribute("data-annst-next-dim") || "faculty");
        reloadAll(root);
    });

    window.EMSDelegate.on("click", "[data-annst-root] [data-annst-drill-role]", function (event, button) {
        var root = rootOf(button);
        if (!root) { return; }
        var form = root.querySelector("[data-annst-filters]");
        setSelect(form.elements.namedItem("role"), button.getAttribute("data-annst-drill-role"));
        setSelect(form.elements.namedItem("dim"), "faculty");
        reloadAll(root);
    });

    window.EMSSearchInput.delegate("[data-annst-root] [data-annst-search]", {
        onSearch: function (value, meta) {
            var root = rootOf(meta.input);
            if (root) { syncUrl(root); loadPeople(root, 1); }
        },
    });

    window.EMSDelegate.on("change", "[data-annst-root] [data-annst-status]", function (event, input) {
        var root = rootOf(input);
        if (root) { syncUrl(root); loadPeople(root, 1); }
    });

    window.EMSDelegate.on("submit", "[data-annst-root] [data-annst-people-filters]", function (event, form) {
        event.preventDefault();
        var root = rootOf(form);
        if (!root) { return; }
        var search = form.querySelector("[data-annst-search]");
        if (search) { window.EMSSearchInput.sync(search); }
        syncUrl(root);
        loadPeople(root, 1);
    });

    window.EMSDelegate.on("click", "[data-annst-root] [data-annst-page]", function (event, button) {
        event.preventDefault();
        var root = rootOf(button);
        var page = parseInt(button.getAttribute("data-annst-page"), 10);
        if (root && page > 0 && !button.disabled) { loadPeople(root, page); }
    });
})();
