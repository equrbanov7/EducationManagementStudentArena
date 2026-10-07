/* «Elanlar» siyahısı — axtarış (300 ms debounce), filtr, sıralama, səhifələmə, skeleton.
 *
 * AJAX-safe: bütün hadisələr `EMSDelegate.on` ilə document səviyyəsindədir, ona görə panel
 * AJAX ilə yenidən yüklənəndə heç nə yenidən bağlanmır; skript təkrar icra olunsa da qoruyucu
 * bayraq ikinci qeydiyyatın qarşısını alır. Server cavabı hazır HTML fraqmentidir
 * (`/elanlar/api/list/` → `_list.html`) — klientdə mətn HTML kimi qurulmur.
 */
(function () {
    "use strict";

    if (window.__emsAnnouncementsList) {
        return;
    }
    window.__emsAnnouncementsList = true;

    var DEBOUNCE_MS = 300;
    var FIELDS = ["q", "category", "state", "sort", "unread", "deadline", "pending"];

    function rootOf(node) {
        return node && node.closest ? node.closest("[data-ann-root]") : null;
    }

    function params(root, page) {
        var form = root.querySelector("[data-ann-filters]");
        var data = new URLSearchParams();
        if (form) {
            FIELDS.forEach(function (name) {
                var field = form.elements.namedItem(name);
                if (!field) { return; }
                if (field.type === "checkbox") {
                    if (field.checked) { data.set(name, field.value || "1"); }
                } else if ((field.value || "").trim()) {
                    data.set(name, field.value.trim());
                }
            });
        }
        if (page && page > 1) { data.set("page", String(page)); }
        return data;
    }

    function syncUrl(root, data) {
        if (!window.history || typeof window.history.replaceState !== "function") { return; }
        try {
            var url = new URL(window.location.href);
            FIELDS.concat(["page", "elan"]).forEach(function (name) { url.searchParams.delete(name); });
            if (root.hasAttribute("data-ann-cabinet")) { url.searchParams.set("section", "announcements"); }
            data.forEach(function (value, key) { url.searchParams.set(key, value); });
            window.history.replaceState(window.history.state, "", url.pathname + "?" + url.searchParams.toString());
        } catch (e) { /* köhnə brauzer — URL sinxronu vacib deyil */ }
    }

    function showSkeleton(root, results) {
        var tpl = root.querySelector("template[data-ann-skeleton]");
        if (tpl && tpl.content) {
            results.replaceChildren(tpl.content.cloneNode(true));
        }
    }

    function load(root, page) {
        var results = root.querySelector("[data-ann-results]");
        var url = root.getAttribute("data-list-url");
        if (!results || !url || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") { return; }
        if (root.__annController) {
            try { root.__annController.abort(); } catch (e) { /* ignore */ }
        }
        var controller = typeof AbortController === "function" ? new AbortController() : null;
        root.__annController = controller;
        var data = params(root, page);
        results.setAttribute("aria-busy", "true");
        showSkeleton(root, results);
        window.EMSCore.fetchJSON(url + "?" + data.toString(), { signal: controller ? controller.signal : undefined })
            .then(function (payload) {
                if (root.__annController !== controller) { return; }
                results.innerHTML = payload && payload.html ? payload.html : "";
                syncUrl(root, data);
                if (page && page > 1) {
                    try { root.scrollIntoView({ block: "start", behavior: "smooth" }); } catch (e) { /* ignore */ }
                }
            })
            .catch(function (error) {
                if (error && error.name === "AbortError") { return; }
                var text = root.querySelector("[data-ann-error-text]");
                var message = document.createElement("p");
                message.className = "ann-error";
                message.setAttribute("role", "alert");
                message.textContent = text ? text.textContent : "Error";
                results.replaceChildren(message);
            })
            .then(function () {
                if (root.__annController === controller) {
                    results.setAttribute("aria-busy", "false");
                    root.__annController = null;
                }
            });
    }

    window.EMSDelegate.on("input", "[data-ann-root] [data-ann-search]", function (event, input) {
        var root = rootOf(input);
        if (!root) { return; }
        window.clearTimeout(root.__annTimer);
        root.__annTimer = window.setTimeout(function () { load(root, 1); }, DEBOUNCE_MS);
    });

    window.EMSDelegate.on("change", "[data-ann-root] [data-ann-filters] select, [data-ann-root] [data-ann-filters] input[type=checkbox]", function (event, field) {
        var root = rootOf(field);
        if (root) { load(root, 1); }
    });

    window.EMSDelegate.on("submit", "[data-ann-root] [data-ann-filters]", function (event, form) {
        event.preventDefault();
        var root = rootOf(form);
        if (root) {
            window.clearTimeout(root.__annTimer);
            load(root, 1);
        }
    });

    window.EMSDelegate.on("click", "[data-ann-root] [data-ann-page]", function (event, button) {
        event.preventDefault();
        var root = rootOf(button);
        var page = parseInt(button.getAttribute("data-ann-page"), 10);
        if (root && page > 0 && !button.disabled) { load(root, page); }
    });
})();
