/* =========================================================================
   appeals_form.js — Student apellyasiya yaratma formasının interaktivliyi.

   Məqsəd (UX):
   - Tələbə əlavə klik etmədən apellyasiya yaza bilsin: şərh sahəsinə yazmağa
     başlayanda və ya səbəb tipini seçəndə həmin sual AVTOMATİK aktivləşir.
   - Hər şərh üçün canlı simvol sayğacı (məs. 12 / 30) və rəng vəziyyəti.
   - Submit yalnız ən azı bir tam doldurulmuş sual olduqda mümkün olsun.
   - Bütün səhv mesajları sadə və yerli (data-* atributları ilə ötürülür).

   AJAX-safe: `window.EMSReady` ilə həm ilk yüklənmədə, həm də profil
   bölməsi AJAX ilə dəyişdiriləndə yenidən işə düşür. İnit idempotentdir
   (form `data-appeals-bound` ilə işarələnir), ona görə listener-lər yığılmır.
   ========================================================================= */
(function () {
    "use strict";

    function clamp(n, min, max) {
        return Math.max(min, Math.min(max, n));
    }

    function format(template, values) {
        return String(template || "").replace(/\{(\w+)\}/g, function (m, key) {
            return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : m;
        });
    }

    function initForm(form) {
        if (!form || form.getAttribute("data-appeals-bound") === "1") {
            return;
        }
        form.setAttribute("data-appeals-bound", "1");
        // JS aktivdir → yığılan body-lər üçün CSS kollaps qaydası işə düşür
        // (no-JS halında body-lər açıq qalır = progressive enhancement).
        form.classList.add("is-enhanced");

        var minLen = parseInt(form.getAttribute("data-min") || "30", 10) || 30;
        var i18n = {
            needOne: form.getAttribute("data-i18n-need-one") || "Ən azı bir sual seçin.",
            chooseReason: form.getAttribute("data-i18n-choose-reason") || "Səbəb tipini seçin.",
            tooShort: form.getAttribute("data-i18n-too-short") || "Daha {n} simvol yazın.",
            selected: form.getAttribute("data-i18n-selected") || "{n} sual seçildi"
        };

        var cards = Array.prototype.slice.call(form.querySelectorAll("[data-appeal-card]"));
        var submitBtn = form.querySelector("[data-appeal-submit]");
        var countEl = form.querySelector("[data-appeal-selected-count]");
        var emptyHint = form.querySelector("[data-appeal-empty-hint]");
        var submitAttempted = false;

        function cardParts(card) {
            return {
                toggle: card.querySelector("[data-appeal-toggle]"),
                body: card.querySelector("[data-appeal-body]"),
                type: card.querySelector("[data-appeal-type]"),
                comment: card.querySelector("[data-appeal-comment]"),
                counterCur: card.querySelector("[data-appeal-counter-cur]"),
                error: card.querySelector("[data-appeal-error]")
            };
        }

        function isActive(card) {
            var p = cardParts(card);
            return !!(p.toggle && p.toggle.checked);
        }

        function setActive(card, active, focusComment) {
            var p = cardParts(card);
            if (p.toggle) {
                p.toggle.checked = active;
            }
            card.classList.toggle("is-active", active);
            if (p.body) {
                p.body.hidden = !active;
                p.body.setAttribute("aria-hidden", active ? "false" : "true");
            }
            if (active && focusComment && p.comment) {
                // Fokus yalnız istifadəçi açıq şəkildə aktivləşdirəndə.
                window.requestAnimationFrame(function () {
                    try { p.comment.focus(); } catch (e) { /* ignore */ }
                });
            }
            if (!active && p.error) {
                p.error.hidden = true;
            }
            updateCounter(card);
            updateSummary();
        }

        function commentLength(card) {
            var p = cardParts(card);
            return p.comment ? p.comment.value.trim().length : 0;
        }

        function updateCounter(card) {
            var p = cardParts(card);
            if (!p.counterCur) { return; }
            var len = commentLength(card);
            p.counterCur.textContent = len;
            var counter = p.counterCur.closest("[data-appeal-counter]");
            if (counter) {
                counter.classList.toggle("is-ok", len >= minLen);
                counter.classList.toggle("is-short", len > 0 && len < minLen);
            }
        }

        function cardValidity(card) {
            // Qaytarır: { valid, reason } — yalnız AKTİV kartlar üçün vacibdir.
            var p = cardParts(card);
            if (!isActive(card)) {
                return { valid: true, reason: null };
            }
            if (p.type && !p.type.value) {
                return { valid: false, reason: "reason" };
            }
            var len = commentLength(card);
            if (len < minLen) {
                return { valid: false, reason: "short", remaining: minLen - len };
            }
            return { valid: true, reason: null };
        }

        function showCardError(card, show) {
            var p = cardParts(card);
            if (!p.error) { return; }
            var v = cardValidity(card);
            if (!show || v.valid) {
                p.error.hidden = true;
                card.classList.remove("has-error");
                return;
            }
            var msg = "";
            if (v.reason === "reason") {
                msg = i18n.chooseReason;
            } else if (v.reason === "short") {
                msg = format(i18n.tooShort, { n: v.remaining });
            }
            p.error.textContent = msg;
            p.error.hidden = false;
            card.classList.add("has-error");
        }

        function activeCards() {
            return cards.filter(isActive);
        }

        function formIsValid() {
            var act = activeCards();
            if (act.length === 0) { return false; }
            return act.every(function (c) { return cardValidity(c).valid; });
        }

        function updateSummary() {
            var count = activeCards().length;
            if (countEl) {
                countEl.textContent = format(i18n.selected, { n: count });
            }
            if (emptyHint) {
                // Xəbərdarlıq yalnız submit cəhdindən sonra və heç nə seçilməyəndə.
                emptyHint.hidden = !(count === 0 && submitAttempted);
            }
            if (submitBtn) {
                var ok = formIsValid();
                submitBtn.disabled = !ok;
                submitBtn.classList.toggle("is-ready", ok);
            }
            // Submit cəhdindən sonra səhvləri canlı göstər.
            if (submitAttempted) {
                activeCards().forEach(function (c) { showCardError(c, true); });
            }
        }

        cards.forEach(function (card) {
            var p = cardParts(card);

            if (p.toggle) {
                p.toggle.addEventListener("change", function () {
                    setActive(card, p.toggle.checked, p.toggle.checked);
                });
            }
            // Auto-aktivləşmə: səbəb tipini seçəndə.
            if (p.type) {
                p.type.addEventListener("focus", function () { if (!isActive(card)) { setActive(card, true, false); } });
                p.type.addEventListener("change", function () {
                    if (!isActive(card)) { setActive(card, true, false); }
                    if (submitAttempted) { showCardError(card, true); }
                    updateSummary();
                });
            }
            // Auto-aktivləşmə: şərhə yazmağa/fokuslanmağa başlayanda.
            if (p.comment) {
                p.comment.addEventListener("focus", function () { if (!isActive(card)) { setActive(card, true, false); } });
                p.comment.addEventListener("input", function () {
                    if (!isActive(card) && p.comment.value.length > 0) { setActive(card, true, false); }
                    updateCounter(card);
                    if (submitAttempted) { showCardError(card, true); }
                    updateSummary();
                });
            }

            // İlkin vəziyyət: server validation səhvindən sonra dolu gələ bilər.
            var preActive = (p.toggle && p.toggle.checked) || (p.comment && p.comment.value.trim().length > 0);
            setActive(card, !!preActive, false);
        });

        // "İşarələnmiş sualları seç" sürətli əməliyyatı.
        var selectMarkedBtn = form.querySelector("[data-appeal-select-marked]");
        if (selectMarkedBtn) {
            selectMarkedBtn.addEventListener("click", function () {
                cards.forEach(function (card) {
                    if (card.getAttribute("data-appeal-marked") === "1") {
                        setActive(card, true, false);
                    }
                });
            });
        }

        // Sual axtarışı (client-side filtr).
        var searchInput = form.querySelector("[data-appeal-search]");
        if (searchInput) {
            searchInput.addEventListener("input", function () {
                var q = searchInput.value.trim().toLowerCase();
                cards.forEach(function (card) {
                    var text = (card.getAttribute("data-appeal-text") || "").toLowerCase();
                    card.hidden = q !== "" && text.indexOf(q) === -1;
                });
            });
        }

        form.addEventListener("submit", function (e) {
            submitAttempted = true;
            if (!formIsValid()) {
                e.preventDefault();
                activeCards().forEach(function (c) { showCardError(c, true); });
                var firstInvalid = activeCards().filter(function (c) { return !cardValidity(c).valid; })[0];
                var target = firstInvalid || cards[0];
                if (activeCards().length === 0 && emptyHint) {
                    emptyHint.hidden = false;
                }
                if (target && typeof target.scrollIntoView === "function") {
                    target.scrollIntoView({ behavior: "smooth", block: "center" });
                }
            }
        });

        updateSummary();
    }

    function initAll() {
        var forms = document.querySelectorAll("[data-appeals-form]");
        Array.prototype.forEach.call(forms, initForm);
    }

    if (window.EMSReady) {
        window.EMSReady(initAll);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
