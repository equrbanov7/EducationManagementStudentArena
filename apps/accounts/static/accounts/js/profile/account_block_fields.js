/* Hesabı dayandırma sahələri (sahib 2026-10-03) — şablon: sections/people/_block_reason_fields.html.
 * Səbəb seçiləndə «kimə yaxınlaşsın» avtomatik təklif olunur (option[data-contact]); operator dəyişə bilər.
 * 2026-10-11 (sahib): «Digər» seçiləndə səbəbin ALTINDA məcburi «Səbəbi yazın» sahəsi açılır
 * ([data-block-other] → name="reason_other"); başqa səbəbdə gizlənir və boşaldılır.
 * `window.EMSBlockFields`: show / reset / read — «Müəllimlər»/«Tələbələr» kataloqu və «Tələbə reyestri» dialoqları işlədir.
 */
(function () {
    "use strict";

    if (window.EMSBlockFields) {
        return;
    }

    var OTHER = "other";
    var MIN_OTHER = 3;

    function setSelect(select, value) {
        if (!select) {
            return;
        }
        select.value = value || "";
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function otherParts(container) {
        var wrap = container.querySelector("[data-block-other]");
        return { wrap: wrap, input: wrap ? wrap.querySelector('[name="reason_other"]') : null };
    }

    function syncOther(container) {
        var reason = container.querySelector("[data-block-reason]");
        var parts = otherParts(container);
        if (!parts.wrap) {
            return;
        }
        var isOther = !!reason && reason.value === OTHER;
        parts.wrap.hidden = !isOther;
        if (parts.input) {
            parts.input.required = isOther;
            parts.input.setAttribute("aria-required", isOther ? "true" : "false");
            if (!isOther) {
                parts.input.value = "";
                parts.input.removeAttribute("aria-invalid");
            }
        }
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
            syncOther(container);
            var parts = otherParts(container);
            if (parts.input && !parts.wrap.hidden) {
                parts.input.focus();
            }
        }
    });

    document.addEventListener("input", function (event) {
        var target = event.target;
        if (target && target.matches && target.matches('[data-block-fields] [name="reason_other"]')) {
            target.removeAttribute("aria-invalid");
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
            syncOther(container);
        },
        /* {payload: {reason_code, contact_code, contact_note, reason_other}} və ya {error: "mətn"} */
        read: function (container) {
            var reason = container.querySelector("[data-block-reason]");
            var contact = container.querySelector("[data-block-contact]");
            var note = container.querySelector('[name="contact_note"]');
            var other = otherParts(container).input;
            var code = reason ? String(reason.value || "") : "";
            var text = note ? String(note.value || "").trim() : "";
            var otherText = other ? String(other.value || "").trim() : "";
            if (!code) {
                return { error: container.getAttribute("data-msg-reason") || "" };
            }
            if (code === OTHER && otherText.length < MIN_OTHER) {
                if (other) {
                    other.setAttribute("aria-invalid", "true");
                    other.focus();
                }
                return { error: container.getAttribute("data-msg-other") || "" };
            }
            return {
                payload: {
                    reason_code: code,
                    contact_code: contact ? String(contact.value || "") : "",
                    contact_note: text,
                    reason_other: code === OTHER ? otherText : "",
                },
            };
        },
    };
})();
