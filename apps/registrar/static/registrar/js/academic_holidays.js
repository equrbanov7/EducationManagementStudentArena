/* =========================================================================
   «Akademik təqvim» → «Bayram və qeyri-iş günləri» — idarə əməlləri (2026-10-19).

   * `[data-acal-hol-open]` — dialoqu açır, `data-acal-hol-prefill` (JSON) dəyərlərini formaya yazır;
   * `form[data-acal-hol-form]` — formu `[data-acal-hol-root]`-un `data-acal-hol-url`-una göndərir;
   * `[data-acal-hol-delete]` — təsdiqdən sonra silir.
   Uğurda bölmə yenidən yüklənir (server-render), xəta formada / tostda göstərilir.

   AJAX-SAFE: yalnız `EMSDelegate` (sənəd səviyyəli, bir dəfə qeydiyyat — təkrar yükləmədə
   `window.EMSAcademicHolidays` qoruyur); kök yoxdursa heç nə etmir. Dinamik dəyərlər data-atributlardan.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSAcademicHolidays) {
        return;
    }

    function root() {
        return document.querySelector("[data-acal-hol-root]");
    }

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function csrfToken(form) {
        var scope = form || root() || document;
        var field = scope.querySelector('input[name="csrfmiddlewaretoken"]');
        if (!field) {
            field = document.querySelector('input[name="csrfmiddlewaretoken"]');
        }
        if (field && field.value) {
            return field.value;
        }
        return (window.EMSCore && window.EMSCore.getCsrfToken && window.EMSCore.getCsrfToken()) || "";
    }

    function post(payload, form) {
        var host = root();
        var body = new URLSearchParams();
        Object.keys(payload).forEach(function (key) {
            if (payload[key] !== null && payload[key] !== undefined) {
                body.append(key, payload[key]);
            }
        });
        return window.EMSCore.fetchJSON(host.getAttribute("data-acal-hol-url"), {
            method: "POST",
            body: body.toString(),
            headers: {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-CSRFToken": csrfToken(form),
            },
        });
    }

    function reload() {
        var host = root();
        var section = (host && host.getAttribute("data-acal-hol-section")) || "academic-calendar";
        var url = new URL(window.location.href);
        url.searchParams.set("section", section);
        if (window.EMSProfileLoadSection) {
            window.EMSProfileLoadSection(section, url.toString());
        } else {
            window.location.assign(url.toString());
        }
    }

    function errorText(err) {
        var payload = err && err.payload;
        var host = root();
        return (payload && (payload.message || payload.detail)) || (host && host.getAttribute("data-acal-hol-error")) || "";
    }

    function showFormError(form, message, field) {
        var box = form.querySelector("[data-ems-form-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
        var nodes = form.querySelectorAll("[name]");
        for (var i = 0; i < nodes.length; i += 1) {
            nodes[i].setAttribute("aria-invalid", field && nodes[i].name === field ? "true" : "false");
        }
    }

    function fill(form, values) {
        var nodes = form.querySelectorAll("[name]");
        for (var i = 0; i < nodes.length; i += 1) {
            var el = nodes[i];
            if (el.name === "csrfmiddlewaretoken") {
                continue;
            }
            var has = Object.prototype.hasOwnProperty.call(values, el.name);
            if (!has && el.dataset.tofKeep === "1") {
                continue;
            }
            if (!has && el.tagName === "SELECT") {
                continue; // seçicinin server tərəfli defoltu qalır
            }
            el.value = has ? values[el.name] : "";
            if (el.tagName === "SELECT" && window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(el);
            }
        }
    }

    window.EMSDelegate.on("click", "[data-acal-hol-open]", function (event, btn) {
        event.preventDefault();
        var dialog = document.getElementById(btn.getAttribute("data-acal-hol-open"));
        if (!dialog) {
            return;
        }
        var form = dialog.querySelector("form");
        if (form) {
            var values = {};
            try {
                values = JSON.parse(btn.getAttribute("data-acal-hol-prefill") || "{}");
            } catch (err) {
                values = {};
            }
            showFormError(form, "");
            fill(form, values);
            var title = dialog.querySelector(".ems-dialog__title");
            var override = btn.getAttribute("data-acal-hol-title");
            if (title && override) {
                title.textContent = override;
            }
        }
        if (window.EMSOverlay) {
            window.EMSOverlay.open(dialog);
        }
    });

    window.EMSDelegate.on("submit", "form[data-acal-hol-form]", function (event, form) {
        event.preventDefault();
        if (!root()) {
            return;
        }
        var payload = {};
        var nodes = form.querySelectorAll("[name]");
        for (var i = 0; i < nodes.length; i += 1) {
            if (nodes[i].name !== "csrfmiddlewaretoken") {
                payload[nodes[i].name] = nodes[i].value;
            }
        }
        var submit = form.querySelector('[type="submit"]');
        if (submit) {
            submit.disabled = true;
        }
        post(payload, form)
            .then(function (data) {
                if (window.EMSOverlay) {
                    window.EMSOverlay.close(form.closest(".ems-overlay"));
                }
                toast(data && data.message, "success");
                reload();
            })
            .catch(function (err) {
                showFormError(form, errorText(err), err && err.payload && err.payload.field);
            })
            .then(function () {
                if (submit) {
                    submit.disabled = false;
                }
            });
    });

    window.EMSDelegate.on("click", "[data-acal-hol-delete]", function (event, btn) {
        event.preventDefault();
        if (btn.disabled || !root()) {
            return;
        }
        var id = btn.getAttribute("data-acal-hol-delete");
        function proceed() {
            btn.disabled = true;
            post({ action: "delete", id: id }, null)
                .then(function (data) {
                    toast(data && data.message, "success");
                    reload();
                })
                .catch(function (err) {
                    toast(errorText(err), "error");
                    btn.disabled = false;
                });
        }
        var confirmText = btn.getAttribute("data-acal-hol-confirm");
        if (!confirmText || !window.EMSConfirm) {
            proceed();
            return;
        }
        window.EMSConfirm.open({ body: confirmText, danger: true }).then(function (ok) {
            if (ok) {
                proceed();
            }
        });
    });

    window.EMSAcademicHolidays = { post: post, reload: reload };
})(window, document);
