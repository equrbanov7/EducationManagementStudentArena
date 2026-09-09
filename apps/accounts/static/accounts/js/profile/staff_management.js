/* =========================================================================
   «Heyət idarəetməsi» — bölmə-xüsusi davranış (2026-09-09 yenidən qurulub).

   Bu fayl yalnız ÜÇ iş görür:
     1) «Kart» → «Üzv kartı» çekmecəsi. Məlumat SƏTRİN `data-hm-payload`
        atributundakı JSON-dan gəlir — ƏLAVƏ SORĞU YOXDUR (N+1 riski yoxdur);
        render DOM API ilə aparılır (`innerHTML`-ə istifadəçi mətni yazılmır).
     2) «Çıxar» → səbəb dialoqu (`ems_ui/_reason_dialog.html`). Dialoq adi
        HTML POST edir (server `next` ilə eyni filtrli görünüşə qaytarır);
        təsdiq düyməsi ≥20 simvola qədər söndürülü qalır (overlay.js).
        UZAQLAŞDIRMA SOFT-DUR — üzvlük deaktiv olur, hesab silinmir.
     3) KPI kartı kliki (`ems:kpi-filter`, nav.js) → `hm_kind` seçicisi dəyişir,
        AVTO filtr (filter_bar.js) bölməni skeletonla yenidən yükləyir.

   Filtr, axtarış və səhifələmə SERVER tərəfindədir. AJAX-safe: hər şey
   `EMSDelegate` ilə sənəd səviyyəsindədir. Seçicilər BU EKRANA XASDIR
   (`data-hm-…`) — `EMSDelegate.on` eyni «hadisə|seçici» açarını ƏVƏZ etdiyi
   üçün başqa faylın açarı işlədilmir (bax `test_static_js_delegate_keys.py`).
   Mətnlər data-atributlardan oxunur (xarici JS Django şablonundan keçmir).
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (!window.EMSDelegate || window.__emsStaffManagementBound) {
        return;
    }
    window.__emsStaffManagementBound = true;

    var DRAWER_ID = "hmMemberDrawer";
    var REMOVE_ID = "hmRemoveDialog";

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null && text !== "") {
            node.textContent = String(text);
        }
        return node;
    }

    function icon(name) {
        var node = el("i", "fas " + name);
        node.setAttribute("aria-hidden", "true");
        return node;
    }

    function t(host, key) {
        return host ? host.getAttribute("data-t-" + key) || "" : "";
    }

    function detailHost() {
        var box = document.getElementById(DRAWER_ID);
        return box ? box.querySelector("[data-hm-detail]") : null;
    }

    /* ---- «Üzv kartı» çekmecəsi -------------------------------------------- */

    function fact(list, label, value) {
        var row = el("div", "hm-detail__fact");
        row.appendChild(el("dt", "hm-detail__label", label));
        row.appendChild(el("dd", "hm-detail__value", value || "—"));
        list.appendChild(row);
    }

    function renderIdentity(host, body, person) {
        var identity = el("div", "hm-detail__identity");
        identity.appendChild(
            el("span", "hm-avatar hm-avatar--lg" + (person.is_leader ? " hm-avatar--lead" : ""), person.initials || "—")
        );
        var meta = el("div", "hm-detail__meta");
        var nameRow = el("div", "hm-detail__name");
        nameRow.appendChild(el("span", "hm-detail__nametext", person.name || ""));
        if (person.is_leader) {
            var lead = el("span", "ems-badge ems-badge--warning");
            lead.appendChild(icon("fa-crown"));
            lead.appendChild(document.createTextNode(" " + t(host, "leader")));
            nameRow.appendChild(lead);
        }
        if (person.kind_label) {
            nameRow.appendChild(el("span", "ems-badge ems-badge--neutral", person.kind_label));
        }
        meta.appendChild(nameRow);
        var facts = el("dl", "hm-detail__facts");
        fact(facts, t(host, "username"), person.username ? "@" + person.username : "");
        fact(facts, t(host, "email"), person.email);
        fact(facts, t(host, "position"), person.position);
        fact(facts, t(host, "unit"), person.unit_chain || person.unit_name);
        fact(facts, t(host, "joined"), person.joined);
        meta.appendChild(facts);
        identity.appendChild(meta);
        body.appendChild(identity);
    }

    function renderRoles(host, body, roles) {
        var wrap = el("section", "hm-detail__section");
        var heading = el("h3", "hm-detail__heading", t(host, "roles"));
        heading.appendChild(el("span", "hm-detail__count", String(roles.length)));
        wrap.appendChild(heading);
        if (!roles.length) {
            wrap.appendChild(el("p", "hm-detail__empty", t(host, "roles-empty")));
            body.appendChild(wrap);
            return;
        }
        var list = el("ul", "hm-detail__list");
        roles.forEach(function (role) {
            var item = el("li", "hm-detail__item");
            var head = el("div", "hm-detail__itemhead");
            head.appendChild(el("span", "ems-badge ems-badge--neutral", role.label || ""));
            if (role.is_primary) {
                head.appendChild(el("span", "ems-badge ems-badge--muted", t(host, "primary")));
            }
            item.appendChild(head);
            var sub = el("div", "hm-detail__itemsub");
            if (role.unit) {
                sub.appendChild(el("span", "hm-detail__chip", role.unit));
            }
            if (role.title) {
                sub.appendChild(el("span", "hm-detail__chip", role.title));
            }
            item.appendChild(sub);
            list.appendChild(item);
        });
        wrap.appendChild(list);
        body.appendChild(wrap);
    }

    window.EMSDelegate.on("click", "[data-hm-card]", function (event, btn) {
        event.preventDefault();
        var box = document.getElementById(DRAWER_ID);
        var host = detailHost();
        if (!box || !host) {
            return;
        }
        var person;
        try {
            person = JSON.parse(btn.getAttribute("data-hm-payload") || "{}");
        } catch (err) {
            person = {};
        }
        var body = host.querySelector("[data-hm-detail-body]");
        if (body) {
            body.textContent = "";
            renderIdentity(host, body, person);
            renderRoles(host, body, person.roles || []);
        }
        var title = document.getElementById(DRAWER_ID + "-title");
        if (title && person.name) {
            title.textContent = person.name;
        }
        var link = box.querySelector("[data-hm-detail-profile]");
        if (link) {
            if (person.profile_url) {
                link.href = person.profile_url;
                link.hidden = false;
            } else {
                link.hidden = true;
            }
        }
        if (window.EMSOverlay && typeof window.EMSOverlay.open === "function") {
            window.EMSOverlay.open(box);
        } else {
            box.hidden = false;
        }
    });

    /* ---- «Çıxar» → səbəb dialoqu ------------------------------------------ */

    window.EMSDelegate.on("click", "[data-hm-remove]", function (event, btn) {
        event.preventDefault();
        var dialog = document.getElementById(REMOVE_ID);
        if (!dialog) {
            return;
        }
        var form = dialog.querySelector("form");
        if (form) {
            var field = form.querySelector('[name="user_id"]');
            if (field) {
                field.value = btn.getAttribute("data-hm-user") || "";
            }
            var reason = form.querySelector("textarea");
            if (reason) {
                reason.value = "";
            }
            var target = form.querySelector("[data-hm-remove-name]");
            if (target) {
                var name = btn.getAttribute("data-hm-name") || "";
                var username = btn.getAttribute("data-hm-username") || "";
                target.textContent = username ? name + " (@" + username + ")" : name;
            }
        }
        if (window.EMSOverlay && typeof window.EMSOverlay.open === "function") {
            window.EMSOverlay.open(dialog);
        } else {
            dialog.hidden = false;
        }
    });

    /* ---- KPI kartı → `hm_kind` filtri ------------------------------------- */

    document.addEventListener("ems:kpi-filter", function (event) {
        var target = event.target;
        var root = target && target.closest ? target.closest("[data-hm-root]") : null;
        if (!root) {
            return;
        }
        var select = root.querySelector('select[name="hm_kind"]');
        if (!select) {
            return;
        }
        var value = (event.detail && event.detail.filter) || "";
        if (select.value === value) {
            return;
        }
        select.value = value;
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
        select.dispatchEvent(new Event("change", { bubbles: true }));
    });
})(window, document);
