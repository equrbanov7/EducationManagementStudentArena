(function () {
    "use strict";
    var NS = window.EMSApplications = window.EMSApplications || {};
    NS.recipientPicker = function (box, item) {
        var old = box.querySelector("[data-apx-recipient-field]");
        if (old) { old.remove(); }
        var destination = item && (item.destination || item);
        if (!destination || !destination.requires_recipient) { return; }
        var label = document.createElement("label");
        label.setAttribute("data-apx-recipient-field", "");
        label.className = "apx-field";
        label.textContent = "Hansı prorektora müraciət edirsiniz?";
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
