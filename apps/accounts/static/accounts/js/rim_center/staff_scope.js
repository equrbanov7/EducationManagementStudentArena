/* One selected staff affiliation; personal fields and other roles are untouched. */
(function (window, document) {
    "use strict";
    var ns = (window.EMSRimCenter = window.EMSRimCenter || {});
    ns.staffScope = {};
    ns.staffScope.render = function (user) {
        var card = user.staff_scope;
        if (!card) { return ""; }
        var esc = ns.escape, labels = card.labels;
        return '<section><h3 class="rim-section-title">' + esc(labels.title) + '</h3><p>' + esc(labels.help) + '</p>' +
            card.memberships.map(function (row) {
                return '<div data-rim-staff-scope="' + esc(row.id) + '" data-current-unit="' + esc(row.unit_id) + '">' +
                    '<p>' + esc(row.role_label) + ' — ' + esc(row.unit_name) + '</p>' +
                    '<div class="bootstrap-single-select bootstrap-single-select--ems"><select class="rim-input bootstrap-single-select__native" ' +
                    'data-bootstrap-select data-live-search="true" aria-label="' + esc(labels.title) + '">' +
                    card.units.map(function (unit) {
                        return '<option value="' + esc(unit.id) + '"' + (unit.id === row.unit_id ? ' selected' : '') + '>' + esc(unit.name) + '</option>';
                    }).join("") + '</select></div><label>' + esc(labels.reason) +
                    '<input class="rim-input" data-rim-scope-reason maxlength="300" minlength="3" required></label>' +
                    '<p class="rim-error" data-rim-scope-error hidden role="alert"></p>' +
                    '<button type="button" class="rim-btn rim-btn--primary" data-rim-scope-save>' + esc(labels.save) + '</button></div>';
            }).join("") + '</section>';
    };
    if (!window.EMSReady || !window.EMSDelegate) { return; }
    window.EMSReady.once("rim-staff-scope", function () {
        window.EMSDelegate.on("click", "[data-rim-scope-save]", function (event, button) {
            event.preventDefault();
            var host = button.closest("[data-rim-staff-scope]"), user = ns.state.selectedUser;
            var cfg = ns.config(), fetchJSON = window.EMSCore && window.EMSCore.fetchJSON;
            if (!host || !user || !cfg || !fetchJSON) { return; }
            var reason = host.querySelector("[data-rim-scope-reason]"), error = host.querySelector("[data-rim-scope-error]");
            if (!reason.reportValidity()) { return; }
            button.disabled = true; error.hidden = true;
            fetchJSON(cfg.actionUrl, {method: "POST", data: {
                action: "move_staff_scope", user_id: user.id, membership_id: host.dataset.rimStaffScope,
                expected_unit_id: host.dataset.currentUnit, unit_id: host.querySelector("select").value, reason: reason.value
            }}).then(function (response) {
                ns.state.selectedUser = response.user;
                ns.render.detail(response.user);
                ns.actions.search();
            }).catch(function (err) {
                error.textContent = ns.errorMessage(err); error.hidden = false;
            }).then(function () { button.disabled = false; });
        });
    });
})(window, document);
