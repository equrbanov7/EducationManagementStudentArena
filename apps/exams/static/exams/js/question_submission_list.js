/* Sual göndərişləri bölməsi — filtr select-lərinin avto-submit-i və
 * göndəriş silmə təsdiqi.
 *
 * QEYD: profil SPA-sı bölmə swap-ında paneldəki <script> taqlarını yenidən
 * icra edir — ona görə bütün dinləyicilər document səviyyəsində DELEGATED
 * qoşulur və qlobal bayraqla ikiqat qoşulmanın qarşısı alınır (CSP: inline
 * handler yoxdur).
 */
(function () {
    "use strict";

    if (window.__qsubListInit) {
        return;
    }
    window.__qsubListInit = true;

    // Filtr select-i dəyişən kimi formanı göndər (axtarış inputunun debounce-u
    // profile/ui.js-dəki js-profile-debounce-search mexanizmindədir).
    document.addEventListener("change", function (event) {
        var select = event.target;
        if (!select || select.tagName !== "SELECT") {
            return;
        }
        var form = select.closest("form.js-qsub-filter-form");
        if (!form) {
            return;
        }
        // Fakültə dəyişəndə köhnə kafedra seçimi yeni fakültəyə aid olmaya
        // bilər — server onsuz da sıfırlayır, amma URL-i təmiz saxlayaq.
        if (select.name === "qsub_faculty") {
            var kafedra = form.querySelector('select[name="qsub_kafedra"]');
            if (kafedra) {
                kafedra.value = "";
            }
        }
        if (select.name === "qsub_year") {
            var period = form.querySelector('select[name="qsub_period"]');
            if (period) {
                period.value = "";
            }
        }
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.submit();
        }
    });

    // Silmə təsdiqi — mərkəzləşmiş bootstrap modalı (_qsub_delete_modal.html).
    // Native window.confirm yalnız modal/bootstrap tapılmayanda fallback-dır.
    function openDeleteModal(actionUrl) {
        var modalEl = document.getElementById("qsubDeleteModal");
        var modalForm = document.getElementById("qsubDeleteModalForm");
        if (!modalEl || !modalForm || typeof bootstrap === "undefined") {
            return false;
        }
        modalForm.action = actionUrl || "";
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
        return true;
    }

    // Siyahı kartındakı mini-forma: submit-i saxla, modalda təsdiq istə.
    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.classList || !form.classList.contains("js-qsub-delete-form")) {
            return;
        }
        // Modal formunun öz submit-i buradan keçməsin (id ilə tanınır).
        if (form.id === "qsubDeleteModalForm") {
            return;
        }
        if (openDeleteModal(form.action)) {
            event.preventDefault();
            return;
        }
        var message = form.getAttribute("data-confirm") || "";
        if (message && !window.confirm(message)) {
            event.preventDefault();
        }
    });

    // Detal səhifəsindəki formaction düyməsi.
    document.addEventListener("click", function (event) {
        var button = event.target && event.target.closest ? event.target.closest(".js-qsub-confirm") : null;
        if (!button) {
            return;
        }
        var actionUrl = button.getAttribute("formaction") || (button.form && button.form.action) || "";
        if (openDeleteModal(actionUrl)) {
            event.preventDefault();
            return;
        }
        var message = button.getAttribute("data-confirm") || "";
        if (message && !window.confirm(message)) {
            event.preventDefault();
        }
    });

    // ── Uzun-siyahılı filtrlər: fakültə/kafedra/müəllim axtarışlı seçiciləri ──
    // EMSSearchableSelect per-element qurulur; bölmə swap-ında panel yeniləndiyi
    // üçün EMSReady(run) ilə hər dəfə yenidən init olunur (komponent ikiqat
    // init-ə qarşı özü qorunur). Seçim hidden inputa yazılır və forma resubmit
    // olunur (profil AJAX bölmə yükləməsi bunu tutur).
    function initFilterPickers(root) {
        root = root && typeof root.querySelector === "function" ? root : document;
        var form = root.querySelector(".js-qsub-filter-form");
        if (!form || !window.EMSSearchableSelect || form.getAttribute("data-qsf-ready") === "1") {
            return;
        }
        var SS = window.EMSSearchableSelect;

        function submitForm() {
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
            } else {
                form.submit();
            }
        }

        function setup(hook, urlAttr, inputName, extra) {
            var el = form.querySelector(".js-" + hook);
            var hidden = form.querySelector("input[name='" + inputName + "']");
            if (!el || !hidden) {
                return null;
            }
            var opts = extra || {};
            opts.url = form.getAttribute(urlAttr) || "";
            var pick = SS.create(el, opts);
            if (!pick) {
                return null;
            }
            // İlkin dəyər (server-dən) — listener-lər hələ qoşulmayıb deyə
            // setValue burada resubmit tetikləmir.
            if (hidden.value && hidden.getAttribute("data-label")) {
                pick.setValue(hidden.value, hidden.getAttribute("data-label"));
            }
            pick.on("change", function () {
                hidden.value = pick.value();
                submitForm();
            });
            return pick;
        }

        var facultyPick = setup("qsf-faculty", "data-faculty-url", "qsub_faculty");
        setup("qsf-kafedra", "data-department-url", "qsub_kafedra", {
            dependParam: "faculty",
            getDependValue: function () {
                return facultyPick ? facultyPick.value() : "";
            }
        });
        setup("qsf-teacher", "data-teacher-url", "qsub_teacher");
        // Fakültə dəyişəndə köhnə kafedra id-si serverdə onsuz da sıfırlanır;
        // resubmit yeni paneli kafedrasız gətirir — əlavə reset lazım deyil.
        form.setAttribute("data-qsf-ready", "1");
    }

    function run(detail) {
        if (detail && detail.section && detail.section !== "question-submissions") {
            return;
        }
        initFilterPickers(detail && detail.panel ? detail.panel : document);
    }

    if (window.EMSReady) {
        window.EMSReady(run);
    } else {
        document.addEventListener("DOMContentLoaded", function () { run(null); });
    }
})();
