/* RİM «yeni hesab» — axtarışlı seçici (qrup / kafedra).
 *
 * NİYƏ ÖZ KOMPONENTİ? Repetisiya bazasında bir universitetin 766 aktiv qrupu
 * var: nə `<select>`, nə də `<datalist>` bu sıxlıqda işlək deyil. Burada
 * WAI-ARIA «combobox + listbox» naxışı var — fokus HƏMİŞƏ input-dadır, aktiv
 * variant `aria-activedescendant` ilə göstərilir (ekran oxuyucu onu oxuyur).
 *
 * Klaviatura: ↓/↑ variantlar, Enter seçir, Escape siyahını bağlayır (dialoqu
 * YOX — bax aşağıdakı capture-fazalı handler), Tab normal davranır.
 *
 * AJAX-safe: bütün hadisələr `EMSDelegate` ilə document-ə delegə olunur; kök
 * element yoxdursa heç nə edilmir (bax docs/frontend/AJAX_SAFE_JS_PATTERN.md).
 */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCreate = window.EMSRimCreate || {});
    if (!window.EMSDelegate || !window.EMSReady) {
        return;
    }

    var SEARCH_DEBOUNCE_MS = 250;
    var combo = (ns.combo = {});
    var timers = {};

    function root() {
        return document.querySelector("[data-rimc-root]");
    }

    function t(key) {
        return ns.t ? ns.t(key) : key;
    }

    function box(el) {
        return el ? el.closest("[data-rimc-combo]") : null;
    }

    function parts(node) {
        if (!node) {
            return null;
        }
        return {
            box: node,
            name: node.getAttribute("data-rimc-combo") || "",
            input: node.querySelector("[data-rimc-combo-input]"),
            value: node.querySelector("[data-rimc-combo-value]"),
            list: node.querySelector("[data-rimc-combo-list]"),
            hint: node.querySelector("[data-rimc-combo-hint]")
        };
    }

    function closeList(node) {
        var p = parts(node);
        if (!p || !p.list) {
            return;
        }
        p.list.hidden = true;
        p.list.textContent = "";
        if (p.input) {
            p.input.setAttribute("aria-expanded", "false");
            p.input.removeAttribute("aria-activedescendant");
        }
    }

    /** Seçilmiş dəyəri təmizləyir — «yazdım, amma siyahıdan seçmədim» halı. */
    function clearValue(node) {
        var p = parts(node);
        if (p && p.value) {
            p.value.value = "";
        }
        if (ns.form && ns.form.refresh) {
            ns.form.refresh();
        }
    }

    function message(node, text) {
        var p = parts(node);
        if (!p || !p.list) {
            return;
        }
        p.list.textContent = "";
        var item = document.createElement("li");
        item.className = "rimc-combo__empty";
        item.textContent = text;
        p.list.appendChild(item);
        p.list.hidden = false;
        if (p.input) {
            p.input.setAttribute("aria-expanded", "true");
        }
    }

    function render(node, payload) {
        var p = parts(node);
        if (!p || !p.list) {
            return;
        }
        var results = (payload && payload.results) || [];
        if (!results.length) {
            message(node, t("no_results"));
            return;
        }
        p.list.textContent = "";
        results.forEach(function (row, index) {
            var item = document.createElement("li");
            item.className = "rimc-combo__item";
            item.id = "rimc-opt-" + p.name + "-" + index;
            item.setAttribute("role", "option");
            item.setAttribute("aria-selected", "false");
            item.setAttribute("data-rimc-option", row.id);
            item.setAttribute("data-rimc-option-text", row.text || "");

            var text = document.createElement("span");
            text.className = "rimc-combo__text";
            text.textContent = row.text || "";
            item.appendChild(text);

            if (row.hint) {
                var hint = document.createElement("span");
                hint.className = "rimc-combo__hint";
                hint.textContent = row.hint;
                item.appendChild(hint);
            }
            p.list.appendChild(item);
        });
        if (payload && payload.has_more) {
            var more = document.createElement("li");
            more.className = "rimc-combo__empty";
            more.textContent = t("more_results");
            p.list.appendChild(more);
        }
        p.list.hidden = false;
        if (p.input) {
            p.input.setAttribute("aria-expanded", "true");
        }
        activate(node, 0);
    }

    function options(node) {
        var p = parts(node);
        return p && p.list ? p.list.querySelectorAll("[data-rimc-option]") : [];
    }

    function activate(node, index) {
        var items = options(node);
        var p = parts(node);
        if (!items.length || !p) {
            return;
        }
        var bounded = Math.max(0, Math.min(index, items.length - 1));
        Array.prototype.forEach.call(items, function (item, position) {
            var active = position === bounded;
            item.classList.toggle("is-active", active);
            item.setAttribute("aria-selected", active ? "true" : "false");
            if (active) {
                if (p.input) {
                    p.input.setAttribute("aria-activedescendant", item.id);
                }
                if (item.scrollIntoView) {
                    item.scrollIntoView({ block: "nearest" });
                }
            }
        });
    }

    function activeIndex(node) {
        var items = options(node);
        for (var i = 0; i < items.length; i += 1) {
            if (items[i].classList.contains("is-active")) {
                return i;
            }
        }
        return -1;
    }

    function choose(node, item) {
        var p = parts(node);
        if (!p || !item) {
            return;
        }
        if (p.value) {
            p.value.value = item.getAttribute("data-rimc-option") || "";
        }
        if (p.input) {
            p.input.value = item.getAttribute("data-rimc-option-text") || "";
        }
        closeList(node);
        if (ns.form && ns.form.refresh) {
            ns.form.refresh();
        }
        if (ns.form && ns.form.clearError) {
            ns.form.clearError(p.name);
        }
    }

    function search(node) {
        var host = root();
        var p = parts(node);
        var fetchJSON = window.EMSCore && window.EMSCore.fetchJSON;
        if (!host || !p || !p.input || !fetchJSON) {
            return;
        }
        var query = p.input.value.trim();
        if (!query) {
            closeList(node);
            return;
        }
        message(node, t("searching"));
        var url =
            host.getAttribute("data-catalog-url") +
            "?catalog=" +
            encodeURIComponent(p.name) +
            "&q=" +
            encodeURIComponent(query);
        fetchJSON(url)
            .then(function (payload) {
                // Sorğu gedərkən istifadəçi yazmağa davam edə bilər — cavabı
                // yalnız input hələ də EYNİ mətni daşıyırsa göstəririk.
                if (p.input.value.trim() === query) {
                    render(node, payload);
                }
            })
            .catch(function () {
                message(node, t("failed"));
            });
    }

    /* ── Hadisələr ──────────────────────────────────────────────────────── */

    window.EMSDelegate.on("input", "[data-rimc-combo-input]", function (event, input) {
        var node = box(input);
        if (!node) {
            return;
        }
        // Mətn dəyişdi → əvvəlki seçim ETİBARSIZDIR (id ilə ad uyğunsuz qalmasın).
        clearValue(node);
        var name = node.getAttribute("data-rimc-combo") || "combo";
        window.clearTimeout(timers[name]);
        timers[name] = window.setTimeout(function () {
            search(node);
        }, SEARCH_DEBOUNCE_MS);
    });

    window.EMSDelegate.on("keydown", "[data-rimc-combo-input]", function (event, input) {
        var node = box(input);
        if (!node) {
            return;
        }
        var items = options(node);
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (!items.length) {
                search(node);
                return;
            }
            activate(node, activeIndex(node) + (event.key === "ArrowDown" ? 1 : -1));
            return;
        }
        if (event.key === "Enter" && items.length) {
            event.preventDefault();
            choose(node, items[Math.max(0, activeIndex(node))]);
        }
    });

    window.EMSDelegate.on("mousedown", "[data-rimc-option]", function (event, item) {
        // `mousedown` — `blur` siyahını bağlamazdan ƏVVƏL seçim tutulsun.
        event.preventDefault();
        choose(box(item), item);
    });

    window.EMSDelegate.on("focusout", "[data-rimc-combo]", function (event, node) {
        var next = event.relatedTarget;
        if (next && node.contains(next)) {
            return;
        }
        closeList(node);
    });

    /* Escape ƏVVƏLCƏ siyahını bağlamalıdır, dialoqu YOX. `ems_ui/overlay.js`
     * öz handler-ini document-in BUBBLE fazasında saxlayır; ona görə bu handler
     * CAPTURE fazasındadır — sıra qeydiyyat ardıcıllığından asılı qalmır. */
    window.EMSReady.once("rim-create-combo-escape", function () {
        document.addEventListener(
            "keydown",
            function (event) {
                if (event.key !== "Escape") {
                    return;
                }
                var node = box(event.target);
                var p = parts(node);
                if (!p || !p.list || p.list.hidden) {
                    return;
                }
                event.stopPropagation();
                closeList(node);
            },
            true
        );
    });

    combo.reset = function reset(scope) {
        var nodes = (scope || document).querySelectorAll("[data-rimc-combo]");
        Array.prototype.forEach.call(nodes, function (node) {
            var p = parts(node);
            if (p.input) {
                p.input.value = "";
            }
            if (p.value) {
                p.value.value = "";
            }
            closeList(node);
        });
    };
})(window, document);
