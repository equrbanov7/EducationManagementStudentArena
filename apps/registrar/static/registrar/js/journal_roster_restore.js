/**
 * «Tələbəni bərpa et» — jurnal səhifəsi (sahib 2026-11-15).
 *
 * Düymə (`data-jrs-open`) modalı açır; siyahı (bu jurnaldan çıxarılmış / dondurulmuş / azad edilmiş tələbələr:
 * ad, qrup, nə vaxt, kim, səbəb) modalın `data-list-url`-indən JSON ilə oxunur. Bir tələbə seçilir → «Bərpa et»
 * → POST (`data-apply-url`, qeyd istəyə bağlı) → səhifə yenilənir (cədvəl server tərəfdə yenidən qurulur, köhnə
 * xanalar yerindədir). Bərpa olunmayan sətir (başqa jurnalda aktiv, akademik status, köçürmə…) səbəbi ilə
 * görünür, seçilə bilmir. Server bütün qapıları yenidən yoxlayır.
 *
 * AJAX-SAFE: hadisələr `EMSDelegate.on` ilə document səviyyəsində BİR dəfə; modal hər dəfə DOM-dan tapılır
 * (null-safe); yazılar `EMSCore.fetchJSON` ilə (CSRF başlığı avtomatik). Mətnlər `textContent` ilə yazılır.
 */
