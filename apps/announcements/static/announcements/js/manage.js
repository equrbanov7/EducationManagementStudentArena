/* Elan formu — rahatlıq qatı (bütün yoxlamalar serverdədir):
 *   * auditoriya bölmələrində axtarış (diakritikaya dözümlü) + seçilmiş say;
 *   * «Kim görəcək: … — təxminən N nəfər» canlı xülasəsi (debounce-lu GET, əhatə serverdə);
 *   * «Müraciət et» rejiminə görə sahələrin göstərilməsi;
 *   * başlıq/xülasə simvol sayğacı (`data-annm-count`);
 *   * məcburi elanın alıcı siyahısı: vəziyyət tabları, axtarış (300 ms debounce), səhifələmə.
 * AJAX-safe: `EMSDelegate` + `EMSReady` (idempotent; qoruyucu bayraq təkrar qeydiyyatı kəsir).
 */
(function () {
    "use strict";

    if (window.__emsAnnouncementsManage) {
        return;
    }
    window.__emsAnnouncementsManage = true;

    function fold(text) {
        return (text || "")
            .toLowerCase()
            .replace(/ə/g, "e").replace(/ı/g, "i").replace(/ö/g, "o").replace(/ü/g, "u")
            .replace(/ğ/g, "g").replace(/ş/g, "s").replace(/ç/g, "c")
            .normalize("NFD").replace(/[̀-ͯ]/g, "");
    }

    function updateCount(root) {
        var counter = root.querySelector("[data-annm-unit-count]");
        if (!counter) { return; }
        var checked = root.querySelectorAll("input[name='audience_units']:checked").length;
        counter.textContent = checked ? (counter.getAttribute("data-label") || "") + ": " + checked : "";
    }

    function updateApplyPanes(root) {
        var selected = root.querySelector("[data-annm-apply-mode]:checked");
        var mode = selected ? selected.value : "none";
        root.querySelectorAll("[data-annm-apply-pane]").forEach(function (pane) {
            var modes = (pane.getAttribute("data-annm-apply-pane") || "").split(" ");
            pane.hidden = modes.indexOf(mode) === -1;
        });
    }

    function updateCounter(input) {
        var max = parseInt(input.getAttribute("data-annm-count"), 10);
        if (!max) { return; }
        var hint = input.parentNode.querySelector(".annm-counter");
        if (!hint) {
            hint = document.createElement("span");
            hint.className = "annm-counter";
            hint.setAttribute("aria-hidden", "true");
            input.parentNode.appendChild(hint);
        }
        hint.textContent = input.value.length + " / " + max;
    }

    var SUMMARY_DEBOUNCE_MS = 350;
    var SEARCH_DEBOUNCE_MS = 300;

    /* ── «Kim görəcək» xülasəsi ─────────────────────────────────────────── */
    function loadSummary(root) {
        var line = root.querySelector("[data-annm-summary]");
        var text = line && line.querySelector("[data-annm-summary-text]");
        var url = line && line.getAttribute("data-url");
        if (!text || !url || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") { return; }
        var data = new URLSearchParams();
        root.querySelectorAll("input[name='audience_families']:checked").forEach(function (box) { data.append("families", box.value); });
        root.querySelectorAll("input[name='audience_units']:checked").forEach(function (box) { data.append("units", box.value); });
        if (root.__annmSummaryCtl) {
            try { root.__annmSummaryCtl.abort(); } catch (e) { /* ignore */ }
        }
        var controller = typeof AbortController === "function" ? new AbortController() : null;
        root.__annmSummaryCtl = controller;
        line.setAttribute("aria-busy", "true");
        window.EMSCore.fetchJSON(url + "?" + data.toString(), { signal: controller ? controller.signal : undefined })
            .then(function (payload) {
                if (root.__annmSummaryCtl !== controller) { return; }
                text.textContent = (payload && payload.text) || "";
                line.classList.toggle("is-warning", Boolean(payload && payload.warning));
            })
            .catch(function (error) {
                if (error && error.name === "AbortError") { return; }
                text.textContent = line.getAttribute("data-msg-error") || "";
                line.classList.add("is-warning");
            })
            .then(function () {
                if (root.__annmSummaryCtl === controller) { line.removeAttribute("aria-busy"); }
            });
    }

    function scheduleSummary(root) {
        window.clearTimeout(root.__annmSummaryTimer);
        root.__annmSummaryTimer = window.setTimeout(function () { loadSummary(root); }, SUMMARY_DEBOUNCE_MS);
    }

    window.EMSDelegate.on("change", "[data-annm-audience] input[name='audience_families'], [data-annm-audience] input[name='audience_units']", function (event, input) {
        var root = input.closest("[data-annm-audience]");
        if (root) { scheduleSummary(root); }
    });

    /* ── Məcburi elanın alıcıları ────────────────────────────────────────── */
    function loadRecipients(root, page) {
        var results = root.querySelector("[data-annm-ack-results]");
        var url = root.getAttribute("data-url");
        var form = root.querySelector("[data-annm-ack-filters]");
        if (!results || !url || !form || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") { return; }
        var status = form.querySelector("[data-annm-ack-status]:checked");
        var search = form.querySelector("[data-annm-ack-search]");
        var data = new URLSearchParams();
        data.set("status", status ? status.value : "pending");
        if (search && search.value.trim()) { data.set("q", search.value.trim()); }
        if (page && page > 1) { data.set("page", String(page)); }
        if (root.__annmAckCtl) {
            try { root.__annmAckCtl.abort(); } catch (e) { /* ignore */ }
        }
        var controller = typeof AbortController === "function" ? new AbortController() : null;
        root.__annmAckCtl = controller;
        results.setAttribute("aria-busy", "true");
        window.EMSCore.fetchJSON(url + "?" + data.toString(), { signal: controller ? controller.signal : undefined })
            .then(function (payload) {
                if (root.__annmAckCtl !== controller) { return; }
                results.innerHTML = payload && payload.html ? payload.html : "";
            })
            .catch(function (error) {
                if (error && error.name === "AbortError") { return; }
                var source = root.querySelector("[data-annm-ack-error]");
                var message = document.createElement("p");
                message.className = "ann-error";
                message.setAttribute("role", "alert");
                message.textContent = source ? source.textContent : "Error";
                results.replaceChildren(message);
            })
            .then(function () {
                if (root.__annmAckCtl === controller) { results.setAttribute("aria-busy", "false"); }
            });
    }

    window.EMSDelegate.on("input", "[data-annm-ack] [data-annm-ack-search]", function (event, input) {
        var root = input.closest("[data-annm-ack]");
        if (!root) { return; }
        window.clearTimeout(root.__annmAckTimer);
        root.__annmAckTimer = window.setTimeout(function () { loadRecipients(root, 1); }, SEARCH_DEBOUNCE_MS);
    });

    window.EMSDelegate.on("change", "[data-annm-ack] [data-annm-ack-status]", function (event, input) {
        var root = input.closest("[data-annm-ack]");
        if (root) { loadRecipients(root, 1); }
    });

    window.EMSDelegate.on("submit", "[data-annm-ack] [data-annm-ack-filters]", function (event, form) {
        event.preventDefault();
        var root = form.closest("[data-annm-ack]");
        if (root) {
            window.clearTimeout(root.__annmAckTimer);
            loadRecipients(root, 1);
        }
    });

    window.EMSDelegate.on("click", "[data-annm-ack] [data-annm-ack-page]", function (event, button) {
        event.preventDefault();
        var root = button.closest("[data-annm-ack]");
        var page = parseInt(button.getAttribute("data-annm-ack-page"), 10);
        if (root && page > 0 && !button.disabled) { loadRecipients(root, page); }
    });

    window.EMSDelegate.on("input", "[data-annm-unit-search]", function (event, input) {
        var root = input.closest("[data-annm-audience]");
        if (!root) { return; }
        var needle = fold(input.value.trim());
        root.querySelectorAll("[data-annm-unit]").forEach(function (row) {
            var checked = row.querySelector("input:checked");
            row.hidden = Boolean(needle) && !checked && fold(row.getAttribute("data-label")).indexOf(needle) === -1;
        });
    });

    window.EMSDelegate.on("change", "[data-annm-audience] input[name='audience_units']", function (event, input) {
        var root = input.closest("[data-annm-audience]");
        if (root) { updateCount(root); }
    });

    window.EMSDelegate.on("change", "[data-annm-apply-mode]", function (event, input) {
        var root = input.closest("[data-annm-apply]");
        if (root) { updateApplyPanes(root); }
    });

    window.EMSDelegate.on("input", "[data-annm-count]", function (event, input) {
        updateCounter(input);
    });

    window.EMSReady(function () {
        document.querySelectorAll("[data-annm-audience]").forEach(function (root) {
            updateCount(root);
            if (!root.__annmSummaryLoaded) {
                root.__annmSummaryLoaded = true;
                loadSummary(root);
            }
        });
        document.querySelectorAll("[data-annm-apply]").forEach(updateApplyPanes);
        document.querySelectorAll("[data-annm-count]").forEach(updateCounter);
    });
})();
