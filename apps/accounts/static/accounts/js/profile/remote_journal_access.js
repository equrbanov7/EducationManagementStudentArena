/* «Kənardan jurnal girişi» kabinet bölməsi (sahib 2026-11-20).
   Şablon: accounts/profile/sections/_remote_journal_access.html (data-atributlar: [data-rja-root]).

   * şəxs seçicisi — server-backed EMSSearchableSelect (`data-url`), seçim gizli `user` sahəsinə yazılır;
     «Əlavə et» yalnız şəxs seçiləndə açılır;
   * «Əlavə et» / «Geri al» — EMSConfirm ilə təsdiq, sonra EMSCore.fetchJSON ilə JSON POST (`data-action-url`);
     uğurdan sonra mesaj (EMSToast) və bölmə yerində yenilənir (EMSProfileLoadSection). Qapı serverdədir.
   AJAX-safe: hadisələr yalnız EMSDelegate ilə, seçici EMSReady ilə qurulur (create idempotentdir). */
(function () {
    "use strict";

    var ROOT = "[data-rja-root]";
    var SECTION = "remote-journal-access";

    function attr(el, name) {
        return (el && el.getAttribute(name)) || "";
    }

    function toast(text, level) {
        if (text && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(text, level || "success");
        }
    }

    function reloadSection() {
        if (typeof window.EMSProfileLoadSection === "function") {
            window.EMSProfileLoadSection(SECTION, window.location.href);
        } else {
            window.location.reload();
        }
    }

    function errorText(root, err) {
        var payload = err && err.payload;
        if (payload && typeof payload === "object" && (payload.message || payload.detail)) {
            return payload.message || payload.detail;
        }
        return attr(root, "data-msg-generic");
    }

    function sync(root, picker) {
        var field = root.querySelector("[data-rja-user]");
        var button = root.querySelector("[data-rja-add]");
        var value = picker ? picker.value() : "";
        if (field) field.value = value || "";
        if (button) button.disabled = !value;
    }

    function pickerFor(root) {
        var host = root.querySelector("[data-rja-picker]");
        if (!host || !host.dataset.url || !window.EMSSearchableSelect) return null;
        var picker = window.EMSSearchableSelect.create(host, {
            url: host.dataset.url,
            multi: false,
            skeleton: true,
            emptyText: host.dataset.empty || "",
        });
        if (picker && !host._rjaBound) {
            host._rjaBound = true;
            picker.on("change", function () { sync(root, picker); });
        }
        return picker;
    }

    function confirmThen(options, run) {
        if (!window.EMSConfirm || typeof window.EMSConfirm.open !== "function") return;
        window.EMSConfirm.open(options).then(function (ok) {
            if (ok) run();
        });
    }

    function send(root, data, button) {
        if (!window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") return;
        if (button) button.disabled = true;
        window.EMSCore.fetchJSON(attr(root, "data-action-url"), { method: "POST", data: data })
            .then(function (payload) {
                toast(payload && payload.message, "success");
                reloadSection();
            })
            .catch(function (err) {
                toast(errorText(root, err), "error");
                if (button) button.disabled = false;
            });
    }

    window.EMSDelegate.on("submit", ROOT + " [data-rja-add-form]", function (event, form) {
        event.preventDefault();
        var root = form.closest(ROOT);
        var picker = pickerFor(root);
        var user = picker ? picker.value() : "";
        if (!user) return;
        var note = form.querySelector("[data-rja-note]");
        var name = picker.text() || "";
        confirmThen({
            title: attr(root, "data-msg-grant-title"),
            body: attr(root, "data-msg-grant-body").replace("%(name)s", name),
            confirmLabel: attr(root, "data-msg-grant-ok"),
        }, function () {
            send(root, { action: "grant", user: user, note: note ? note.value : "" }, form.querySelector("[data-rja-add]"));
        });
    });

    window.EMSDelegate.on("click", ROOT + " [data-rja-revoke]", function (event, button) {
        var root = button.closest(ROOT);
        confirmThen({
            title: attr(root, "data-msg-revoke-title"),
            body: attr(root, "data-msg-revoke-body").replace("%(name)s", attr(button, "data-name")),
            confirmLabel: attr(root, "data-msg-revoke-ok"),
            danger: true,
        }, function () {
            send(root, { action: "revoke", grant: attr(button, "data-grant") }, button);
        });
    });

    window.EMSReady(function () {
        document.querySelectorAll(ROOT).forEach(function (root) {
            sync(root, pickerFor(root));
        });
    });
})();
