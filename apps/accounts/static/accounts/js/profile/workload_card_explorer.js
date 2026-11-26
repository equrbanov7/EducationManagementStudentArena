/* Fənn kartındakı mövcud bölgüləri yerində süzür. Yaddaş yalnız cari DOM-a aiddir. */
(function (window, document) {
    "use strict";

    var gettext = window.gettext || function (value) { return value; };
    var LIMIT = 4;
    var instances = new WeakMap();

    function fold(text) {
        return String(text || "").toLowerCase().normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "").replace(/ə/g, "e").replace(/ı/g, "i").trim();
    }

    function formatCount(template, count) {
        return window.EMSWorkloadCards.fmt(template, { n: count });
    }

    function textOf(node, selector) {
        return Array.from(node.querySelectorAll(selector), function (item) { return item.textContent; }).join(" ");
    }

    function matches(text, terms) {
        return terms.every(function (term) { return text.indexOf(term) !== -1; });
    }

    function buttonFor(list, id, inside) {
        list.id = id;
        var button = document.createElement("button");
        button.type = "button";
        button.className = "wl-preview-toggle";
        button.setAttribute("data-wl-preview-toggle", "");
        button.setAttribute("aria-controls", id);
        var sectionTitle = list.closest(".wl-kind").querySelector(".wl-kind__label");
        if (sectionTitle) button.setAttribute("aria-describedby", sectionTitle.id);
        if (inside) {
            var wrapper = document.createElement(list.tagName === "UL" ? "li" : "span");
            wrapper.className = "wl-preview-more";
            wrapper.appendChild(button);
            list.appendChild(wrapper);
        } else {
            list.after(button);
        }
        return button;
    }

    function preview(list, elements, id, key, saved, nested, focusRow) {
        var button = elements.length > LIMIT ? buttonFor(list, id, nested) : null;
        var expanded = !!(saved && saved.has(key));
        var items = elements.map(function (node) {
            var hit = node.matches(".is-match") || !!node.querySelector(".is-match");
            var rowId = node.dataset.rowId || node.dataset.leadRowId;
            var names = node.matches(".wl-stream__teacher,.wl-chip,.wl-pill") ? node.textContent :
                textOf(node, ".wl-line__group,.wl-pill,.wl-chip__name,.wl-chip__section,.wl-chip__note,.wl-stream__teacher,.wl-line__vacant,.wl-badge--section,.wl-act__label");
            return { node: node, text: fold(names), priority: hit || (!!focusRow && rowId === focusRow) };
        });
        // Saxlama sırası eyni qalır, URL-dən və müəllim süzgəcindən hədəflənən sətir ilkin görünüşə daxil olur.
        var ordered = items.filter(function (item) { return item.priority; })
            .concat(items.filter(function (item) { return !item.priority; }));
        var first = new Set(ordered.slice(0, LIMIT));
        var currentTerms = [];
        function draw(terms) {
            currentTerms = terms;
            var count = 0;
            items.forEach(function (item) {
                var found = matches(item.text, terms);
                if (found) count += 1;
                item.node.hidden = terms.length ? !found : !(expanded || !button || first.has(item));
            });
            if (button) {
                button.hidden = !!terms.length;
                if (nested) button.parentElement.hidden = !!terms.length;
                button.setAttribute("aria-expanded", String(expanded));
                button.textContent = expanded ? gettext("Daha az göstər") : formatCount(gettext("Hamısını göstər (%(n)s)"), items.length);
            }
            return count;
        }
        if (button) button.addEventListener("click", function () {
            expanded = !expanded;
            draw(currentTerms);
        });
        return { key: key, draw: draw, expanded: function () { return expanded; } };
    }

    function createSearch(card) {
        var bar = document.createElement("div");
        bar.className = "wl-card-search";
        var label = document.createElement("label");
        var icon = document.createElement("i");
        icon.className = "fas fa-magnifying-glass";
        icon.setAttribute("aria-hidden", "true");
        var input = document.createElement("input");
        input.type = "search";
        input.placeholder = gettext("Qrup və ya müəllim axtar");
        input.setAttribute("aria-label", input.placeholder);
        var subject = card.querySelector(".wl-card__subject");
        subject.id = "wl-subject-" + card.dataset.cardId;
        input.setAttribute("aria-describedby", subject.id);
        input.setAttribute("data-wl-card-search", "");
        label.append(icon, input);
        var status = document.createElement("span");
        status.setAttribute("data-wl-search-status", "");
        status.setAttribute("role", "status");
        bar.append(label, status);
        card.querySelector(".wl-card__head").after(bar);
        return { input: input, status: status };
    }

    function bindCard(card, previous) {
        var details = card.querySelector("[data-wl-card-rows]");
        var opener = card.querySelector("[data-wl-card-rows-toggle]");
        details.addEventListener("toggle", function () { opener.setAttribute("aria-expanded", String(details.open)); });
        if (window.EMSWorkloadPickers && window.EMSDelegate) card.classList.add("wl-card--has-plan-toggle");
        var groupList = card.querySelector(".wl-card__group-list");
        var groups = Array.from(card.querySelectorAll(".wl-card__group"), function (node) {
            return { node: node, name: fold(node.textContent) };
        });
        var sets = [];
        var nestedSets = [];
        var scope = card.closest("[data-focus-row]");
        var focusRow = scope ? scope.dataset.focusRow : "";
        var id = "wl-preview-" + card.dataset.cardId;
        var large = groups.length > LIMIT;
        var teachers = new Set();
        Array.from(card.querySelectorAll(":scope > .wl-kind")).forEach(function (section) {
            var list = section.querySelector(":scope > .wl-lines, :scope > .wl-streams") || section;
            var rows = Array.from(list.children).filter(function (element) {
                return element.matches(".wl-line,.wl-stream,.wl-act");
            });
            if (!rows.length) return;
            var kind = section.className.match(/wl-kind--([\w-]+)/)[1];
            var sectionId = id + "-" + kind;
            var heading = section.querySelector(".wl-kind__label");
            if (heading) heading.id = sectionId + "-heading";
            large = large || rows.length > LIMIT;
            var parentSet = preview(list, rows, sectionId, kind, previous.expanded, false, focusRow);
            sets.push({ section: section, preview: parentSet });
            rows.forEach(function (row, index) {
                if (!large) {
                    row.querySelectorAll(".wl-chip__name,.wl-stream__teacher").forEach(function (teacher) {
                        teachers.add(fold(teacher.textContent));
                    });
                    large = teachers.size > LIMIT;
                }
                var rowKey = [kind, row.dataset.rowId || row.dataset.leadRowId, row.dataset.groupId || row.dataset.activity || ""].join("|");
                var groupLabel = row.querySelector(".wl-stream__groups,.wl-line__group");
                var names = row.querySelector(".wl-line__entries,.wl-stream__who");
                function addNested(container, contextSelector, prefix) {
                    if (!container || container.children.length <= LIMIT) return;
                    large = true;
                    var elements = Array.from(container.children);
                    var set = preview(container, elements, sectionId + prefix + index, rowKey + prefix, previous.expanded, true, "");
                    nestedSets.push({ context: fold(textOf(row, contextSelector)), preview: set });
                }
                addNested(names, ".wl-line__group,.wl-pill,.wl-act__label", "-who-");
                addNested(groupLabel, ".wl-stream__teacher,.wl-chip__name,.wl-chip__section", "-groups-");
            });
        });
        var initialGroupOpen = previous.groupOpen || false;
        if (groupList) groupList.open = initialGroupOpen;
        var search = large ? createSearch(card) : null;
        var filtering = false;
        function update() {
            var query = search ? fold(search.input.value) : "";
            var terms = query ? query.split(/\s+/) : [];
            var count = 0;
            sets.forEach(function (set) {
                var found = set.preview.draw(terms);
                count += found;
                set.section.hidden = !!query && !found;
            });
            nestedSets.forEach(function (set) {
                var remainingTerms = terms.filter(function (term) { return !matches(set.context, [term]); });
                set.preview.draw(remainingTerms);
            });
            var matchedGroups = 0;
            groups.forEach(function (group) {
                group.node.hidden = !!query && !matches(group.name, terms);
                if (!group.node.hidden) matchedGroups += 1;
            });
            if (groupList) {
                if (query && !filtering) initialGroupOpen = groupList.open;
                groupList.hidden = !!query && !matchedGroups;
                groupList.open = query ? !!matchedGroups && (initialGroupOpen || !count) : initialGroupOpen;
            }
            if (search) {
                var total = count || matchedGroups;
                search.status.textContent = !query ? "" : total ? formatCount(gettext("%(n)s nəticə"), total) : gettext("Uyğun nəticə tapılmadı.");
            }
            filtering = !!query;
        }
        if (search) {
            search.input.value = previous.query || "";
            search.input.addEventListener("input", update);
        }
        update();
        instances.set(card, function () {
            var expanded = new Set();
            sets.concat(nestedSets).forEach(function (set) {
                if (set.preview.expanded()) expanded.add(set.preview.key);
            });
            return { expanded: expanded, query: search ? search.input.value : "",
                groupOpen: filtering ? initialGroupOpen : !!(groupList && groupList.open) };
        });
    }

    window.EMSWorkloadCardExplorer = {
        capture: function (host) {
            var saved = new Map();
            host.querySelectorAll("[data-wl-card]").forEach(function (card) {
                if (instances.has(card)) saved.set(card.dataset.cardKey, instances.get(card)());
            });
            return saved;
        },
        bind: function (host, saved) {
            host.querySelectorAll("[data-wl-card]").forEach(function (card) {
                if (!instances.has(card)) bindCard(card, saved && saved.get(card.dataset.cardKey) || {});
            });
        }
    };
})(window, document);
