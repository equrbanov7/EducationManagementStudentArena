/**
 * «Bu müəllimə bərpa et» — jurnal siyahısının tarixçə sətri (sahib 2026-11-03).
 * Source: registrar/partials/_journal_history_restore.html + _journal_history_restore_modal.html
 *
 * Sətirdəki düymə (`data-jl-hrestore-open`) təsdiq modalını açır: nə dəyişəcəyi sətrin gizli siyahısından
 * (`data-jl-hrestore-steps`) köçürülür. İndiki sahib sonradan yazıbsa xəbərdarlıq + məcburi səbəb, yazmayıbsa
 * səbəb istəyə bağlıdır (sahib 2026-11-04). Admin siyahısında müəllim `data-teacher-id`-dən POST-a gedir.
 * Uğur → yaşıl toast, qısa fasilədən sonra səhifə yenilənir (sətir «Cari dərs yüküm»ə keçir). Xəta → modalda
 * və toast-da serverin mətni (sorğunun dilində); JSON olmayan cavabda ümumi mətn — heç vaxt xam səhifə yox.
 *
 * NİYƏ «İŞLƏMİRDİ» (sahib 2026-11-04): bu fayl `/jurnal/` tam səhifəsində `{% block content %}` içində,
 * `js/core/http.js`-dən (EMSCore) ƏVVƏL icra olunur. Köhnə kod yüklənəndə `!window.EMSCore` görüb çıxırdı —
 * düymə heç vaxt bağlanmırdı (kliklə heç nə olmurdu). İndi qeydiyyat yalnız `EMSDelegate`-dən asılıdır
 * (`ems_early.js` stub-u növbəyə yığır), `EMSCore` isə klik anında oxunur.
 *
 * AJAX-SAFE: yalnız `EMSDelegate.on` (document səviyyəsində), bir dəfə bağlanır; URL düymənin
 * data-atributundadır; yazı `EMSCore.fetchJSON` ilə (CSRF başlığı avtomatik). Modal açılanda `<body>`-yə
 * köçürülür ki, kabinet qabığının konteynerləri onu kəsməsin (idempotent: köhnə nüsxə silinir).
 */
