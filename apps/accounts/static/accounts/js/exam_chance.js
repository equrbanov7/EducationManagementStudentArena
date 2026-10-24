/* «Yenidən imtahan cəhdi» — filtr formunun avto-submit-i, grant formasının xülasəsi və ön-doldurma.
 *
 * Select dəyişən kimi forma göndərilir (fakültə dəyişəndə kafedra sıfırlanır —
 * server onsuz da yad kafedranı rədd edir, URL təmiz qalsın); axtarış
 * inputları (imtahan + tələbə) vahid EMSSearchInput qaydası ilə (2026-10-14:
 * yazı dayananda 1500 ms, ≥ 2 simvol, Enter dərhal, IME) — göndəriş «quiet»
 * bölmə yükləməsidir: input əvəzlənmir, fokus və yazılan hərflər qalır.
 *
 * QEYD: profil SPA-sı bölmə swap-ında paneldəki <script> taqlarını yenidən
 * icra edir — dinləyicilər document səviyyəsində DELEGATED qoşulur və qlobal
 * bayraqla ikiqat qoşulma önlənir (CSP: inline handler yoxdur).
 */
(function () {
    "use strict";

    if (window.__exchInit) {
        return;
    }
    window.__exchInit = true;

    function submitForm(form, input) {
        window.EMSSearchInput.submitForm(form, { input: input || null });
    }

    document.addEventListener("change", function (event) {
        var select = event.target;
        if (!select || select.tagName !== "SELECT") {
            return;
        }
        var form = select.closest("form.js-exch-filter");
        if (!form) {
            return;
        }
        if (select.classList.contains("js-exch-faculty")) {
            var kafedra = form.querySelector('select[name="chance_kafedra"]');
            if (kafedra) {
                kafedra.value = "";
            }
        }
        submitForm(form);
    });

    /* 2026-10-18 (sahib): rəsmi şans — «25% müraciəti» səbəbində imtahan siyahısı seçilmiş tələbələrin
     * 25% fənlərinə görə süzülür; altda «kimə, nə, niyə» xülasəsi. Server qaydanı yenidən yoxlayır. */
    function syncGrant(form) {
        var reason = form.getAttribute("data-exch-reason");
        var checked = Array.prototype.slice.call(form.querySelectorAll('input[name="student_ids"]:checked'));
        var select = form.querySelector("[data-exch-exam]");
        if (select && reason === "retake_25") {
            var allowed = {};
            checked.forEach(function (box) {
                (box.getAttribute("data-exch-subjects") || "").split(",").forEach(function (id) {
                    if (id) { allowed[id] = true; }
                });
            });
            var any = Object.keys(allowed).length > 0;
            Array.prototype.forEach.call(select.options, function (option) {
                if (!option.value) { return; }
                var ok = !any || allowed[option.getAttribute("data-subject")] === true;
                option.hidden = !ok;
                option.disabled = !ok;
                if (!ok && option.selected) { select.value = ""; }
            });
            if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
                window.EMSBootstrapSelect.refresh(select);
            }
        }
        var summary = form.querySelector("[data-exch-summary]");
        if (summary) {
            var names = checked.map(function (box) {
                var label = box.closest("label");
                var name = label ? label.querySelector(".exch-stu__name") : null;
                return name ? name.textContent.trim() : "";
            }).filter(Boolean);
            var exam = select && select.selectedIndex > 0 ? select.options[select.selectedIndex].textContent.trim() : "";
            summary.textContent = names.length && exam ? names.join(", ") + " → " + exam : "";
        }
    }

    /* 2026-10-24: ön-doldurma süzgəc dəyişəndə itməsin — seçilmiş imtahan və işarələnmiş tələbələr süzgəc
     * formasının gizli `chance_exam` / `chance_student` sahələrinə yazılır (server çipləri yenidən işarələyir). */
    function keepSelection(form) {
        var filter = document.querySelector("form.js-exch-filter");
        if (!filter) {
            return;
        }
        var examKeep = filter.querySelector("[data-exch-keep-exam]");
        var select = form.querySelector("[data-exch-exam]");
        if (examKeep && select) {
            examKeep.value = select.value || "";
        }
        var studentsKeep = filter.querySelector("[data-exch-keep-students]");
        if (studentsKeep) {
            studentsKeep.value = Array.prototype.map.call(
                form.querySelectorAll('input[name="student_ids"]:checked'),
                function (box) { return box.value; }
            ).slice(0, 20).join(",");
        }
    }

    document.addEventListener("change", function (event) {
        var form = event.target && event.target.closest ? event.target.closest("form[data-exch-grant]") : null;
        if (form) {
            syncGrant(form);
            keepSelection(form);
        }
    });

    /* «Son verilən cəhd hüquqları» sətri → həmin tələbə + imtahan üçün grant forması (cari əsas saxlanılır;
     * əsas seçilməyibsə forma 1-ci addımı göstərir). Sənəd linki öz işini görür. */
    window.EMSDelegate.on("click", "tr[data-exch-prefill]", function (event, row) {
        var link = event.target.closest ? event.target.closest("a") : null;
        if (link && !link.classList.contains("exch-prefill")) {
            return;
        }
        var url = row.getAttribute("data-exch-prefill");
        if (!url) {
            return;
        }
        event.preventDefault();
        if (typeof window.EMSProfileLoadSection === "function") {
            window.EMSProfileLoadSection("exam-chance", url);
        } else {
            window.location.assign(url);
        }
    });

    /* Ön-doldurulmuş açılış (`chance_focus=grant`): forma görünən yerə sürüşür — hər URL üçün bir dəfə
     * (sonrakı süzgəc yükləmələri səhifəni yerindən oynatmır). */
    window.EMSReady(function () {
        Array.prototype.forEach.call(document.querySelectorAll("form[data-exch-grant]"), syncGrant);
        var card = document.querySelector("#exchGrantCard[data-exch-focus]");
        if (!card || window.__exchFocusedHref === window.location.href) {
            return;
        }
        window.__exchFocusedHref = window.location.href;
        if (typeof card.scrollIntoView === "function") {
            card.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    });

    window.EMSSearchInput.delegate("form.js-exch-filter input[data-exch-debounce]", {
        onSearch: function (value, meta) {
            submitForm(meta.input.closest("form.js-exch-filter"), meta.input);
        },
    });
})();
