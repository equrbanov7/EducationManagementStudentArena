/* =========================================================================
   appeals_review.js — Müəllim/reviewer apellyasiya qərar formasının UX-i.

   - Qərar (qəbul/rədd) seçiləndə "cavab/izah" sahəsi tələb olunur (ulduz +
     vurğu) və fokuslanır.
   - "Qəbul et" seçiləndə "veriləcək bal" sahəsi açılır; əvvəlki → yeni bal
     canlı göstərilir (həm kart, həm ümumi).
   - Qərar verilmiş (kilidli) item-lər heç bir interaktiv kontrola malik deyil.
   - Submit yalnız hər qərarın izahı olduqda mümkündür (backend qaydası ilə eyni).

   AJAX-safe: window.EMSReady + window.EMSAppealsReview.init (dashboard swap).
   ========================================================================= */
(function () {
    "use strict";

    function format(template, values) {
        return String(template || "").replace(/\{(\w+)\}/g, function (m, key) {
            return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : m;
        });
    }

    function num(value) {
        var n = parseFloat(value);
        return isNaN(n) ? 0 : n;
    }

    function fmtNum(n) {
        var r = Math.round(n * 100) / 100;
        return String(r);
    }

    function initForm(form) {
        if (!form || form.getAttribute("data-appeals-review-bound") === "1") {
            return;
        }
        form.setAttribute("data-appeals-review-bound", "1");

        var i18n = {
            needResponse: form.getAttribute("data-i18n-need-response") || gettext("Cavab/izah mətni yazın."),
            decisions: form.getAttribute("data-i18n-decisions") || gettext("{n} qərar verildi")
        };
        var currentScore = num(form.getAttribute("data-current-score"));
        var rawMax = form.getAttribute("data-max-score");
        var maxScore = (rawMax === null || rawMax === "") ? null : num(rawMax);
        var newScoreEl = form.querySelector("[data-review-new-score]");

        var cards = Array.prototype.slice.call(form.querySelectorAll('[data-review-card]'));
        // Kilidli kartlar interaktiv deyil.
        var editable = cards.filter(function (c) { return c.getAttribute("data-review-locked") !== "1"; });
        var submitBtn = form.querySelector("[data-review-submit]");
        var countEl = form.querySelector("[data-review-decisions-count]");
        var submitAttempted = false;

        function parts(card) {
            return {
                decision: card.querySelector("[data-review-decision]"),
                response: card.querySelector("[data-review-response]"),
                error: card.querySelector("[data-review-error]"),
                required: card.querySelector("[data-review-required]"),
                panel: card.querySelector(".appeal-review-panel"),
                points: card.querySelector("[data-review-points]"),
                pointsInput: card.querySelector("[data-review-points-input]"),
                cardNext: card.querySelector("[data-review-card-next]")
            };
        }

        function decisionValue(card) {
            var p = parts(card);
            return p.decision ? p.decision.value : "";
        }

        function isDecided(card) {
            var v = decisionValue(card);
            return v === "accept" || v === "reject";
        }

        function cardMax(card) {
            return num(card.getAttribute("data-review-max")) || 0;
        }

        function existingDelta(card) {
            return num(card.getAttribute("data-review-existing-delta")) || 0;
        }

        function awardForCard(card) {
            var configured = num(card.getAttribute("data-review-award"));
            return configured > 0 ? configured : 1;
        }

        function awardedForCard(card) {
            var p = parts(card);
            if (!p.pointsInput) { return awardForCard(card); }
            var v = num(p.pointsInput.value);
            var mx = cardMax(card);
            if (v < 0) { v = 0; }
            if (mx && v > mx) { v = mx; }
            return v;
        }

        function scoreDeltaForCard(card) {
            var v = decisionValue(card);
            if (v === "accept") {
                return awardedForCard(card) - existingDelta(card);
            }
            if (v === "reject") {
                return -existingDelta(card);
            }
            return 0;
        }

        function isValid(card) {
            if (!isDecided(card)) { return true; }
            var p = parts(card);
            return !!(p.response && p.response.value.trim().length > 0);
        }

        function recomputeScores() {
            var sum = 0;
            editable.forEach(function (card) {
                var p = parts(card);
                var delta = scoreDeltaForCard(card);
                sum += delta;
                if (decisionValue(card) === "accept") {
                    if (p.cardNext) {
                        p.cardNext.textContent = fmtNum(currentScore + delta);
                    }
                } else if (p.cardNext) {
                    p.cardNext.textContent = fmtNum(currentScore + delta);
                }
            });
            if (newScoreEl) {
                var total = currentScore + sum;
                if (total < 0) { total = 0; }
                if (maxScore !== null && total > maxScore) { total = maxScore; }
                newScoreEl.textContent = fmtNum(total) + (maxScore !== null ? " / " + fmtNum(maxScore) : "");
            }
        }

        function reflectDecision(card, focusResponse) {
            var p = parts(card);
            var v = decisionValue(card);
            var decided = v === "accept" || v === "reject";
            if (p.panel) {
                p.panel.classList.toggle("is-decided", decided);
            }
            if (p.required) {
                p.required.hidden = !decided;
            }
            if (p.points) {
                p.points.hidden = v !== "accept";
            }
            if (decided && focusResponse && p.response) {
                window.requestAnimationFrame(function () {
                    try { p.response.focus(); } catch (e) { /* ignore */ }
                });
            }
            if (!decided && p.error) {
                p.error.hidden = true;
                card.classList.remove("has-error");
            }
        }

        function showError(card, show) {
            var p = parts(card);
            if (!p.error) { return; }
            if (!show || isValid(card)) {
                p.error.hidden = true;
                card.classList.remove("has-error");
                return;
            }
            p.error.textContent = i18n.needResponse;
            p.error.hidden = false;
            card.classList.add("has-error");
        }

        function decidedCards() {
            return editable.filter(isDecided);
        }

        function updateSummary() {
            if (countEl) {
                countEl.textContent = format(i18n.decisions, { n: decidedCards().length });
            }
            recomputeScores();
            if (submitAttempted) {
                decidedCards().forEach(function (c) { showError(c, true); });
            }
        }

        editable.forEach(function (card) {
            var p = parts(card);
            if (p.decision) {
                p.decision.addEventListener("change", function () {
                    reflectDecision(card, true);
                    if (submitAttempted) { showError(card, true); }
                    updateSummary();
                });
            }
            if (p.response) {
                p.response.addEventListener("input", function () {
                    if (submitAttempted) { showError(card, true); }
                });
            }
            if (p.pointsInput) {
                p.pointsInput.addEventListener("input", recomputeScores);
            }
            reflectDecision(card, false);
        });

        form.addEventListener("submit", function (e) {
            submitAttempted = true;
            var invalid = decidedCards().filter(function (c) { return !isValid(c); });
            if (invalid.length > 0) {
                e.preventDefault();
                invalid.forEach(function (c) { showError(c, true); });
                if (invalid[0].scrollIntoView) {
                    invalid[0].scrollIntoView({ behavior: "smooth", block: "center" });
                }
            }
        });

        // ── 5 dəqiqəlik redaktə sayğacı ──
        function pad(n) { return (n < 10 ? "0" : "") + n; }
        Array.prototype.forEach.call(form.querySelectorAll("[data-appeal-countdown]"), function (el) {
            var remaining = parseInt(el.getAttribute("data-appeal-countdown"), 10);
            if (isNaN(remaining)) { return; }
            var windowBox = el.closest("[data-review-window]");
            var card = el.closest("[data-review-card]");
            var panel = card ? card.querySelector(".appeal-review-panel") : null;
            var timer = null;
            function tick() {
                el.textContent = pad(Math.floor(remaining / 60)) + ":" + pad(remaining % 60);
                if (remaining <= 0) {
                    if (windowBox) { windowBox.classList.add("is-expired"); }
                    if (panel) { panel.classList.add("is-expired"); }
                    if (timer) { clearInterval(timer); }
                    updateSummary();
                    return;
                }
                remaining -= 1;
            }
            tick();
            timer = setInterval(tick, 1000);
        });

        updateSummary();
    }

    function initAll() {
        var forms = document.querySelectorAll("[data-appeals-review-form]");
        Array.prototype.forEach.call(forms, initForm);
    }

    // Dashboard daxili AJAX swap-dan sonra əl ilə çağırmaq üçün açıq init.
    window.EMSAppealsReview = window.EMSAppealsReview || { init: initAll };

    if (window.EMSReady) {
        window.EMSReady(initAll);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