(function (window, document) {
    "use strict";

    if (window.__jlHistoryRestoreBound) return;
    var delegate = window.EMSDelegate;
    if (!delegate || typeof delegate.on !== "function") return;
    window.__jlHistoryRestoreBound = true;

    var RELOAD_DELAY_MS = 900;
    var state = { url: "", teacher: "", busy: false, lastFocused: null, modal: null };

    function modalEl() {
        if (state.modal && document.contains(state.modal)) return state.modal;
        return document.querySelector("[data-jl-hrestore-modal]");
    }

    function adoptModal() {
        var modal = document.querySelector("[data-jl-hrestore-modal]");
        if (!modal) return null;
        Array.prototype.forEach.call(document.querySelectorAll("[data-jl-hrestore-modal]"), function (other) {
            if (other !== modal && other.parentNode === document.body) other.parentNode.removeChild(other);
        });
        if (modal.parentNode !== document.body) document.body.appendChild(modal);
        state.modal = modal;
        return modal;
    }

    function part(modal, hook) {
        return modal ? modal.querySelector("[" + hook + "]") : null;
    }

    function toast(text, level) {
        if (text && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(text, level);
        }
    }

    function setError(modal, text) {
        var box = part(modal, "data-jl-hrestore-error");
        if (!box) return;
        box.textContent = text || "";
        box.hidden = !text;
    }

    function copyList(target, source) {
        if (!target) return;
        while (target.firstChild) target.removeChild(target.firstChild);
        if (!source) return;
        Array.prototype.forEach.call(source.children, function (item) {
            target.appendChild(item.cloneNode(true));
        });
    }

    function setText(modal, hook, value) {
        var node = part(modal, hook);
        if (node) node.textContent = value || "";
    }

    function openModal(button) {
        var modal = adoptModal();
        if (!modal) return;
        var row = button.closest(".jl-hrestore") || button.parentNode;
        state.url = button.getAttribute("data-url") || "";
        state.teacher = button.getAttribute("data-teacher-id") || "";
        state.lastFocused = button;
        setText(modal, "data-jl-hrestore-teacher", button.getAttribute("data-teacher"));
        setText(modal, "data-jl-hrestore-subject", button.getAttribute("data-subject"));
        setText(modal, "data-jl-hrestore-group", button.getAttribute("data-group"));
        copyList(part(modal, "data-jl-hrestore-plan"), row ? row.querySelector("[data-jl-hrestore-steps]") : null);
        // İndiki sahib sonradan yazıbsa: kim/nə qədər/nə vaxtdan + səbəb məcburi; yazmayıbsa səbəb istəyə bağlı.
        var written = button.getAttribute("data-written-since") === "1";
        copyList(part(modal, "data-jl-hrestore-warnlist"), row ? row.querySelector("[data-jl-hrestore-warnings]") : null);
        var box = part(modal, "data-jl-hrestore-warnbox");
        var required = part(modal, "data-jl-hrestore-required");
        var optional = part(modal, "data-jl-hrestore-optional");
        if (box) box.hidden = !written;
        if (required) required.hidden = !written;
        if (optional) optional.hidden = written;
        var reason = part(modal, "data-jl-hrestore-reason");
        if (reason) reason.value = "";
        var submitButton = part(modal, "data-jl-hrestore-submit");
        if (submitButton) submitButton.disabled = false;
        setError(modal, "");
        modal.hidden = false;
        if (reason) reason.focus();
    }

    function closeModal() {
        var modal = modalEl();
        if (!modal || modal.hidden || state.busy) return;
        modal.hidden = true;
        state.url = "";
        state.teacher = "";
        if (state.lastFocused && document.contains(state.lastFocused)) state.lastFocused.focus();
        state.lastFocused = null;
    }

    function errorText(modal, err) {
        var payload = err && err.payload;
        if (payload && typeof payload === "object") {
            if (payload.message) return String(payload.message);
            if (payload.detail && payload.view_as_blocked) return String(payload.detail);
        }
        // HTML xəta səhifəsi / şəbəkə xətası — xam mətn göstərilmir.
        return modal.getAttribute("data-generic-error") || "Error";
    }

    function fail(modal, button, err) {
        var payload = err && err.payload;
        if (payload && typeof payload === "object" && payload.view_as_ended && payload.redirect) {
            window.location.href = payload.redirect;
            return;
        }
        var text = errorText(modal, err);
        setError(modal, text);
        // View-as bloku http.js-də artıq toast olunur — ikinci dəfə göstərmirik.
        if (!(payload && typeof payload === "object" && payload.view_as_blocked)) toast(text, "danger");
        state.busy = false;
        button.disabled = false;
    }

    function submit(button) {
        var modal = modalEl();
        if (!modal || state.busy || !state.url) return;
        var core = window.EMSCore;
        if (!core || typeof core.fetchJSON !== "function") {
            setError(modal, modal.getAttribute("data-generic-error") || "Error");
            return;
        }
        var reason = part(modal, "data-jl-hrestore-reason");
        state.busy = true;
        button.disabled = true;
        setError(modal, "");
        var data = { reason: reason ? reason.value : "", teacher: state.teacher };
        core.fetchJSON(state.url, { method: "POST", data: data })
            .then(function (payload) {
                if (!payload || typeof payload !== "object" || !payload.ok) {
                    fail(modal, button, { payload: payload });
                    return;
                }
                toast(payload.message, "success");
                window.setTimeout(function () {
                    window.location.reload();
                }, RELOAD_DELAY_MS);
            })
            .catch(function (err) {
                fail(modal, button, err);
            });
    }

    delegate.on("click", "[data-jl-hrestore-open]", function (event, button) {
        event.preventDefault();
        openModal(button);
    });
    delegate.on("click", "[data-jl-hrestore-close]", function (event) {
        event.preventDefault();
        closeModal();
    });
    delegate.on("click", "[data-jl-hrestore-submit]", function (event, button) {
        event.preventDefault();
        submit(button);
    });
    delegate.on("keydown", "[data-jl-hrestore-modal]", function (event) {
        if (event.key === "Escape") closeModal();
    });
})(window, document);
