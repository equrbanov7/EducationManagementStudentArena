/* «25% və alt qrup» — tələbə paneli (`my-retakes`) və heyət növbəsi (`retake-desk`), sahib 2026-10-18.
 * Şablonlar: registrar/retake/*.html. AJAX-safe: dinləyicilər `document`-də BİR dəfə (window bayrağı);
 * yazılar `EMSCore.fetchJSON` (FormData → CSRF başlığı avtomatik), uğurdan sonra bölmə yerində yenilənir.
 * Dialoqlar `ems_ui/overlay.js`-dədir (`data-ems-overlay-open`); bu fayl yalnız formanı doldurur və göndərir.
 */
(function (window, document) {
    "use strict";

    if (window.EMSRetake) {
        return;
    }
    window.EMSRetake = true;

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function rootOf(node) {
        return node && node.closest ? node.closest("[data-rt-root]") : null;
    }

    /* Yeniləmədən sonra eyni tab açıq qalsın (məs. «Müraciətlərim»), birinciyə atılmasın. */
    var pendingTab = "";
    window.EMSReady(function () {
        if (!pendingTab) {
            return;
        }
        var key = pendingTab;
        pendingTab = "";
        window.setTimeout(function () {
            var button = document.querySelector('[data-rt-root] [data-ems-tab="' + key + '"]');
            if (button) {
                button.click();
            }
        }, 0);
    });

    function reload(root) {
        var current = root ? root.querySelector('[data-ems-tab][aria-current="page"]') : null;
        pendingTab = current ? current.getAttribute("data-ems-tab") : "";
        var section = root ? root.getAttribute("data-rt-section") : "";
        var current = window.location.pathname + window.location.search;
        var panel = root ? root.closest("[data-profile-section-panel]") : null;
        var url = current.indexOf("section=" + section) !== -1 ? current : panel && panel.getAttribute("data-source-url");
        if (window.EMSProfileLoadSection && section && url) {
            window.EMSProfileLoadSection(section, url);
        } else {
            window.location.reload();
        }
    }

    function showError(form, message) {
        var box = form.querySelector("[data-ems-form-error], [data-rt-error]");
        if (box) {
            box.textContent = message;
            box.hidden = !message;
        } else if (message) {
            toast(message, "error");
        }
    }

    function setText(dialog, key, value) {
        dialog.querySelectorAll('[data-rt-text="' + key + '"]').forEach(function (node) {
            node.textContent = value || "";
        });
    }

    function setHidden(form, name, value) {
        var field = form.querySelector('input[type="hidden"][name="' + name + '"]');
        if (!field) {
            field = document.createElement("input");
            field.type = "hidden";
            field.name = name;
            form.appendChild(field);
        }
        field.value = value || "";
    }

    function resetForm(form) {
        form.reset();
        showError(form, "");
        if (window.EMSOverlay && typeof window.EMSOverlay.syncReason === "function") {
            window.EMSOverlay.syncReason(form);
        }
    }

    /* ── Tələbə: müraciət dialoqu ───────────────────────────────────────── */
    document.addEventListener("click", function (event) {
        var trigger = event.target.closest ? event.target.closest("[data-rt-apply]") : null;
        if (!trigger) {
            return;
        }
        var dialog = document.getElementById("rtApplyDialog");
        var form = dialog ? dialog.querySelector("form") : null;
        if (!form) {
            return;
        }
        resetForm(form);
        var kind = trigger.getAttribute("data-rt-kind");
        form.querySelector('[data-rt-field="enrollment"]').value = trigger.getAttribute("data-rt-enrollment") || "";
        form.querySelector('[data-rt-field="kind"]').value = kind;
        setText(dialog, "subject", trigger.getAttribute("data-rt-subject"));
        dialog.querySelectorAll("[data-rt-kind-note], [data-rt-kind-only]").forEach(function (node) {
            var match = node.getAttribute("data-rt-kind-note") || node.getAttribute("data-rt-kind-only");
            node.hidden = match !== kind;
        });
    });

    /* ── Tələbə: geri götürmə dialoqu ───────────────────────────────────── */
    document.addEventListener("click", function (event) {
        var trigger = event.target.closest ? event.target.closest("[data-rt-withdraw]") : null;
        if (!trigger) {
            return;
        }
        var dialog = document.getElementById("rtWithdrawDialog");
        var form = dialog ? dialog.querySelector("form") : null;
        if (!form) {
            return;
        }
        resetForm(form);
        form.setAttribute("action", trigger.getAttribute("data-rt-url") || "");
        setText(dialog, "subject", trigger.getAttribute("data-rt-subject"));
    });

    /* ── Heyət: əməl dialoqları ─────────────────────────────────────────── */
    function loadOfferings(select, url) {
        if (!select || !url) {
            return;
        }
        while (select.options.length > 1) {
            select.remove(1);
        }
        window.EMSCore.fetchJSON(url)
            .then(function (payload) {
                (payload && payload.results ? payload.results : []).forEach(function (row) {
                    var option = document.createElement("option");
                    option.value = row.id;
                    option.textContent = row.text;
                    select.appendChild(option);
                });
                if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
                    window.EMSBootstrapSelect.refresh(select);
                }
            })
            .catch(function () {
                toast(select.getAttribute("data-rt-load-error") || "", "error");
            });
    }

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest ? event.target.closest("[data-rt-open]") : null;
        if (!trigger) {
            return;
        }
        var dialog = document.getElementById(trigger.getAttribute("data-ems-overlay-open"));
        var form = dialog ? dialog.querySelector("form") : null;
        if (!form) {
            return;
        }
        resetForm(form);
        form.setAttribute("action", trigger.getAttribute("data-rt-url") || "");
        setHidden(form, "action", trigger.getAttribute("data-rt-action"));
        var box = trigger.closest("[data-rt-subject]");
        var who = box ? [box.getAttribute("data-rt-student"), box.getAttribute("data-rt-subject")].filter(Boolean).join(" · ") : "";
        setText(dialog, "who", who);
        var select = form.querySelector("[data-rt-offerings-select]");
        if (select) {
            var placing = trigger.getAttribute("data-rt-action") === "place";
            var optional = form.querySelector("[data-rt-offering-opt]");
            if (optional) {
                optional.hidden = placing;
            }
            loadOfferings(select, trigger.getAttribute("data-rt-offerings"));
        }
    });

    /* ── Bütün POST formaları (panelin içində) ──────────────────────────── */
    document.addEventListener("submit", function (event) {
        var form = event.target;
        var root = rootOf(form);
        if (!root || (form.getAttribute("method") || "get").toLowerCase() !== "post") {
            return;
        }
        event.preventDefault();
        var url = form.getAttribute("action");
        if (!url) {
            return;
        }
        var submit = form.querySelector('[type="submit"]');
        if (submit) {
            submit.disabled = true;
        }
        showError(form, "");
        window.EMSCore.fetchJSON(url, { method: "POST", body: new FormData(form) })
            .then(function (payload) {
                toast(payload && payload.message, "success");
                var overlay = form.closest(".ems-overlay");
                if (overlay && window.EMSOverlay) {
                    window.EMSOverlay.close(overlay);
                }
                reload(root);
            })
            .catch(function (error) {
                var payload = error && error.payload;
                var structured = payload && typeof payload === "object";
                var message = (structured && (payload.error || payload.detail)) || root.getAttribute("data-rt-error-generic") || "";
                showError(form, message);
            })
            .finally(function () {
                if (submit) {
                    submit.disabled = false;
                }
            });
    });

    /* ── Növbə filtri: select dəyişəndə / axtarış yazılanda avtomatik tətbiq ─ */
    var searchTimer = null;
    document.addEventListener("change", function (event) {
        var field = event.target;
        if (field && field.matches && field.matches("[data-rt-auto-field]") && field.form) {
            field.form.requestSubmit();
        }
    });
    document.addEventListener("input", function (event) {
        var field = event.target;
        if (!field || !field.matches || !field.matches("[data-rt-auto-search]") || !field.form) {
            return;
        }
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(function () {
            field.form.setAttribute("data-ems-quiet-submit", "1");
            field.form.requestSubmit();
        }, 400);
    });
})(window, document);
