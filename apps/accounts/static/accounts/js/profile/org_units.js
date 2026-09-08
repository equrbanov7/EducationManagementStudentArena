/* =========================================================================
   «Fakültələr» / «Kafedralar» reyestri — bölmə-xüsusi davranış (2026-09-08).

   Dialoq açılışı, prefill və JSON POST ORTAQ `teaching_office.js`-dədir. Bu
   fayl yalnız:
     1) sətir düyməsindəki bölmə adını dialoqun hədəf zolağına yazır;
     2) axtarışlı şəxs/müəllim seçicisini (`EMSSearchableSelect`) hər açılışda
        sıfırdan qurur — namizəd URL-i növə/kafedraya görə dəyişir;
     3) koordinator dialoqunda əhatə (ixtisas) select-ini sətrin JSON-undan doldurur;
     4) «Heyət» çekmecəsini JSON-dan render edir və təyinat silməni göndərir;
        çekmecə bağlananda dəyişiklik varsa bölmə fraqmenti yenilənir.

   AJAX-safe: hər şey `EMSDelegate` ilə sənəd səviyyəsində; bölmə swap olunsa
   da işləyir. Mətnlər data-atributlardan gəlir (xarici JS şablondan keçmir).
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (!window.EMSDelegate || window.__emsOrgUnitsBound) {
        return;
    }
    window.__emsOrgUnitsBound = true;

    var DRAWER_ID = "ouStaffDrawer";
    var ROOT_SELECTOR = '[data-tof-root][data-tof-section="org-faculties"], [data-tof-root][data-tof-section="org-kafedras"]';
    var state = { url: "", unitId: "", unitName: "", specialties: "[]", dirty: false };

    function root() {
        return document.querySelector(ROOT_SELECTOR);
    }

    function esc(value) {
        return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, function (ch) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
        });
    }

    function fmt(template, args) {
        var index = 0;
        return String(template || "").replace(/%[sd]/g, function () {
            var value = args[index];
            index += 1;
            return value === null || value === undefined ? "" : String(value);
        });
    }

    function t(host, key) {
        return host ? host.getAttribute("data-t-" + key) || "" : "";
    }

    function initials(name) {
        var parts = String(name || "").split(/\s+/).filter(Boolean);
        if (!parts.length) {
            return "—";
        }
        if (parts.length === 1) {
            return parts[0].slice(0, 2).toUpperCase();
        }
        return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
    }

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    /* ---- Dialoq seçiciləri ------------------------------------------------ */

    function buildPicker(dialog, btn) {
        var host = dialog.querySelector("[data-ou-picker]");
        var hidden = dialog.querySelector("[data-ou-picker-value]");
        if (!host || !hidden || !window.EMSSearchableSelect) {
            return;
        }
        // URL hər açılışda dəyişə bilər (kafedra istisnası) — seçici təmiz
        // markup klonundan yenidən qurulur (bax `teaching_office_groups.js`).
        var seed = host._ouSeed || host.cloneNode(true);
        var fresh = seed.cloneNode(true);
        fresh._ouSeed = seed;
        host.parentNode.replaceChild(fresh, host);
        host = fresh;
        hidden.value = "";

        var kind = host.getAttribute("data-kind") || "staff";
        var url = host.getAttribute("data-url") || "";
        if (!url) {
            return;
        }
        url += (url.indexOf("?") === -1 ? "?" : "&") + "kind=" + encodeURIComponent(kind);
        var unitId = btn.getAttribute("data-ou-unit-id") || "";
        if (kind === "teacher" && unitId) {
            url += "&unit=" + encodeURIComponent(unitId);
        }
        var picker = window.EMSSearchableSelect.create(host, {
            url: url,
            multi: false,
            skeleton: true,
            pageSize: 20,
            emptyText: host.getAttribute("data-empty") || "",
            onChange: function () {
                hidden.value = (picker && typeof picker.value === "function" && picker.value()) || "";
            }
        });
        host._ouPicker = picker;
        window.setTimeout(function () {
            var input = host.querySelector(".ems-ss__search");
            if (input) {
                input.focus();
            }
        }, 40);
    }

    function fillScope(dialog, btn) {
        var wrap = dialog.querySelector("[data-ou-scope-wrap]");
        if (!wrap) {
            return;
        }
        var roleField = dialog.querySelector('input[name="role"]');
        var role = roleField ? roleField.value : "";
        var select = wrap.querySelector("[data-ou-scope-select]");
        var list = [];
        try {
            list = JSON.parse(btn.getAttribute("data-ou-specialties") || "[]");
        } catch (err) {
            list = [];
        }
        if (select) {
            var allLabel = select.getAttribute("data-all-label") || "";
            select.innerHTML = "";
            var first = document.createElement("option");
            first.value = "";
            first.textContent = allLabel;
            select.appendChild(first);
            list.forEach(function (item) {
                var option = document.createElement("option");
                option.value = item.id;
                option.textContent = item.name;
                select.appendChild(option);
            });
            select.value = "";
            if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
                window.EMSBootstrapSelect.refresh(select);
            }
        }
        wrap.hidden = role !== "program_coordinator";
    }

    // ⚠️ SEÇİCİ QƏSDƏN FƏRQLİDİR: `EMSDelegate.on` eyni «hadisə|seçici» açarını
    // ƏVƏZ EDİR (yığmır) — çılpaq `[data-tof-open]` yazsaq `teaching_office.js`-in
    // prefill/açılış dinləyicisi silinər. Bizim düymələrin hamısı
    // `data-ou-unit-name` daşıyır; ortaq dinləyici ƏVVƏL qaçır (skript sırası),
    // dialoq artıq açıqdır — seçicinin menyusu ölçü ala bilir.
    window.EMSDelegate.on("click", "[data-tof-open][data-ou-unit-name]", function (event, btn) {
        if (!root()) {
            return;
        }
        var dialog = document.getElementById(btn.getAttribute("data-tof-open") || "");
        if (!dialog) {
            return;
        }
        var nameEl = dialog.querySelector("[data-ou-target-name]");
        if (nameEl) {
            nameEl.textContent = btn.getAttribute("data-ou-unit-name") || "";
        }
        buildPicker(dialog, btn);
        fillScope(dialog, btn);
    });

    /* ---- «Heyət» çekmecəsi ------------------------------------------------ */

    function drawer() {
        return document.getElementById(DRAWER_ID);
    }

    function staffHost() {
        var el = drawer();
        return el ? el.querySelector("[data-ou-staff]") : null;
    }

    function setBusy(host, busy) {
        var skeleton = host.querySelector("[data-ou-staff-skeleton]");
        if (skeleton) {
            skeleton.hidden = !busy;
        }
        host.setAttribute("aria-busy", busy ? "true" : "false");
    }

    function showError(host, message) {
        var el = host.querySelector("[data-ou-staff-error]");
        if (el) {
            el.textContent = message || "";
            el.hidden = !message;
        }
    }

    function personRow(host, member, group) {
        var sub = "@" + esc(member.username);
        if (member.scope) {
            sub += " · " + esc(t(host, "scope")) + ": " + esc(member.scope);
        }
        var remove = "";
        if (group.removable) {
            remove =
                '<button type="button" class="ems-btn ems-btn--sm ems-btn--danger ou-staff__remove" data-ou-remove' +
                ' data-membership="' + esc(member.membership_id) + '"' +
                ' data-name="' + esc(member.name) + '"' +
                ' data-role-label="' + esc(member.role_label) + '">' +
                '<i class="fas fa-user-minus" aria-hidden="true"></i> ' + esc(t(host, "remove")) +
                "</button>";
        }
        return (
            '<li class="ou-staff__row">' +
            '<span class="ou-avatar" aria-hidden="true">' + esc(initials(member.name)) + "</span>" +
            '<span class="ou-staff__main">' +
            '<a class="ou-staff__name" href="' + esc(member.profile_url) + '" target="_blank" rel="noopener" title="' + esc(t(host, "profile")) + '">' + esc(member.name) + "</a>" +
            '<span class="ou-staff__sub">' + sub + "</span>" +
            "</span>" +
            remove +
            "</li>"
        );
    }

    /* Çekmecə içindən mövcud dialoqları açan düymələr — dialoq DOM-da yoxdursa
       (səlahiyyət yoxdur) düymə də yoxdur. Prefill/açılış ortaq mexanizmdir. */
    function openButton(dialogId, label, title, prefill, extra) {
        if (!document.getElementById(dialogId)) {
            return "";
        }
        var attrs =
            ' data-tof-open="' + esc(dialogId) + '"' +
            ' data-tof-title="' + esc(title) + '"' +
            " data-tof-prefill='" + esc(JSON.stringify(prefill)).replace(/&#39;/g, "&#39;") + "'" +
            ' data-ou-unit-name="' + esc(state.unitName) + '"' +
            (extra || "");
        return '<button type="button" class="ems-btn ems-btn--sm ou-staff__cta"' + attrs + '><i class="fas fa-plus" aria-hidden="true"></i> ' + esc(label) + "</button>";
    }

    function groupAddButton(host, group, unit) {
        var isFaculty = unit.type === "faculty";
        if (group.key === "vice_dean") {
            return openButton("ouRoleDialog", t(host, "add"), t(host, "add-vice-dean"),
                { action: "add_role", id: state.unitId, role: "vice_dean", user: "", scope: "", reason: "" });
        }
        if (group.key === "program_coordinator") {
            return openButton("ouRoleDialog", t(host, "add"), t(host, "add-coordinator"),
                { action: "add_role", id: state.unitId, role: "program_coordinator", user: "", scope: "", reason: "" },
                ' data-ou-specialties="' + esc(state.specialties) + '"');
        }
        if (group.key === "teacher" && !isFaculty) {
            return openButton("ouTeacherDialog", t(host, "add"), t(host, "add-teacher"),
                { action: "add_teacher", id: state.unitId, membership: "", reason: "" },
                ' data-ou-unit-id="' + esc(state.unitId) + '"');
        }
        return "";
    }

    function headButton(host, unit) {
        var head = unit.head;
        var title = unit.type === "faculty" ? t(host, "assign-dean") : t(host, "assign-chair-head");
        var label = head ? t(host, "change-head") : t(host, "assign-head");
        var button = openButton("ouHeadDialog", label, title, {
            action: "assign_head",
            id: state.unitId,
            head: head ? head.user_id : "",
            head_label: head ? head.name : "",
            reason: ""
        });
        return button.replace('<i class="fas fa-plus" aria-hidden="true"></i> ', head ? '<i class="fas fa-pen" aria-hidden="true"></i> ' : '<i class="fas fa-user-plus" aria-hidden="true"></i> ');
    }

    function render(host, payload) {
        var unitEl = host.querySelector("[data-ou-staff-unit]");
        var body = host.querySelector("[data-ou-staff-body]");
        var unit = payload.unit || {};
        var head = unit.head;
        var headHtml = head
            ? '<div class="ou-person"><span class="ou-avatar" aria-hidden="true">' + esc(initials(head.name)) + "</span>" +
              '<a class="ou-person__name" href="' + esc(head.profile_url) + '" target="_blank" rel="noopener">' + esc(head.name) + "</a></div>"
            : '<span class="ou-missing">' + esc(t(host, "no-head")) + "</span>";
        if (unitEl) {
            unitEl.innerHTML =
                '<div class="ou-staff__title">' +
                '<span class="ou-staff__type">' + esc(unit.type_label) + (unit.parent_name ? " · " + esc(unit.parent_name) : "") + "</span>" +
                "<strong>" + esc(unit.name) + (unit.code ? ' <span class="ou-unit__code ems-mono">' + esc(unit.code) + "</span>" : "") + "</strong>" +
                "</div>" +
                '<div class="ou-staff__head"><span class="ou-staff__label">' + esc(unit.head_label) + "</span>" + headHtml +
                (payload.can_assign_head ? headButton(host, unit) : "") + "</div>";
        }
        var html = "";
        (payload.groups || []).forEach(function (group) {
            var members = group.members || [];
            html += '<section class="ou-staff__group"><div class="ou-staff__grouphead"><h3 class="ou-staff__label">' + esc(group.label) +
                ' <span class="ou-staff__count">' + esc(fmt(t(host, "count"), [members.length])) + "</span></h3>" +
                (payload.can_assign_members ? groupAddButton(host, group, unit) : "") + "</div>";
            if (!members.length) {
                html += '<p class="ou-staff__empty">' + esc(t(host, "empty")) + "</p>";
            } else {
                html += '<ul class="ou-staff__list">' + members.map(function (member) { return personRow(host, member, group); }).join("") + "</ul>";
            }
            html += "</section>";
        });
        var children = payload.children || [];
        html += '<section class="ou-staff__group"><h3 class="ou-staff__label">' + esc(payload.children_label) +
            ' <span class="ou-staff__count">' + children.length + "</span></h3>";
        if (!children.length) {
            html += '<p class="ou-staff__empty">' + esc(t(host, "children-empty")) + "</p>";
        } else {
            html += '<ul class="ou-staff__children">' + children.map(function (child) {
                var headName = child.head_name
                    ? esc(child.head_name)
                    : '<span class="ou-missing ou-missing--soft">' + esc(t(host, "no-head")) + "</span>";
                return '<li class="ou-staff__child"><span class="ou-staff__child-name">' + esc(child.name) +
                    (child.code ? ' <span class="ou-unit__code ems-mono">' + esc(child.code) + "</span>" : "") +
                    '</span><span class="ou-staff__child-head">' + headName + "</span></li>";
            }).join("") + "</ul>";
        }
        html += "</section>";
        if (body) {
            body.innerHTML = html;
        }
    }

    function load(host) {
        if (!window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
            return;
        }
        setBusy(host, true);
        showError(host, "");
        var body = host.querySelector("[data-ou-staff-body]");
        if (body) {
            body.innerHTML = "";
        }
        var requestUrl = state.url;
        window.EMSCore.fetchJSON(requestUrl)
            .then(function (payload) {
                if (requestUrl !== state.url) {
                    return; // başqa bölmə açılıb — köhnə cavab atılır
                }
                setBusy(host, false);
                render(host, payload || {});
            })
            .catch(function (err) {
                if (requestUrl !== state.url) {
                    return;
                }
                setBusy(host, false);
                showError(host, (err && err.payload && err.payload.message) || t(host, "error"));
            });
    }

    window.EMSDelegate.on("click", "[data-ou-staff-open]", function (event, btn) {
        event.preventDefault();
        var el = drawer();
        var host = staffHost();
        if (!el || !host) {
            return;
        }
        state.url = btn.getAttribute("data-url") || "";
        state.unitId = btn.getAttribute("data-unit-id") || "";
        state.unitName = btn.getAttribute("data-unit-name") || "";
        state.specialties = btn.getAttribute("data-ou-specialties") || "[]";
        state.dirty = false;
        if (window.EMSOverlay) {
            window.EMSOverlay.open(el);
        }
        load(host);
    });

    window.EMSDelegate.on("click", "[data-ou-remove]", function (event, btn) {
        event.preventDefault();
        var host = staffHost();
        var section = root();
        if (!host || !section || !window.EMSTeachingOffice) {
            return;
        }
        var confirmText = fmt(t(host, "confirm"), [btn.getAttribute("data-name"), btn.getAttribute("data-role-label")]);
        if (confirmText && !window.confirm(confirmText)) {
            return;
        }
        btn.disabled = true;
        window.EMSTeachingOffice
            .post(section.getAttribute("data-tof-action-url"), {
                action: "remove_role",
                id: state.unitId,
                membership: btn.getAttribute("data-membership") || ""
            }, null)
            .then(function (payload) {
                state.dirty = true;
                toast(payload && payload.message, "success");
                load(host);
            })
            .catch(function (err) {
                btn.disabled = false;
                showError(host, (err && err.payload && err.payload.message) || t(host, "error"));
            });
    });

    // Çekmecə bağlananda təyinat dəyişibsə cədvəl/KPI yenilənir.
    document.addEventListener("ems:overlay:close", function (event) {
        var overlay = event.target;
        if (!overlay || overlay.id !== DRAWER_ID || !state.dirty) {
            return;
        }
        state.dirty = false;
        var section = root();
        if (!section || !window.EMSTeachingOffice) {
            return;
        }
        var key = section.getAttribute("data-tof-section");
        window.EMSTeachingOffice.reload(key, window.EMSTeachingOffice.sectionUrl(key, {}));
    });
})(window, document);
