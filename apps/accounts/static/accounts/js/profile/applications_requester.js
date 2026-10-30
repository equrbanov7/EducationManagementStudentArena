/* Müraciət göndərənin tam adı, hesabı və cari tenant-scoped vəzifə/bölməsi. */
(function (window) {
    "use strict";
    var NS = (window.EMSApplications = window.EMSApplications || {});
    function unique(values) {
        return values.filter(function (value, index) { return value && values.indexOf(value) === index; });
    }
    function lines(person, fallback) {
        person = person || {};
        var position = person.position || "";
        var roles = (person.roles || []).filter(function (role) {
            return position.split(/\s*\/\s*/).indexOf(role) < 0;
        });
        var job = unique([position, roles.join(" / ")]).join(" · ");
        var units = unique([].concat(person.chairs || [], person.schools || [], person.units || []));
        return unique([person.username ? "@" + person.username : "", job, units.join(" · ") || fallback || ""]);
    }
    NS.requesterMeta = function (person, fallback) { return lines(person, fallback).join(" · "); };
    NS.requesterHTML = function (person, fallback) {
        person = person || {};
        var name = person.full_name || person.name || person.username || "";
        return '<span class="apx-person"><strong class="apx-person__name">' + NS.esc(name) + "</strong>" +
            lines(person, fallback).map(function (line) {
                return '<span class="apx-person__line">' + NS.esc(line) + "</span>";
            }).join("") + "</span>";
    };
})(window);
