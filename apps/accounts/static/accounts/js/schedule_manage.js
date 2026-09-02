/* «Cədvəl idarəetməsi» bölməsi (schedule-manage) — AJAX-safe panel məntiqi.
 *
 * Panel SERVER-RENDER-lidir: seçicilər dəyişəndə bölmə fraqmenti yenidən
 * yüklənir (window.EMSProfileLoadSection). JS yalnız üç şeyi edir:
 *   1) seçici dəyişikliyində panel URL-ini qurub yenidən yükləmək;
 *   2) SAXLAMADAN ƏVVƏL konflikt yoxlaması (JSON POST → `check_url`);
 *   3) slot əlavəsi / silinməsi (JSON POST → `action_url`) + təsdiq dialoqu.
 *
 * Qaydalar (CLAUDE.md + docs/frontend/AJAX_SAFE_JS_PATTERN.md):
 *   · inline JS yoxdur — dinamik dəyərlər `data-*` atributlarındadır;
 *   · `EMSDelegate.on` ilə document səviyyəsində delegasiya (swap-safe);
 *   · kök element (`[data-smx-root]`) yoxdursa heç nə etmir (null-safe).
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
        return;
    }

    function root() {
        return document.querySelector("[data-smx-root]");
    }

    function texts() {
        var host = root();
        var node = host && host.querySelector("[data-smx-i18n]");
        return node ? node.dataset : {};
    }

    function reload(host, overrides) {
        var base = host.getAttribute("data-reload-url") || "";
        var form = host.querySelector("[data-smx-filters]");
        var params = new URLSearchParams();
        if (form) {
            form.querySelectorAll("[data-smx-reload]").forEach(function (field) {
                if (field.name && field.value) {
                    params.set(field.name, field.value);
                }
            });
        }
        Object.keys(overrides || {}).forEach(function (key) {
            if (overrides[key]) {
                params.set(key, overrides[key]);
            } else {
                params.delete(key);
            }
        });
        var url = base + params.toString();
        if (typeof window.EMSProfileLoadSection === "function") {
            window.EMSProfileLoadSection("schedule-manage", url);
        } else {
            window.location.href = url;
        }
    }

    function formPayload(host) {
        var form = host.querySelector("[data-smx-add]");
        if (!form) {
            return null;
        }
        var payload = {};
        ["offering_id", "slot_kind", "weekday", "time_slot", "start_time", "end_time", "room", "week_type"].forEach(
            function (name) {
                var field = form.querySelector('[name="' + name + '"]');
                payload[name] = field ? field.value : "";
            }
        );
        return payload;
    }

    function showError(host, message) {
        var box = host.querySelector("[data-smx-error]");
        if (!box) {
            return;
        }
        box.textContent = message || "";
        box.hidden = !message;
    }

    function showConflict(host, payload, clean) {
        var box = host.querySelector("[data-smx-conflict]");
        if (!box) {
            return;
        }
        var t = texts();
        box.classList.remove("is-clean", "is-clash");
        if (clean) {
            box.textContent = t.clean || "";
            box.classList.add("is-clean");
            box.hidden = false;
            return;
        }
        if (!payload) {
            box.hidden = true;
            box.textContent = "";
            return;
        }
        var parts = [
            (t.conflict || "") + ": " + (payload.subject_code || ""),
            payload.group || "",
            payload.instructor || "",
            payload.room || "",
            (payload.start_time || "") + "–" + (payload.end_time || ""),
            payload.reason ? "(" + payload.reason + ")" : "",
        ].filter(Boolean);
        box.textContent = parts.join(" · ");
        box.classList.add("is-clash");
        box.hidden = false;
    }

    function firstErrorText(errors) {
        if (!errors) {
            return "";
        }
        var keys = Object.keys(errors);
        for (var i = 0; i < keys.length; i++) {
            if (typeof errors[keys[i]] === "string") {
                return errors[keys[i]];
            }
        }
        return "";
    }

    function runCheck(host) {
        var payload = formPayload(host);
        if (!payload) {
            return Promise.resolve(false);
        }
        showError(host, texts().checking || "");
        return window.EMSCore.fetchJSON(host.getAttribute("data-check-url"), { method: "POST", data: payload })
            .then(function (result) {
                showError(host, result.ok ? "" : firstErrorText(result.errors));
                showConflict(host, result.conflict, result.ok);
                return Boolean(result.ok);
            })
            .catch(function (err) {
                var body = err && err.payload;
                showError(host, (body && body.message) || texts().error || "");
                return false;
            });
    }

    function submitAdd(host) {
        var payload = formPayload(host);
        if (!payload) {
            return;
        }
        payload.action = "add";
        showError(host, "");
        window.EMSCore.fetchJSON(host.getAttribute("data-action-url"), { method: "POST", data: payload })
            .then(function () {
                reload(host, {});
            })
            .catch(function (err) {
                var body = err && err.payload;
                showError(host, firstErrorText(body && body.errors) || (body && body.message) || texts().error || "");
                showConflict(host, body && body.conflict, false);
            });
    }

    function openDialog(host, slotId, label) {
        var dialog = host.querySelector("[data-smx-dialog]");
        if (!dialog) {
            return;
        }
        dialog.dataset.slotId = slotId;
        var body = dialog.querySelector("[data-smx-dialog-body]");
        if (body) {
            body.textContent = label || "";
        }
        dialog.hidden = false;
    }

    function closeDialog(host) {
        var dialog = host && host.querySelector("[data-smx-dialog]");
        if (dialog) {
            dialog.hidden = true;
            dialog.dataset.slotId = "";
        }
    }

    function confirmDelete(host) {
        var dialog = host.querySelector("[data-smx-dialog]");
        var slotId = dialog && dialog.dataset.slotId;
        if (!slotId) {
            return;
        }
        window.EMSCore.fetchJSON(host.getAttribute("data-action-url"), {
            method: "POST",
            data: { action: "delete", slot_id: slotId },
        })
            .then(function () {
                closeDialog(host);
                reload(host, {});
            })
            .catch(function (err) {
                closeDialog(host);
                var body = err && err.payload;
                showError(host, (body && body.message) || texts().error || "");
            });
    }

    // ── Delegated hadisələr ─────────────────────────────────────────────────

    DELEGATE.on("change", "[data-smx-reload]", function () {
        var host = root();
        if (!host) {
            return;
        }
        // Görünüş dəyişəndə əks rejimin seçimi mənasızdır — sıfırlanır ki,
        // «müəllim cədvəli» rejimindən qayıdanda köhnə filtr ilişib qalmasın.
        reload(host, {});
    });

    DELEGATE.on("change", "[data-smx-time]", function (event, field) {
        var host = root();
        if (!host) {
            return;
        }
        var custom = host.querySelectorAll("[data-smx-custom]");
        var manual = !field.value;
        custom.forEach(function (node) {
            node.hidden = !manual;
        });
    });

    DELEGATE.on("click", "[data-smx-check]", function () {
        var host = root();
        if (host) {
            runCheck(host);
        }
    });

    DELEGATE.on("submit", "[data-smx-add]", function (event) {
        event.preventDefault();
        var host = root();
        if (host) {
            submitAdd(host);
        }
    });

    DELEGATE.on("click", "[data-smx-delete]", function (event, button) {
        var host = root();
        if (host) {
            openDialog(host, button.getAttribute("data-smx-delete"), button.getAttribute("data-label") || "");
        }
    });

    DELEGATE.on("click", "[data-smx-dialog-close]", function () {
        closeDialog(root());
    });

    DELEGATE.on("click", "[data-smx-dialog-confirm]", function () {
        var host = root();
        if (host) {
            confirmDelete(host);
        }
    });
})(window, document);
