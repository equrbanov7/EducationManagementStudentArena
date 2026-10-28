/* Müraciət/cavab düzəlişi və bərpa olunan silmə. İcazələr server payload-undandır. */
(function () {
    "use strict";
    var NS = window.EMSApplications = window.EMSApplications || {};
    NS.contentButtons = function (app) {
        var actions = app.content_actions || {};
        var buttons = [];
        if (actions.can_edit) { buttons.push('<button type="button" class="apx-btn" data-apx-edit-application>' + NS.esc(NS.t("editApplication")) + '</button>'); }
        if (actions.can_delete) { buttons.push('<button type="button" class="apx-btn apx-btn--danger" data-apx-delete-application>' + NS.esc(NS.t("deleteApplication")) + '</button>'); }
        if (actions.can_restore) { buttons.push('<button type="button" class="apx-btn apx-btn--primary" data-apx-restore-application>' + NS.esc(NS.t("restoreApplication")) + '</button>'); }
        return '<div class="apx-content-tools">' +
            (app.deleted_at ? '<p role="status">' + NS.esc(NS.t("deletedBanner")) + '</p>' : '') +
            (app.edited_at ? '<small>' + NS.esc(NS.t("edited")) + ' · ' + NS.esc(NS.dateTime(app.edited_at)) + '</small>' : '') +
            '<div class="apx-act__buttons">' + buttons.join('') + '</div></div>';
    };
    function openEditor(app, event) {
        var box = NS.dialogs.open("content-edit");
        if (!box) { return; }
        box.__contentApp = app;
        box.__contentEvent = event || null;
        box.querySelector("[data-apx-content-title]").textContent = event ? NS.t("editReply") : NS.t("editApplication");
        box.querySelector("[data-apx-content-subject-field]").hidden = !!event;
        box.querySelector("[data-apx-content-subject]").value = app.subject;
        box.querySelector("[data-apx-content-text]").value = event ? event.text : app.body;
    }
    function save() {
        var box = NS.root.querySelector('[data-apx-dialog="content-edit"]');
        var app = box.__contentApp;
        var event = box.__contentEvent;
        var text = box.querySelector("[data-apx-content-text]").value;
        var fields = event
            ? { event: event.id, text: text, revision: event.revision || "" }
            : { subject: box.querySelector("[data-apx-content-subject]").value, body: text, updated_at: app.updated_at };
        var button = box.querySelector("[data-apx-content-save]");
        button.disabled = true;
        NS.submitAction(app.id, event ? "edit_reply" : "edit_application", fields).then(function () {
            NS.dialogs.close("content-edit");
        }).catch(function (error) {
            NS.dialogs.showErrors(box, NS.errorList(error));
        }).then(function () { button.disabled = false; });
    }
    function changeVisibility(restoring) {
        var app = NS.current;
        if (!app) { return; }
        NS.dialogs.confirm(restoring ? NS.t("restoreApplication") : NS.t("deleteApplication"),
            restoring ? NS.t("restorePrompt") : NS.t("deletePrompt"), function () {
                NS.submitAction(app.id, restoring ? "restore_application" : "delete_application", { updated_at: app.updated_at })
                    .then(function () { NS.dialogs.close("confirm"); NS.refreshCounts(); })
                    .catch(function (error) { NS.toast(NS.errorList(error)[0], "error"); });
            });
    }
    function start() {
        if (NS.__contentWired) { return; }
        NS.__contentWired = true;
        window.EMSDelegate.on("click", "[data-apx-edit-application]", function () {
            if (NS.current && (NS.current.content_actions || {}).can_edit) { openEditor(NS.current); }
        });
        window.EMSDelegate.on("click", "[data-apx-edit-reply]", function (event, node) {
            var app = NS.current;
            if (!app) { return; }
            var reply = (app.events || []).filter(function (item) { return item.id === node.getAttribute("data-apx-edit-reply"); })[0];
            if (reply && reply.can_moderate && !reply.is_hidden) { openEditor(app, reply); }
        });
        window.EMSDelegate.on("click", "[data-apx-content-save]", save);
        window.EMSDelegate.on("click", "[data-apx-delete-application]", function () { changeVisibility(false); });
        window.EMSDelegate.on("click", "[data-apx-restore-application]", function () { changeVisibility(true); });
    }
    (function ready(attempt) {
        if (window.EMSDelegate && NS.api) { start(); return; }
        if (attempt < 200) { window.setTimeout(function () { ready(attempt + 1); }, 25); }
    })(0);
})();
