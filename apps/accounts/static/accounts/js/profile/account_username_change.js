/* «İstifadəçi adını dəyiş» — «Parol sıfırlama» bölməsində (sahib 2026-10-26: «pass bilmədən username dəyişə bilim»).
 *
 * Əsas fayl (`account_password_reset.js`) nəticə kartlarını qurur və ortaq köməkçiləri `window.EMSPwr`-də açır;
 * bu fayl ondan SONRA yüklənir (hər ikisi `defer`). Axın: kartda «İstifadəçi adını dəyiş» → `_reason_dialog.html`
 * (yeni ad + səbəb ≥ server həddi, `EMSOverlay`) → POST {user_id, new_username, reason} → kart yenilənir.
 * «Avtomatik təklif» serverdən boş `ad.soyad` gətirir (YAZMIR). Parol, sessiya və e-poçt təsdiqi toxunulmur.
 *
 * AJAX-SAFE: hadisələr `EMSDelegate.on` ilə bir dəfə bağlanır; fayl təkrar yüklənsə bayraqla çıxır.
 * Endpoint URL-ləri `data-*`, mətnlər `#pwr-strings`-dən; dinamik məzmun yalnız `textContent` / `value` ilə.
 */
(function (window, document) {
    "use strict";

    if (window.EMSPwrRename) {
        return;
    }

    var pendingButton = null;

    function core() {
        return window.EMSPwr || null;
    }

    function strings() {
        return core() ? core().strings() : {};
    }

    function dialog() {
        return document.getElementById("pwr-rename-dialog");
    }

    function sync(box) {
        if (box && window.EMSOverlay && typeof window.EMSOverlay.syncReason === "function") {
            window.EMSOverlay.syncReason(box);
        }
    }

    function showError(box, message) {
        var node = box && box.querySelector("[data-ems-form-error]");
        if (!node) {
            return;
        }
        node.textContent = message || "";
        node.hidden = !message;
    }

    function setBusy(button, busy) {
        if (!button) {
            return;
        }
        var t = strings();
        var label = button.lastChild;
        button.disabled = busy;
        if (label && label.nodeType === 3) {
            label.textContent = " " + (busy ? t.renaming : t.rename);
        }
    }

    function errorText(error) {
        var t = strings();
        return core() ? core().errorMessage(error, t.genericError) : t.genericError;
    }

    window.EMSDelegate.on("click", "[data-pwr-rename]", function (event, button) {
        event.preventDefault();
        var person = core() ? core().getPerson(button.getAttribute("data-pwr-rename")) : null;
        var box = dialog();
        if (!person || button.disabled || !box || !window.EMSOverlay) {
            return;
        }
        var t = strings();
        var body = box.querySelector("[data-pwr-rename-body]");
        if (body) {
            body.textContent = core().format(t.renameBody, { name: person.full_name, username: person.username });
        }
        var userField = box.querySelector("[data-pwr-rename-user]");
        if (userField) {
            userField.value = String(person.id);
        }
        var input = box.querySelector("[data-pwr-rename-input]");
        if (input) {
            input.value = person.username || "";
        }
        var reason = box.querySelector("[data-ems-reason-field]");
        if (reason) {
            reason.value = "";
        }
        showError(box, "");
        pendingButton = button;
        window.EMSOverlay.open(box);
        sync(box);
        if (input) {
            input.focus();
            input.select();
        }
    });

    window.EMSDelegate.on("click", "[data-pwr-rename-suggest]", function (event, button) {
        event.preventDefault();
        var scope = core() ? core().root() : null;
        var box = dialog();
        var userField = box && box.querySelector("[data-pwr-rename-user]");
        var input = box && box.querySelector("[data-pwr-rename-input]");
        if (!scope || !userField || !input || button.disabled) {
            return;
        }
        button.disabled = true;
        showError(box, "");
        window.EMSCore.fetchJSON(scope.getAttribute("data-rename-suggest-url"), {
            method: "POST",
            data: { user_id: userField.value }
        })
            .then(function (payload) {
                input.value = (payload && payload.username) || input.value;
                if (payload && payload.is_current) {
                    showError(box, core().format(strings().suggestCurrent, { username: payload.username }));
                }
                sync(box);
                input.focus();
            })
            .catch(function (error) {
                showError(box, errorText(error));
            })
            .then(function () {
                button.disabled = false;
            });
    });

    window.EMSDelegate.on("submit", "[data-pwr-rename-form]", function (event, form) {
        event.preventDefault();
        var scope = core() ? core().root() : null;
        var box = dialog();
        var t = strings();
        var userField = form.querySelector("[data-pwr-rename-user]");
        var input = form.querySelector("[data-pwr-rename-input]");
        var reasonField = form.querySelector("[data-ems-reason-field]");
        var person = userField && core() ? core().getPerson(userField.value) : null;
        var reason = reasonField ? (reasonField.value || "").trim() : "";
        var reasonBox = form.querySelector(".ems-reason");
        var minimum = Number(reasonBox ? reasonBox.getAttribute("data-ems-min-length") : 0) || 0;
        if (!scope || !person || !input) {
            return;
        }
        if (reason.length < minimum) {
            showError(box, t.reasonRequired);
            return;
        }
        var submit = form.querySelector("[data-ems-reason-submit]");
        if (submit) {
            submit.disabled = true;
        }
        var button = pendingButton;
        setBusy(button, true);
        window.EMSCore.fetchJSON(scope.getAttribute("data-rename-url"), {
            method: "POST",
            data: { user_id: person.id, new_username: (input.value || "").trim(), reason: reason }
        })
            .then(function (payload) {
                pendingButton = null;
                if (reasonField) {
                    reasonField.value = "";
                }
                window.EMSOverlay.close(box);
                var updated = (payload && payload.user) || person;
                core().setPerson(updated);
                var item = button && button.closest(".pwr-person");
                if (item && item.parentNode) {
                    item.parentNode.replaceChild(core().renderPerson(updated, strings()), item);
                }
                var query = scope.querySelector("[data-pwr-query]");
                if (query && payload && query.value.trim().toLowerCase() === String(payload.old_username).toLowerCase()) {
                    query.value = updated.username;
                }
                core().toast(payload.message, "success");
            })
            .catch(function (error) {
                showError(box, errorText(error));
                setBusy(button, false);
            })
            .then(function () {
                sync(box);
            });
    });

    window.EMSPwrRename = { loaded: true };
})(window, document);
