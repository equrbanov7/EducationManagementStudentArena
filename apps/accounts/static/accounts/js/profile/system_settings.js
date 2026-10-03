/* «Sistem tənzimləmələri» (sahib 2026-10-03) — şablon: sections/_system_settings.html.
 * AJAX-safe: hadisələr sənəd səviyyəsində bir dəfə qeyd olunur (bölmə swap olunsa da təkrarlanmır).
 * «Yadda saxla» → JSON POST (EMSCore.fetchJSON); sahə xətaları sətrin altında; uğurda bölmə yenilənir.
 * «Standarta qaytar» sahəni defolta qaytarır (yadda saxlayanda sətir bazadan silinir).
 */
(function () {
    "use strict";

    if (window.EMSSystemSettings) {
        return;
    }
    window.EMSSystemSettings = true;

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function setValue(field, value) {
        field.value = value;
        if (field.tagName === "SELECT") {
            field.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }

    function clearErrors(form) {
        form.querySelectorAll("[data-ss-error]").forEach(function (node) {
            node.hidden = true;
            node.textContent = "";
        });
    }

    function showErrors(form, errors) {
        Object.keys(errors || {}).forEach(function (key) {
            var row = form.querySelector('[data-ss-field="' + key + '"]');
            var node = row ? row.querySelector("[data-ss-error]") : null;
            if (node) {
                node.textContent = errors[key];
                node.hidden = false;
            }
        });
    }

    function reload(root) {
        var panel = root.closest("[data-profile-section-panel]");
        var url = panel ? panel.getAttribute("data-source-url") : "";
        if (window.EMSProfileLoadSection && url) {
            window.EMSProfileLoadSection("system-settings", url);
        } else {
            window.location.reload();
        }
    }

    document.addEventListener("click", function (event) {
        var reset = event.target.closest ? event.target.closest("[data-ss-reset]") : null;
        if (!reset) {
            return;
        }
        var row = reset.closest("[data-ss-field]");
        if (!row) {
            return;
        }
        row.querySelectorAll("[data-default]").forEach(function (field) {
            setValue(field, field.getAttribute("data-default"));
        });
    });

    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.matches || !form.matches("[data-ss-form]")) {
            return;
        }
        event.preventDefault();
        var root = form.closest("[data-ss-root]");
        var url = root ? root.getAttribute("data-ss-url") : "";
        if (!url || !window.EMSCore) {
            return;
        }
        var data = {};
        form.querySelectorAll("input[name], select[name]").forEach(function (field) {
            if (field.name !== "csrfmiddlewaretoken") {
                data[field.name] = field.value;
            }
        });
        var submit = form.querySelector("[data-ss-submit]");
        if (submit) {
            submit.disabled = true;
        }
        clearErrors(form);
        window.EMSCore.fetchJSON(url, { method: "POST", data: data })
            .then(function (payload) {
                toast(payload && payload.message, "success");
                reload(root);
            })
            .catch(function (err) {
                var payload = (err && err.payload) || {};
                showErrors(form, payload.errors);
                toast(payload.message || (err && err.message) || "", "error");
            })
            .then(function () {
                if (submit) {
                    submit.disabled = false;
                }
            });
    });
})();
