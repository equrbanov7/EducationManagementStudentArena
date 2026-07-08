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
            needOne: form.getAttribute("data-i18n-need-one") || gettext("Ən azı bir sual seçin."),
            chooseReason: form.getAttribute("data-i18n-choose-reason") || gettext("Səbəb tipini seçin."),
            tooShort: form.getAttribute("data-i18n-too-short") || gettext("Daha {n} simvol yazın."),
            selected: form.getAttribute("data-i18n-selected") || gettext("{n} sual seçildi"),
            fixBoth: form.getAttribute("data-i18n-fix-both")
                || gettext("{q}-ci sualda səbəb tipini seçib izahı ən azı {min} simvol yazmalısınız, ya da “Apellyasiya et” düyməsini söndürməlisiniz."),
            fixReason: form.getAttribute("data-i18n-fix-reason")
                || gettext("{q}-ci sualda səbəb tipini seçməlisiniz, ya da “Apellyasiya et” düyməsini söndürməlisiniz."),
            fixComment: form.getAttribute("data-i18n-fix-comment")
                || gettext("{q}-ci sualda izahı ən azı {min} simvol yazmalısınız, ya da “Apellyasiya et” düyməsini söndürməlisiniz.")
        };

        var cards = Array.prototype.slice.call(form.querySelectorAll("[data-appeal-card]"));
        var submitBtn = form.querySelector("[data-appeal-submit]");
        var countEl = form.querySelector("[data-appeal-selected-count]");
        var emptyHint = form.querySelector("[data-appeal-empty-hint]");
        var submitHint = form.querySelector("[data-appeal-submit-hint]");
        var submitAttempted = false;
        var searchScope = form.closest(".appeal-shell")
            || form.closest(".appeal-embedded")
            || form.parentElement
            || document;
        var selectMarkedBtn = searchScope.querySelector("[data-appeal-select-marked]");

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

        function isLocked(card) {
            return card.getAttribute("data-appeal-locked") === "1";
        }

        function isActive(card) {
            if (isLocked(card)) {
                return false;
            }
            var p = cardParts(card);
            return !!(p.toggle && p.toggle.checked);
        }

        function setActive(card, active, focusComment) {
            var p = cardParts(card);
            if (isLocked(card)) {
                active = false;
                focusComment = false;
            }
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

        function cardIssues(card) {
            var p = cardParts(card);
            var issues = [];
            if (!isActive(card)) {
                return { valid: true, issues: issues, remaining: 0 };
            }
            if (p.type && !p.type.value) {
                issues.push("reason");
            }
            var len = commentLength(card);
            if (len < minLen) {
                issues.push("comment");
            }
            return { valid: issues.length === 0, issues: issues, remaining: clamp(minLen - len, 0, minLen) };
        }

        function cardValidity(card) {
            var issues = cardIssues(card);
            if (issues.valid) {
                return { valid: true, reason: null, remaining: 0 };
            }
            if (issues.issues.indexOf("reason") !== -1) {
                return { valid: false, reason: "reason", remaining: issues.remaining };
            }
            return { valid: false, reason: "short", remaining: issues.remaining };
        }

        function showCardError(card, show) {
            var p = cardParts(card);
            if (!p.error) { return; }
            var issueState = cardIssues(card);
            if (!show || issueState.valid) {
                p.error.hidden = true;
                card.classList.remove("has-error");
                return;
            }
            var msg = "";
            var hasReasonIssue = issueState.issues.indexOf("reason") !== -1;
            var hasCommentIssue = issueState.issues.indexOf("comment") !== -1;
            if (hasReasonIssue && hasCommentIssue) {
                msg = gettext("Səbəb tipini seçin və izahı ən azı {min} simvol yazın.");
                msg = format(msg, { min: minLen });
            } else if (hasReasonIssue) {
                msg = i18n.chooseReason;
            } else if (hasCommentIssue) {
                msg = format(i18n.tooShort, { n: issueState.remaining });
            }
            p.error.textContent = msg;
            p.error.hidden = false;
            card.classList.add("has-error");
        }

        function activeCards() {
            return cards.filter(isActive);
        }

        function markedCards() {
            return cards.filter(function (card) {
                return card.getAttribute("data-appeal-marked") === "1" && !isLocked(card);
            });
        }

        function updateMarkedButtonState() {
            if (!selectMarkedBtn) { return; }
            var marked = markedCards();
            var allMarkedSelected = marked.length > 0 && marked.every(isActive);
            var labelEl = selectMarkedBtn.querySelector("[data-appeal-select-marked-label]");
            var iconEl = selectMarkedBtn.querySelector("i");
            var selectLabel = selectMarkedBtn.getAttribute("data-label-select") || gettext("İşarələnmişləri seç");
            var clearLabel = selectMarkedBtn.getAttribute("data-label-clear") || gettext("İşarələnmişləri ləğv et");

            if (labelEl) {
                labelEl.textContent = allMarkedSelected ? clearLabel : selectLabel;
            }
            if (iconEl) {
                iconEl.className = allMarkedSelected ? "fas fa-times me-1" : "fas fa-bookmark me-1";
            }
            selectMarkedBtn.setAttribute("aria-pressed", allMarkedSelected ? "true" : "false");
            selectMarkedBtn.classList.toggle("btn-warning", allMarkedSelected);
            selectMarkedBtn.classList.toggle("btn-outline-warning", !allMarkedSelected);
        }

        function formIsValid() {
            var act = activeCards();
            if (act.length === 0) { return false; }
            return act.every(function (c) { return cardValidity(c).valid; });
        }

        function questionNumber(card) {
            var numberEl = card.querySelector(".appeal-question-number");
            var raw = numberEl ? numberEl.textContent.trim() : "";
            if (raw) { return raw; }
            return String(cards.indexOf(card) + 1);
        }

        function firstInvalidCard() {
            return activeCards().filter(function (c) { return !cardIssues(c).valid; })[0] || null;
        }

        function submitErrorMessage() {
            var act = activeCards();
            if (act.length === 0) { return ""; }
            var card = firstInvalidCard();
            if (!card) { return ""; }
            var issues = cardIssues(card).issues;
            var values = { q: questionNumber(card), min: minLen };
            if (issues.indexOf("reason") !== -1 && issues.indexOf("comment") !== -1) {
                return format(i18n.fixBoth, values);
            }
            if (issues.indexOf("reason") !== -1) {
                return format(i18n.fixReason, values);
            }
            return format(i18n.fixComment, values);
        }

        function updateSubmitHint() {
            if (!submitHint) { return; }
            var msg = submitAttempted ? submitErrorMessage() : "";
            submitHint.textContent = msg;
            submitHint.hidden = !msg;
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
                submitBtn.setAttribute("aria-disabled", ok ? "false" : "true");
                submitBtn.classList.toggle("is-ready", ok);
            }
            // Submit cəhdindən sonra səhvləri canlı göstər.
            if (submitAttempted) {
                activeCards().forEach(function (c) { showCardError(c, true); });
            }
            updateSubmitHint();
            updateMarkedButtonState();
        }

        function focusFirstInvalid(card) {
            if (!card) { return; }
            var issues = cardIssues(card).issues;
            var p = cardParts(card);
            var target = issues.indexOf("reason") !== -1 ? p.type : p.comment;
            if (target) {
                window.setTimeout(function () {
                    try { target.focus(); } catch (err) { /* ignore */ }
                }, 250);
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
                p.type.addEventListener("focus", function () { if (!isLocked(card) && !isActive(card)) { setActive(card, true, false); } });
                p.type.addEventListener("change", function () {
                    if (!isLocked(card) && !isActive(card)) { setActive(card, true, false); }
                    if (submitAttempted) { showCardError(card, true); }
                    updateSummary();
                });
            }
            // Auto-aktivləşmə: şərhə yazmağa/fokuslanmağa başlayanda.
            if (p.comment) {
                p.comment.addEventListener("focus", function () { if (!isLocked(card) && !isActive(card)) { setActive(card, true, false); } });
                p.comment.addEventListener("input", function () {
                    if (!isLocked(card) && !isActive(card) && p.comment.value.length > 0) { setActive(card, true, false); }
                    updateCounter(card);
                    if (submitAttempted) { showCardError(card, true); }
                    updateSummary();
                });
            }

            // İlkin vəziyyət: server validation səhvindən sonra dolu gələ bilər.
            var preActive = (p.toggle && p.toggle.checked) || (p.comment && p.comment.value.trim().length > 0);
            setActive(card, !!preActive, false);
        });

        // "İşarələnmiş sualları seç/ləğv et" sürətli əməliyyatı.
        if (selectMarkedBtn) {
            selectMarkedBtn.addEventListener("click", function () {
                var marked = markedCards();
                var shouldClear = marked.length > 0 && marked.every(isActive);
                marked.forEach(function (card) {
                    setActive(card, !shouldClear, false);
                });
            });
        }

        // Sual axtarışı (client-side filtr).
        var searchInput = searchScope.querySelector("[data-appeal-search]");
        if (searchInput) {
            searchInput.addEventListener("input", function () {
                var q = searchInput.value.trim().toLowerCase();
                cards.forEach(function (card) {
                    var text = (card.getAttribute("data-appeal-text") || "").toLowerCase();
                    card.hidden = q !== "" && text.indexOf(q) === -1;
                });
            });
        }

        // Göndərməzdən əvvəl təsdiq modalı (varsa).
        var confirmModalEl = searchScope.querySelector("[data-appeal-confirm-modal]")
            || document.querySelector("[data-appeal-confirm-modal]");
        var confirmBtn = confirmModalEl ? confirmModalEl.querySelector("[data-appeal-confirm-submit]") : null;
        var submitConfirmed = false;
        var bsModalInstance = null;

        function confirmModal() {
            if (!confirmModalEl || !window.bootstrap || !window.bootstrap.Modal) { return null; }
            if (!bsModalInstance) {
                bsModalInstance = window.bootstrap.Modal.getOrCreateInstance(confirmModalEl);
            }
            return bsModalInstance;
        }

        if (confirmBtn) {
            confirmBtn.addEventListener("click", function () {
                submitConfirmed = true;
                var modal = confirmModal();
                if (modal) { modal.hide(); }
                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
            });
        }

        form.addEventListener("submit", function (e) {
            submitAttempted = true;
            if (!formIsValid()) {
                e.preventDefault();
                activeCards().forEach(function (c) { showCardError(c, true); });
                updateSubmitHint();
                var firstInvalid = firstInvalidCard();
                var target = firstInvalid || cards[0];
                if (activeCards().length === 0 && emptyHint) {
                    emptyHint.hidden = false;
                }
                if (target && target.hidden && searchInput) {
                    searchInput.value = "";
                    cards.forEach(function (card) { card.hidden = false; });
                }
                if (target && typeof target.scrollIntoView === "function") {
                    target.scrollIntoView({ behavior: "smooth", block: "center" });
                }
                focusFirstInvalid(firstInvalid);
                return;
            }
            // Etibarlıdır — təsdiq modalı varsa əvvəlcə onu göstər, sonra göndər.
            var modal = confirmModal();
            if (modal && !submitConfirmed) {
                e.preventDefault();
                modal.show();
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
