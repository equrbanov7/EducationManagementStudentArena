/*
 * EMSMultiSelect — stilli ÇOXSEÇİMLİ seçici (2026-10-16).
 *
 * Sahib qaydası (2026-09-09): «hər yerdə stilli bootstrap select, uzun siyahıda menyu-daxili axtarış,
 * daxili göy fokus haşiyəsi YOX». Tək seçici (`bootstrap_select.js`) `select.value = …` yazır — `multiple`
 * elementdə ilk klik bütün seçimləri silərdi. Bu komponent həmin vizual dili (toggle, menyu, axtarış)
 * təkrarlayır, amma variantları checkbox kimi göstərir.
 *
 * Markup:
 *     <select name="group_ids" multiple data-ems-multi-select
 *             data-ms-placeholder="Seçilməyib"            (istəyə bağlı)
 *             data-ms-count-format="{count} qrup seçilib" (istəyə bağlı)
 *             data-ms-search-placeholder="Qrup axtar…"    (istəyə bağlı; data-live-search-placeholder da olar)
 *             data-ms-search="true|false"                 (default: ≥ 8 variant olanda axtarış görünür)
 *             data-ms-max-labels="2">                     (bu saya qədər adlar sadalanır, sonra «N seçilib»)
 *
 * Native `<select multiple>` GİZLİ dəyər anbarı olaraq qalır: forma serializasiyası, `option.selected`,
 * `EMSWorkloadForms.ensureOption` dəyişmir. Hər seçim dəyişikliyində native-də `change` (bubbles) atılır.
 *
 * Yenidən sinxron:
 *   * variant əlavə/silinməsi, `selected`/`disabled`/`hidden` atributu → MutationObserver (avtomatik);
 *   * `option.selected = …` PROPERTY yazısı mutasiya vermir → `EMSMultiSelect.refresh(select)` çağırın
 *     (və ya native-də `change` atın). `EMSBootstrapSelect.refresh/sync/init` `multiple` seçicini bura ötürür.
 *
 * Menyu bağlananda native-də `ems-multi-select:close` (bubbles) atılır (2026-10-25).
 *
 * API: `window.EMSMultiSelect = { enhance(select), init(root), refresh(select), sync(select) }`.
 * AJAX-safe: `EMSReady` ilə hər bölmə swap-ından sonra `[data-ems-multi-select]` qoşulur (idempotent).
 */
