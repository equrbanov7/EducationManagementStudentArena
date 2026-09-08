/* =========================================================================
   «Struktur üzvləri» reyestri — bölmə-xüsusi davranış (2026-09-08).

   Bu fayl yalnız:
     1) «Ətraflı» → «Üzv kartı» çekmecəsi: JSON (`structure_member_detail`)
        DOM ilə render olunur (innerHTML-ə istifadəçi mətni yazılmır);
     2) KPI kartı kliki (`ems:kpi-filter`, nav.js) → `om_kind` seçicisi dəyişir,
        avto filtr (filter_bar.js) bölməni yenidən yükləyir.

   Filtr/səhifələmə server tərəfindədir. AJAX-safe: hər şey `EMSDelegate` ilə
   sənəd səviyyəsində; bölmə swap olunsa da işləyir. Seçicilər bölməyə xasdır
   (`[data-om-…]`) — `EMSDelegate.on` eyni açarı ƏVƏZ ETDİYİ üçün başqa faylın
   seçicisi işlədilmir. Mətnlər data-atributlardan gəlir (xarici JS şablondan
   keçmir).
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (!window.EMSDelegate || window.__emsOrgMembersBound) {
        return;
    }
    window.__emsOrgMembersBound = true;

    var DRAWER_ID = "omMemberDrawer";
    var state = { url: "" };

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

    function drawer() {
        return document.getElementById(DRAWER_ID);
    }

    function detailHost() {
        var box = drawer();
        return box ? box.querySelector("[data-om-detail]") : null;
    }

    function setBusy(host, busy) {
        var skeleton = host.querySelector("[data-om-detail-skeleton]");
        if (skeleton) {
            skeleton.hidden = !busy;
        }
        host.setAttribute("aria-busy", busy ? "true" : "false");
    }

    function showError(host, message) {
        var box = host.querySelector("[data-om-detail-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
    }

    /* ---- Render köməkçiləri ---------------------------------------------- */

    function roleBadge(label, lead) {
        var badge = el("span", "om-role__badge" + (lead ? " om-role__badge--lead" : ""));
        if (lead) {
            badge.appendChild(icon("fa-crown"));
        }
        badge.appendChild(document.createTextNode(label || ""));
        return badge;
    }

    function fact(list, label, value) {
        var row = el("div", "om-detail__fact");
        row.appendChild(el("dt", "om-detail__label", label));
        row.appendChild(el("dd", "om-detail__value", value || "—"));
        list.appendChild(row);
    }

    function section(body, title, count) {
        var wrap = el("section", "om-detail__section");
        var heading = el("h3", "om-detail__heading", title);
        heading.appendChild(el("span", "om-detail__count", String(count)));
        wrap.appendChild(heading);
        body.appendChild(wrap);
        return wrap;
    }

    function chip(text, warn) {
        return el("span", "om-detail__chip" + (warn ? " om-detail__chip--warn" : ""), text);
    }

    function renderIdentity(host, body, person) {
        var identity = el("div", "om-detail__identity");
        identity.appendChild(
            el("span", "om-avatar om-avatar--lg" + (person.is_leader ? " om-avatar--lead" : ""), person.initials || "—")
        );
        var meta = el("div", "om-detail__meta");
        var nameRow = el("div", "om-detail__name");
        var link = el("a", "om-detail__namelink", person.name || "");
        link.href = person.profile_url || "#";
        link.target = "_blank";
        link.rel = "noopener";
        nameRow.appendChild(link);
        if (person.is_leader) {
            var lead = el("span", "ems-badge ems-badge--warning");
            lead.appendChild(icon("fa-crown"));
            lead.appendChild(document.createTextNode(" " + t(host, "leader")));
            nameRow.appendChild(lead);
        }
        if (person.is_active === false) {
            nameRow.appendChild(el("span", "ems-badge ems-badge--muted", t(host, "inactive")));
        }
        meta.appendChild(nameRow);
        var facts = el("dl", "om-detail__facts");
        fact(facts, t(host, "username"), person.username ? "@" + person.username : "");
        fact(facts, t(host, "email"), person.email);
        fact(facts, t(host, "joined"), person.joined);
        meta.appendChild(facts);
        identity.appendChild(meta);
        body.appendChild(identity);
    }

    function renderRoles(host, body, rows) {
        var wrap = section(body, t(host, "roles"), rows.length);
        if (!rows.length) {
            wrap.appendChild(el("p", "om-detail__empty", t(host, "roles-empty")));
            return;
        }
        var list = el("ul", "om-detail__list");
        rows.forEach(function (row) {
            var item = el("li", "om-detail__item");
            var head = el("div", "om-detail__itemhead");
            head.appendChild(roleBadge(row.role_label, row.is_leader));
            if (row.is_primary) {
                head.appendChild(el("span", "ems-badge ems-badge--neutral", t(host, "primary")));
            }
            item.appendChild(head);
            var sub = el("div", "om-detail__itemsub");
            if (row.title) {
                sub.appendChild(chip(t(host, "title") + ": " + row.title));
            }
            if (row.employee_id) {
                sub.appendChild(chip(t(host, "employee") + " " + row.employee_id));
            }
            if (row.scope_unit) {
                var scopeText = row.scope_unit;
                if (row.scope_type_label) {
                    scopeText += " (" + row.scope_type_label + ")";
                }
                if (row.scope_trail) {
                    scopeText += " · " + row.scope_trail;
                }
                sub.appendChild(chip(scopeText));
            } else if (row.scope_missing) {
                sub.appendChild(chip(t(host, "scope-missing"), true));
            } else {
                sub.appendChild(chip(t(host, "scope-all")));
            }
            if (row.since) {
                sub.appendChild(chip(t(host, "since") + ": " + row.since));
            }
            item.appendChild(sub);
            list.appendChild(item);
        });
        wrap.appendChild(list);
    }

    function renderHeads(host, body, units) {
        var wrap = section(body, t(host, "heads"), units.length);
        if (!units.length) {
            wrap.appendChild(el("p", "om-detail__empty", t(host, "heads-empty")));
            return;
        }
        var list = el("ul", "om-detail__list");
        units.forEach(function (unit) {
            var item = el("li", "om-detail__item om-detail__item--head");
            var label = el("span", "om-detail__headlabel");
            label.appendChild(icon("fa-crown"));
            label.appendChild(document.createTextNode(" " + (unit.label || "")));
            item.appendChild(label);
            item.appendChild(
                el("span", "om-detail__headunit", (unit.unit || "") + (unit.type_label ? " · " + unit.type_label : ""))
            );
            list.appendChild(item);
        });
        wrap.appendChild(list);
    }

    function render(host, payload) {
        var body = host.querySelector("[data-om-detail-body]");
        if (!body) {
            return;
        }
        var person = payload.person || {};
        body.textContent = "";
        renderIdentity(host, body, person);
        renderRoles(host, body, payload.memberships || []);
        renderHeads(host, body, payload.headed_units || []);

        var box = drawer();
        var title = document.getElementById(DRAWER_ID + "-title");
        if (title && person.name) {
            title.textContent = person.name;
        }
        var link = box ? box.querySelector("[data-om-detail-profile]") : null;
        if (link) {
            if (person.profile_url) {
                link.href = person.profile_url;
                link.hidden = false;
            } else {
                link.hidden = true;
            }
        }
    }

    function load(host) {
        if (!window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
            return;
        }
        setBusy(host, true);
        showError(host, "");
        var body = host.querySelector("[data-om-detail-body]");
        if (body) {
            body.textContent = "";
        }
        var requestUrl = state.url;
        window.EMSCore.fetchJSON(requestUrl)
            .then(function (payload) {
                if (requestUrl !== state.url) {
                    return; // başqa üzv açılıb — köhnə cavab atılır
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

    /* ---- «Ətraflı» → çekmecə ---------------------------------------------- */

    window.EMSDelegate.on("click", "[data-om-detail-open]", function (event, btn) {
        event.preventDefault();
        var box = drawer();
        var host = detailHost();
        if (!box || !host) {
            return;
        }
        state.url = btn.getAttribute("data-url") || "";
        var title = document.getElementById(DRAWER_ID + "-title");
        if (title) {
            title.textContent = btn.getAttribute("data-name") || title.textContent;
        }
        var link = box.querySelector("[data-om-detail-profile]");
        if (link) {
            link.hidden = true;
        }
        if (window.EMSOverlay && typeof window.EMSOverlay.open === "function") {
            window.EMSOverlay.open(box);
        } else {
            box.hidden = false;
        }
        load(host);
    });

    /* ---- KPI kartı → `om_kind` filtri ------------------------------------ */

    document.addEventListener("ems:kpi-filter", function (event) {
        var target = event.target;
        var root = target && target.closest ? target.closest("[data-om-root]") : null;
        if (!root) {
            return;
        }
        var select = root.querySelector('select[name="om_kind"]');
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
