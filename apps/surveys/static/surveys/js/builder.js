/* =========================================================================
   Sorğu qurucusu (2026-09-30) — kabinet bölməsi «Sorğu qurucusu».

   * Ayarlar: məcburilik → qapı siyasətləri, siyasət → möhlət günü (göstər/gizlət);
     vahid/ixtisas siyahılarında axtarış.
   * Sual redaktoru: `form[data-svb-op]` göndərişləri XHR ilə (EMSCore.fetchJSON) gedir,
     server siyahını YENİDƏN render edir və bu skript `[data-svb-editor]`-i dəyişir.
     JS olmasa formalar adi POST + yönləndirmə ilə işləyir (proqressiv inkişaf).
   * Sıra: tutacaqdan sürüklə-burax (HTML5 DnD, yalnız eyni bölmə daxilində) və
     klaviatura — tutacaqda Alt+↑ / Alt+↓; nəticə `aria-live` ilə elan olunur.
   * Növə görə sahələr: `[data-svb-kinds~="single"]` blokları seçilmiş növə görə.

   AJAX-SAFE: yalnız EMSDelegate (document üzərində) + EMSReady (idempotent, null-safe).
   Mətnlər serverdən (data-* atributları / render olunmuş HTML) gəlir — burada sabit mətn yoxdur.
   ========================================================================= */