(function (window, document) {
    "use strict";

    var SELECTOR = "select[multiple][data-ems-multi-select]";
    var SEARCH_THRESHOLD = 8;
    var MENU_MAX = 320; // CSS max-height (20rem) ilə uyğun
    var uid = 0;

    function gettext(text) {
        return typeof window.gettext === "function" ? window.gettext(text) : text;
    }

    function matcherFor(needle) {
        if (window.EMSSearch && typeof window.EMSSearch.matcher === "function") {
            return window.EMSSearch.matcher(needle);
        }
        var lowered = needle.toLowerCase();
        return function (text) {
            return String(text || "").toLowerCase().indexOf(lowered) !== -1;
        };
    }

    /** Sahənin adı: `<label for>` və ya əhatə edən `<label>`-in öz mətni (variant mətnləri çıxmaqla). */
    function fieldName(select) {
        var label = select.labels && select.labels[0];
        if (!label) return select.getAttribute("aria-label") || "";
        var clone = label.cloneNode(true);
        Array.prototype.forEach.call(clone.querySelectorAll("select, .ems-multi-select"), function (node) {
            node.parentNode.removeChild(node);
        });
        return clone.textContent.replace(/\s+/g, " ").trim();
    }

    function el(tag, className, attrs) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        Object.keys(attrs || {}).forEach(function (key) {
            node.setAttribute(key, attrs[key]);
        });
        return node;
    }

    function enhance(select) {
        if (!select || select.tagName !== "SELECT" || !select.multiple) return null;
        if (select._emsMultiSelectApi) return select._emsMultiSelectApi;
        // Klonlanmış (api-siz) element: köhnə qabıq qalıbsa sil, yenidən qur.
        var stale = select.nextElementSibling;
        if (stale && stale.classList.contains("ems-multi-select")) stale.parentNode.removeChild(stale);

        uid += 1;
        var menuId = "ems-ms-menu-" + uid;
        var listId = "ems-ms-list-" + uid;
        var name = fieldName(select);
        var data = select.dataset;
        var maxLabels = parseInt(data.msMaxLabels || "2", 10);
        if (isNaN(maxLabels) || maxLabels < 0) maxLabels = 2;

        select.dataset.emsMultiSelectReady = "true";
        select.classList.add("ems-multi-select__native", "is-enhanced");
        select.setAttribute("tabindex", "-1");
        select.setAttribute("aria-hidden", "true");

        var root = el("div", "ems-multi-select");
        if (select.classList.contains("ems-select")) root.classList.add("ems-multi-select--ems");

        var toggle = el("button", "btn btn-outline-secondary bootstrap-single-select__toggle ems-multi-select__toggle", {
            type: "button",
            "aria-haspopup": "listbox",
            "aria-expanded": "false",
            "aria-controls": menuId,
        });
        var label = el("span", "bootstrap-single-select__label-text");
        var caret = el("span", "bootstrap-single-select__caret");
        caret.innerHTML = '<i class="fas fa-chevron-down" aria-hidden="true"></i>';
        toggle.appendChild(label);
        toggle.appendChild(caret);

        var menu = el("div", "bootstrap-single-select__menu ems-multi-select__menu", { id: menuId });
        menu.hidden = true;

        var head = el("div", "bootstrap-single-select__search ems-multi-select__head");
        var search = el("input", "form-control form-control-sm bootstrap-single-select__search-input", {
            type: "search",
            autocomplete: "off",
            "aria-controls": listId,
        });
        var searchText = data.msSearchPlaceholder || data.liveSearchPlaceholder || gettext("Axtar…");
        search.placeholder = searchText;
        search.setAttribute("aria-label", searchText);
        var actions = el("div", "ems-multi-select__actions");
        var allBtn = el("button", "ems-multi-select__action", { type: "button", "data-ms-action": "all" });
        allBtn.textContent = gettext("Hamısı");
        var clearBtn = el("button", "ems-multi-select__action", { type: "button", "data-ms-action": "clear" });
        clearBtn.textContent = gettext("Təmizlə");
        actions.appendChild(allBtn);
        actions.appendChild(clearBtn);
        head.appendChild(search);
        head.appendChild(actions);

        var list = el("div", "ems-multi-select__list", {
            id: listId,
            role: "listbox",
            "aria-multiselectable": "true",
        });
        if (name) list.setAttribute("aria-label", name);
        var empty = el("div", "bootstrap-single-select__search-empty ems-multi-select__empty", { role: "status" });
        empty.textContent = data.liveSearchEmpty || gettext("Uyğun nəticə yoxdur");
        empty.hidden = true;

        menu.appendChild(head);
        menu.appendChild(list);
        menu.appendChild(empty);
        root.appendChild(toggle);
        root.appendChild(menu);
        select.insertAdjacentElement("afterend", root);

        function optionButtons() {
            return Array.prototype.slice.call(list.querySelectorAll(".ems-multi-select__option"));
        }

        function visibleButtons() {
            return optionButtons().filter(function (button) {
                return !button.hidden && !button.disabled;
            });
        }

        function nativeOption(button) {
            return select.options[Number(button.dataset.index)] || null;
        }

        function isOpen() {
            return !menu.hidden;
        }

        function summary() {
            var picked = Array.prototype.filter.call(select.options, function (option) {
                return option.selected;
            });
            if (!picked.length) return { text: data.msPlaceholder || gettext("Seçilməyib"), empty: true };
            if (picked.length <= maxLabels) {
                return {
                    text: picked
                        .map(function (option) {
                            return option.textContent.trim();
                        })
                        .join(", "),
                    empty: false,
                };
            }
            var format = data.msCountFormat || gettext("{count} seçilib");
            return { text: format.replace("{count}", String(picked.length)), empty: false };
        }

        function sync() {
            optionButtons().forEach(function (button) {
                var option = nativeOption(button);
                var on = !!(option && option.selected);
                button.classList.toggle("is-selected", on);
                button.setAttribute("aria-selected", on ? "true" : "false");
            });
            var state = summary();
            label.textContent = state.text;
            toggle.classList.toggle("is-placeholder", state.empty);
            toggle.disabled = select.disabled;
            toggle.classList.toggle("is-disabled", select.disabled);
            toggle.setAttribute("aria-label", name ? name + ": " + state.text : state.text);
            if (select.disabled && isOpen()) close(false);
        }

        function applySearch() {
            var needle = String(search.value || "").trim();
            var hit = needle ? matcherFor(needle) : null;
            var shown = 0;
            optionButtons().forEach(function (button) {
                var match = !hit || hit(button.textContent || "");
                button.hidden = !match;
                if (match) shown += 1;
            });
            list.querySelectorAll(".ems-multi-select__group").forEach(function (header) {
                var next = header.nextElementSibling;
                var any = false;
                while (next && !next.classList.contains("ems-multi-select__group")) {
                    if (!next.hidden) any = true;
                    next = next.nextElementSibling;
                }
                header.hidden = !any;
            });
            empty.hidden = shown > 0 || !optionButtons().length;
        }

        function rebuild() {
            list.innerHTML = "";
            var lastGroup = null;
            var count = 0;
            Array.prototype.forEach.call(select.options, function (option, index) {
                if (option.hidden) return;
                var group = option.parentNode && option.parentNode.tagName === "OPTGROUP" ? option.parentNode : null;
                if (group && group !== lastGroup) {
                    var header = el("div", "ems-multi-select__group", { role: "presentation" });
                    header.textContent = group.label || "";
                    list.appendChild(header);
                }
                lastGroup = group;
                var button = el("button", "bootstrap-single-select__option ems-multi-select__option", {
                    type: "button",
                    role: "option",
                    tabindex: "-1",
                    "aria-selected": "false",
                });
                button.dataset.index = String(index);
                button.dataset.value = option.value;
                button.disabled = option.disabled || (group ? group.disabled : false);
                var box = el("span", "ems-multi-select__box", { "aria-hidden": "true" });
                box.innerHTML = '<i class="fas fa-check"></i>';
                var text = el("span", "bootstrap-single-select__option-label");
                text.textContent = option.textContent;
                button.appendChild(box);
                button.appendChild(text);
                list.appendChild(button);
                count += 1;
            });
            var mode = data.msSearch;
            head.hidden = false;
            search.hidden = mode === "false" || (mode !== "true" && data.liveSearch !== "true" && count < SEARCH_THRESHOLD);
            applySearch();
            sync();
        }

        function emitChange() {
            select.dispatchEvent(new Event("change", { bubbles: true }));
        }

        function toggleOption(button) {
            var option = button && !button.disabled ? nativeOption(button) : null;
            if (!option) return;
            option.selected = !option.selected;
            sync();
            emitChange();
        }

        function setMany(buttons, value) {
            var changed = false;
            buttons.forEach(function (button) {
                var option = nativeOption(button);
                if (option && !option.disabled && option.selected !== value) {
                    option.selected = value;
                    changed = true;
                }
            });
            sync();
            if (changed) emitChange();
        }

        /* ── açılış / bağlanış (Bootstrap Dropdown-suz: modal, jsdom və klaviatura üçün sabit) ── */
        function position() {
            // Modal body kimi overflow konteynerində kəsilməsin — viewport-a görə fixed, yer yoxdursa yuxarı.
            var rect = toggle.getBoundingClientRect();
            var vh = window.innerHeight || document.documentElement.clientHeight || 0;
            var gap = 6;
            var below = vh - rect.bottom - gap - 8;
            var above = rect.top - gap - 8;
            var needed = Math.min(MENU_MAX, menu.scrollHeight || MENU_MAX);
            var up = below < needed && above > below;
            menu.classList.add("is-fixed");
            menu.style.left = rect.left + "px";
            menu.style.width = rect.width + "px";
            menu.style.top = up ? "auto" : rect.bottom + gap + "px";
            menu.style.bottom = up ? vh - rect.top + gap + "px" : "auto";
            menu.style.maxHeight = Math.max(160, Math.min(MENU_MAX, up ? above : below)) + "px";
        }

        function onOutside(event) {
            if (!root.contains(event.target)) close(false);
        }

        function onScroll(event) {
            if (event.target instanceof window.Node && menu.contains(event.target)) return;
            close(false);
        }

        function onResize() {
            close(false);
        }

        function open(focusLast) {
            if (isOpen() || select.disabled) return;
            menu.hidden = false;
            toggle.classList.add("show");
            toggle.setAttribute("aria-expanded", "true");
            search.value = "";
            applySearch();
            position();
            document.addEventListener("pointerdown", onOutside, true);
            document.addEventListener("mousedown", onOutside, true);
            window.addEventListener("scroll", onScroll, true);
            window.addEventListener("resize", onResize);
            var items = visibleButtons();
            if (focusLast && items.length) items[items.length - 1].focus();
            else if (!search.hidden) search.focus();
            else if (items.length) items[0].focus();
        }

        function close(restoreFocus) {
            if (!isOpen()) return;
            menu.hidden = true;
            toggle.classList.remove("show");
            toggle.setAttribute("aria-expanded", "false");
            menu.classList.remove("is-fixed");
            ["left", "width", "top", "bottom", "maxHeight"].forEach(function (prop) {
                menu.style[prop] = "";
            });
            document.removeEventListener("pointerdown", onOutside, true);
            document.removeEventListener("mousedown", onOutside, true);
            window.removeEventListener("scroll", onScroll, true);
            window.removeEventListener("resize", onResize);
            if (restoreFocus) toggle.focus();
            // 2026-10-25: «seçim bitdi» siqnalı — səhifə (məs. nəticə süzgəci) hər klikdə yox,
            // menyu bağlananda tətbiq etsin.
            select.dispatchEvent(new CustomEvent("ems-multi-select:close", { bubbles: true }));
        }

        function move(from, delta) {
            var items = visibleButtons();
            if (!items.length) return;
            var at = items.indexOf(from);
            if (at === -1) {
                items[delta > 0 ? 0 : items.length - 1].focus();
                return;
            }
            var next = at + delta;
            if (next < 0) {
                if (!search.hidden) search.focus();
                return;
            }
            items[Math.min(next, items.length - 1)].focus();
        }

        toggle.addEventListener("click", function () {
            if (isOpen()) close(false);
            else open(false);
        });

        toggle.addEventListener("keydown", function (event) {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                open(event.key === "ArrowUp");
            } else if (event.key === "Escape" && isOpen()) {
                event.preventDefault();
                event.stopPropagation(); // modalı bağlamasın
                close(true);
            }
        });

        menu.addEventListener("keydown", function (event) {
            var target = event.target;
            if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                close(true);
                return;
            }
            if (target === search) {
                if (event.key === "ArrowDown") {
                    event.preventDefault();
                    move(null, 1);
                } else if (event.key === "Enter") {
                    event.preventDefault(); // formanı göndərməsin — ilk görünən variantı dəyiş
                    toggleOption(visibleButtons()[0]);
                }
                return;
            }
            if (!target.classList || !target.classList.contains("ems-multi-select__option")) return;
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                move(target, event.key === "ArrowDown" ? 1 : -1);
            } else if (event.key === "Home" || event.key === "End") {
                event.preventDefault();
                var items = visibleButtons();
                if (items.length) items[event.key === "Home" ? 0 : items.length - 1].focus();
            }
            // Space/Enter — düymənin native aktivləşməsi `click` verir (aşağıda), ekran oxuyucuları da.
        });

        menu.addEventListener("click", function (event) {
            // Komponent `<label>` içindədirsə klik gizli native-ə «ötürülməsin».
            if (!(event.target.closest && event.target.closest("input"))) event.preventDefault();
            var actionBtn = event.target.closest && event.target.closest("[data-ms-action]");
            if (actionBtn) {
                setMany(actionBtn.dataset.msAction === "all" ? visibleButtons() : optionButtons(), actionBtn.dataset.msAction === "all");
                return;
            }
            var button = event.target.closest && event.target.closest(".ems-multi-select__option");
            if (button) toggleOption(button);
        });

        search.addEventListener("input", applySearch);

        root.addEventListener("focusout", function (event) {
            if (isOpen() && event.relatedTarget && !root.contains(event.relatedTarget)) close(false);
        });

        // `<label>` kliki gizli native-ə fokus verərsə görünən toggle-a ötür.
        select.addEventListener("focus", function () {
            toggle.focus();
        });
        select.addEventListener("change", sync);
        if (select.form) {
            select.form.addEventListener("reset", function () {
                window.setTimeout(sync, 0);
            });
        }

        var observer = null;
        if (typeof window.MutationObserver === "function") {
            observer = new window.MutationObserver(function () {
                rebuild();
            });
            observer.observe(select, {
                childList: true,
                subtree: true,
                characterData: true,
                attributes: true,
                attributeFilter: ["selected", "disabled", "hidden", "label"],
            });
        }

        function refresh() {
            if (observer) observer.takeRecords(); // gözləyən mutasiyalar bu rebuild-ə daxildir
            rebuild();
        }

        var api = { refresh: refresh, sync: sync, open: open, close: close, root: root };
        select._emsMultiSelectApi = api;
        rebuild();
        return api;
    }

    function init(scope) {
        var base = scope || document;
        if (!base.querySelectorAll) return;
        if (base.matches && base.matches(SELECTOR)) enhance(base);
        base.querySelectorAll(SELECTOR).forEach(enhance);
    }

    window.EMSMultiSelect = {
        enhance: enhance,
        init: init,
        refresh: function (select) {
            if (!select) return;
            if (select._emsMultiSelectApi) select._emsMultiSelectApi.refresh();
            else if (select.hasAttribute && select.hasAttribute("data-ems-multi-select")) enhance(select);
        },
        sync: function (select) {
            if (select && select._emsMultiSelectApi) select._emsMultiSelectApi.sync();
        },
    };

    if (typeof window.EMSReady === "function") {
        window.EMSReady(function (detail) {
            init(detail && detail.panel ? detail.panel : document);
        });
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            init(document);
        });
    } else {
        init(document);
    }
})(window, document);
