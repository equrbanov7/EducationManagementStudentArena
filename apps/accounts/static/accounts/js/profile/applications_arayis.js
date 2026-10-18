/* «Müraciətlərim» detalı → «Arayış sorğusu» emalçısına «Arayışı hazırla və əlavə et» (sahib 2026-10-19).
 *
 * Blok YALNIZ server `app.arayis_tool` verəndə qurulur. `attached` (siyahı) doludursa «Arayış əlavə olunub»
 * + hər arayış üçün «kod · təqdim yeri · Arayışı aç» göstərilir, forma isə GİZLİDİR — «Yeni arayış hazırla
 * (başqa yer üçün)» onu açır. Başqa yer → yeni möhür + fayl; eyni yer → server mövcud faylı qaytarır (kilid +
 * yoxlama kodu, ikinci qeyd yazılmır). Blok emalçı +
 * `transcript.issue` əhatəsi üçündür, view-as-da gəlmir. Bütün mətnlər serverdəndir; DOM `textContent` ilə
 * yazılır. Göndəriş `arayis_tool.url`-ə POST (place) → cavab adi əməl cavabıdır (yenilənmiş detal), `NS.applyDetail` ilə tətbiq olunur.
 * `applications_detail.js` `render()`-dən sonra `NS.arayis.decorate(body, app)` çağırır.
 * AJAX-safe: klik dinləyicisi BİR DƏFƏ (`EMSDelegate`) qoşulur.
 */
