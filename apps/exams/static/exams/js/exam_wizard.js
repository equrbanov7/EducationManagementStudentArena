/* =========================================================================
   exam_wizard.js — Yeni imtahan sehrbazı (4 addım) naviqasiyası + aydın xəta.

   exam_create_edit_modal.js form-u modal-a inject edəndə `bindModalForm()`
   bu modulun `window.EMSExamWizard.init(form)`-unu çağırır. Modul:
     • addımlar arası keçid (rail / Geri / Növbəti / Yadda saxla),
     • addım-əsaslı minimal validasiya (1-ci addımda ad mütləqdir),
     • server 400 qaytaranda `.field-error`-ları toplayıb yuxarıda AYDIN xəta
       xülasəsi qurur və ilk xətalı addıma keçirir, sahələri işıqlandırır.
   Heç bir sahə adı/ID dəyişdirilmir — yalnız görünüş/naviqasiya.
   ========================================================================= */
(function () {
    "use strict";

    function i18n(key, fallback) {
        var dict = window.EXAM_WIZARD_I18N || {};
        return dict[key] || fallback;
    }

    function clearTransientError(formGroup) {
        if (!formGroup) {
            return;
        }
        formGroup.classList.remove("is-invalid");
        var transient = formGroup.querySelector(".field-error[data-ew-transient]");
        if (transient) {
            transient.parentNode.removeChild(transient);
        }
    }

    function markInvalid(input, message) {
        if (!input) {
            return;
        }
        var formGroup = input.closest(".form-group") || input.parentNode;
        if (!formGroup) {
            return;
        }
        formGroup.classList.add("is-invalid");
        if (message && !formGroup.querySelector(".field-error")) {
            var div = document.createElement("div");
            div.className = "field-error";
            div.setAttribute("data-ew-transient", "1");
            div.textContent = message;
            formGroup.appendChild(div);
        }
    }

    function EMSExamWizardInit(form) {
        if (!form) {
            return;
        }
        var panels = Array.prototype.slice.call(form.querySelectorAll("[data-ew-panel]"));
        if (!panels.length) {
            return;
        }
        var steps = Array.prototype.slice.call(form.querySelectorAll("[data-ew-step-nav]"));
        var dots = Array.prototype.slice.call(form.querySelectorAll("[data-ew-mstep] .ew-msdot"));
        var titleEl = form.querySelector("[data-ew-title]");
        var descEl = form.querySelector("[data-ew-desc]");
        var progEl = form.querySelector("[data-ew-prog]");
        var backBtn = form.querySelector("[data-ew-back]");
        var nextBtn = form.querySelector("[data-ew-next]");
        var submitBtn = form.querySelector("[data-ew-submit]");
        var errBox = form.querySelector("[data-ew-errors]");
        var total = panels.length;
        var current = 0;
        // Redaktə rejimində Yadda saxla bütün addımlarda görünür (sonuncunu
        // gözləmədən saxlamaq olsun); yaratmada yalnız son addımda.
        var editing = form.getAttribute("data-editing") === "1";

        var stepWord = i18n("step", "Addım");

        function setTitleFor(index) {
            var panel = panels[index];
            if (titleEl && panel.getAttribute("data-ew-step-title")) {
                titleEl.textContent = panel.getAttribute("data-ew-step-title");
            }
            if (descEl && panel.getAttribute("data-ew-step-desc")) {
                descEl.textContent = panel.getAttribute("data-ew-step-desc");
            }
        }

        function render() {
            panels.forEach(function (panel, i) {
                panel.classList.toggle("is-active", i === current);
            });
            steps.forEach(function (step, i) {
                step.classList.toggle("is-active", i === current);
                step.classList.toggle("is-done", i < current);
            });
            dots.forEach(function (dot, i) {
                dot.classList.toggle("is-on", i === current);
                dot.classList.toggle("is-done", i < current);
            });
            setTitleFor(current);
            if (progEl) {
                progEl.textContent = stepWord + " " + (current + 1) + " / " + total;
            }
            var isLast = current === total - 1;
            if (backBtn) {
                backBtn.hidden = current === 0;
            }
            if (nextBtn) {
                nextBtn.hidden = isLast;
            }
            if (submitBtn) {
                submitBtn.hidden = !isLast && !editing;
            }
        }

        function goTo(index) {
            current = Math.max(0, Math.min(index, total - 1));
            render();
            var body = form.querySelector(".ew-pane-body");
            if (body) {
                body.scrollTop = 0;
            }
        }

        /* ── step 1: ad mütləqdir ── */
        function validateStep(index) {
            if (index !== 0) {
                return true;
            }
            var titleInput = form.querySelector('[name="title"]');
            if (titleInput && !titleInput.value.trim()) {
                markInvalid(titleInput, i18n("titleRequired", "İmtahan adı mütləqdir."));
                titleInput.focus();
                return false;
            }
            if (titleInput) {
                clearTransientError(titleInput.closest(".form-group"));
            }
            return true;
        }

        if (nextBtn) {
            nextBtn.addEventListener("click", function () {
                if (validateStep(current)) {
                    goTo(current + 1);
                }
            });
        }
        if (backBtn) {
            backBtn.addEventListener("click", function () {
                goTo(current - 1);
            });
        }
        steps.forEach(function (step, i) {
            step.addEventListener("click", function () {
                // İrəli getmək üçün cari addım keçərli olmalıdır; geriyə sərbəst.
                if (i > current && !validateStep(current)) {
                    return;
                }
                goTo(i);
            });
        });

        /* ── imtahan kodu: təsadüfi 6 rəqəm yarat ── */
        var genBtn = form.querySelector("[data-ew-gencode]");
        if (genBtn) {
            genBtn.addEventListener("click", function () {
                var codeInput = form.querySelector('[name="access_code"]');
                if (!codeInput) {
                    return;
                }
                codeInput.value = String(Math.floor(100000 + Math.random() * 900000));
                codeInput.dispatchEvent(new Event("input", { bubbles: true }));
                codeInput.focus();
            });
        }

        /* ── server 400: xətaları topla, xülasə qur, ilk xətalı addıma keç ── */
        function collectErrors() {
            var items = [];
            panels.forEach(function (panel, index) {
                panel.querySelectorAll(".field-error").forEach(function (errEl) {
                    var text = (errEl.textContent || "").trim();
                    if (!text) {
                        return;
                    }
                    var group = errEl.closest(".form-group");
                    if (group) {
                        group.classList.add("is-invalid");
                    }
                    var field = group ? group.querySelector("input, select, textarea") : null;
                    items.push({ panel: index, text: text, field: field });
                });
            });
            var nonField = form.querySelector(".ew-nonfield");
            if (nonField && nonField.textContent.trim()) {
                items.unshift({ panel: 0, text: nonField.textContent.trim(), field: null });
            }
            return items;
        }

        function showErrorSummary(items) {
            if (!errBox) {
                return;
            }
            var list = errBox.querySelector("[data-ew-errlist]");
            var head = errBox.querySelector("[data-ew-errcount]");
            if (head) {
                head.textContent = i18n("errorsTitle", "Zəhmət olmasa aşağıdakı xətaları düzəldin:");
            }
            if (list) {
                list.innerHTML = "";
                items.forEach(function (item) {
                    var li = document.createElement("li");
                    var a = document.createElement("a");
                    a.textContent = item.text;
                    a.addEventListener("click", function () {
                        goTo(item.panel);
                        if (item.field) {
                            item.field.focus();
                        }
                    });
                    li.appendChild(a);
                    list.appendChild(li);
                });
            }
            errBox.hidden = false;
        }

        var errors = collectErrors();
        if (errors.length) {
            showErrorSummary(errors);
            goTo(errors[0].panel);
        } else {
            if (errBox) {
                errBox.hidden = true;
            }
            goTo(0);
        }
    }

    window.EMSExamWizard = { init: EMSExamWizardInit };
})();
