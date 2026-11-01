/* Müraciət göndərənin tam adı, hesabı və cari tenant-scoped vəzifə/bölməsi. */
(function (window) {
    "use strict";
    var NS = (window.EMSApplications = window.EMSApplications || {});
    function unique(values) {
        return values.filter(function (value, index) { return value && values.indexOf(value) === index; });
    }
    function details(person, fallback) {
        person = person || {};
        var position = person.position || "";
        var roles = (person.roles || []).filter(function (role) {
            return position.split(/\s*\/\s*/).indexOf(role) < 0;
        });
        var job = unique([position, roles.join(" / ")]).join(" · ");
        var units = unique([].concat(person.chairs || [], person.schools || [], person.units || []));
        return [
            { kind: "account", text: person.username ? "@" + person.username : "" },
            { kind: "job", text: job },
            { kind: "units", text: units.join(" · ") || fallback || "" },
        ].filter(function (entry) { return entry.text; });
    }
    NS.requesterMeta = function (person, fallback) { return details(person, fallback).map(function (entry) { return entry.text; }).join(" · "); };
    NS.requesterHTML = function (person, fallback) {
        person = person || {};
        var name = person.full_name || person.name || person.username || "";
        return '<span class="apx-person"><strong class="apx-person__name">' + NS.esc(name) + "</strong>" +
            details(person, fallback).map(function (entry) {
                return '<span class="apx-person__line apx-person__' + entry.kind + '">' + NS.esc(entry.text) + "</span>";
            }).join("") + "</span>";
    };
})(window);
