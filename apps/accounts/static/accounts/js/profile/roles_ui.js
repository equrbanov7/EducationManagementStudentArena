/* =========================================================================
   Rol / icazə kabinet bölmələri — «Rol təyin et» və «Rolları idarə et»
   davranışı (2026-09-09).

   NƏ EDİR
   -------
   * `[data-roles-open]` — sətirdəki dəyərləri (`data-roles-prefill` JSON)
     dialoq formasına köçürüb dialoqu açır («Rol ver», «Rolu geri al»);
   * «Rolu yenilə» / «Təşkilata əlavə et» — təsdiq dialoqunu doldurur, sonra
     serverin imzalı ƏMƏLİYYAT TOKENİ ilə (prepare → submit) göndərir.

   NƏ ETMİR
   --------
   Dialoqun fokus tələsi, Escape, scrim — ORTAQ `ems_ui/overlay.js`-dədir.
   Filtr panelinin draft↔applied məntiqi `ems_ui/filter_bar.js`-dədir.
   Rol vermə/geri alma formaları ADİ POST-dur (server yönləndirir) — burada
   JSON göndəriş yoxdur.

   AJAX-SAFE: yalnız `EMSDelegate` (sənəd səviyyəli). Seçicilər bu üç bölməyə
   MƏXSUSDUR — `EMSDelegate` eyni «hadisə|seçici» açarını ikinci faylda əvəz
   edir (bax `apps/accounts/tests/test_static_js_delegate_keys.py`).
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSRolesUI) {
        return;
    }

    var pending = null;
    var inFlight = false;

    function root() {
        return document.querySelector('[data-roles-root][data-roles-section="role-assignment"]');
    }

    function text(value) {
        return (value || "").toString().trim();
    }

    function t(host, name) {
        return host ? text(host.getAttribute("data-t-" + name)) : "";
    }

    function csrf() {
        var field = document.querySelector('#roleAssignmentActionForm input[name="csrfmiddlewaretoken"]');
        if (!field) {
            field = document.querySelector('input[name="csrfmiddlewaretoken"]');
        }
        if (field && field.value) {
            return field.value;
        }
        return (window.EMSCore && window.EMSCore.getCsrfToken && window.EMSCore.getCsrfToken()) || "";
    }

    function setText(id, value) {
        var node = document.getElementById(id);
        if (node) {
            node.textContent = value || "";
        }
    }

    function showError(dialog, message) {
        if (!dialog) {
            return;
        }
        var box = dialog.querySelector("[data-roles-confirm-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
    }

    /* ---- 1. Dialoq açılışı + prefill ------------------------------------ */

    window.EMSDelegate.on("click", "[data-roles-open]", function (event, btn) {
        event.preventDefault();
        var dialog = document.getElementById(btn.getAttribute("data-roles-open"));
        if (!dialog) {
            return;
        }
        var values = {};
        var raw = btn.getAttribute("data-roles-prefill");
        if (raw) {
            try {
                values = JSON.parse(raw);
            } catch (err) {
                values = {};
            }
        }
        var form = dialog.querySelector("form");
        if (form) {
            var errorBox = form.querySelector("[data-ems-form-error]");
            if (errorBox) {
                errorBox.hidden = true;
                errorBox.textContent = "";
            }
            var nodes = form.querySelectorAll("[name]");
            for (var i = 0; i < nodes.length; i += 1) {
                var field = nodes[i];
                if (field.name === "csrfmiddlewaretoken") {
                    continue;
                }
                var has = Object.prototype.hasOwnProperty.call(values, field.name);
                // Gizli sahələr (əməl adı, `next`) yalnız AÇIQ göstərildikdə
                // dəyişir — sabit dəyərləri şablon verir.
                if (!has && field.type === "hidden") {
                    continue;
                }
                field.value = has ? values[field.name] : "";
                if (window.EMSBootstrapSelect && field.tagName === "SELECT") {
                    window.EMSBootstrapSelect.sync(field);
                }
            }
        }
        var person = dialog.querySelector("[data-roles-target-person]");
        if (person) {
            person.textContent = text(btn.getAttribute("data-roles-person"));
        }
        var role = dialog.querySelector("[data-roles-target-role]");
        if (role) {
            role.textContent = text(btn.getAttribute("data-roles-role"));
        }
        if (window.EMSOverlay) {
            window.EMSOverlay.open(dialog);
        }
    });

    /* ---- 2. «Rol təyin et» təsdiqi -------------------------------------- */

    function selectedRole(button) {
        var row = button.closest("tr");
        var select = row ? row.querySelector("[data-role-assignment-role-select]") : null;
        if (!select) {
            return { id: "", label: "" };
        }
        var option = select.options[select.selectedIndex];
        return { id: text(select.value), label: text(option ? option.textContent : "") };
    }

    function buildOperation(button) {
        var role = selectedRole(button);
        var username = text(button.getAttribute("data-user-username"));
        var operation = {
            button: button,
            action: text(button.getAttribute("data-target-action")),
            membershipId: text(button.getAttribute("data-target-membership-id")),
            userId: text(button.getAttribute("data-target-user-id")),
            roleId: role.id,
            roleLabel: role.label,
            fullName: text(button.getAttribute("data-user-full-name")),
            username: username ? "@" + username.replace(/^@/, "") : "",
            email: text(button.getAttribute("data-user-email")),
            organization: text(button.getAttribute("data-organization-name")),
            oldRole: text(button.getAttribute("data-old-role"))
        };
        operation.isValid = Boolean(
            operation.action &&
                operation.roleId &&
                ((operation.action === "update_member" && operation.membershipId) ||
                    (operation.action === "attach_user" && operation.userId))
        );
        return operation;
    }

    function paint(operation) {
        var host = root();
        var dialog = document.getElementById("roleAssignmentActionConfirmModal");
        setText(
            "roleAssignmentConfirmLeadText",
            operation.action === "attach_user" ? t(host, "attach") : t(host, "update")
        );
        setText("roleAssignmentConfirmFullName", operation.fullName);
        setText("roleAssignmentConfirmUsername", operation.username);
        setText("roleAssignmentConfirmEmail", operation.email);
        setText("roleAssignmentConfirmOrg", operation.organization);
        setText("roleAssignmentConfirmOldRole", operation.oldRole);
        setText("roleAssignmentConfirmRole", operation.roleLabel);
        var submit = document.getElementById("roleAssignmentConfirmSubmitBtn");
        if (submit) {
            submit.disabled = inFlight || !operation.isValid;
        }
        showError(dialog, "");
        return dialog;
    }

    window.EMSDelegate.on("click", ".js-role-assignment-action-confirm", function (event, btn) {
        event.preventDefault();
        if (btn.disabled) {
            return;
        }
        pending = buildOperation(btn);
        var dialog = paint(pending);
        if (dialog && window.EMSOverlay) {
            window.EMSOverlay.open(dialog);
        }
    });

    window.EMSDelegate.on("change", "[data-role-assignment-role-select]", function (event, select) {
        if (!pending || !pending.button) {
            return;
        }
        var row = select.closest("tr");
        if (!row || row !== pending.button.closest("tr")) {
            return;
        }
        pending = buildOperation(pending.button);
        paint(pending);
    });

    /* ---- 3. Göndəriş: prepare_operation → imzalı token → əsl POST ------- */

    function post(url, payload) {
        var body = new URLSearchParams();
        Object.keys(payload).forEach(function (key) {
            if (payload[key] !== "" && payload[key] !== null && payload[key] !== undefined) {
                body.set(key, payload[key]);
            }
        });
        var token = csrf();
        body.set("csrfmiddlewaretoken", token);
        return window
            .fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-CSRFToken": token
                },
                body: body.toString()
            })
            .then(function (response) {
                return response
                    .json()
                    .catch(function () {
                        return {};
                    })
                    .then(function (data) {
                        return { ok: response.ok, data: data || {} };
                    });
            });
    }

    window.EMSDelegate.on("click", "#roleAssignmentConfirmSubmitBtn", function (event, btn) {
        event.preventDefault();
        if (!pending || !pending.isValid || inFlight) {
            return;
        }
        var host = root();
        if (!host) {
            return;
        }
        var url = host.getAttribute("data-roles-action-url");
        var nextUrl = host.getAttribute("data-roles-next");
        var dialog = document.getElementById("roleAssignmentActionConfirmModal");
        var operation = pending;
        var label = btn.textContent;
        inFlight = true;
        btn.disabled = true;
        btn.textContent = t(host, "working") || label;

        post(url, {
            action: "prepare_operation",
            target_action: operation.action,
            new_role_id: operation.roleId,
            membership_id: operation.membershipId,
            user_id: operation.userId
        })
            .then(function (prepared) {
                if (!prepared.ok || !prepared.data.success || !prepared.data.operation_token) {
                    throw new Error(prepared.data.message || t(host, "error"));
                }
                return post(url, {
                    action: operation.action,
                    membership_id: operation.membershipId,
                    user_id: operation.userId,
                    role_id: operation.roleId,
                    operation_token: prepared.data.operation_token,
                    next: nextUrl
                });
            })
            .then(function (result) {
                if (!result.ok || !result.data.success) {
                    throw new Error(result.data.message || t(host, "error"));
                }
                if (window.EMSOverlay) {
                    window.EMSOverlay.close(dialog);
                }
                var target = result.data.redirect_url || nextUrl;
                // Bölmə AJAX-safe siyahısındadırsa panel yerində yenilənir;
                // deyilsə (və ya swap alınmasa) tam naviqasiyaya düşürük —
                // əks halda əməl uğurlu olsa da ekran köhnə qalırdı.
                if (!window.EMSProfileLoadSection) {
                    window.location.assign(target);
                    return;
                }
                Promise.resolve(window.EMSProfileLoadSection("role-assignment", target)).then(function (ok) {
                    if (!ok) {
                        window.location.assign(target);
                    }
                });
            })
            .catch(function (error) {
                showError(dialog, (error && error.message) || t(host, "error"));
            })
            .then(function () {
                inFlight = false;
                btn.disabled = false;
                btn.textContent = t(host, "confirm") || label;
            });
    });

    window.EMSRolesUI = { version: "2026-09-09" };
})(window, document);
