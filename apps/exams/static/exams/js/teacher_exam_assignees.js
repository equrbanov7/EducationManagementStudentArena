/* =========================================================================
   «Tapşırıq təyin olunmuşlar» — qrup / tələbə əlavə et, çıxar, istisna et (sahib 2026-10-27).

   Bütün dəyərlər `[data-eas-root]` data-atributlarından oxunur (CSP: inline JS yoxdur).
   Əməl POST → `data-update-url` (sehrbazın saxlama qapıları). Server cavabları:
     * 200 {success}                         → səhifə yenilənir (mesaj toast kimi gəlir);
     * 400 {unit_coverage_required: [...]}  → fənnin jurnalında olmayan qrup: səbəb dialoqu → forced_units;
     * 409 {subject_change_required: {...}} → nəticəli midterm: təsdiq + səbəb → subject_change_*;
     * başqa xəta                            → toast.
   AJAX-safe: EMSReady (idempotent init) + EMSDelegate (document-səviyyəli, yığılmır).
   ========================================================================= */
(function (window, document) {
    "use strict";

    var REASON_MIN = 10;
    var pending = null; // səbəb gözləyən əməl: {action, fields, kind, groups}

    function root() {
        return document.querySelector("[data-eas-root]");
    }

    function msg(key) {
        var el = root();
        return (el && el.dataset[key]) || "";
    }

    function toast(text, level) {
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(text, level || "danger");
        }
    }

    function confirmAction(body) {
        if (window.EMSConfirm && typeof window.EMSConfirm.open === "function") {
            return window.EMSConfirm.open({ body: body, danger: true, confirmLabel: msg("msgConfirm") });
        }
        return Promise.resolve(true);
    }

    function picker(selector) {
        var el = document.querySelector(selector);
        return el && el._emsSearchable ? el._emsSearchable : null;
    }

    function send(action, fields, extra) {
        var el = root();
        if (!el || !window.EMSCore) {
            return;
        }
        var body = new FormData();
        body.append("action", action);
        Object.keys(fields).forEach(function (name) {
            [].concat(fields[name]).forEach(function (value) {
                body.append(name, value);
            });
        });
        Object.keys(extra || {}).forEach(function (name) {
            body.append(name, extra[name]);
        });
        window.EMSCore.fetchJSON(el.dataset.updateUrl, { method: "POST", body: body })
            .then(function () {
                window.location.reload();
            })
            .catch(function (err) {
                var payload = (err && err.payload) || {};
                if (payload.unit_coverage_required) {
                    openReason({ action: action, fields: fields, kind: "units", groups: payload.unit_coverage_required }, payload.error);
                    return;
                }
                if (payload.subject_change_required) {
                    openReason({ action: action, fields: fields, kind: "subject", groups: [] }, payload.error);
                    return;
                }
                toast(payload.error || msg("msgError"));
            });
    }

    function groupLine(group) {
        var text = msg("msgUncovered").replace("{n}", group.uncovered).replace("{total}", group.total);
        var names = (group.names || []).join(", ");
        if (group.more) {
            names += (names ? ", " : "") + msg("msgMore").replace("{n}", group.more);
        }
        return group.name + " — " + text + (names ? " (" + names + ")" : "");
    }

    function openReason(state, message) {
        var dialog = document.getElementById("easReasonDialog");
        if (!dialog || !window.EMSOverlay) {
            toast(message || msg("msgError"));
            return;
        }
        pending = state;
        dialog.querySelector("[data-eas-reason-message]").textContent = message || "";
        var list = dialog.querySelector("[data-eas-reason-list]");
        list.textContent = "";
        state.groups.forEach(function (group) {
            var item = document.createElement("li");
            item.textContent = groupLine(group);
            list.appendChild(item);
        });
        dialog.querySelector("[data-eas-reason-confirm-wrap]").hidden = state.kind !== "subject";
        dialog.querySelector("[data-eas-reason-confirm]").checked = false;
        window.EMSOverlay.open("easReasonDialog");
    }

    function submitReason(event) {
        event.preventDefault();
        var dialog = document.getElementById("easReasonDialog");
        if (!dialog || !pending) {
            return;
        }
        var reason = (dialog.querySelector("[data-eas-reason-text]").value || "").trim();
        if (reason.length < REASON_MIN) {
            dialog.querySelector("[data-eas-reason-text]").focus();
            return;
        }
        var extra = {};
        if (pending.kind === "subject") {
            if (!dialog.querySelector("[data-eas-reason-confirm]").checked) {
                dialog.querySelector("[data-eas-reason-confirm]").focus();
                return;
            }
            extra.subject_change_confirm = "1";
            extra.subject_change_reason = reason;
        } else {
            var forced = {};
            pending.groups.forEach(function (group) {
                forced[group.id] = reason;
            });
            extra.forced_units = JSON.stringify(forced);
        }
        var state = pending;
        pending = null;
        window.EMSOverlay.close(dialog);
        send(state.action, state.fields, extra);
    }

    window.EMSReady(function () {
        var el = root();
        if (!el || !el.dataset.canEdit || !window.EMSSearchableSelect) {
            return;
        }
        window.EMSSearchableSelect.create(el.querySelector(".js-eas-unit-picker"), {
            url: el.dataset.groupSearchUrl,
            multi: true,
        });
        window.EMSSearchableSelect.create(el.querySelector(".js-eas-user-picker"), {
            url: el.dataset.userSearchUrl,
            multi: true,
        });
    });

    window.EMSDelegate.on("click", ".js-eas-add-units", function () {
        var pick = picker(".js-eas-unit-picker");
        var ids = pick ? pick.ids() : [];
        if (!ids.length) {
            toast(msg("msgPickGroups"), "warning");
            return;
        }
        send("add_units", { allowed_units: ids });
    });

    window.EMSDelegate.on("click", ".js-eas-add-users", function () {
        var pick = picker(".js-eas-user-picker");
        var ids = pick ? pick.ids() : [];
        if (!ids.length) {
            toast(msg("msgPickUsers"), "warning");
            return;
        }
        send("add_users", { users: ids });
    });

    window.EMSDelegate.on("click", ".js-eas-remove-unit", function (event, button) {
        confirmAction(button.dataset.label + "\n\n" + msg("msgRemoveUnit")).then(function (ok) {
            if (ok) {
                send("remove_unit", { unit: button.dataset.unit });
            }
        });
    });

    var USER_MESSAGES = {
        remove_user: "msgRemoveUser",
        exclude_user: "msgExcludeUser",
        include_user: "msgIncludeUser",
    };

    window.EMSDelegate.on("click", ".js-eas-user-action", function (event, button) {
        var action = button.dataset.action;
        if (!USER_MESSAGES[action]) {
            return;
        }
        confirmAction(button.dataset.name + "\n\n" + msg(USER_MESSAGES[action])).then(function (ok) {
            if (ok) {
                send(action, { user: button.dataset.user });
            }
        });
    });

    window.EMSDelegate.on("submit", ".js-eas-reason-form", submitReason);
})(window, document);
