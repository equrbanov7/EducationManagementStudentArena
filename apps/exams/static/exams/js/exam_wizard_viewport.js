/* İmtahan sehrbazı + «Sual əlavə et» modalı — mobil görünən sahə (visualViewport) uyğunlaşdırması.
 *
 * Problem (2026-10-14): telefonda tam ekran vərəq `position:fixed; inset:0` ilə LAYOUT
 * viewport-a bağlıdır. Virtual klaviatura açılanda iOS Safari və Android Chrome layout
 * viewport-u kiçiltmir (yalnız GÖRÜNƏN sahə kiçilir) — altlıq («Növbəti» / «Yadda saxla»)
 * klaviaturanın altında qalırdı.
 *
 * Həll: klaviatura açıq ikən (itən hündürlük > 120px, zoom yoxdur) modalın elementinə
 * `--ems-vvh` / `--ems-vvt` CSS dəyişənləri (görünən sahənin hündürlüyü / yuxarı ofseti)
 * və `.is-kbd` sinfi yazılır; CSS (exam_wizard.css, question_form.css) onları istifadə
 * edir. Dəyişən yazmaq `element.style.setProperty` ilə edilir — CSP-yə toxunmur.
 * Fokuslu sahə klaviatura ilə örtülməsin deyə görünən sahəyə gətirilir.
 *
 * Əlavə: «Növbəti»/«Yarat» doğrulaması uğursuz olanda birinci xətalı sahə (gizli native select-in
 * fokusu işləmir) görünən sahəyə gətirilir və ekran oxuyucu üçün `aria-invalid` /
 * `aria-describedby` yazılır — əks halda telefonda xəta qatdan kənarda qalır, «heç nə olmadı» görünür.
 *
 * Əlavə: tablet enində (576–860px) təqvim dialoqu `.ew-pane-body` içində absolute qalır və
 * kəsilir — açılanda görünən sahəyə sürüşdürülür (telefonda CSS alt vərəqdir).
 *
 * AJAX-safe: yalnız `document` səviyyəsində delegasiya; modal DOM-da olmasa heç nə etmir.
 */
(function () {
    "use strict";

    if (window.__emsModalViewportFit) {
        return;
    }
    window.__emsModalViewportFit = true;

    var SELECTOR = ".exam-wizard-modal, .qf-modal";
    var KEYBOARD_MIN_PX = 120;
    var FIELD_SELECTOR = "input:not([type=checkbox]):not([type=radio]):not([type=hidden]), textarea, select, [contenteditable]";
    var vv = window.visualViewport;
    var active = null;
    var kbdOpen = false;

    function isTouchDevice() {
        return !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
    }

    function clear(modal) {
        if (!modal) {
            return;
        }
        modal.style.removeProperty("--ems-vvh");
        modal.style.removeProperty("--ems-vvt");
        modal.classList.remove("is-kbd");
    }

    function revealFocused(modal) {
        var el = document.activeElement;
        if (!el || !modal.contains(el) || !el.matches || !el.matches(FIELD_SELECTOR)) {
            return;
        }
        window.setTimeout(function () {
            if (el.scrollIntoView) {
                el.scrollIntoView({ block: "center", behavior: "smooth" });
            }
        }, 60);
    }

    function sync() {
        if (!active || !vv) {
            return;
        }
        var lost = window.innerHeight - vv.height;
        var open = isTouchDevice() && vv.scale <= 1.01 && lost > KEYBOARD_MIN_PX;
        if (open) {
            active.style.setProperty("--ems-vvh", Math.round(vv.height) + "px");
            active.style.setProperty("--ems-vvt", Math.round(vv.offsetTop) + "px");
            active.classList.add("is-kbd");
            if (!kbdOpen) {
                revealFocused(active);
            }
        } else {
            clear(active);
        }
        kbdOpen = open;
    }

    document.addEventListener("shown.bs.modal", function (event) {
        var modal = event.target && event.target.matches && event.target.matches(SELECTOR) ? event.target : null;
        if (!modal) {
            return;
        }
        active = modal;
        kbdOpen = false;
        sync();
    });

    document.addEventListener("hidden.bs.modal", function (event) {
        var modal = event.target;
        if (modal && modal === active) {
            clear(modal);
            active = null;
            kbdOpen = false;
        }
    });

    if (vv) {
        vv.addEventListener("resize", sync);
        vv.addEventListener("scroll", sync);
    }

    // Doğrulama xətası: birinci xətalı sahəni görünən sahəyə gətir + a11y bağlantıları.
    var errSeq = 0;
    function surfaceErrors(modal) {
        var panel = modal.querySelector(".ew-panel.is-active");
        if (!panel) {
            return;
        }
        var groups = panel.querySelectorAll(".form-group.is-invalid");
        Array.prototype.forEach.call(groups, function (group) {
            var err = group.querySelector(".field-error");
            var control = group.querySelector("input:not([type=hidden]), textarea, .bootstrap-single-select__toggle");
            if (!err || !control) {
                return;
            }
            if (!err.id) {
                errSeq += 1;
                err.id = "ewErr" + errSeq;
            }
            control.setAttribute("aria-invalid", "true");
            control.setAttribute("aria-describedby", err.id);
        });
        if (groups.length) {
            groups[0].scrollIntoView({ block: "center", behavior: "smooth" });
        }
    }

    document.addEventListener("click", function (event) {
        var btn = event.target && event.target.closest ? event.target.closest("[data-ew-next], [data-ew-submit]") : null;
        var modal = btn ? btn.closest(".exam-wizard-modal") : null;
        if (modal) {
            window.setTimeout(function () {
                surfaceErrors(modal);
            }, 40);
        }
    });

    // Sahə düzələndə (exam_wizard.js xətanı silir) köhnəlmiş aria-invalid təmizlənir.
    function clearStaleInvalid(event) {
        var modal = event.target && event.target.closest ? event.target.closest(".exam-wizard-modal") : null;
        if (!modal) {
            return;
        }
        window.setTimeout(function () {
            Array.prototype.forEach.call(modal.querySelectorAll("[aria-invalid=true][aria-describedby^=ewErr]"), function (control) {
                var group = control.closest(".form-group");
                if (!group || !group.classList.contains("is-invalid")) {
                    control.removeAttribute("aria-invalid");
                    control.removeAttribute("aria-describedby");
                }
            });
        }, 0);
    }
    document.addEventListener("input", clearStaleInvalid);
    document.addEventListener("change", clearStaleInvalid);

    // Təqvim dialoqu (tablet eni): açılanda kəsilməsin.
    document.addEventListener("click", function (event) {
        var toggle = event.target && event.target.closest ? event.target.closest("[data-ems-dt-toggle]") : null;
        if (!toggle || !active || !active.contains(toggle)) {
            return;
        }
        window.setTimeout(function () {
            var pop = active && active.querySelector(".ems-dt__pop");
            if (pop && window.getComputedStyle(pop).position === "absolute" && pop.scrollIntoView) {
                pop.scrollIntoView({ block: "nearest", behavior: "smooth" });
            }
        }, 30);
    });
})();