(function (window, document) {
    "use strict";

    var dragged = null;
    var dragStartOrder = "";
    // Klaviatura ilə sıra dəyişəndə redaktor yenidən render olunur — fokus həmin sualın
    // tutacağına qaytarılır (Alt+↑/↓ ardıcıl basıla bilsin).
    var refocusQuestion = null;

    function syncHeadCount(fresh) {
        // Başlıqdakı «Suallar: N» XHR ilə dəyişən blokdan kənardadır — yalnız rəqəmi yeniləyirik
        // (mətn serverdə tərcümə olunub; burada sabit mətn yoxdur).
        var head = document.querySelector(".svb-head__count");
        var count = fresh ? fresh.getAttribute("data-svb-count") : null;
        if (head && count !== null && /^\d+$/.test(count)) {
            head.textContent = head.textContent.replace(/\d+/, count);
        }
    }

    function orderOf(list) {
        var ids = [];
        var cards = list ? list.querySelectorAll("[data-svb-q]") : [];
        for (var i = 0; i < cards.length; i += 1) {
            ids.push(cards[i].getAttribute("data-svb-q"));
        }
        return ids.join(",");
    }

    function applyKinds(form) {
        var select = form.querySelector("[data-svb-kind]");
        if (!select) {
            return;
        }
        var kind = select.value;
        var boxes = form.querySelectorAll("[data-svb-kinds]");
        for (var i = 0; i < boxes.length; i += 1) {
            var kinds = (boxes[i].getAttribute("data-svb-kinds") || "").split(" ");
            boxes[i].hidden = kinds.indexOf(kind) === -1;
        }
    }

    function applySettings(form) {
        var mandatory = form.querySelector('input[name="obligation"][value="mandatory"]');
        var policies = form.querySelector("[data-svb-policies]");
        if (mandatory && policies) {
            policies.hidden = !mandatory.checked;
        }
        var policy = form.querySelector('input[name="gate_policy"]:checked');
        var defer = form.querySelector("[data-svb-defer]");
        if (defer) {
            defer.hidden = !policy || policy.value !== "defer_days";
        }
    }

    function filterList(input) {
        var list = document.getElementById(input.getAttribute("data-svb-filter"));
        if (!list) {
            return;
        }
        var query = (input.value || "").trim().toLocaleLowerCase();
        var items = list.querySelectorAll("[data-svb-label]");
        for (var i = 0; i < items.length; i += 1) {
            var checked = items[i].querySelector("input:checked");
            var match = !query || (items[i].getAttribute("data-svb-label") || "").indexOf(query) !== -1;
            items[i].hidden = !match && !checked;
        }
    }

    function announce(editor, text) {
        var live = editor ? editor.querySelector("[data-svb-live]") : null;
        if (live && text) {
            live.textContent = text;
        }
    }

    function toast(text, level) {
        if (text && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(text, level);
        }
    }

    function swapEditor(editor, html, openLastGroup) {
        if (!editor || !html) {
            return null;
        }
        var holder = document.createElement("div");
        holder.innerHTML = html; // serverdə render olunmuş, Django-escape olunmuş fraqment
        var fresh = holder.querySelector("[data-svb-editor]");
        if (!fresh) {
            return null;
        }
        editor.parentNode.replaceChild(fresh, editor);
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.init === "function") {
            window.EMSBootstrapSelect.init(fresh);
        }
        var forms = fresh.querySelectorAll("form[data-svb-kindform]");
        for (var i = 0; i < forms.length; i += 1) {
            applyKinds(forms[i]);
        }
        syncHeadCount(fresh);
        if (refocusQuestion) {
            var handle = null;
            var moved = fresh.querySelectorAll("[data-svb-q]");
            for (var m = 0; m < moved.length; m += 1) {
                if (moved[m].getAttribute("data-svb-q") === refocusQuestion) {
                    handle = moved[m].querySelector("[data-svb-handle]");
                }
            }
            refocusQuestion = null;
            if (handle) {
                handle.focus();
            }
        }
        if (openLastGroup !== null && openLastGroup !== undefined) {
            var list = fresh.querySelector('[data-svb-list][data-group="' + openLastGroup + '"]');
            var cards = list ? list.querySelectorAll("[data-svb-q]") : [];
            var last = cards.length ? cards[cards.length - 1] : null;
            var details = last ? last.querySelector("details") : null;
            if (details) {
                details.open = true;
                var field = details.querySelector("textarea, input[type='text']");
                if (field) {
                    field.focus();
                }
            }
        }
        return fresh;
    }

    function send(editor, url, body, openLastGroup) {
        if (!window.EMSCore || !window.EMSCore.fetchJSON) {
            return false;
        }
        editor.setAttribute("aria-busy", "true");
        window.EMSCore.fetchJSON(url, { method: "POST", body: body })
            .then(function (payload) {
                var fresh = swapEditor(editor, payload && payload.html, openLastGroup);
                announce(fresh, payload && payload.message);
                toast(payload && payload.message, "success");
            })
            .catch(function (error) {
                var payload = error && error.payload;
                editor.removeAttribute("aria-busy");
                if (payload && payload.html) {
                    swapEditor(editor, payload.html, null);
                }
                refocusQuestion = null;
                toast(payload && payload.message ? payload.message : String(error && error.message || ""), "error");
            });
        return true;
    }

    function groupKeyOf(form) {
        var group = form.querySelector('input[name="page"], input[name="section"]');
        return group ? group.value : null;
    }

    function postOrder(list) {
        var editor = list.closest("[data-svb-editor]");
        if (!editor) {
            return;
        }
        var body = new FormData();
        body.append("op", "reorder");
        body.append("group", list.getAttribute("data-group") || "");
        var cards = list.querySelectorAll("[data-svb-q]");
        for (var i = 0; i < cards.length; i += 1) {
            body.append("order", cards[i].getAttribute("data-svb-q"));
        }
        send(editor, editor.getAttribute("data-post-url"), body, null);
    }

    function bindDelegates() {
        if (!window.EMSDelegate || window.__emsSurveyBuilderBound) {
            return;
        }
        window.__emsSurveyBuilderBound = true;

        window.EMSDelegate.on("change", "form[data-svb-kindform] [data-svb-kind]", function (event, select) {
            applyKinds(select.form);
        });
        window.EMSDelegate.on("change", "form[data-svb-settings] input[type='radio']", function (event, input) {
            applySettings(input.form);
        });
        window.EMSDelegate.on("input", "[data-svb-filter]", function (event, input) {
            filterList(input);
        });

        window.EMSDelegate.on("submit", "form[data-svb-op]", function (event, form) {
            var editor = form.closest("[data-svb-editor]");
            if (!editor || editor.getAttribute("aria-busy") === "true") {
                if (editor) {
                    event.preventDefault();
                }
                return;
            }
            var body = new FormData(form);
            if (event.submitter && event.submitter.name) {
                body.append(event.submitter.name, event.submitter.value);
            }
            var openLast = form.hasAttribute("data-svb-open-last") ? groupKeyOf(form) : null;
            if (send(editor, form.getAttribute("action"), body, openLast)) {
                event.preventDefault();
            }
        });

        // Klaviatura ilə sıra: tutacaqda Alt + ↑/↓.
        window.EMSDelegate.on("keydown", "[data-svb-handle]", function (event, handle) {
            if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) {
                return;
            }
            event.preventDefault();
            var card = handle.closest("[data-svb-q]");
            var list = card ? card.parentNode : null;
            if (!card || !list) {
                return;
            }
            var sibling = event.key === "ArrowUp" ? card.previousElementSibling : card.nextElementSibling;
            if (!sibling || !sibling.hasAttribute("data-svb-q")) {
                return;
            }
            if (event.key === "ArrowUp") {
                list.insertBefore(card, sibling);
            } else {
                list.insertBefore(sibling, card);
            }
            handle.focus();
            refocusQuestion = card.getAttribute("data-svb-q");
            postOrder(list);
        });

        // Sürüklə-burax — yalnız TUTACAQDAN başlayır (kartdakı mətn seçimi / textarea sürükləməni
        // tetikləməsin) və yalnız eyni siyahı (bölmə) daxilində.
        window.EMSDelegate.on("pointerdown", "[data-svb-handle]", function (event, handle) {
            var card = handle.closest("[data-svb-q]");
            if (card) {
                card.setAttribute("draggable", "true");
            }
        });
        window.EMSDelegate.on("pointerup", "[data-svb-handle]", function (event, handle) {
            var card = handle.closest("[data-svb-q]");
            if (card && card !== dragged) {
                card.removeAttribute("draggable");
            }
        });
        window.EMSDelegate.on("dragstart", "[data-svb-q][draggable='true']", function (event, card) {
            dragged = card;
            dragStartOrder = orderOf(card.parentNode);
            card.classList.add("is-dragging");
            if (event.dataTransfer) {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", card.getAttribute("data-svb-q"));
            }
        });
        window.EMSDelegate.on("dragover", "[data-svb-q]", function (event, card) {
            if (!dragged || dragged === card || dragged.parentNode !== card.parentNode) {
                return;
            }
            event.preventDefault();
            var rect = card.getBoundingClientRect();
            var after = event.clientY > rect.top + rect.height / 2;
            card.parentNode.insertBefore(dragged, after ? card.nextSibling : card);
        });
        window.EMSDelegate.on("drop", "[data-svb-q]", function (event) {
            if (dragged) {
                event.preventDefault();
            }
        });
        window.EMSDelegate.on("dragend", "[data-svb-q]", function (event, card) {
            card.classList.remove("is-dragging");
            card.removeAttribute("draggable");
            var list = card.parentNode;
            dragged = null;
            if (list && list.hasAttribute("data-svb-list") && orderOf(list) !== dragStartOrder) {
                postOrder(list);
            }
        });
    }

    function init() {
        bindDelegates();
        var forms = document.querySelectorAll("form[data-svb-kindform]");
        for (var i = 0; i < forms.length; i += 1) {
            applyKinds(forms[i]);
        }
        var settings = document.querySelector("form[data-svb-settings]");
        if (settings) {
            applySettings(settings);
        }
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    } else {
        document.addEventListener("DOMContentLoaded", init);
    }
})(window, document);
