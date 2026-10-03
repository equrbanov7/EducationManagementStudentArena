/* «Tələbə reyestri» kartı → HESAB bloku (sahib 2026-10-03): vəziyyət, dayandırma səbəbi, «kimə yaxınlaşmalı»,
 * «Hesabı dayandır» (səbəb seçimi dialoqu) və «Blokdan çıxar». Göndəriş kataloqun endpoint-inədir
 * (`accounts:people_action`, scope + icazə + audit serverdə). Kart məlumatı `sr:card` hadisəsi ilə gəlir.
 */
(function () {
    "use strict";

    if (window.EMSRegistryAccount) {
        return;
    }
    window.EMSRegistryAccount = true;

    var current = null;

    function root() {
        return document.querySelector("[data-sr-root]");
    }

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function statusText(status) {
        var box = document.querySelector("[data-sr-account]");
        var key = "data-label-" + status;
        return (box && box.getAttribute(key)) || status;
    }

    function render(payload) {
        var box = document.querySelector("[data-sr-account]");
        if (!box) {
            return;
        }
        var account = payload && payload.account;
        current = account ? { account: account, name: payload.name || "" } : null;
        box.hidden = !account;
        if (!account) {
            return;
        }
        var status = box.querySelector("[data-sr-account-status]");
        if (status) {
            status.textContent = statusText(account.status);
            status.setAttribute("data-status", account.status);
        }
        var facts = box.querySelector("[data-sr-account-facts]");
        if (facts) {
            facts.hidden = account.status !== "blocked";
            ["reason", "contact", "note", "blocked_at"].forEach(function (key) {
                var node = facts.querySelector('[data-sr-account-field="' + key + '"]');
                if (node) {
                    node.textContent = account[key] || "—";
                }
            });
        }
        var canBlock = !!payload.can_block;
        var block = box.querySelector("[data-sr-account-block]");
        var unblock = box.querySelector("[data-sr-account-unblock]");
        if (block) {
            block.hidden = !(canBlock && account.status === "active" && document.querySelector("[data-sr-block-dialog]"));
        }
        if (unblock) {
            unblock.hidden = !(canBlock && account.status === "blocked");
        }
    }

    function post(body) {
        var host = root();
        var url = host ? host.getAttribute("data-sr-people-action-url") : "";
        if (!url || !window.EMSCore) {
            return Promise.reject(new Error("no_url"));
        }
        return window.EMSCore.fetchJSON(url, { method: "POST", data: body });
    }

    function applyResult(status, extra) {
        if (!current) {
            return;
        }
        var account = current.account;
        account.status = status;
        ["reason", "contact", "note", "blocked_at"].forEach(function (key) {
            account[key] = extra && extra[key] ? extra[key] : "";
        });
        render({ account: account, name: current.name, can_block: true });
    }

    function today() {
        var now = new Date();
        var pad = function (n) {
            return (n < 10 ? "0" : "") + n;
        };
        return pad(now.getDate()) + "." + pad(now.getMonth() + 1) + "." + now.getFullYear();
    }

    function errorMessage(err) {
        return (err && err.payload && err.payload.message) || (err && err.message) || "";
    }

    document.addEventListener("sr:card", function (event) {
        render(event.detail);
    });

    document.addEventListener("click", function (event) {
        var blockBtn = event.target.closest ? event.target.closest("[data-sr-account-block]") : null;
        if (blockBtn && current) {
            var dialog = document.querySelector("[data-sr-block-dialog]");
            if (!dialog) {
                return;
            }
            var fields = dialog.querySelector("[data-block-fields]");
            if (window.EMSBlockFields) {
                window.EMSBlockFields.show(fields, true);
                window.EMSBlockFields.reset(fields);
            }
            var target = dialog.querySelector("[data-sr-block-target]");
            if (target) {
                target.textContent = current.name;
            }
            var error = dialog.querySelector("[data-sr-block-error]");
            if (error) {
                error.hidden = true;
            }
            if (window.EMSOverlay && typeof window.EMSOverlay.open === "function") {
                window.EMSOverlay.open(dialog);
            } else {
                dialog.hidden = false;
            }
            return;
        }
        var unblockBtn = event.target.closest ? event.target.closest("[data-sr-account-unblock]") : null;
        if (unblockBtn && current) {
            var ask = window.EMSConfirm && typeof window.EMSConfirm.open === "function"
                ? window.EMSConfirm.open({ body: unblockBtn.getAttribute("data-confirm") || "" })
                : Promise.resolve(false);
            ask.then(function (ok) {
                if (!ok) {
                    return;
                }
                unblockBtn.disabled = true;
                post({ action: "unblock", user_id: current.account.user_id, reason: "Reyestrdən bərpa" })
                    .then(function () {
                        applyResult("active", null);
                    })
                    .catch(function (err) {
                        toast(errorMessage(err), "error");
                    })
                    .then(function () {
                        unblockBtn.disabled = false;
                    });
            });
        }
    });

    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.matches || !form.matches("[data-sr-block-form]") || !current) {
            return;
        }
        event.preventDefault();
        var dialog = form.closest("[data-sr-block-dialog]");
        var fields = form.querySelector("[data-block-fields]");
        var error = form.querySelector("[data-sr-block-error]");
        var picked = window.EMSBlockFields ? window.EMSBlockFields.read(fields) : { error: "" };
        if (picked.error !== undefined) {
            if (error) {
                error.textContent = picked.error;
                error.hidden = !picked.error;
            }
            return;
        }
        var body = { action: "block", user_id: current.account.user_id };
        Object.keys(picked.payload).forEach(function (key) {
            body[key] = picked.payload[key];
        });
        var submit = form.querySelector("[data-sr-block-submit]");
        if (submit) {
            submit.disabled = true;
        }
        post(body)
            .then(function (data) {
                var result = (data && data.result) || {};
                var reason = form.querySelector("[data-block-reason]");
                var contact = form.querySelector("[data-block-contact]");
                applyResult("blocked", {
                    reason: reason ? reason.options[reason.selectedIndex].text : "",
                    contact: contact ? contact.options[contact.selectedIndex].text : "",
                    note: result.contact_note || "",
                    blocked_at: today(),
                });
                if (window.EMSOverlay && typeof window.EMSOverlay.close === "function") {
                    window.EMSOverlay.close(dialog);
                } else if (dialog) {
                    dialog.hidden = true;
                }
            })
            .catch(function (err) {
                if (error) {
                    error.textContent = errorMessage(err);
                    error.hidden = false;
                }
            })
            .then(function () {
                if (submit) {
                    submit.disabled = false;
                }
            });
    });
})();
