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
        // 2026-11-10 (sahib): prorektor seçimi növün ALTINDA açılan dropdown kimi — layihənin stilli
        // select komponenti (axtarışlı), hər sətirdə ad-soyad + vəzifə («Tədris işləri üzrə prorektor»).
        var field = document.createElement("div");
        field.setAttribute("data-apx-recipient-field", "");
        field.className = "apx-recipient";
        var label = document.createElement("label");
        label.className = "apx-field__label";
        label.htmlFor = "apx-recipient-select";
        label.textContent = NS.t("selectRecipient");
        var req = document.createElement("span");
        req.className = "apx-req";
        req.textContent = " *";
        label.appendChild(req);
        var wrap = document.createElement("div");
        wrap.className = "bootstrap-single-select bootstrap-single-select--ems";
        var select = document.createElement("select");
        select.id = "apx-recipient-select";
        select.setAttribute("data-apx-recipient", "");
        select.className = "apx-select bootstrap-single-select__native";
        select.setAttribute("data-bootstrap-select", "");
        select.required = true;
        var people = item.recipients || [];
        if (people.length > 6) { select.setAttribute("data-live-search", "true"); }
        select.add(new Option(NS.t("selectRecipient"), ""));
        people.forEach(function (person) {
            var option = new Option(person.title ? person.name + " — " + person.title : person.name, person.id);
            if (person.title) { option.setAttribute("data-subtext", person.title); option.textContent = person.name; }
            option.setAttribute("data-search", person.name + " " + (person.title || ""));
            select.add(option);
        });
        wrap.appendChild(select);
        field.appendChild(label);
        field.appendChild(wrap);
        var chosen = item.code ? box.querySelector('[data-apx-pick-kind="' + item.code + '"]') : null;
        var anchor = chosen || box.querySelector("[data-apx-route]") || box.querySelector("[data-apx-unit-list]");
        anchor.parentNode.insertBefore(field, anchor.nextSibling);
    };
})();
