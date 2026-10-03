/* Hesabı dayandırma sahələri (sahib 2026-10-03) — şablon: sections/people/_block_reason_fields.html.
 * Səbəb seçiləndə «kimə yaxınlaşsın» avtomatik təklif olunur (option[data-contact]); operator dəyişə bilər.
 * `window.EMSBlockFields`: show / reset / read — «Tələbələr» kataloqu və «Tələbə reyestri» dialoqları işlədir.
 */
(function () {
    "use strict";

    if (window.EMSBlockFields) {
        return;
    }

    function setSelect(select, value) {
        if (!select) {
            return;
        }
        select.value = value || "";
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function syncContact(container) {
        var reason = container.querySelector("[data-block-reason]");
        var contact = container.querySelector("[data-block-contact]");
        if (!reason || !contact) {
            return;
        }
        var option = reason.options[reason.selectedIndex];
        var suggested = option ? option.getAttribute("data-contact") : "";
        if (suggested) {
            setSelect(contact, suggested);
        }
    }

    document.addEventListener("change", function (event) {
        var target = event.target;
        if (!target || !target.matches || !target.matches("[data-block-reason]")) {
            return;
        }
        var container = target.closest("[data-block-fields]");
        if (container) {
            syncContact(container);
        }
    });

    window.EMSBlockFields = {
        show: function (container, visible) {
            if (container) {
                container.hidden = !visible;
            }
        },
        reset: function (container) {
            if (!container) {
                return;
            }
            setSelect(container.querySelector("[data-block-reason]"), "");
            var contact = container.querySelector("[data-block-contact]");
            if (contact && contact.options.length) {
                setSelect(contact, contact.options[0].value);
            }
            var note = container.querySelector('[name="contact_note"]');
            if (note) {
                note.value = "";
            }
        },
        /* {payload: {reason_code, contact_code, contact_note}} və ya {error: "mətn"} */
        read: function (container) {
            var reason = container.querySelector("[data-block-reason]");
            var contact = container.querySelector("[data-block-contact]");
            var note = container.querySelector('[name="contact_note"]');
            var code = reason ? String(reason.value || "") : "";
            var text = note ? String(note.value || "").trim() : "";
            if (!code) {
                return { error: container.getAttribute("data-msg-reason") || "" };
            }
            if (code === "other" && text.length < 3) {
                return { error: container.getAttribute("data-msg-note") || "" };
            }
            return {
                payload: {
                    reason_code: code,
                    contact_code: contact ? String(contact.value || "") : "",
                    contact_note: text,
                },
            };
        },
    };
})();
