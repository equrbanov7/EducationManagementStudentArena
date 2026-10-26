/* «Parol sıfırlama» — səbəb dialoqu + birdəfəlik parol dialoqu (sahib 2026-10-26).
 *
 * Əsas fayl (`account_password_reset.js`) axtarışı və nəticə kartlarını qurur və ortaq
 * köməkçiləri `window.EMSPwr`-də açır; bu fayl ondan SONRA yüklənir (hər ikisi `defer`).
 * Axın: «Parolu sıfırla» → `_reason_dialog.html` (səbəb ≥ server həddi, `EMSOverlay`)
 * → POST {user_id, reason} → parol `#pwr-result-dialog`-da BİR DƏFƏ göstərilir.
 *
 * AJAX-SAFE: hadisələr `EMSDelegate.on` / `EMSReady.once` ilə bir dəfə bağlanır; fayl
 * təkrar yüklənsə bayraqla çıxır.
 *
 * TƏHLÜKƏSİZLİK: müvəqqəti parol YALNIZ `[data-pwr-secret]` elementinin mətnində yaşayır —
 * dəyişəndə, storage-da, console-da saxlanılmır; dialoqun bağlanması («Verdim», ×, Escape),
 * 10 dəqiqəlik taymer və səhifədən çıxış onu DOM-dan silir. Mətnlər `textContent` ilə yazılır.
 */
