/* =========================================================================
   Anonim sorğu forması — simvol sayğacı + ikiqat göndərişə qarşı kilid.

   AJAX-SAFE: yalnız EMSDelegate (document üzərində delegasiya) və EMSReady
   (idempotent, null-safe) işlədilir. Yoxlama SERVERDƏDİR — bu skript olmasa da
   forma tam işləyir (proqressiv inkişaf).
   ========================================================================= */
(function (window, document) {
    "use strict";

    var LIMIT = 1500;
    var NEAR = 0.9;

    function updateCounter(field) {
        var targetId = field.getAttribute("data-svy-counter");
        var counter = targetId ? document.getElementById(targetId) : null;
        if (!counter) {
            return;
        }
        var max = parseInt(field.getAttribute("maxlength"), 10) || LIMIT;
        var length = (field.value || "").length;
        counter.textContent = length + " / " + max;
        counter.classList.toggle("is-near", length >= Math.floor(max * NEAR));
    }

    function bindDelegates() {
        if (!window.EMSDelegate || window.__emsSurveyFormBound) {
            return;
        }
        window.__emsSurveyFormBound = true;

        window.EMSDelegate.on("input", "[data-svy-counter]", function (event, field) {
            updateCounter(field);
        });

        // İkiqat göndəriş: server unikal məhdudiyyətlə qoruyur; bu yalnız UX-dir.
        window.EMSDelegate.on("submit", "form[data-svy-form]", function (event, form) {
            if (form.getAttribute("data-svy-sending") === "1") {
                event.preventDefault();
                return;
            }
            form.setAttribute("data-svy-sending", "1");
            form.setAttribute("aria-busy", "true");
            var button = form.querySelector("[data-svy-submit]");
            if (button) {
                button.setAttribute("disabled", "disabled");
            }
        });

        // bfcache ilə geri qayıdanda (brauzerin «geri» düyməsi) kilid açılsın.
        window.addEventListener("pageshow", function () {
            var forms = document.querySelectorAll("form[data-svy-form][data-svy-sending]");
            for (var i = 0; i < forms.length; i += 1) {
                forms[i].removeAttribute("data-svy-sending");
                forms[i].removeAttribute("aria-busy");
                var button = forms[i].querySelector("[data-svy-submit]");
                if (button) {
                    button.removeAttribute("disabled");
                }
            }
        });
    }

    function init() {
        bindDelegates();
        var fields = document.querySelectorAll("[data-svy-counter]");
        for (var i = 0; i < fields.length; i += 1) {
            updateCounter(fields[i]);
        }
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    } else {
        document.addEventListener("DOMContentLoaded", init);
    }
})(window, document);
