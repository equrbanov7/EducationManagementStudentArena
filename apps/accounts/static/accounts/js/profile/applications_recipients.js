(function () {
    "use strict";
    var NS = window.EMSApplications = window.EMSApplications || {};
    NS.recipientPicker = function (box, item) {
        var old = box.querySelector("[data-apx-recipient-field]");
        if (old) { old.remove(); }
        var destination = item && (item.destination || item);
        var previousScope = box.querySelector("[data-apx-scope-field]");
        if (previousScope) { previousScope.remove(); }
        if (destination && destination.resolve_by === "chair" && box.__app) {
            var scopeLabel = document.createElement("label");
            scopeLabel.className = "apx-field";
            scopeLabel.setAttribute("data-apx-scope-field", "");
            scopeLabel.textContent = NS.t("selectChair");
            var scopeSelect = document.createElement("select");
            scopeSelect.className = "apx-input";
            scopeSelect.setAttribute("data-apx-scope", "");
            scopeSelect.required = true;
            scopeSelect.add(new Option(NS.t("selectChair"), ""));
            (box.__app.forward_scopes || []).forEach(function (scope) { scopeSelect.add(new Option(scope.name, scope.id)); });
            scopeLabel.appendChild(scopeSelect);
            var scopeAnchor = box.querySelector("[data-apx-unit-list]");
            scopeAnchor.parentNode.insertBefore(scopeLabel, scopeAnchor.nextSibling);
        }
        if (!destination || !destination.requires_recipient) { return; }
        var label = document.createElement("label");
        label.setAttribute("data-apx-recipient-field", "");
        label.className = "apx-field";
        label.textContent = NS.t("selectRecipient");
        var select = document.createElement("select");
        select.setAttribute("data-apx-recipient", "");
        select.className = "apx-input";
        select.required = true;
        select.add(new Option(NS.t("selectRecipient"), ""));
        (item.recipients || []).forEach(function (person) { select.add(new Option(person.name, person.id)); });
        label.appendChild(select);
        var anchor = box.querySelector("[data-apx-route]") || box.querySelector("[data-apx-unit-list]");
        anchor.parentNode.insertBefore(label, anchor.nextSibling);
    };
})();