(function (window, document) {
    "use strict";

    if (window.EMSPwrDialogs) {
        return;
    }

    var SECRET_TTL_MS = 10 * 60 * 1000;
    var secretTimer = null;

    function core() {
        return window.EMSPwr || null;
    }

    function strings() {
        return core() ? core().strings() : {};
    }

    function format(template, values) {
        return core() ? core().format(template, values) : String(template || "");
    }

    /* ── Birdəfəlik parol ─────────────────────────────────────────────── */
    function resultDialog() {
        return document.getElementById("pwr-result-dialog");
    }

    function confirmDialog() {
        return document.getElementById("pwr-confirm-dialog");
    }

    function clearSecret() {
        if (secretTimer) {
            window.clearTimeout(secretTimer);
            secretTimer = null;
        }
        var dialog = resultDialog();
        if (!dialog) {
            return;
        }
        var secret = dialog.querySelector("[data-pwr-secret]");
        if (secret) {
            secret.textContent = "";
        }
        var who = dialog.querySelector("[data-pwr-result-who]");
        if (who) {
            who.textContent = "";
        }
        if (!dialog.hidden && window.EMSOverlay) {
            window.EMSOverlay.close(dialog);
        }
    }

    /* Sahib 2026-10-26: parol BİR DƏFƏ, dialoqda (`_dialog.html`, scrim-ə klik bağlamır). */
    function showSecret(person, password) {
        var t = strings();
        var dialog = resultDialog();
        var secret = dialog && dialog.querySelector("[data-pwr-secret]");
        if (!dialog || !secret || !window.EMSOverlay) {
            return;
        }
        secret.textContent = password;
        var who = dialog.querySelector("[data-pwr-result-who]");
        if (who) {
            who.textContent = format(t.resultFor, { name: person.full_name, username: person.username });
        }
        window.EMSOverlay.open(dialog);
        if (secretTimer) {
            window.clearTimeout(secretTimer);
        }
        secretTimer = window.setTimeout(clearSecret, SECRET_TTL_MS);
    }

    /* ── Sıfırlama (səbəb dialoqu → POST → parol dialoqu) ─────────────── */
    var pendingButton = null;

    function setButtonBusy(button, busy) {
        if (!button) {
            return;
        }
        var t = strings();
        var label = button.lastChild;
        button.disabled = busy;
        if (label && label.nodeType === 3) {
            label.textContent = " " + (busy ? t.resetting : t.reset);
        }
    }

    function dialogError(dialog, message) {
        var box = dialog && dialog.querySelector("[data-ems-form-error]");
        if (!box) {
            return;
        }
        box.textContent = message || "";
        box.hidden = !message;
    }

    window.EMSDelegate.on("click", "[data-pwr-reset]", function (event, button) {
        event.preventDefault();
        var person = core() ? core().getPerson(button.getAttribute("data-pwr-reset")) : null;
        var dialog = confirmDialog();
        if (!person || button.disabled || !dialog || !window.EMSOverlay) {
            return;
        }
        var t = strings();
        var body = dialog.querySelector("[data-pwr-confirm-body]");
        if (body) {
            body.textContent = format(t.confirmBody, { name: person.full_name, username: person.username });
        }
        var userField = dialog.querySelector("[data-pwr-confirm-user]");
        if (userField) {
            userField.value = String(person.id);
        }
        var reason = dialog.querySelector("[data-ems-reason-field]");
        if (reason) {
            reason.value = "";
        }
        dialogError(dialog, "");
        pendingButton = button;
        window.EMSOverlay.open(dialog);
    });

    window.EMSDelegate.on("submit", "[data-pwr-reason-form]", function (event, form) {
        event.preventDefault();
        var scope = core() ? core().root() : null;
        var dialog = confirmDialog();
        var t = strings();
        var userField = form.querySelector("[data-pwr-confirm-user]");
        var reasonField = form.querySelector("[data-ems-reason-field]");
        var person = userField && core() ? core().getPerson(userField.value) : null;
        var reason = reasonField ? (reasonField.value || "").trim() : "";
        var reasonBox = form.querySelector(".ems-reason");
        var minimum = Number(reasonBox ? reasonBox.getAttribute("data-ems-min-length") : 0) || 0;
        if (!scope || !person) {
            return;
        }
        if (reason.length < minimum) {
            dialogError(dialog, t.reasonRequired);
            return;
        }
        var submit = form.querySelector("[data-ems-reason-submit]");
        if (submit) {
            submit.disabled = true;
        }
        var button = pendingButton;
        setButtonBusy(button, true);
        window.EMSCore.fetchJSON(scope.getAttribute("data-reset-url"), {
            method: "POST",
            data: { user_id: person.id, reason: reason }
        })
            .then(function (payload) {
                pendingButton = null;
                if (reasonField) {
                    reasonField.value = "";
                }
                window.EMSOverlay.close(dialog);
                var updated = (payload && payload.user) || person;
                core().setPerson(updated);
                var item = button && button.closest(".pwr-person");
                if (item && item.parentNode) {
                    item.parentNode.replaceChild(core().renderPerson(updated, strings()), item);
                }
                showSecret(updated, payload.password);
                core().toast(payload.message, "success");
            })
            .catch(function (error) {
                dialogError(dialog, core() ? core().errorMessage(error, t.genericError) : t.genericError);
                setButtonBusy(button, false);
            })
            .then(function () {
                if (submit && window.EMSOverlay) {
                    window.EMSOverlay.syncReason(dialog);
                }
            });
    });

    /* ── Kopyala / gizlət ─────────────────────────────────────────────── */
    function selectSecret(secret) {
        if (!window.getSelection || !document.createRange) {
            return;
        }
        var range = document.createRange();
        range.selectNodeContents(secret);
        var selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
    }

    window.EMSDelegate.on("click", "[data-pwr-copy]", function (event, button) {
        event.preventDefault();
        var dialog = button.closest("#pwr-result-dialog");
        var secret = dialog && dialog.querySelector("[data-pwr-secret]");
        var t = strings();
        if (!secret || !secret.textContent) {
            return;
        }
        if (window.navigator.clipboard && typeof window.navigator.clipboard.writeText === "function") {
            window.navigator.clipboard.writeText(secret.textContent).then(
                function () {
                    core().toast(t.copied, "success");
                },
                function () {
                    selectSecret(secret);
                    core().toast(t.copyFailed, "warning");
                }
            );
            return;
        }
        selectSecret(secret);
        core().toast(t.copyFailed, "warning");
    });

    window.EMSDelegate.on("click", "[data-pwr-done]", function (event) {
        event.preventDefault();
        clearSecret();
        var scope = core() ? core().root() : null;
        var input = scope && scope.querySelector("[data-pwr-query]");
        if (input) {
            input.value = "";
            input.focus();
        }
    });

    /* Parol dialoqu HƏR yolla (×, Escape, «Verdim») bağlananda parol DOM-dan silinir. */
    window.EMSReady.once("pwr-result-close", function () {
        document.addEventListener("ems:overlay:close", function (event) {
            if (event.target && event.target.id === "pwr-result-dialog") {
                clearSecret();
            }
        });
    });

    window.EMSReady.once("pwr-pagehide", function () {
        window.addEventListener("pagehide", clearSecret);
    });

    window.EMSPwrDialogs = { clearSecret: clearSecret };
})(window, document);
