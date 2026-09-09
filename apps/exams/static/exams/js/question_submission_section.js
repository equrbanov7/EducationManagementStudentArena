/* «Sual göndərişləri» bölməsi — KPI status filtrləri + «yol» çekmecəsi.
 *
 * NƏ EDİR
 * -------
 * 1. KPI kartına klik (`ems:kpi-filter`, `ems_ui/nav.js`) filtr panelinin
 *    `qsub_status` seçicisini dəyişir və AVTO tətbiqi işə salır — kart və
 *    select həmişə eyni vəziyyəti göstərir.
 * 2. Sətrin «yol» düyməsi tək çekmecəni (`#qsubDrawer`) həmin göndərişin
 *    detalı ilə doldurub açır.  Məlumat bölmənin `application/json` blokundan
 *    (`#qsubDrawerData`) gəlir; DOM `textContent` ilə qurulur (innerHTML YOX).
 *
 * AJAX-SAFE: `EMSDelegate` (document səviyyəsi) + `EMSReady.once`; panel swap
 * script-i yenidən icra etsə də dinləyicilər yığılmır.
 */
(function () {
    "use strict";

    function payload() {
        var node = document.getElementById("qsubDrawerData");
        if (!node) {
            return {};
        }
        try {
            return JSON.parse(node.textContent || "{}");
        } catch (err) {
            return {};
        }
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = text;
        }
        return node;
    }

    function metaList(rows) {
        var dl = el("dl", "qsub-drawer__meta");
        (rows || []).forEach(function (item) {
            dl.appendChild(el("dt", null, item.label));
            dl.appendChild(el("dd", null, item.value));
        });
        return dl;
    }

    function timeline(events) {
        // Markup `templates/partials/ems_ui/_timeline.html` ilə eynidir —
        // üslub ORTAQ fayldan (`ems_ui/timeline.css`) gəlir, kopyalanmır.
        var list = el("ol", "ems-tl");
        (events || []).forEach(function (event) {
            var item = el("li", "ems-tl__item");
            var gutter = el("div", "ems-tl__gutter");
            gutter.setAttribute("aria-hidden", "true");
            gutter.appendChild(el("span", "ems-tl__dot ems-tl__dot--" + (event.tone || "neutral")));
            gutter.appendChild(el("span", "ems-tl__line"));
            item.appendChild(gutter);

            var main = el("div", "ems-tl__main");
            var head = el("div", "ems-tl__head");
            head.appendChild(el("span", "ems-tl__who", event.actor));
            head.appendChild(el("span", "ems-tl__when", event.date));
            main.appendChild(head);
            main.appendChild(el("div", "ems-tl__what", event.action));
            if (event.reason) {
                main.appendChild(el("div", "ems-tl__reason", event.reason));
            }
            item.appendChild(main);
            list.appendChild(item);
        });
        return list;
    }

    function render(box, detail) {
        box.textContent = "";
        var head = el("div", "qsub-drawer__head");
        head.appendChild(el("p", "qsub-drawer__title", detail.title));
        head.appendChild(el("span", detail.statusClass, detail.status));
        box.appendChild(head);

        if (detail.bank && detail.bank.text) {
            box.appendChild(el("p", "qsub-drawer__bank", detail.bank.text));
        }
        box.appendChild(metaList(detail.meta));

        if (detail.events && detail.events.length) {
            box.appendChild(timeline(detail.events));
        } else {
            box.appendChild(el("p", "qsub-drawer__placeholder", box.getAttribute("data-empty-text") || ""));
        }

        if (detail.url) {
            var link = el("a", "ems-btn ems-btn--primary qsub-drawer__open", box.getAttribute("data-open-text") || "");
            link.href = detail.url;
            box.appendChild(link);
        }
    }

    window.EMSDelegate.on("click", "[data-qsub-drawer]", function (event, btn) {
        event.preventDefault();
        var box = document.querySelector("[data-qsub-drawer-body]");
        if (!box || !window.EMSOverlay) {
            return;
        }
        var detail = payload()[btn.getAttribute("data-qsub-drawer")];
        if (!detail) {
            return;
        }
        render(box, detail);
        window.EMSOverlay.open("qsubDrawer");
    });

    // KPI kartı → filtr panelinin status seçicisi (tək həqiqət mənbəyi URL-dir).
    window.EMSReady.once("qsub-kpi-status-filter", function () {
        document.addEventListener("ems:kpi-filter", function (event) {
            var root = event.target && event.target.closest ? event.target.closest("[data-qsub-root]") : null;
            if (!root) {
                return;
            }
            var form = root.querySelector("[data-ems-filters]");
            var select = form ? form.querySelector('select[name="qsub_status"]') : null;
            if (!form || !select || !window.EMSFilterBar) {
                return;
            }
            var wanted = event.detail && event.detail.filter ? event.detail.filter : "";
            select.value = wanted === "all" ? "" : wanted;
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(select);
            }
            window.EMSFilterBar.apply(form);
        });
    });
})();
