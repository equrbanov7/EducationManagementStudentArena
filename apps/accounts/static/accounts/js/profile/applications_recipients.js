(function () {
    "use strict";
    var NS = window.EMSApplications = window.EMSApplications || {};
    // Uzun siyahı ola bilər — layihənin axtarışlı stilli select komponenti (native select deyil).
    function scopePicker(box, scopes, labelKey) {
        var scopeField = document.createElement("div");
        scopeField.className = "apx-field";
        scopeField.setAttribute("data-apx-scope-field", "");
        var scopeLabel = document.createElement("label");
        scopeLabel.className = "apx-field__label";
        scopeLabel.htmlFor = "apx-scope-select";
        scopeLabel.textContent = NS.t(labelKey);
        var scopeWrap = document.createElement("div");
        scopeWrap.className = "bootstrap-single-select bootstrap-single-select--ems";
        var scopeSelect = document.createElement("select");
        scopeSelect.id = "apx-scope-select";
        scopeSelect.className = "apx-select bootstrap-single-select__native";
        scopeSelect.setAttribute("data-apx-scope", "");
        scopeSelect.setAttribute("data-bootstrap-select", "");
        scopeSelect.required = true;
        scopeSelect.add(new Option(NS.t(labelKey), ""));
        scopes.forEach(function (scope) {
            var option = new Option(scope.name, scope.id);
            if (scope.school) { option.setAttribute("data-subtext", scope.school); }
            option.setAttribute("data-search", scope.name + " " + (scope.school || ""));
            scopeSelect.add(option);
        });
        // Yeganə seçim (adi emalçının öz məktəbi) əvvəlcədən seçilir.
        if (scopes.length === 1) { scopeSelect.value = scopes[0].id; }
        scopeWrap.appendChild(scopeSelect);
        scopeField.appendChild(scopeLabel);
        scopeField.appendChild(scopeWrap);
        var scopeAnchor = box.querySelector("[data-apx-unit-list]") || box.querySelector("[data-apx-route]");
        scopeAnchor.parentNode.insertBefore(scopeField, scopeAnchor.nextSibling);
    }
    NS.recipientPicker = function (box, item) {
        var old = box.querySelector("[data-apx-recipient-field]");
        if (old) { old.remove(); }
        var destination = item && (item.destination || item);
        var previousScope = box.querySelector("[data-apx-scope-field]");
        if (previousScope) { previousScope.remove(); }
        if (destination && box.__app) {
            // MR-000302 (sahib 2026-11-12): RİM bütün kafedraları görür (məktəbinkilər əvvəldə).
            // Sahib 2026-11-17: dekanlığa yönləndirəndə də eyni qaydada MƏKTƏB (dekanlıq) seçilir.
            if (destination.resolve_by === "chair") {
                var chairs = box.__app.forward_scopes || [];
                var anySchool = chairs.some(function (scope) { return scope.own_school === false; });
                scopePicker(box, chairs, anySchool ? "selectAnyChair" : "selectChair");
            } else if (destination.code === "dekan" && (box.__app.forward_schools || []).length) {
                scopePicker(box, box.__app.forward_schools, "selectSchool");
            }
        }
        // Yaratma formasında: aidiyyəti tapılmayan göndərən dekanlığı (məktəbi) özü seçir.
        if (!box.__app && item && item.schools && item.schools.length) {
            scopePicker(box, item.schools, "selectSchool");
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