(function (window, document) {
    "use strict";

    var state = { busy: false, lastFocused: null, selected: "" };

    function modalEl() {
        return document.querySelector("[data-jrs-modal]");
    }

    function part(modal, hook) {
        return modal ? modal.querySelector("[" + hook + "]") : null;
    }

    function text(modal, name) {
        return (modal && modal.getAttribute(name)) || "";
    }

    function setError(modal, message) {
        var box = part(modal, "data-jrs-error");
        if (!box) return;
        box.textContent = message || "";
        box.hidden = !message;
    }

    function errorText(modal, err) {
        var payload = err && err.payload;
        if (payload && typeof payload === "object" && payload.message) return payload.message;
        return text(modal, "data-msg-error") || "Error";
    }

    function el(tag, className, content) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (content) node.textContent = content;
        return node;
    }

    function syncSubmit(modal) {
        var submit = part(modal, "data-jrs-submit");
        if (submit) submit.disabled = state.busy || !state.selected;
    }

    function setBlocked(modal, message) {
        var box = part(modal, "data-jrs-blocked");
        var label = part(modal, "data-jrs-blocked-text");
        if (label) label.textContent = message || "";
        if (box) box.hidden = !message;
    }

    function rowNode(modal, row) {
        var item = el("label", "jrs-row" + (row.restorable ? "" : " is-disabled"));
        var radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "jrs-pick";
        radio.value = row.enrollment;
        radio.disabled = !row.restorable;
        radio.setAttribute("data-jrs-pick", "");
        item.appendChild(radio);

        var body = el("span", "jrs-row__body");
        var head = el("span", "jrs-row__head");
        head.appendChild(el("b", "jrs-row__name", row.name));
        head.appendChild(el("span", "jrs-row__status jrs-row__status--" + (row.status || "dropped"), row.status_label));
        body.appendChild(head);

        var meta = [];
        if (row.group) {
            var group = text(modal, "data-label-group") + ": " + row.group;
            if (row.source_group && row.source_group !== row.group) {
                group += " · " + text(modal, "data-label-source") + " " + row.source_group;
            }
            meta.push(group);
        }
        if (row.when) meta.push(row.when);
        if (row.by) meta.push(text(modal, "data-label-by") + ": " + row.by);
        if (meta.length) body.appendChild(el("span", "jrs-row__meta", meta.join(" · ")));

        if (row.reason || row.note) {
            var reason = el("span", "jrs-row__reason");
            reason.textContent =
                text(modal, "data-label-reason") + ": " + [row.reason, row.note].filter(Boolean).join(" — ");
            body.appendChild(reason);
        }
        if (row.message) {
            var info = el("span", "jrs-row__info");
            var icon = el("i", "fas fa-circle-info");
            icon.setAttribute("aria-hidden", "true");
            info.appendChild(icon);
            info.appendChild(document.createTextNode(" " + row.message));
            body.appendChild(info);
        }
        item.appendChild(body);
        return item;
    }

    function render(modal, payload) {
        var list = part(modal, "data-jrs-list");
        if (!list) return;
        list.textContent = "";
        setBlocked(modal, payload && payload.blocked);
        var rows = (payload && payload.rows) || [];
        if (!rows.length) {
            list.appendChild(el("p", "jrs-empty", text(modal, "data-msg-empty")));
            return;
        }
        rows.forEach(function (row) {
            list.appendChild(rowNode(modal, row));
        });
    }

    function load(modal) {
        var list = part(modal, "data-jrs-list");
        if (list) {
            list.textContent = "";
            list.appendChild(el("p", "jrs-empty", text(modal, "data-msg-loading")));
        }
        return window.EMSCore.fetchJSON(modal.getAttribute("data-list-url"))
            .then(function (payload) {
                render(modal, payload);
            })
            .catch(function (err) {
                if (list) list.textContent = "";
                setError(modal, errorText(modal, err));
            });
    }

    function openModal(button) {
        var modal = modalEl();
        if (!modal || !window.EMSCore) return;
        state.lastFocused = button;
        state.selected = "";
        state.busy = false;
        var note = part(modal, "data-jrs-note");
        if (note) note.value = "";
        setError(modal, "");
        syncSubmit(modal);
        modal.hidden = false;
        load(modal).then(function () {
            var first = modal.querySelector("[data-jrs-pick]:not([disabled])") || part(modal, "data-jrs-close");
            if (first) first.focus();
        });
    }

    function closeModal() {
        var modal = modalEl();
        if (!modal || modal.hidden) return;
        modal.hidden = true;
        setError(modal, "");
        state.selected = "";
        if (state.lastFocused && document.contains(state.lastFocused)) state.lastFocused.focus();
        state.lastFocused = null;
    }

    function pick(radio) {
        var modal = modalEl();
        if (!modal || radio.disabled) return;
        state.selected = radio.value || "";
        Array.prototype.forEach.call(modal.querySelectorAll(".jrs-row"), function (row) {
            row.classList.toggle("is-selected", row.contains(radio));
        });
        setError(modal, "");
        syncSubmit(modal);
    }

    function submit(button) {
        var modal = modalEl();
        if (!modal || state.busy) return;
        if (!state.selected) {
            setError(modal, text(modal, "data-msg-pick"));
            return;
        }
        var note = part(modal, "data-jrs-note");
        state.busy = true;
        button.disabled = true;
        setError(modal, "");
        window.EMSCore.fetchJSON(modal.getAttribute("data-apply-url"), {
            method: "POST",
            data: { enrollment: state.selected, note: note ? note.value.trim() : "" },
        })
            .then(function () {
                window.location.reload();
            })
            .catch(function (err) {
                state.busy = false;
                syncSubmit(modal);
                setError(modal, errorText(modal, err));
            });
    }

    function boot() {
        var delegate = window.EMSDelegate;
        if (!delegate || typeof delegate.on !== "function" || !window.EMSCore) return;
        delegate.on("click", "[data-jrs-open]", function (event, button) {
            event.preventDefault();
            openModal(button);
        });
        delegate.on("click", "[data-jrs-close]", function (event) {
            event.preventDefault();
            closeModal();
        });
        delegate.on("change", "[data-jrs-pick]", function (event, radio) {
            pick(radio);
        });
        delegate.on("click", "[data-jrs-submit]", function (event, button) {
            event.preventDefault();
            submit(button);
        });
        delegate.on("keydown", "[data-jrs-modal]", function (event) {
            if (event.key === "Escape") closeModal();
        });
    }

    if (window.EMSReady && typeof window.EMSReady.once === "function") {
        window.EMSReady.once("journal-roster-restore", boot);
    } else if (!window.__jrsBooted) {
        window.__jrsBooted = true;
        boot();
    }
})(window, document);
