/* Toplu sual workbench-i — önizləmə SKELETONU + göndərişdən əvvəl TƏSDİQ xülasəsi
 * (sahib 2026-09-20). Ortaq partial-da (_bulk_question_workbench.html) 5 səhifə
 * üçün eyni davranış:
 *  • «Önizlə» göndərilən kimi nəticə yerində skeleton görünür (səhifə POST ilə
 *    yenilənənədək) — istifadəçi boş ekran görmür;
 *  • «Göndər / Yadda saxla» basılanda EMSConfirm ilə qısa xülasə: seçilmiş sual
 *    sayı, onlarda xəta/xəbərdarlıq, göndəriş meta-sı (başlıq, dil, fənn, imtahan
 *    növü, qruplar, qeyd) — təsdiqdən sonra forma normal yolla gedir.
 * Mətnlər `.bulk-page-wrapper` data-atributlarından oxunur (djangojs borcu yox).
 * Capture fazası: testQuestionBank.js-in öz submit qoruyucusundan ƏVVƏL işə düşür. */
(function () {
    "use strict";
    var wrap = document.querySelector(".bulk-page-wrapper");
    if (!wrap || wrap.dataset.wbConfirmInit === "1") return;
    wrap.dataset.wbConfirmInit = "1";
    var T = wrap.dataset;

    // ── Önizləmə skeletonu ──────────────────────────────────────────────────
    function skeletonCard() {
        var card = document.createElement("div");
        card.className = "wb-skeleton__card";
        card.innerHTML =
            '<span class="skeleton skeleton-circle"></span>' +
            '<div class="wb-skeleton__body">' +
            '<span class="skeleton skeleton-line skeleton-line--lg"></span>' +
            '<span class="skeleton skeleton-line skeleton-line--sm"></span>' +
            '<div class="wb-skeleton__opts"><span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span></div>' +
            "</div>";
        return card;
    }
    function showPreviewSkeleton() {
        var old = wrap.querySelector(".results-container");
        var box = document.createElement("section");
        box.className = "wb-skeleton";
        box.setAttribute("role", "status");
        box.setAttribute("aria-live", "polite");
        var head = document.createElement("div");
        head.className = "wb-skeleton__head";
        head.innerHTML = '<i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i>';
        head.appendChild(document.createTextNode(" " + (T.skeletonText || "…")));
        box.appendChild(head);
        var chips = document.createElement("div");
        chips.className = "wb-skeleton__chips";
        for (var i = 0; i < 4; i += 1) {
            var c = document.createElement("span");
            c.className = "skeleton skeleton-pill";
            chips.appendChild(c);
        }
        box.appendChild(chips);
        for (var j = 0; j < 3; j += 1) box.appendChild(skeletonCard());
        if (old) {
            old.replaceWith(box);
        } else {
            var main = wrap.querySelector(".main-card");
            if (main) main.insertAdjacentElement("afterend", box);
            else wrap.appendChild(box);
        }
        if (box.scrollIntoView) box.scrollIntoView({ block: "start", behavior: "smooth" });
    }
    var previewForm = wrap.querySelector(".split-layout");
    if (previewForm) {
        // Bubbling + sonuncu: testQuestionBank.js fayl çıxarması üçün preventDefault
        // edibsə skeleton göstərilmir (o, çıxarmadan sonra yenidən requestSubmit edir).
        previewForm.addEventListener("submit", function (event) {
            if (event.defaultPrevented) return;
            showPreviewSkeleton();
        });
    }

    // ── Göndərişdən əvvəl təsdiq xülasəsi ──────────────────────────────────
    function selectedText(sel) {
        if (!sel) return "";
        var opt = sel.options[sel.selectedIndex];
        return sel.value && opt ? opt.textContent.trim() : "";
    }
    function line(label, value) {
        return value ? label + ": " + value + "\n" : "";
    }
    function summary() {
        var checked = Array.prototype.slice.call(wrap.querySelectorAll(".qcheck:checked"));
        var errors = 0;
        var warnings = 0;
        checked.forEach(function (cb) {
            var card = cb.closest(".q-card");
            if (!card) return;
            if (card.classList.contains("has-error")) errors += 1;
            else if (card.classList.contains("has-warning")) warnings += 1;
        });
        var text = "";
        var title = document.getElementById("qsubTitle");
        if (title) {
            text += line(T.labelTitle, title.value.trim());
            text += line(T.labelLanguage, selectedText(document.getElementById("qsubLanguage")));
            text += line(T.labelSubject, selectedText(document.getElementById("qsubSubject")));
            text += line(T.labelExamKind, selectedText(document.getElementById("qsubExamKind")));
            var groups = Array.prototype.slice
                .call(wrap.querySelectorAll("[data-qsub-group-checkbox]:checked"))
                .map(function (cb) {
                    var lab = cb.closest(".qsubm-chip");
                    var name = lab ? lab.querySelector(".qsubm-chip__label") : null;
                    return name ? name.textContent.trim() : cb.value;
                });
            text += line(T.labelGroups, groups.join(", "));
            var note = document.getElementById("qsubNote");
            if (note && note.value.trim()) text += line(T.labelNote, note.value.trim().slice(0, 160));
        }
        text += line(T.confirmSelected, String(checked.length));
        if (errors) text += line(T.confirmErrors, String(errors));
        if (warnings) text += line(T.confirmWarnings, String(warnings));
        return { text: text.trim(), count: checked.length, errors: errors };
    }

    // ⚠️ Meta sahələri `form="saveForm"` + `required`-dir və styled select vidceti
    // native <select>-i gizlədir: brauzer «invalid control is not focusable» deyib
    // göndərişi SƏSSİZ dayandırırdı (submit hadisəsi heç yaranmırdı). Ona görə
    // qapı düymənin KLİKİNDƏDİR: əvvəl validasiya (çatışmayan sahə vurğulanır),
    // sonra təsdiq, sonra real göndəriş.
    function markInvalid(el) {
        var wrap = el.closest(".bootstrap-single-select") || el.closest(".qsubm-input-wrap") || el;
        var toggle = wrap.querySelector ? wrap.querySelector(".bootstrap-single-select__toggle") : null;
        var target = toggle || el;
        target.classList.add("is-invalid");
        target.addEventListener("focus", function clear() { target.classList.remove("is-invalid"); }, { once: true });
        var field = el.closest(".qsubm-field") || wrap;
        if (field && field.scrollIntoView) field.scrollIntoView({ block: "center", behavior: "smooth" });
        if (toggle) toggle.focus(); else if (el.focus) el.focus();
    }
    function firstInvalid(form) {
        var controls = Array.prototype.slice.call(form.elements);
        for (var i = 0; i < controls.length; i += 1) {
            var c = controls[i];
            if (c.willValidate && !c.checkValidity()) return c;
        }
        return null;
    }
    var saveForm = document.getElementById("saveForm");
    var saveBtn = saveForm ? saveForm.querySelector(".save-btn") : null;
    if (saveForm && saveBtn && window.EMSConfirm) {
        saveBtn.addEventListener("click", function (event) {
            if (saveForm.dataset.wbConfirmed === "1") return; // təsdiqdən sonrakı real göndəriş
            event.preventDefault();
            event.stopImmediatePropagation();
            var bad = firstInvalid(saveForm);
            if (bad) {
                markInvalid(bad);
                if (window.EMSToast && window.EMSToast.show) window.EMSToast.show(T.confirmInvalid || "", "warning");
                return;
            }
            var info = summary();
            if (!info.count) {
                window.EMSConfirm.open({ title: T.confirmTitle || "", body: T.confirmNone || "", confirmLabel: T.confirmBack || undefined, cancelLabel: T.confirmBack || undefined });
                return;
            }
            var body = document.getElementById("emsConfirmModalBody");
            if (body) body.classList.add("wb-confirm-body");
            window.EMSConfirm
                .open({ title: T.confirmTitle || "", body: info.text, confirmLabel: T.confirmOk || undefined, danger: false })
                .then(function (ok) {
                    if (body) body.classList.remove("wb-confirm-body");
                    if (!ok) return;
                    saveForm.dataset.wbConfirmed = "1";
                    if (saveForm.requestSubmit) saveForm.requestSubmit(saveBtn);
                    else saveForm.submit();
                });
        }, true);
    }
})();
