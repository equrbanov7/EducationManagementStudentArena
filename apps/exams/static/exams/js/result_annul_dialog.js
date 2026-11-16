/**
 * Nəticənin ləğvi / ləğvin bərpası — iki addımlı pəncərə (sahib 2026-11-17).
 *
 * Açan düymə: `[data-annul-open]` / `[data-restore-open]` (data-*-url + data-*-student). 1-ci addımda forma
 * yoxlanılır («Davam et»), 2-ci addımda xülasə + xəbərdarlıq göstərilir — yalnız «Təsdiq et» formu göndərir
 * (səhvən bir kliklə ləğv olmasın). Markup: exams/partials/_result_annul_dialogs.html.
 * AJAX-safe: yalnız EMSDelegate (document səviyyəsi) + EMSReady.once; elementlər hər dəfə yenidən oxunur.
 */
(function () {
    "use strict";

    function dialogOf(el) {
        return el ? el.closest("dialog.xan-dialog") : null;
    }

    function showStep(dialog, name) {
        Array.prototype.forEach.call(dialog.querySelectorAll("[data-xan-step]"), function (step) {
            step.hidden = step.getAttribute("data-xan-step") !== name;
        });
        var focusTarget = name === "confirm"
            ? dialog.querySelector("[data-xan-step='confirm'] [data-xan-submit]")
            : dialog.querySelector("[data-xan-note]");
        if (focusTarget) focusTarget.focus();
    }

    function setError(dialog, visible) {
        var error = dialog.querySelector("[data-xan-error]");
        if (error) error.hidden = !visible;
    }

    function openDialog(id, url, student) {
        var dialog = document.getElementById(id);
        if (!dialog || !url) return;
        var form = dialog.querySelector("form");
        form.reset();
        form.setAttribute("action", url);
        var name = dialog.querySelector("[data-xan-student]");
        if (name) name.textContent = student || "";
        var submit = dialog.querySelector("[data-xan-submit]");
        if (submit) submit.disabled = false;
        setError(dialog, false);
        showStep(dialog, "edit");
        if (typeof dialog.showModal === "function") {
            dialog.showModal();
        } else {
            dialog.setAttribute("open", "");
        }
        showStep(dialog, "edit");
    }

    function closeDialog(dialog) {
        if (!dialog) return;
        if (typeof dialog.close === "function") {
            dialog.close();
        } else {
            dialog.removeAttribute("open");
        }
    }

    function checkedReasonLabel(form) {
        var input = form.querySelector("input[name='reason']:checked");
        if (!input) return "";
        var label = input.closest("label");
        return label ? label.textContent.trim() : input.value;
    }

    // Layihə qaydası: tarix gg.aa.iiii (input dəyəri ISO-dur).
    function displayDate(iso) {
        var parts = String(iso || "").split("-");
        return parts.length === 3 ? parts[2] + "." + parts[1] + "." + parts[0] : iso;
    }

    function fill(dialog, key, text) {
        var el = dialog.querySelector("[data-xan-sum='" + key + "']");
        if (el) el.textContent = text || "—";
    }

    function onNext(dialog) {
        var form = dialog.querySelector("form");
        var note = form.querySelector("[data-xan-note]");
        var noteText = note ? note.value.trim() : "";
        var kind = form.getAttribute("data-xan-form");
        var valid = !!noteText;
        if (kind === "annul") {
            valid = valid && !!form.querySelector("input[name='reason']:checked");
            var dateInput = form.querySelector("[data-xan-date]");
            valid = valid && !!(dateInput && dateInput.value);
        }
        setError(dialog, !valid);
        if (!valid) {
            if (note && !noteText) note.focus();
            return;
        }
        fill(dialog, "note", noteText);
        if (kind === "annul") {
            fill(dialog, "reason", checkedReasonLabel(form));
            var date = form.querySelector("[data-xan-date]");
            fill(dialog, "date", date ? displayDate(date.value) : "");
            var file = form.querySelector("[data-xan-file]");
            fill(dialog, "file", file && file.files && file.files.length ? file.files[0].name : "");
        }
        showStep(dialog, "confirm");
    }

    window.EMSReady.once("exams-result-annul-dialog", function () {
        window.EMSDelegate.on("click", "[data-annul-open]", function (evt, btn) {
            evt.preventDefault();
            openDialog("xanAnnulDialog", btn.getAttribute("data-annul-url"), btn.getAttribute("data-annul-student"));
        });
        window.EMSDelegate.on("click", "[data-restore-open]", function (evt, btn) {
            evt.preventDefault();
            openDialog("xanRestoreDialog", btn.getAttribute("data-restore-url"), btn.getAttribute("data-restore-student"));
        });
        window.EMSDelegate.on("click", "dialog.xan-dialog [data-xan-close]", function (evt, btn) {
            closeDialog(dialogOf(btn));
        });
        window.EMSDelegate.on("click", "dialog.xan-dialog [data-xan-next]", function (evt, btn) {
            var dialog = dialogOf(btn);
            if (dialog) onNext(dialog);
        });
        window.EMSDelegate.on("click", "dialog.xan-dialog [data-xan-back]", function (evt, btn) {
            var dialog = dialogOf(btn);
            if (dialog) showStep(dialog, "edit");
        });
        // Yalnız 2-ci addımdakı «Təsdiq et» göndərir; Enter ilə 1-ci addımdan göndəriş olmasın. İkiqat klik yox.
        document.addEventListener("submit", function (evt) {
            var form = evt.target;
            if (!form || !form.matches || !form.matches("dialog.xan-dialog form")) return;
            var dialog = dialogOf(form);
            var confirmStep = dialog ? dialog.querySelector("[data-xan-step='confirm']") : null;
            if (!confirmStep || confirmStep.hidden) {
                evt.preventDefault();
                if (dialog) onNext(dialog);
                return;
            }
            var submit = dialog.querySelector("[data-xan-submit]");
            if (submit) {
                if (submit.disabled) {
                    evt.preventDefault();
                    return;
                }
                window.setTimeout(function () { submit.disabled = true; }, 0);
            }
        });
    });
})();
