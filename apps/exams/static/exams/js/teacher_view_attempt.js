/* Müəllimin cəhd baxışı («Bax») — exams/teacher/teacher_view_attempt.html (yenidən dizayn 2026-10-17).

   * anonim pəncərənin geri sayımı ([data-review-countdown]);
   * bal halqası ([data-rv-pct] → CSS `--rv-pct`) və bölgü zolağı ([data-rv-share] →
     flex-grow) — dəyər server-dən data-atributla gəlir; inline `style="…"` yazılmır,
     CSSOM ilə qoyulur (CSP `style-src-attr` lazım deyil);
   * «Çap et» ([data-rv-print]).

   AJAX-safe: EMSReady (idempotent, null-safe) + EMSDelegate. */
(function (window, document) {
    "use strict";

    function pad(value) {
        return String(value).padStart(2, "0");
    }

    function startCountdown(node) {
        if (node.dataset.rvCountdownBound === "1") {
            return;
        }
        node.dataset.rvCountdownBound = "1";
        var secondsLeft = parseInt(node.getAttribute("data-review-countdown"), 10);
        if (Number.isNaN(secondsLeft) || secondsLeft <= 0) {
            node.textContent = "00:00:00";
            return;
        }
        function render() {
            var hours = Math.floor(secondsLeft / 3600);
            var minutes = Math.floor((secondsLeft % 3600) / 60);
            node.textContent = pad(hours) + ":" + pad(minutes) + ":" + pad(secondsLeft % 60);
        }
        render();
        var timer = window.setInterval(function () {
            if (!document.contains(node)) {
                window.clearInterval(timer);
                return;
            }
            secondsLeft = Math.max(0, secondsLeft - 1);
            render();
        }, 1000);
    }

    function clampPercent(raw) {
        var value = parseFloat(raw);
        if (Number.isNaN(value)) {
            return null;
        }
        return Math.min(100, Math.max(0, value));
    }

    function paintMeters(root) {
        root.querySelectorAll("[data-rv-pct]").forEach(function (ring) {
            var pct = clampPercent(ring.getAttribute("data-rv-pct"));
            if (pct !== null) {
                ring.style.setProperty("--rv-pct", String(pct));
            }
        });
        root.querySelectorAll("[data-rv-share]").forEach(function (seg) {
            var share = clampPercent(seg.getAttribute("data-rv-share"));
            if (share !== null) {
                seg.style.flexGrow = String(share);
            }
        });
    }

    function init() {
        document.querySelectorAll("[data-review-countdown]").forEach(startCountdown);
        paintMeters(document);
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    if (window.EMSDelegate) {
        window.EMSDelegate.on("click", "[data-rv-print]", function (event) {
            event.preventDefault();
            window.print();
        });
    }

    window.EMSAttemptReview = { paintMeters: paintMeters, clampPercent: clampPercent };
})(window, document);
