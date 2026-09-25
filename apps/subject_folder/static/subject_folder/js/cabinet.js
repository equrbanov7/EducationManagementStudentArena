/* =========================================================================
   «Fənn qovluğu» kabinet bölmələri — ortaq davranış (müəllim, yoxlama, tələbə).

   NƏ EDİR
   -------
   * `[data-sf-open="<dialogId>"]` → dialoqu açır; formanı sıfırlayır və düymənin
     `data-sf-fill-<ad>` atributları ilə sahələri doldurur (`data-sf-dialog-title`
     başlığı, `data-sf-mode` isə `[data-sf-only]` bloklarını idarə edir);
   * `form[data-sf-form]` → `FormData` (multipart) kimi `subject_folder:action`-a
     göndərir; xəta formanın `[data-ems-form-error]`-ında, uğur toast + bölmənin
     yenidən yüklənməsi (cavab `url` verirsə həmin ünvana keçid);
   * `[data-sf-post="<əməl>"]` → təsdiq (`data-sf-confirm`) + `data-sf-field-<ad>`
     sahələri ilə tək əməl;
   * `select[data-sf-kind]` → material növünə görə `[data-sf-kind-show]` sahələri.

   Server qaydaları (icazə, limitlər) burada TƏKRARLANMIR — hamısı servisdədir.
   AJAX-SAFE: yalnız `EMSDelegate` (sənəd səviyyəli) və idempotent qoruyucu.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSSubjectFolder) {
        return;
    }

    var FILL_PREFIX = "data-sf-fill-";
    var FIELD_PREFIX = "data-sf-field-";

    function rootOf(node) {
        return (node && node.closest && node.closest("[data-sf-root]")) || document.querySelector("[data-sf-root]");
    }

    function text(root, key, fallback) {
        return (root && root.getAttribute("data-i18n-" + key)) || fallback || "";
    }

    function toast(message, level) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, level || "success");
        }
    }

    function csrfToken(scope) {
        var field = scope && scope.querySelector('input[name="csrfmiddlewaretoken"]');
        if (!field) {
            var root = rootOf(scope);
            field = root && root.querySelector('input[name="csrfmiddlewaretoken"]');
        }
        if (field && field.value) {
            return field.value;
        }
        return (window.EMSCore && window.EMSCore.getCsrfToken && window.EMSCore.getCsrfToken()) || "";
    }

    function post(root, body, scope) {
        var url = root && root.getAttribute("data-sf-action-url");
        body.delete("csrfmiddlewaretoken");
        return fetch(url, {
            method: "POST",
            body: body,
            credentials: "same-origin",
            headers: { "X-CSRFToken": csrfToken(scope || root), "X-Requested-With": "XMLHttpRequest" }
        }).then(function (response) {
            return response
                .json()
                .catch(function () {
                    return {};
                })
                .then(function (payload) {
                    return { ok: response.ok && payload.ok !== false, payload: payload || {} };
                });
        });
    }

    function reload(root, url) {
        var section = root && root.getAttribute("data-sf-section");
        var target = url || window.location.href;
        if (section && window.EMSProfileLoadSection) {
            window.EMSProfileLoadSection(section, target);
        } else if (url) {
            window.location.assign(url);
        } else {
            window.location.reload();
        }
    }

    function confirmed(el) {
        var message = el && el.getAttribute("data-sf-confirm");
        if (!message) {
            return Promise.resolve(true);
        }
        if (!window.EMSConfirm || typeof window.EMSConfirm.open !== "function") {
            // Təsdiq dialoqu (`ems_confirm.js`, qlobal) yoxdursa əməl İCRA OLUNMUR — fail-safe.
            return Promise.resolve(false);
        }
        return window.EMSConfirm.open({
            body: message,
            confirmLabel: text(rootOf(el), "yes"),
            danger: el.getAttribute("data-sf-danger") === "1"
        });
    }

    function showError(form, message) {
        var box = form && form.querySelector("[data-ems-form-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        } else if (message) {
            toast(message, "error");
        }
    }

    function afterSuccess(root, payload, origin) {
        var after = origin && origin.getAttribute("data-sf-after");
        var level = payload.level || "success";
        toast(payload.message, level);
        (payload.warnings || []).forEach(function (warning) {
            toast(warning, "warning");
        });
        if (after === "drawer" && window.EMSSubjectFolderReview) {
            window.EMSSubjectFolderReview.reload();
            return;
        }
        var overlay = origin && origin.closest && origin.closest(".ems-overlay");
        if (overlay && window.EMSOverlay) {
            window.EMSOverlay.close(overlay);
        }
        reload(root, payload.url);
    }

    /* ---- Dialoqu doldur ------------------------------------------------- */

    function setField(form, name, value) {
        var field = form.elements.namedItem(name);
        if (!field) {
            return;
        }
        if (field.type === "checkbox") {
            field.checked = value === "1" || value === "true";
        } else if (field.type !== "file") {
            field.value = value;
        }
        if (field.tagName === "SELECT") {
            field.dispatchEvent(new Event("change", { bubbles: true }));
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(field);
            }
        }
    }

    function applyMode(form, mode) {
        form.querySelectorAll("[data-sf-only]").forEach(function (node) {
            node.hidden = Boolean(mode) && node.getAttribute("data-sf-only") !== mode;
        });
    }

    function applyKind(form) {
        var select = form && form.querySelector("select[data-sf-kind]");
        if (!select) {
            return;
        }
        var kind = select.value;
        form.querySelectorAll("[data-sf-kind-show]").forEach(function (node) {
            var kinds = (node.getAttribute("data-sf-kind-show") || "").split(/\s+/);
            node.hidden = kinds.indexOf(kind) === -1;
        });
    }

    window.EMSDelegate.on("click", "[data-sf-open]", function (event, button) {
        event.preventDefault();
        var overlay = document.getElementById(button.getAttribute("data-sf-open"));
        var form = overlay && overlay.querySelector("form");
        if (!overlay || !form) {
            return;
        }
        form.reset();
        showError(form, "");
        Array.prototype.forEach.call(button.attributes, function (attr) {
            if (attr.name.indexOf(FILL_PREFIX) === 0) {
                setField(form, attr.name.slice(FILL_PREFIX.length), attr.value);
            }
        });
        var title = button.getAttribute("data-sf-dialog-title");
        var heading = overlay.querySelector(".ems-dialog__title");
        if (title && heading) {
            heading.textContent = title;
        }
        applyMode(form, button.getAttribute("data-sf-mode") || "");
        applyKind(form);
        if (window.EMSOverlay) {
            window.EMSOverlay.open(overlay);
        }
    });

    window.EMSDelegate.on("change", "select[data-sf-kind]", function (event, select) {
        applyKind(select.form);
    });

    /* ---- Forma göndərişi ------------------------------------------------ */

    window.EMSDelegate.on("submit", "form[data-sf-form]", function (event, form) {
        event.preventDefault();
        var root = rootOf(form);
        var submitter = event.submitter || form.querySelector('[type="submit"]');
        var mode = submitter && submitter.getAttribute("data-sf-answer-mode");
        if (mode) {
            var actionField = form.querySelector("[data-sf-answer-action]");
            if (actionField) {
                actionField.value = mode;
            }
        }
        if (form.hasAttribute("data-sf-bulk") && !form.querySelector("[data-sf-check]:checked")) {
            return;
        }
        confirmed(mode ? submitter : null).then(function (ok) {
            if (!ok) {
                return;
            }
            var buttons = form.querySelectorAll('[type="submit"]');
            buttons.forEach(function (button) {
                button.disabled = true;
            });
            showError(form, "");
            post(root, new FormData(form), form)
                .then(function (result) {
                    if (!result.ok) {
                        showError(form, result.payload.message || text(root, "error"));
                        return;
                    }
                    afterSuccess(root, result.payload, form);
                })
                .catch(function () {
                    showError(form, text(root, "error"));
                })
                .then(function () {
                    buttons.forEach(function (button) {
                        button.disabled = false;
                    });
                });
        });
    });

    /* ---- Tək əməl düymələri --------------------------------------------- */

    window.EMSDelegate.on("click", "[data-sf-post]", function (event, button) {
        event.preventDefault();
        if (button.disabled) {
            return;
        }
        var root = rootOf(button);
        confirmed(button).then(function (ok) {
            if (!ok) {
                return;
            }
            var body = new FormData();
            body.append("action", button.getAttribute("data-sf-post"));
            Array.prototype.forEach.call(button.attributes, function (attr) {
                if (attr.name.indexOf(FIELD_PREFIX) === 0) {
                    body.append(attr.name.slice(FIELD_PREFIX.length), attr.value);
                }
            });
            button.disabled = true;
            post(root, body, button)
                .then(function (result) {
                    if (!result.ok) {
                        toast(result.payload.message || text(root, "error"), "error");
                        return;
                    }
                    afterSuccess(root, result.payload, button);
                })
                .catch(function () {
                    toast(text(root, "error"), "error");
                })
                .then(function () {
                    button.disabled = false;
                });
        });
    });

    window.EMSSubjectFolder = { post: post, reload: reload, toast: toast, rootOf: rootOf, text: text };
})(window, document);
