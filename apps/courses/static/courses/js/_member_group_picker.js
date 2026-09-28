/*
 * courses/js/_member_group_picker.js — «Qrup əlavə et» modalının seçicisi (2026-09-28).
 * Mənbə: apps/courses/templates/courses/partials/_member_form_modal.html (#groupPicker).
 *
 * Köhnə seçici serverdə render olunan `exams.StudentGroup` siyahısını süzürdü —
 * həmin cədvəl real bazada BOŞDUR, modal heç vaxt qrup göstərmirdi. İndi qruplar
 * reyestrdən (`courses:available_groups`) asinxron gəlir. Göndəriş (submit)
 * `_member_form_modal.js`-dədir: forma gizli `group_ids` input-larını göndərir.
 * AJAX-safe: bütün hadisələr EMSDelegate ilə document-ə delegə olunur.
 */
(function (window, document) {
    "use strict";

    if (!window.EMSDelegate) {
        return;
    }

    var SEARCH_DEBOUNCE_MS = 250;

    function searchMatcher(query) {
        var q = String(query || "").trim();
        var m = window.EMSSearch ? window.EMSSearch.matcher(q) : null;
        var low = q.toLowerCase();
        return function (text) {
            var t = String(text || "").replace(/\u0307/g, "");
            return m ? m(t) : !low || t.toLowerCase().indexOf(low) !== -1;
        };
    }

    function cfg() {
        var el = document.getElementById("memberFormModalConfig");
        return el ? el.dataset : {};
    }

    function byId(id) {
        return document.getElementById(id);
    }

    /* ── Qrup seçicisi (2026-09-28: reyestr qrupları, asinxron) ─────────────
     * Mənbə: `courses:available_groups` → {mine: [...], others: [...]}.
     * «Mənim qruplarım» (müəllimin cari dövrdə dərs dediyi qruplar) hər zaman
     * göstərilir və yerində süzülür; axtarış sözü yazılanda serverdən təşkilatın
     * DİGƏR aktiv qrupları da gəlir. Seçilmişlər gizli `group_ids` input-ları kimi
     * çip sətrində saxlanılır — axtarış dəyişəndə itmir. */
    var groups = { seq: 0, timer: null, controller: null, mine: [], others: [], q: "" };

    function groupRoot() {
        return byId("groupPicker");
    }

    function groupChips() {
        return byId("group_selected_chips");
    }

    function groupSelected(id) {
        var chips = groupChips();
        return !!(chips && chips.querySelector('[data-group-chip="' + id + '"]'));
    }

    function updateGroupCount() {
        var chips = groupChips();
        var n = chips ? chips.querySelectorAll('input[name="group_ids"]').length : 0;
        var counter = byId("group_counter");
        var row = byId("group_selected_row");
        if (counter) {
            counter.textContent = String(n);
        }
        if (row) {
            row.hidden = n === 0;
        }
    }

    function toggleGroup(id, name, on) {
        var chips = groupChips();
        if (!chips) {
            return;
        }
        var existing = chips.querySelector('[data-group-chip="' + id + '"]');
        if (!on) {
            if (existing) {
                existing.parentNode.removeChild(existing);
            }
            var box = byId("group_" + id);
            if (box) {
                box.checked = false;
            }
            updateGroupCount();
            return;
        }
        if (existing) {
            return;
        }
        var chip = document.createElement("span");
        chip.className = "picker-chip";
        chip.setAttribute("data-group-chip", id);
        var text = document.createElement("span");
        text.className = "picker-chip__text";
        text.textContent = name;
        chip.appendChild(text);
        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "picker-chip__remove";
        remove.setAttribute("data-group-chip-remove", id);
        remove.setAttribute("aria-label", (cfg().i18nRemove || "") + ": " + name);
        remove.textContent = "×";
        chip.appendChild(remove);
        var hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "group_ids";
        hidden.value = id;
        chip.appendChild(hidden);
        chips.appendChild(chip);
        updateGroupCount();
    }

    function groupSkeleton(list) {
        list.textContent = "";
        var sk = document.createElement("div");
        sk.className = "picker-skeleton picker-skeleton--groups";
        sk.setAttribute("aria-hidden", "true");
        for (var i = 0; i < 4; i++) {
            sk.appendChild(document.createElement("span"));
        }
        list.appendChild(sk);
    }

    function groupRow(group, root) {
        var id = String(group.id);
        var row = document.createElement("label");
        row.className = "list-item-row picker-group" + (group.in_course ? " is-disabled" : "");
        row.htmlFor = "group_" + id;

        var box = document.createElement("input");
        box.type = "checkbox";
        box.id = "group_" + id;
        box.className = "custom-item-checkbox";
        box.setAttribute("data-group-id", id);
        box.setAttribute("data-group-name", group.name);
        box.checked = groupSelected(id);
        box.disabled = !!group.in_course;
        row.appendChild(box);

        var body = document.createElement("span");
        body.className = "picker-group__body";
        var title = document.createElement("span");
        title.className = "picker-group__name";
        title.textContent = group.name;
        body.appendChild(title);
        var meta = [];
        if (group.specialty) {
            meta.push(group.specialty);
        }
        if (group.subjects && group.subjects.length) {
            meta.push(group.subjects.join(", "));
        }
        if (meta.length) {
            var sub = document.createElement("span");
            sub.className = "picker-group__meta";
            sub.textContent = meta.join(" · ");
            body.appendChild(sub);
        }
        row.appendChild(body);

        var side = document.createElement("span");
        side.className = "picker-group__side";
        if (group.in_course) {
            var tag = document.createElement("span");
            tag.className = "picker-group__tag";
            tag.textContent = root.getAttribute("data-i18n-in-course") || "";
            side.appendChild(tag);
        }
        var count = document.createElement("span");
        count.className = "picker-group__count";
        count.title = root.getAttribute("data-i18n-students") || "";
        count.textContent = String(group.student_count || 0);
        side.appendChild(count);
        row.appendChild(side);
        return row;
    }

    function groupHeading(text) {
        var h = document.createElement("div");
        h.className = "picker-group__heading";
        h.textContent = text;
        return h;
    }

    function groupNote(text, isError) {
        var n = document.createElement("div");
        n.className = "picker-status" + (isError ? " picker-status--error" : "");
        n.textContent = text;
        return n;
    }

    function renderGroups() {
        var root = groupRoot();
        var list = byId("group_list_container");
        if (!root || !list) {
            return;
        }
        var match = searchMatcher(groups.q);
        var mine = groups.mine.filter(function (g) {
            return !groups.q || match(g.name + " " + (g.specialty || "") + " " + (g.subjects || []).join(" "));
        });
        list.textContent = "";
        var frag = document.createDocumentFragment();
        frag.appendChild(groupHeading(root.getAttribute("data-i18n-mine") || ""));
        if (mine.length) {
            mine.forEach(function (g) { frag.appendChild(groupRow(g, root)); });
        } else {
            frag.appendChild(groupNote(groups.q ? (root.getAttribute("data-i18n-empty-search") || "") : (root.getAttribute("data-i18n-empty-mine") || ""), false));
        }
        if (groups.q) {
            frag.appendChild(groupHeading(root.getAttribute("data-i18n-others") || ""));
            if (groups.others.length) {
                groups.others.forEach(function (g) { frag.appendChild(groupRow(g, root)); });
            } else {
                frag.appendChild(groupNote(root.getAttribute("data-i18n-empty-search") || "", false));
            }
        } else {
            frag.appendChild(groupNote(root.getAttribute("data-i18n-search-hint") || "", false));
        }
        list.appendChild(frag);
    }

    function loadGroups() {
        var root = groupRoot();
        var list = byId("group_list_container");
        if (!root || !list) {
            return;
        }
        var seq = ++groups.seq;
        if (groups.controller) {
            groups.controller.abort();
        }
        groups.controller = window.AbortController ? new window.AbortController() : null;
        list.setAttribute("aria-busy", "true");
        if (!groups.mine.length || groups.q) {
            groupSkeleton(list);
        }
        var url = root.getAttribute("data-available-url");
        var params = new URLSearchParams({ q: groups.q });
        window.EMSCore
            .fetchJSON(url + "?" + params.toString(), { signal: groups.controller ? groups.controller.signal : undefined })
            .then(function (payload) {
                if (seq !== groups.seq) {
                    return;
                }
                groups.mine = (payload && payload.mine) || [];
                groups.others = (payload && payload.others) || [];
                list.setAttribute("aria-busy", "false");
                renderGroups();
            })
            .catch(function (error) {
                if (error && error.name === "AbortError") {
                    return;
                }
                if (seq !== groups.seq) {
                    return;
                }
                list.setAttribute("aria-busy", "false");
                list.textContent = "";
                list.appendChild(groupNote(root.getAttribute("data-i18n-error") || "", true));
            });
    }

    window.EMSDelegate.on("show.bs.modal", "#addGroupModal", function () {
        var input = byId("group_search_input");
        groups.q = input ? input.value.trim() : "";
        loadGroups();
        updateGroupCount();
    });

    window.EMSDelegate.on("input", "#group_search_input", function (event, input) {
        groups.q = (input.value || "").trim();
        if (groups.timer) {
            window.clearTimeout(groups.timer);
        }
        renderGroups();
        groups.timer = window.setTimeout(loadGroups, SEARCH_DEBOUNCE_MS);
    });

    window.EMSDelegate.on("change", "#group_list_container .custom-item-checkbox", function (event, box) {
        toggleGroup(box.getAttribute("data-group-id"), box.getAttribute("data-group-name") || "", box.checked);
    });

    window.EMSDelegate.on("click", "[data-group-chip-remove]", function (event, btn) {
        toggleGroup(btn.getAttribute("data-group-chip-remove"), "", false);
    });
})(window, document);
