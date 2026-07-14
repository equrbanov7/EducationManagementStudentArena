/* =========================================================================
   appeals_sections.js — Profil dashboard apellyasiya bölmələri (tələbə
   "Apellyasiyalarım" + reviewer "Apellyasiyalar") üçün modal/filtr davranışı.

   Niyə static fayl + document-level delegation (EMSDelegate):
   Bu məntiq əvvəl bölmə şablonlarının daxilindəki <script> bloklarında idi və
   AJAX section swap-larından sonra listener-lər DOM-dan çıxarılmış köhnə
   node-larda qalırdı — "Bax" düyməsi gah modal açır, gah da standalone
   səhifəyə atırdı. EMSDelegate `document` üzərində qeydiyyat aparır, swap-lar
   ona təsir etmir (bax: static/js/ems_ajax_init.js). Elementlər hər event-də
   təzədən tapılır, ona görə köhnəlmiş referans problemi yaranmır.
   ========================================================================= */
(function () {
    "use strict";

    if (!window.EMSDelegate) {
        return;
    }

    var LOADING_HTML =
        '<div class="appeal-skeleton"><div class="appeal-skeleton__row"></div><div class="appeal-skeleton__row"></div></div>';
    var filterTimer = null;
    var listFetchAbort = null;

    function panelFor(el, section) {
        return el && el.closest ? el.closest('[data-profile-section-panel="' + section + '"]') : null;
    }

    function loadErrorText(panel) {
        return (panel && panel.getAttribute("data-i18n-load-error")) || "Yüklənmə alınmadı, yenidən cəhd edin.";
    }

    function withParam(url, extra) {
        return url + (url.indexOf("?") === -1 ? "?" : "&") + extra;
    }

    function cleanupOrphanBackdrops() {
        // Section swap açıq modalı DOM-dan çıxararsa (məs. brauzer Back),
        // backdrop sahibsiz qalıb səhifəni kilidləyə bilər — açılışdan əvvəl təmizlə.
        if (document.querySelector(".modal.show")) { return; }
        Array.prototype.forEach.call(document.querySelectorAll(".modal-backdrop"), function (n) { n.remove(); });
        document.body.classList.remove("modal-open");
        document.body.style.removeProperty("overflow");
        document.body.style.removeProperty("padding-right");
    }

    function getModal(modalEl) {
        if (!modalEl || !(window.bootstrap && window.bootstrap.Modal)) {
            return null;
        }
        cleanupOrphanBackdrops();
        return window.bootstrap.Modal.getOrCreateInstance(modalEl);
    }

    function makeAlert(type, msg) {
        var div = document.createElement("div");
        div.className = "alert alert-" + type;
        div.setAttribute("role", "alert");
        div.setAttribute("data-manage-flash", "1");
        div.textContent = msg;
        return div;
    }

    function clearFlash(root) {
        var old = root.querySelectorAll("[data-manage-flash]");
        Array.prototype.forEach.call(old, function (n) { n.remove(); });
    }

    function showToast(type, msg) {
        var container = document.querySelector("body > .toast-container");
        if (!container) {
            container = document.createElement("div");
            container.className = "toast-container";
            container.setAttribute("aria-live", "polite");
            container.setAttribute("aria-atomic", "true");
            document.body.appendChild(container);
        }
        var toast = document.createElement("div");
        toast.className = "alert alert-" + type + " app-toast app-toast--" + type + " fade show";
        toast.setAttribute("role", "alert");
        toast.setAttribute("data-auto-hide", "7000");
        toast.setAttribute("data-toast-item", "1");
        toast.innerHTML =
            '<span class="app-toast__icon" aria-hidden="true"><i class="fas fa-check"></i></span>' +
            '<span class="app-toast__body"></span>' +
            '<button type="button" class="app-toast__close" data-toast-dismiss data-bs-dismiss="alert" aria-label="Bağla">' +
            '<i class="fas fa-xmark" aria-hidden="true"></i></button>';
        var body = toast.querySelector(".app-toast__body");
        if (body) { body.textContent = msg; }
        container.appendChild(toast);
    }

    function fetchFragmentInto(url, modalBody, panel, afterSwap) {
        modalBody.innerHTML = LOADING_HTML;
        fetch(withParam(url, "fragment=1"), {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        })
            .then(function (r) {
                if (!r.ok) {
                    // Server mənalı xəta göndəribsə (403 JSON) onu göstər —
                    // generik "Yüklənmə alınmadı" yalnız son çarədir.
                    return r.text().then(function (t) {
                        var msg = "";
                        try { msg = (JSON.parse(t) || {}).error || ""; } catch (e) { /* JSON deyil */ }
                        throw new Error(msg || ("http_" + r.status));
                    });
                }
                return r.text();
            })
            .then(function (html) {
                modalBody.innerHTML = html;
                modalBody.scrollTop = 0;
                if (afterSwap) { afterSwap(); }
            })
            .catch(function (err) {
                modalBody.innerHTML = "";
                var message = err && err.message && err.message.indexOf("http_") !== 0
                    ? err.message
                    : loadErrorText(panel);
                modalBody.appendChild(makeAlert("danger", message));
            });
    }

    /* ── Tələbə: "Apellyasiyalarım" — detal modalı ─────────────────────── */

    window.EMSDelegate.on("click", "[data-appeal-detail-url]", function (event, link) {
        var panel = panelFor(link, "my-appeals");
        if (!panel) { return; }
        var modalEl = panel.querySelector("[data-appeal-detail-modal]");
        var modalBody = modalEl ? modalEl.querySelector("[data-appeal-modal-body]") : null;
        var modal = modalBody ? getModal(modalEl) : null;
        if (!modal) { return; } // bootstrap yoxdursa native keçid (server yönləndirər)
        event.preventDefault();
        modal.show();
        fetchFragmentInto(link.getAttribute("data-appeal-detail-url"), modalBody, panel, null);
    });

    window.EMSDelegate.on("hidden.bs.modal", "[data-appeal-detail-modal]", function (event, modalEl) {
        var body = modalEl.querySelector("[data-appeal-modal-body]");
        if (body) { body.innerHTML = LOADING_HTML; }
    });

    /* ── Reviewer: "Apellyasiyalar" — siyahı yeniləmə (AJAX) ───────────── */

    function listQueryFromLocation() {
        try {
            var p = new URLSearchParams(window.location.search);
            p.delete("section");
            p.delete("page");
            return p.toString();
        } catch (e) { return ""; }
    }

    function reloadManageList(panel, queryString) {
        var bodyHost = panel.querySelector("[data-manage-body]");
        var manageUrl = panel.getAttribute("data-manage-url");
        if (!bodyHost || !manageUrl || typeof window.fetch !== "function") { return; }
        var q = typeof queryString === "string" ? queryString : listQueryFromLocation();
        if (listFetchAbort) {
            try { listFetchAbort.abort(); } catch (e) { /* ignore */ }
        }
        var controller = (typeof AbortController === "function") ? new AbortController() : null;
        listFetchAbort = controller;
        var opts = {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        };
        if (controller) { opts.signal = controller.signal; }
        bodyHost.setAttribute("aria-busy", "true");
        fetch(withParam(manageUrl, "fragment=1&embedded=1" + (q ? "&" + q : "")), opts)
            .then(function (r) {
                if (!r.ok) { throw new Error("http"); }
                return r.text();
            })
            .then(function (html) {
                bodyHost.innerHTML = html;
                if (window.EMSBootstrapSelect && window.EMSBootstrapSelect.init) {
                    window.EMSBootstrapSelect.init(bodyHost);
                }
            })
            .catch(function (err) {
                if (err && err.name === "AbortError") { return; }
                /* fail-soft: köhnə siyahı qalır */
            })
            .then(function () {
                if (listFetchAbort === controller) { listFetchAbort = null; }
                bodyHost.removeAttribute("aria-busy");
            });
    }

    function filterParamsFromForm(form) {
        var params = new URLSearchParams();
        try {
            var data = new FormData(form);
            data.forEach(function (value, key) {
                if (typeof File !== "undefined" && value instanceof File) { return; }
                params.set(key, value);
            });
        } catch (e) { /* ignore */ }
        params.set("section", "manage-appeals");
        params.delete("page");
        return params;
    }

    function syncFilterUrl(params) {
        if (!window.history || !window.history.replaceState) { return; }
        try {
            var target = new URL(window.location.href);
            target.search = params.toString();
            window.history.replaceState(
                { section: "manage-appeals", ajax: true },
                "",
                target.pathname + target.search
            );
        } catch (e) { /* ignore */ }
    }

    function submitManageFilter(form, panel) {
        if (typeof window.fetch !== "function") {
            HTMLFormElement.prototype.submit.call(form);
            return;
        }
        var params = filterParamsFromForm(form);
        syncFilterUrl(params);
        var listParams = new URLSearchParams(params.toString());
        listParams.delete("section");
        listParams.delete("page");
        reloadManageList(panel, listParams.toString());
    }

    /* ── Filtr formları: manage → AJAX reload; tələbə → profil AJAX form ── */

    function submitFilterForm(form) {
        if (!form) { return; }
        if (filterTimer) {
            window.clearTimeout(filterTimer);
            filterTimer = null;
        }
        var managePanel = panelFor(form, "manage-appeals");
        if (managePanel && form.hasAttribute("data-appeal-manage-filter-form")) {
            submitManageFilter(form, managePanel);
            return;
        }
        // Tələbə formu (data-profile-ajax-form): submit-i profil AJAX qatı tutur.
        if (form.requestSubmit) {
            form.requestSubmit();
        } else {
            HTMLFormElement.prototype.submit.call(form);
        }
    }

    function scheduleFilterSubmit(form, delayMs) {
        if (!form) { return; }
        if (filterTimer) { window.clearTimeout(filterTimer); }
        filterTimer = window.setTimeout(function () {
            submitFilterForm(form);
        }, delayMs);
    }

    window.EMSDelegate.on("submit", "[data-appeal-manage-filter-form]", function (event, form) {
        event.preventDefault();
        submitFilterForm(form);
    });

    window.EMSDelegate.on("input", "[data-appeal-auto-search]", function (event, field) {
        if (field.form) { scheduleFilterSubmit(field.form, 350); }
    });

    window.EMSDelegate.on("keydown", "[data-appeal-auto-search]", function (event, field) {
        if (event.key !== "Enter" || !field.form) { return; }
        event.preventDefault();
        submitFilterForm(field.form);
    });

    window.EMSDelegate.on("change", "[data-appeal-auto-field]", function (event, field) {
        if (field.form) { scheduleFilterSubmit(field.form, 0); }
    });

    /* ── Reviewer: "Bax" → qərar modalı ────────────────────────────────── */

    window.EMSDelegate.on("click", "[data-appeal-review-url]", function (event, link) {
        var panel = panelFor(link, "manage-appeals");
        if (!panel) { return; }
        var modalEl = panel.querySelector("[data-manage-review-modal]");
        var modalBody = modalEl ? modalEl.querySelector("[data-manage-modal-body]") : null;
        var modal = modalBody ? getModal(modalEl) : null;
        if (!modal) { return; }
        event.preventDefault();
        modal.show();
        fetchFragmentInto(link.getAttribute("data-appeal-review-url"), modalBody, panel, function () {
            // Bootstrap select-ləri yenidən qur (native deyil) + qərar formu UX-i.
            if (window.EMSBootstrapSelect && window.EMSBootstrapSelect.init) {
                window.EMSBootstrapSelect.init(modalBody);
            }
            if (window.EMSAppealsReview && window.EMSAppealsReview.init) {
                window.EMSAppealsReview.init();
            }
        });
    });

    // Detal daxilində geri / ləğv → modalı bağla və siyahını yenilə.
    window.EMSDelegate.on("click", "[data-manage-detail-back], [data-review-cancel]", function (event, el) {
        var panel = panelFor(el, "manage-appeals");
        if (!panel) { return; }
        event.preventDefault();
        var modal = getModal(panel.querySelector("[data-manage-review-modal]"));
        if (modal) { modal.hide(); }
        if (panel.scrollIntoView) {
            panel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        reloadManageList(panel);
    });

    // Qərar formu submit → AJAX (client validation appeals_review.js-də).
    window.EMSDelegate.on("submit", "[data-appeals-review-form]", function (event, form) {
        var panel = panelFor(form, "manage-appeals");
        if (!panel) { return; }
        if (event.defaultPrevented) { return; } // client validation bloklayıb
        event.preventDefault();
        var modalEl = panel.querySelector("[data-manage-review-modal]");
        var modalBody = modalEl ? modalEl.querySelector("[data-manage-modal-body]") : null;
        fetch(withParam(form.getAttribute("action") || window.location.href, "fragment=1"), {
            method: "POST",
            body: new FormData(form),
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d && d.ok) {
                    var modal = getModal(modalEl);
                    if (modal) { modal.hide(); }
                    reloadManageList(panel);
                    if (panel.scrollIntoView) {
                        panel.scrollIntoView({ behavior: "smooth", block: "start" });
                    }
                    if (window.EMSProfile && typeof window.EMSProfile.refreshBadges === "function") {
                        try { window.EMSProfile.refreshBadges(); } catch (e) { /* ignore */ }
                    }
                    showToast("success", d.toast || d.message || "OK");
                } else if (modalBody) {
                    clearFlash(modalBody);
                    modalBody.insertBefore(
                        makeAlert("danger", (d && d.error) || loadErrorText(panel)),
                        modalBody.firstChild
                    );
                    modalBody.scrollTop = 0;
                }
            })
            .catch(function () {
                window.location.href = form.getAttribute("action") || window.location.href;
            });
    });

    window.EMSDelegate.on("hidden.bs.modal", "[data-manage-review-modal]", function (event, modalEl) {
        var body = modalEl.querySelector("[data-manage-modal-body]");
        if (body) { body.innerHTML = LOADING_HTML; }
    });

    /* ── Siyahıdakı "qalan vaxt" sayğacı — canlı tick ─────────────────────
       Server-render yalnız başlanğıc dəyəri verir; sekmə açıq qalsa da
       (başqa sekmədə olsanız belə) hər saniyə burda dekrementlənir.
       AJAX filtr swap-ından sonra köhnə node-lar DOM-dan çıxır (isConnected
       false olur) və siyahıdan silinir; yeni gələn [data-appeal-countdown]
       elementlər hər tick-də (scanCountdowns) avtomatik tutulur. ────────── */
    var activeCountdowns = [];

    function pad2(n) { return (n < 10 ? "0" : "") + n; }

    function renderCountdown(el, remaining) {
        el.textContent = pad2(Math.floor(remaining / 60)) + ":" + pad2(remaining % 60);
    }

    function bindCountdown(el) {
        if (!el || el.getAttribute("data-countdown-bound") === "1") { return; }
        var remaining = parseInt(el.getAttribute("data-appeal-countdown"), 10);
        if (isNaN(remaining)) { return; }
        el.setAttribute("data-countdown-bound", "1");
        var windowBox = el.closest("[data-review-window]");
        if (remaining <= 0) {
            renderCountdown(el, 0);
            if (windowBox) { windowBox.classList.add("is-expired"); }
            return;
        }
        renderCountdown(el, remaining);
        activeCountdowns.push({ el: el, remaining: remaining, windowBox: windowBox });
    }

    function scanCountdowns(root) {
        var scope = (root && root.querySelectorAll) ? root : document;
        Array.prototype.forEach.call(scope.querySelectorAll("[data-appeal-countdown]"), bindCountdown);
    }

    function tickCountdowns() {
        scanCountdowns(document);
        activeCountdowns = activeCountdowns.filter(function (c) {
            if (!c.el.isConnected) { return false; }
            c.remaining -= 1;
            if (c.remaining <= 0) {
                renderCountdown(c.el, 0);
                if (c.windowBox) { c.windowBox.classList.add("is-expired"); }
                return false;
            }
            renderCountdown(c.el, c.remaining);
            return true;
        });
    }

    window.setInterval(tickCountdowns, 1000);

    if (window.EMSReady) {
        window.EMSReady(function () { scanCountdowns(document); });
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () { scanCountdowns(document); });
    } else {
        scanCountdowns(document);
    }
})();
