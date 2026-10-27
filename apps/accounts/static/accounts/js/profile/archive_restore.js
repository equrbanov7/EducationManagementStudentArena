/* «Arxivdən çıxar» — səhvən arxivlənmiş (məzun sayılmış) cari tələbənin hesabı (sahib 2026-10-27).
 *
 * Eyni komponent iki yerdədir: RİM mərkəzinin detal kartı və «Parol sıfırlama» nəticəsi. Düymə
 * `[data-archive-restore-open]` (data-user-id / data-name / data-username / data-needs-year / data-source)
 * öz panelindəki `[data-archive-restore]` dialoqunu (`_reason_dialog.html`, `EMSOverlay`) açır; forma
 * POST {user_id, reason, admission_year} göndərir. Nəticə `document`-ə hadisə kimi yayılır ki, hər səth öz
 * siyahısını yeniləsin:
 *   ems:archive-restore:open   {source, userId}
 *   ems:archive-restore:done   {source, userId, payload}
 *   ems:archive-restore:closed {source, userId, done}
 *
 * AJAX-SAFE: hadisələr `EMSDelegate.on` ilə bir dəfə bağlanır; fayl təkrar yüklənsə bayraqla çıxır. Endpoint
 * və mətnlər `data-*`-dadır; dinamik məzmun yalnız `textContent` / `value` ilə yazılır.
 */
(function (window, document) {
    "use strict";

    if (window.EMSArchiveRestore || !window.EMSDelegate || !window.EMSReady) {
        return;
    }

    var pending = null;

    function format(template, values) {
        return String(template || "").replace(/\{(\w+)\}/g, function (match, key) {
            return Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match;
        });
    }

    function emit(name, detail) {
        document.dispatchEvent(new CustomEvent(name, { detail: detail }));
    }

    function wrapperFor(node) {
        var panel = node.closest("[data-profile-section-panel]");
        return (panel || document).querySelector("[data-archive-restore]");
    }

    function showError(box, message) {
        var node = box && box.querySelector("[data-ems-form-error]");
        if (node) {
            node.textContent = message || "";
            node.hidden = !message;
        }
    }

    function sync(box) {
        if (box && window.EMSOverlay && typeof window.EMSOverlay.syncReason === "function") {
            window.EMSOverlay.syncReason(box);
        }
    }

    function errorText(error, fallback) {
        var payload = error && error.payload;
        if (payload && typeof payload === "object" && payload.message) {
            return payload.message;
        }
        return fallback;
    }

    window.EMSDelegate.on("click", "[data-archive-restore-open]", function (event, button) {
        event.preventDefault();
        var wrapper = wrapperFor(button);
        var box = wrapper && wrapper.querySelector(".ems-overlay");
        if (!box || button.disabled || !window.EMSOverlay) {
            return;
        }
        var userId = button.getAttribute("data-user-id") || "";
        var body = box.querySelector("[data-archive-restore-body]");
        if (body) {
            body.textContent = format(wrapper.getAttribute("data-text-body"), {
                name: button.getAttribute("data-name") || "",
                username: button.getAttribute("data-username") || ""
            });
        }
        var userField = box.querySelector("[data-archive-restore-user]");
        if (userField) {
            userField.value = userId;
        }
        var yearWrap = box.querySelector("[data-archive-restore-year-field]");
        var yearField = box.querySelector("[data-archive-restore-year]");
        if (yearWrap) {
            yearWrap.hidden = button.getAttribute("data-needs-year") !== "1";
        }
        if (yearField) {
            yearField.value = "";
        }
        var reason = box.querySelector("[data-ems-reason-field]");
        if (reason) {
            reason.value = "";
        }
        showError(box, "");
        pending = { source: button.getAttribute("data-source") || "", userId: userId, done: false };
        emit("ems:archive-restore:open", { source: pending.source, userId: userId });
        window.EMSOverlay.open(box);
        sync(box);
    });

    window.EMSDelegate.on("submit", "[data-archive-restore-form]", function (event, form) {
        event.preventDefault();
        var wrapper = form.closest("[data-archive-restore]");
        var box = form.closest(".ems-overlay");
        var userField = form.querySelector("[data-archive-restore-user]");
        if (!wrapper || !box || !userField || !userField.value) {
            return;
        }
        var reasonField = form.querySelector("[data-ems-reason-field]");
        var reason = reasonField ? (reasonField.value || "").trim() : "";
        var reasonBox = form.querySelector(".ems-reason");
        var minimum = Number(reasonBox ? reasonBox.getAttribute("data-ems-min-length") : 0) || 0;
        if (reason.length < minimum) {
            showError(box, wrapper.getAttribute("data-text-reason-required"));
            return;
        }
        var yearWrap = form.querySelector("[data-archive-restore-year-field]");
        var yearField = form.querySelector("[data-archive-restore-year]");
        var year = yearWrap && !yearWrap.hidden && yearField ? (yearField.value || "").trim() : "";
        var minYear = Number(wrapper.getAttribute("data-min-year")) || 2000;
        var maxYear = Number(wrapper.getAttribute("data-max-year")) || 2100;
        if (year && (!/^\d{4}$/.test(year) || Number(year) < minYear || Number(year) > maxYear)) {
            showError(box, wrapper.getAttribute("data-text-year-invalid"));
            return;
        }
        var submit = form.querySelector("[data-ems-reason-submit]");
        if (submit) {
            submit.disabled = true;
        }
        showError(box, "");
        var state = pending;
        window.EMSCore.fetchJSON(wrapper.getAttribute("data-url"), {
            method: "POST",
            data: { user_id: userField.value, reason: reason, admission_year: year }
        })
            .then(function (payload) {
                if (state) {
                    state.done = true;
                }
                emit("ems:archive-restore:done", {
                    source: state ? state.source : "",
                    userId: userField.value,
                    payload: payload
                });
                if (window.EMSToast && typeof window.EMSToast.show === "function" && payload && payload.message) {
                    window.EMSToast.show(payload.message, "success");
                }
                window.EMSOverlay.close(box);
            })
            .catch(function (error) {
                showError(box, errorText(error, wrapper.getAttribute("data-text-error")));
            })
            .then(function () {
                sync(box);
            });
    });

    window.EMSReady.once("archive-restore-overlay-close", function () {
        document.addEventListener("ems:overlay:close", function (event) {
            var target = event.target;
            if (!pending || !target || !target.closest || !target.closest("[data-archive-restore]")) {
                return;
            }
            var state = pending;
            pending = null;
            emit("ems:archive-restore:closed", { source: state.source, userId: state.userId, done: state.done });
        });
    });

    window.EMSArchiveRestore = { loaded: true };
})(window, document);
