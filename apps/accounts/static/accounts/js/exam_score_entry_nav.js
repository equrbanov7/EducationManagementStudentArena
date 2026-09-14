/*
 * exam_score_entry_nav.js — İmtahan Mərkəzi: bal köçürmə panelinin naviqasiya
 * və köməkçi davranışları (2026-09-14). `exam_score_entry.js`-in QARDAŞIDIR
 * (modul-ölçü büdcəsi, SOFT_CAP=600); ortaq funksiyalar `window.EMSExamScoreEntry`
 * API-sindən (əsas fayl `defer` ilə bundan əvvəl yüklənir).
 *
 *   · «İmtahan növü» çipi seçimlə sinxron; toggle etiketi boş qalarsa server
 *     etiketi (`data-ese-exam-kind-label`) ilə doldurulur — sahibin serverindəki
 *     «boş select» şikayəti;
 *   · «Dəyişiklikləri sıfırla» — bütün sahələr server dəyərinə;
 *   · sətrin «tarixçə» düyməsi → `<template>` klonu çekmecəyə (əlavə sorğu yox);
 *   · görünüş / sıra / vəziyyət / növ çip linkləri paneli SPA ilə yenidən
 *     yükləyir; loader bölməni tanımırsa tam səhifə keçidi.
 *
 * CSP: inline yoxdur. AJAX-safe: `EMSDelegate` (açarlar `data-ese-exam-kind`,
 * `data-ese-reset`, `data-ese-history`, `data-ese-nav` — yalnız burada).
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    function api() {
        return window.EMSExamScoreEntry || null;
    }

    function root() {
        return document.querySelector("[data-ese-root]");
    }

    /* ---- İmtahan növü çipi + toggle etiketi (sahibin «boş select» şikayəti) ---- */

    function syncExamKind(host) {
        var select = host.querySelector("[data-ese-exam-kind]");
        var chip = host.querySelector("[data-ese-exam-kind-chip]");
        if (!select) {
            return;
        }
        var option = select.options[select.selectedIndex];
        var label = option && option.textContent.trim() ? option.textContent.trim() : select.getAttribute("data-ese-exam-kind-label") || "";
        if (chip) {
            chip.textContent = label;
        }
        var wrap = select.closest(".bootstrap-single-select");
        var text = wrap ? wrap.querySelector(".bootstrap-single-select__label-text") : null;
        if (text && !text.textContent.trim()) {
            text.textContent = label;
        }
    }

    DELEGATE.on("change", "[data-ese-exam-kind]", function () {
        var host = root();
        if (host) {
            syncExamKind(host);
        }
    });

    /* ---- Sıfırla ------------------------------------------------------------- */

    DELEGATE.on("click", "[data-ese-reset]", function (event) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        api().rows(host).forEach(function (row) {
            var input = api().scoreInput(row);
            if (input) {
                input.value = input.getAttribute("data-initial") || "";
            }
            row.querySelectorAll("[data-ese-q]").forEach(function (select) {
                select.value = select.getAttribute("data-initial") || "";
                api().syncPlaceholderToggle(select);
                if (window.EMSBootstrapSelect) {
                    window.EMSBootstrapSelect.sync(select);
                }
            });
        });
        api().syncAll(host);
    });

    /* ---- Tarixçə çekmecəsi ---------------------------------------------------- */

    DELEGATE.on("click", "[data-ese-history]", function (event, btn) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        var id = btn.getAttribute("data-ese-history");
        var template = host.querySelector('[data-ese-history-tpl="' + id + '"]');
        var body = host.querySelector("[data-ese-drawer-body]");
        if (!template || !body) {
            return;
        }
        body.textContent = "";
        body.appendChild(template.content.cloneNode(true));
        if (window.EMSOverlay) {
            window.EMSOverlay.open("eseHistoryDrawer");
        }
    });

    /* ---- Görünüş / sıra / çip linkləri — paneli SPA ilə yenidən yüklə ---------- */

    DELEGATE.on("click", "[data-ese-nav]", function (event, link) {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }
        var href = link.getAttribute("href") || "";
        var panel = link.closest("[data-profile-section-panel]");
        var section = panel ? panel.getAttribute("data-profile-section-panel") : "";
        if (!href || !section || typeof window.EMSProfileLoadSection !== "function") {
            return; // kabinetdən kənar: linkin öz davranışı
        }
        event.preventDefault();
        var url = new URL(href, window.location.href);
        url.searchParams.set("section", section);
        var result = window.EMSProfileLoadSection(section, url.pathname + url.search);
        // Loader bölməni tanımırsa (`false`) səssiz qalmasın — tam səhifə keçidi.
        if (result && typeof result.then === "function") {
            result.then(function (ok) {
                if (ok === false) {
                    window.location.assign(url.pathname + url.search);
                }
            });
        }
    });


    window.EMSReady(function () {
        var host = root();
        if (!host || !api()) {
            return;
        }
        syncExamKind(host);
        // Komponent gücləndirməsi (`bootstrap_select.js`) bundan sonra da işləyə
        // bilər — toggle etiketi boş qalıbsa server etiketi ilə doldur.
        window.setTimeout(function () {
            var again = root();
            if (again) {
                syncExamKind(again);
            }
        }, 0);
    });
})(window, document);
