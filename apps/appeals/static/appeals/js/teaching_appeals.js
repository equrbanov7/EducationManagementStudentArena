/* =========================================================================
   «Fənnimə aid apellyasiyalar» (`teaching-appeals`) — kabinet bölməsi, sahib 2026-10-27.

   * `[data-ta-open-appeal="<id>"]` → çekməcəni açır, `appeals:teaching_appeal_detail` JSON
     fraqmentini (serverdə render olunub, yalnız-oxu) gövdəyə yerləşdirir;
   * `[data-ta-root][data-ta-open]` (bildiriş keçidi `?ta_open=<id>`) → bölmə yüklənəndə çekməcə özü açılır;
   * KPI kartı (`ems:kpi-filter`, nav.js) → «Status» süzgəci; avto filtr axını (filter_bar.js) bölməni yeniləyir.

   AJAX-SAFE: dinləyicilər `document`-də BİR dəfə (`EMSDelegate` + window bayrağı), ilkin açılış `EMSReady`
   ilə hər swap-dan sonra yoxlanır (idempotent: `data-ta-opened`). Inline skript / üslub yoxdur (CSP).
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSTeachingAppeals) {
        return;
    }
    window.EMSTeachingAppeals = true;

    var DRAWER_ID = "taAppealDrawer";
    var current = null;

    function rootOf(node) {
        return (node && node.closest && node.closest("[data-ta-root]")) || document.querySelector("[data-ta-root]");
    }

    function drawerBody(drawer) {
        return drawer && drawer.querySelector("[data-ta-drawer-body]");
    }

    function note(body, text) {
        body.textContent = "";
        var paragraph = document.createElement("p");
        paragraph.className = "ta-muted";
        paragraph.textContent = text || "";
        body.appendChild(paragraph);
    }

    function setHeading(drawer, payload) {
        var title = drawer.querySelector(".ems-drawer__title");
        if (title && !drawer.hasAttribute("data-ta-default-title")) {
            drawer.setAttribute("data-ta-default-title", title.textContent);
        }
        if (title && payload.title) {
            title.textContent = payload.title;
        }
        var sub = drawer.querySelector(".ems-drawer__sub");
        if (!sub && title && payload.subtitle) {
            sub = document.createElement("p");
            sub.className = "ems-drawer__sub";
            title.insertAdjacentElement("afterend", sub);
        }
        if (sub) {
            sub.textContent = payload.subtitle || "";
        }
    }

    function load(id, origin) {
        var root = rootOf(origin);
        var drawer = document.getElementById(DRAWER_ID);
        var body = drawerBody(drawer);
        if (!root || !drawer || !body || !id) {
            return;
        }
        current = String(id);
        // Əvvəlki apellyasiyanın adı yüklənmə / xəta zamanı başlıqda qalmasın.
        setHeading(drawer, { title: drawer.getAttribute("data-ta-default-title") || "", subtitle: "" });
        note(body, root.getAttribute("data-i18n-loading"));
        if (window.EMSOverlay && drawer.hidden) {
            window.EMSOverlay.open(drawer);
        }
        var url = (root.getAttribute("data-ta-detail-base") || "") + encodeURIComponent(current) + "/";
        window.EMSCore.fetchJSON(url)
            .then(function (payload) {
                if (current !== String(id)) {
                    return;
                }
                if (!payload || payload.ok === false || typeof payload.html !== "string") {
                    note(body, (payload && payload.message) || root.getAttribute("data-i18n-error"));
                    return;
                }
                body.innerHTML = payload.html;
                setHeading(drawer, payload);
            })
            .catch(function (err) {
                if (current === String(id)) {
                    note(body, (err && err.payload && err.payload.message) || root.getAttribute("data-i18n-error"));
                }
            });
    }

    window.EMSDelegate.on("click", "[data-ta-open-appeal]", function (event, button) {
        event.preventDefault();
        load(button.getAttribute("data-ta-open-appeal"), button);
    });

    /* Sətrin istənilən yerinə klik (düymə / link xaricində) çekməcəni açır — böyük toxunma hədəfi. */
    window.EMSDelegate.on("click", "tr[data-ta-row]", function (event, row) {
        if (event.target.closest && event.target.closest("a, button, input, select, label")) {
            return;
        }
        load(row.getAttribute("data-ta-row"), row);
    });

    /* KPI kartı → «Status» süzgəci (server tərəfli; filter_bar.js avto rejimi change-də bölməni yeniləyir). */
    document.addEventListener("ems:kpi-filter", function (event) {
        var target = event.target;
        var panel = target && target.closest ? target.closest('[data-profile-section-panel="teaching-appeals"]') : null;
        var select = panel ? panel.querySelector('select[name="ta_status"]') : null;
        if (!select) {
            return;
        }
        var value = (event.detail && event.detail.filter) || "";
        if (select.value === value) {
            return;
        }
        select.value = value;
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
        select.dispatchEvent(new Event("change", { bubbles: true }));
    });

    /* Bildiriş keçidi: `?ta_open=<id>` — bölmə hər yükləndikdə bir dəfə. */
    function autoOpen() {
        var root = document.querySelector("[data-ta-root][data-ta-open]:not([data-ta-opened])");
        if (!root) {
            return;
        }
        root.setAttribute("data-ta-opened", "1");
        load(root.getAttribute("data-ta-open"), root);
        dropOpenParam();
    }

    /* `ta_open` bir dəfəlikdir: URL-də qalsa, süzgəc / səhifə dəyişəndə çekməcə yenidən açılardı. */
    function dropOpenParam() {
        try {
            var url = new URL(window.location.href);
            if (!url.searchParams.has("ta_open")) {
                return;
            }
            url.searchParams.delete("ta_open");
            window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
        } catch (err) {
            /* köhnə brauzer — çekməcə yenə açılır, yalnız URL təmizlənmir */
        }
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(autoOpen);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", autoOpen);
    } else {
        autoOpen();
    }
})(window, document);
