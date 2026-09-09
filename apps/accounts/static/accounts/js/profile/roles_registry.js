/* ═══════════════════════════════════════════════════════════════════════════
   roles_registry.js — «Təşkilat rolları» reyestrinin çekmecəsi

   Reyestr OXU səthidir: serverə heç nə göndərmir. Rolun tam icazə siyahısı
   səhifə ilə birlikdə `#rolreg-data` JSON blokunda gəlir, çekmecə onu DOM-a
   yazır — ikinci sorğu yoxdur.

   AJAX-safe: `EMSDelegate` (qlobal delegasiya, swap-dan sonra da işləyir) və
   `EMSReady` (idempotent). Mətn HƏMİŞƏ `textContent` ilə yazılır — rol adı və
   izahı istifadəçi məlumatıdır, `innerHTML` burada XSS qapısı olardı.
   ═══════════════════════════════════════════════════════════════════════════ */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    var DRAWER_ID = "rolregDetail";
    var cache = null;

    function entries() {
        if (cache) {
            return cache;
        }
        var node = document.getElementById("rolreg-data");
        if (!node) {
            return [];
        }
        try {
            cache = JSON.parse(node.textContent) || [];
        } catch (err) {
            cache = [];
        }
        return cache;
    }

    /* Panel yenidən yükləndikdə (süzgəc/AJAX swap) köhnə JSON keşi etibarsızdır. */
    document.addEventListener("profile:section:loaded", function () {
        cache = null;
    });

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = String(text);
        }
        return node;
    }

    function metaItem(label, value) {
        var box = el("div", "rolreg-drawer__metaitem");
        box.appendChild(el("span", "rolreg-drawer__metalabel", label));
        box.appendChild(el("span", "rolreg-drawer__metavalue", value));
        return box;
    }

    function renderGroups(host, entry, t) {
        if (entry.wildcard) {
            host.appendChild(el("p", "rolreg-drawer__note", t.tAll));
            return;
        }
        if (!entry.groups || !entry.groups.length) {
            host.appendChild(el("p", "rolreg-drawer__note", t.tNone));
            return;
        }
        entry.groups.forEach(function (group) {
            var box = el("div", "rolreg-drawer__group");
            var head = el("div", "rolreg-drawer__grouphead");
            head.appendChild(el("span", null, group.label));
            head.appendChild(el("span", "rolreg-drawer__count", group.count));
            box.appendChild(head);
            var list = el("ul", "rolreg-drawer__list");
            group.items.forEach(function (item) {
                var li = el("li", "rolreg-drawer__perm");
                li.appendChild(el("span", null, item.label));
                li.appendChild(el("code", "rolreg-drawer__key", item.key));
                list.appendChild(li);
            });
            box.appendChild(list);
            host.appendChild(box);
        });
    }

    function open(roleId) {
        var host = document.querySelector("[data-rolreg-drawer-body]");
        if (!host || !window.EMSOverlay) {
            return;
        }
        var entry = entries().filter(function (row) {
            return String(row.id) === String(roleId);
        })[0];
        if (!entry) {
            return;
        }
        var t = host.dataset;
        host.textContent = "";

        var title = document.getElementById(DRAWER_ID + "-title");
        if (title) {
            title.textContent = entry.label;
        }

        var meta = el("div", "rolreg-drawer__meta");
        meta.appendChild(metaItem(t.tLevel, entry.level));
        meta.appendChild(metaItem(t.tScope, entry.scope_label));
        meta.appendChild(metaItem(t.tMembers, entry.members));
        host.appendChild(meta);

        if (entry.description) {
            host.appendChild(el("p", "rolreg-drawer__desc", entry.description));
        }
        host.appendChild(el("p", "rolreg-drawer__note", t.tLevelnote));

        var permsHead = el("div", "rolreg-drawer__grouphead");
        permsHead.appendChild(el("span", null, t.tPerms));
        permsHead.appendChild(el("span", "rolreg-drawer__count", entry.permission_count));
        host.appendChild(permsHead);

        renderGroups(host, entry, {
            tAll: t.tAll,
            tNone: t.tNone,
        });

        window.EMSOverlay.open(DRAWER_ID);
    }

    DELEGATE.on("click", "[data-rolreg-open]", function (event, button) {
        event.preventDefault();
        open(button.getAttribute("data-rolreg-open"));
    });
})(window, document);
