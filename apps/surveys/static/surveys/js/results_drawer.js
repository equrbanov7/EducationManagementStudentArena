/* =========================================================================
   results_drawer.js — müəllim kartı çekməcəsi.

   «Ətraflı» (`[data-svr-detail]`) → `ems_ui/overlay.js` ilə çekməcə açılır
   (fokus tələsi, Escape, fokusun qayıtması), gövdə `surveys:results_teacher`
   fraqmentindən (server-render, avtomatik escape olunmuş Django şablonu —
   kabinet bölmə yükləyicisi kimi) doldurulur; qrafiklər və şərh axtarışı
   yerləşdikdən sonra qoşulur. Köhnə sorğu yenisi açılanda ləğv olunur.
   ========================================================================= */
(function (window, document) {
    "use strict";

    var NS = (window.EMSSurveyResults = window.EMSSurveyResults || {});
    if (NS.drawer) {
        return;
    }

    var controller = null;

    function destroyCharts(scope) {
        scope.querySelectorAll("canvas").forEach(function (canvas) {
            if (canvas._svrChart) {
                canvas._svrChart.destroy();
                canvas._svrChart = null;
            }
        });
    }

    function loading(t) {
        var box = document.createElement("div");
        box.className = "svr-drawer__loading";
        box.setAttribute("role", "status");
        var label = document.createElement("span");
        label.className = "sr-only";
        label.textContent = t.i18nLoading || "";
        box.appendChild(label);
        for (var i = 0; i < 4; i += 1) {
            var line = document.createElement("div");
            line.className = "skeleton skeleton-line" + (i === 0 ? " skeleton-line--lg" : "");
            line.setAttribute("aria-hidden", "true");
            box.appendChild(line);
        }
        return box;
    }

    function failure(t) {
        var box = document.createElement("div");
        box.className = "ems-state ems-state--error svr-state";
        box.setAttribute("role", "status");
        var text = document.createElement("p");
        text.className = "ems-state__title";
        text.textContent = t.i18nError || "";
        box.appendChild(text);
        return box;
    }

    function hydrate(body, print) {
        var detail = body.querySelector("[data-svr-detail-root]");
        if (!detail) {
            return;
        }
        if (print && detail.getAttribute("data-print-url")) {
            print.setAttribute("href", detail.getAttribute("data-print-url"));
            print.hidden = false;
        }
        if (NS.charts) {
            detail.querySelectorAll("[data-svr-charts]").forEach(function (container) {
                NS.charts.render(container);
            });
        }
        if (NS.text) {
            NS.text.scan(detail);
        }
    }

    function open(button) {
        var overlay = document.getElementById("svr-drawer");
        if (!overlay) {
            return;
        }
        var body = overlay.querySelector("[data-svr-drawer-body]");
        var title = overlay.querySelector("[data-svr-drawer-title]");
        var print = overlay.querySelector("[data-svr-drawer-print]");
        var t = (overlay.closest("[data-i18n-n]") || overlay).dataset;
        if (!body) {
            return;
        }
        if (title && button.getAttribute("data-svr-detail-title")) {
            title.textContent = button.getAttribute("data-svr-detail-title");
        }
        if (print) {
            print.hidden = true;
            print.removeAttribute("href");
        }
        destroyCharts(body);
        body.textContent = "";
        body.appendChild(loading(t));
        body.setAttribute("aria-busy", "true");
        if (window.EMSOverlay) {
            window.EMSOverlay.open(overlay);
        } else {
            overlay.hidden = false;
        }
        if (controller) {
            controller.abort();
        }
        controller = typeof AbortController === "function" ? new AbortController() : null;
        var options = {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest", Accept: "text/html" }
        };
        if (controller) {
            options.signal = controller.signal;
        }
        window
            .fetch(button.getAttribute("data-svr-detail"), options)
            .then(function (response) {
                return response.text().then(function (html) {
                    return { ok: response.ok, status: response.status, html: html };
                });
            })
            .then(function (result) {
                body.removeAttribute("aria-busy");
                if (!result.html || result.status >= 500) {
                    body.textContent = "";
                    body.appendChild(failure(t));
                    return;
                }
                body.innerHTML = result.html; // eyni mənşəli, server-render (escape olunmuş) fraqment
                hydrate(body, print);
            })
            .catch(function (err) {
                if (err && err.name === "AbortError") {
                    return;
                }
                body.removeAttribute("aria-busy");
                body.textContent = "";
                body.appendChild(failure(t));
            });
    }

    window.EMSDelegate.on("click", "[data-svr-detail]", function (event, button) {
        event.preventDefault();
        open(button);
    });

    window.EMSReady.once("svr-drawer-close", function () {
        document.addEventListener("ems:overlay:close", function (event) {
            var overlay = event.target;
            if (!overlay || overlay.id !== "svr-drawer") {
                return;
            }
            if (controller) {
                controller.abort();
                controller = null;
            }
            var body = overlay.querySelector("[data-svr-drawer-body]");
            if (body) {
                destroyCharts(body);
            }
        });
    });

    NS.drawer = { open: open };
})(window, document);