(function () {
    "use strict";

    var NS = (window.EMSApplications = window.EMSApplications || {});
    if (NS.arayis) {
        return;
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text) {
            node.textContent = String(text);
        }
        return node;
    }

    /* Əlavə olunmuş arayışların siyahısı: «KOD · təqdim yeri · Arayışı aç». */
    function attachedList(tool) {
        var wrap = el("div", "apx-arayis__done");
        wrap.setAttribute("data-apx-arayis-done", "");
        wrap.setAttribute("role", "status");
        wrap.appendChild(el("p", "apx-arayis__done-title", tool.attached_label));
        var list = el("ul", "apx-arayis__list");
        tool.attached.forEach(function (row) {
            var item = el("li", "apx-arayis__item");
            item.setAttribute("data-apx-arayis-item", row.code || "");
            item.appendChild(el("span", "apx-arayis__code", (tool.code_label ? tool.code_label + ": " : "") + row.code));
            item.appendChild(el("span", "apx-arayis__place", row.place));
            var link = el("a", "apx-arayis__link", tool.open_label);
            link.href = row.download_url;
            link.target = "_blank";
            link.rel = "noopener";
            link.title = row.name || "";
            item.appendChild(link);
            list.appendChild(item);
        });
        wrap.appendChild(list);
        return wrap;
    }

    function form(tool, hidden) {
        var wrap = el("div", "apx-arayis__form");
        wrap.setAttribute("data-apx-arayis-form", "");
        wrap.hidden = !!hidden;
        var errors = el("ul", "apx-errors");
        errors.setAttribute("data-apx-arayis-errors", "");
        errors.hidden = true;
        wrap.appendChild(errors);
        var label = el("label", "apx-act__label", tool.place_label);
        label.setAttribute("for", "apx-arayis-place");
        wrap.appendChild(label);
        var input = el("input", "apx-act__input");
        input.type = "text";
        input.id = "apx-arayis-place";
        input.maxLength = Number(tool.place_max) || 200;
        input.placeholder = tool.place_placeholder || "";
        input.autocomplete = "off";
        input.setAttribute("data-apx-arayis-place", "");
        wrap.appendChild(input);
        var buttons = el("div", "apx-act__buttons");
        var button = el("button", "ems-btn ems-btn--sm ems-btn--primary", tool.button);
        button.type = "button";
        button.setAttribute("data-apx-arayis-submit", "");
        buttons.appendChild(button);
        wrap.appendChild(buttons);
        if (hidden && tool.same_place_hint) {
            wrap.appendChild(el("div", "apx-act__hint", tool.same_place_hint));
        }
        return wrap;
    }

    function decorate(body, app) {
        var tool = app && app.arayis_tool;
        if (!body || !tool || body.querySelector("[data-apx-arayis]")) {
            return;
        }
        var attached = Array.isArray(tool.attached) ? tool.attached : [];
        var box = el("div", "apx-act apx-arayis");
        box.setAttribute("data-apx-arayis", tool.url);
        box.appendChild(el("h3", "apx-arayis__title", tool.title));
        if (attached.length) {
            box.appendChild(attachedList({
                attached: attached,
                attached_label: tool.attached_label,
                code_label: tool.code_label,
                open_label: tool.open_label,
            }));
        }
        if (tool.blocked) {
            box.appendChild(el("p", "apx-arayis__blocked", tool.blocked));
        } else if (attached.length) {
            /* Artıq əlavə olunub: forma GİZLİ, ikinci dərəcəli düymə onu açır (başqa yer → yeni arayış). */
            var again = el("button", "ems-btn ems-btn--sm", tool.again_label);
            again.type = "button";
            again.setAttribute("data-apx-arayis-again", "");
            again.setAttribute("aria-expanded", "false");
            box.appendChild(again);
            box.appendChild(form(tool, true));
        } else {
            box.appendChild(form(tool, false));
        }
        box.appendChild(el("div", "apx-act__hint", tool.hint));
        var act = body.querySelector(".apx-act");
        if (act && act.parentNode) {
            act.parentNode.insertBefore(box, act);
        } else {
            body.appendChild(box);
        }
    }

    function reveal(button) {
        var box = button.closest("[data-apx-arayis]");
        var wrap = box && box.querySelector("[data-apx-arayis-form]");
        if (!wrap) {
            return;
        }
        wrap.hidden = false;
        button.hidden = true;
        button.setAttribute("aria-expanded", "true");
        var input = wrap.querySelector("[data-apx-arayis-place]");
        if (input) {
            try {
                input.focus();
            } catch (error) {
                /* fokus alınmasa da forma işləyir */
            }
        }
    }

    function showErrors(box, messages) {
        var list = box.querySelector("[data-apx-arayis-errors]");
        if (!list) {
            return;
        }
        list.textContent = "";
        (messages || []).forEach(function (text) {
            list.appendChild(el("li", "", text));
        });
        list.hidden = !(messages && messages.length);
    }

    function submit(button) {
        var box = button.closest("[data-apx-arayis]");
        var app = NS.current;
        if (!box || !app || !window.EMSCore) {
            return;
        }
        var place = box.querySelector("[data-apx-arayis-place]");
        var form = new FormData();
        form.append("place", place ? place.value.trim() : "");
        button.disabled = true;
        showErrors(box, []);
        window.EMSCore.fetchJSON(box.getAttribute("data-apx-arayis"), {
            method: "POST",
            body: form,
            headers: { "X-CSRFToken": NS.csrfToken ? NS.csrfToken() : "" },
        })
            .then(function (payload) {
                var updated = payload && payload.application;
                if (updated && NS.applyDetail) {
                    NS.applyDetail(updated);
                }
            })
            .catch(function (error) {
                button.disabled = false;
                showErrors(box, NS.errorList ? NS.errorList(error) : []);
            });
    }

    NS.arayis = { decorate: decorate, reveal: reveal };

    (function ready(attempt) {
        if (window.EMSDelegate) {
            window.EMSDelegate.on("click", "[data-apx-arayis-submit]", function (event, node) {
                submit(node);
            });
            window.EMSDelegate.on("click", "[data-apx-arayis-again]", function (event, node) {
                reveal(node);
            });
            return;
        }
        if (attempt > 200) {
            return;
        }
        window.setTimeout(function () {
            ready(attempt + 1);
        }, 25);
    })(0);
})();
