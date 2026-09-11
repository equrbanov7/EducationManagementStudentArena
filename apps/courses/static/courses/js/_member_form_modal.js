/*
 * _member_form_modal.js
 * Mənbə: apps/courses/templates/courses/partials/_member_form_modal.html
 *
 * «Tələbə əlavə et» / «Qrup əlavə et» modalları: AJAX göndəriş (uğurda reload)
 * və window.deleteMember. Konfiq (üzv-silmə URL-i + i18n) #memberFormModalConfig
 * data-* atributlarından oxunur; CSRF/fetch — EMSCore.fetchJSON.
 *
 * Audit 2026-09-10 P1-4 (düzəliş 2026-09-12): tələbə siyahısı artıq serverdə
 * render olunmur — real bazada auth_user = 8 443 sətir idi və modal ~8 min DOM
 * sətri çıxarırdı. İndi «Tələbələr» seçicisi asinxron picker-dir:
 *   - modal açılanda ilk səhifə (20) `courses:available_students`-dən gəlir;
 *   - yazdıqca (debounce 250 ms) `q` ilə axtarılır, köhnə cavablar `seq` +
 *     AbortController ilə atılır;
 *   - «Daha çox göstər» növbəti səhifəni ƏLAVƏ edir (server max 50/sorğu);
 *   - seçilənlər axtarışlar arasında İTMİR: hər seçilmiş id üçün formada gizli
 *     `<input name="user_ids">` (çip sətrində) saxlanılır — POST müqaviləsi
 *     (user_ids[] + group_name) dəyişməyib; nəticə sətirlərinin checkbox-larının
 *     `name`-i YOXDUR ki, eyni id iki dəfə göndərilməsin.
 *
 * AJAX-safe: bütün hadisələr `EMSDelegate` ilə document-ə delegə olunur
 * (seçicilər bu fayla məxsusdur — test_static_js_delegate_keys), yalnız
 * window.deleteMember `EMSReady` içində təyin olunur ki, bu partial-ın
 * tərifi course_dashboard.js-in dərhal təyinatını üstələsin.
 */
(function (window, document) {
    "use strict";

    if (!window.EMSDelegate || !window.EMSReady) {
        if (window.console && window.console.warn) {
            window.console.warn("_member_form_modal.js: EMSDelegate/EMSReady yoxdur — ems_early.js yüklənməyib?");
        }
        return;
    }

    var SEARCH_DEBOUNCE_MS = 250;

    function cfg() {
        var el = document.getElementById("memberFormModalConfig");
        return el ? el.dataset : {};
    }

    function byId(id) {
        return document.getElementById(id);
    }

    /* ── Tələbə picker-i (P1-4) ─────────────────────────────────────────── */
    var picker = {
        q: "",
        page: 1,
        hasMore: false,
        loading: false,
        seq: 0,
        timer: null,
        controller: null
    };

    function pickerRoot() {
        return byId("studentPicker");
    }

    function listEl() {
        return byId("student_list_container");
    }

    function chipsEl() {
        return byId("student_selected_chips");
    }

    function moreBtn() {
        return document.querySelector("[data-student-picker-more]");
    }

    function selectedIds() {
        var chips = chipsEl();
        if (!chips) {
            return [];
        }
        return Array.prototype.map.call(chips.querySelectorAll('input[name="user_ids"]'), function (input) {
            return input.value;
        });
    }

    function isSelected(id) {
        var chips = chipsEl();
        return !!(chips && chips.querySelector('[data-student-chip="' + id + '"]'));
    }

    function updateSelectionUi() {
        var count = selectedIds().length;
        var counter = byId("student_counter");
        var row = byId("student_selected_row");
        if (counter) {
            counter.textContent = String(count);
        }
        if (row) {
            row.hidden = count === 0;
        }
    }

    /** Seçilmiş id üçün çip + gizli `user_ids` input-u (formanın göndərdiyi dəyər). */
    function addSelection(id, label) {
        var chips = chipsEl();
        if (!chips || isSelected(id)) {
            return;
        }
        var d = cfg();

        var chip = document.createElement("span");
        chip.className = "picker-chip";
        chip.setAttribute("data-student-chip", id);

        var text = document.createElement("span");
        text.className = "picker-chip__text";
        text.textContent = label;
        chip.appendChild(text);

        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "picker-chip__remove";
        remove.setAttribute("data-student-chip-remove", id);
        remove.setAttribute("aria-label", (d.i18nRemove || "") + ": " + label);
        remove.textContent = "×";
        chip.appendChild(remove);

        var hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "user_ids";
        hidden.value = id;
        chip.appendChild(hidden);

        chips.appendChild(chip);
        updateSelectionUi();
    }

    function removeSelection(id) {
        var chips = chipsEl();
        var chip = chips ? chips.querySelector('[data-student-chip="' + id + '"]') : null;
        if (chip) {
            chip.parentNode.removeChild(chip);
        }
        var checkbox = byId("user_" + id);
        if (checkbox) {
            checkbox.checked = false;
        }
        updateSelectionUi();
    }

    function clearSelection() {
        var chips = chipsEl();
        var list = listEl();
        if (chips) {
            chips.textContent = "";
        }
        if (list) {
            Array.prototype.forEach.call(list.querySelectorAll(".custom-item-checkbox"), function (checkbox) {
                checkbox.checked = false;
            });
        }
        updateSelectionUi();
    }

    function setStatus(text, isError) {
        var list = listEl();
        if (!list) {
            return;
        }
        var status = list.querySelector("[data-student-picker-status]");
        if (!text) {
            if (status) {
                status.parentNode.removeChild(status);
            }
            return;
        }
        if (!status) {
            status = document.createElement("div");
            status.setAttribute("data-student-picker-status", "");
            list.appendChild(status);
        }
        status.className = "picker-status" + (isError ? " picker-status--error" : "");
        status.textContent = text;
    }

    function chipLabel(user) {
        var username = user.username || String(user.id);
        if (user.full_name && user.full_name !== user.username) {
            return username + " (" + user.full_name + ")";
        }
        return username;
    }

    /** Nəticə sətri — textContent ilə qurulur (XSS yoxdur), checkbox-da `name` YOXDUR. */
    function renderRow(user) {
        var id = String(user.id);

        var row = document.createElement("div");
        row.className = "list-item-row";
        row.setAttribute("data-user-id", id);

        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.id = "user_" + id;
        checkbox.className = "custom-item-checkbox";
        checkbox.setAttribute("data-user-id", id);
        checkbox.setAttribute("data-label", chipLabel(user));
        checkbox.checked = isSelected(id);

        var label = document.createElement("label");
        label.htmlFor = checkbox.id;
        label.className = "custom-item-label";
        label.textContent = user.username || "";
        if (user.full_name && user.full_name !== user.username) {
            var muted = document.createElement("span");
            muted.className = "text-muted";
            muted.textContent = " (" + user.full_name + ")";
            label.appendChild(muted);
        }

        row.appendChild(checkbox);
        row.appendChild(label);
        return row;
    }

    function clearRows() {
        var list = listEl();
        if (!list) {
            return;
        }
        Array.prototype.forEach.call(list.querySelectorAll(".list-item-row"), function (row) {
            row.parentNode.removeChild(row);
        });
    }

    /**
     * Cari `picker.q` / `picker.page` ilə endpoint-i çağırır.
     * append=false → siyahı sıfırlanır (yeni axtarış), append=true → növbəti səhifə.
     */
    function load(append) {
        var root = pickerRoot();
        var list = listEl();
        if (!root || !list) {
            return;
        }
        var url = root.getAttribute("data-available-url");
        if (!url) {
            return;
        }
        var d = cfg();
        var pageSize = parseInt(root.getAttribute("data-page-size"), 10) || 20;
        var params = new URLSearchParams({
            q: picker.q,
            page: String(picker.page),
            limit: String(pageSize)
        });
        var seq = ++picker.seq;

        if (picker.controller) {
            picker.controller.abort();
        }
        picker.controller = window.AbortController ? new window.AbortController() : null;
        picker.loading = true;
        list.setAttribute("aria-busy", "true");

        var more = moreBtn();
        if (more) {
            more.disabled = true;
        }
        if (!append) {
            clearRows();
            setStatus(d.i18nLoading || "", false);
        }

        window.EMSCore
            .fetchJSON(url + (url.indexOf("?") === -1 ? "?" : "&") + params.toString(), {
                signal: picker.controller ? picker.controller.signal : undefined
            })
            .then(function (payload) {
                if (seq !== picker.seq) {
                    return; // köhnə cavab — daha yeni sorğu var
                }
                var users = (payload && payload.users) || [];
                setStatus("", false);
                var fragment = document.createDocumentFragment();
                users.forEach(function (user) {
                    if (!byId("user_" + user.id)) {
                        fragment.appendChild(renderRow(user));
                    }
                });
                list.appendChild(fragment);
                if (!list.querySelector(".list-item-row")) {
                    setStatus(d.i18nEmpty || "", false);
                }
                picker.hasMore = !!(payload && payload.has_more);
                if (more) {
                    more.hidden = !picker.hasMore;
                }
            })
            .catch(function (error) {
                if ((error && error.name === "AbortError") || seq !== picker.seq) {
                    return;
                }
                setStatus(d.i18nServerError || d.i18nError || "Error", true);
                picker.hasMore = false;
                if (more) {
                    more.hidden = true;
                }
            })
            .then(function () {
                if (seq !== picker.seq) {
                    return;
                }
                picker.loading = false;
                list.setAttribute("aria-busy", "false");
                if (more) {
                    more.disabled = false;
                }
            });
    }

    function resetPicker() {
        var input = byId("student_search_input");
        var more = moreBtn();
        if (picker.timer) {
            window.clearTimeout(picker.timer);
            picker.timer = null;
        }
        picker.q = "";
        picker.page = 1;
        picker.hasMore = false;
        if (input) {
            input.value = "";
        }
        if (more) {
            more.hidden = true;
        }
        clearSelection();
        load(false);
    }

    // Bootstrap `show.bs.modal` modal elementindən qabarcıqlanır (bubbles) —
    // document-dəki delegat onu tutur. modal.js-in `form.reset()`-i (elementin
    // öz dinləyicisi) bundan ƏVVƏL işləyir, sonra biz təzə siyahını yükləyirik.
    window.EMSDelegate.on("show.bs.modal", "#addStudentModal", function () {
        resetPicker();
    });

    window.EMSDelegate.on("input", "#student_search_input", function (event, input) {
        var value = (input.value || "").trim();
        if (picker.timer) {
            window.clearTimeout(picker.timer);
        }
        picker.timer = window.setTimeout(function () {
            picker.timer = null;
            picker.q = value;
            picker.page = 1;
            load(false);
        }, SEARCH_DEBOUNCE_MS);
    });

    // Enter axtarış sahəsində formanı göndərməməlidir.
    window.EMSDelegate.on("keydown", "#student_search_input", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
        }
    });

    window.EMSDelegate.on("change", "#student_list_container .custom-item-checkbox", function (event, checkbox) {
        var id = checkbox.getAttribute("data-user-id");
        if (!id) {
            return;
        }
        if (checkbox.checked) {
            addSelection(id, checkbox.getAttribute("data-label") || id);
        } else {
            removeSelection(id);
        }
    });

    // Sətrin boş sahəsinə klik — checkbox/label-in öz davranışına toxunmuruq.
    window.EMSDelegate.on("click", "#student_list_container .list-item-row", function (event, row) {
        if (event.target.closest("input, label")) {
            return;
        }
        var checkbox = row.querySelector(".custom-item-checkbox");
        if (!checkbox) {
            return;
        }
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event("change", { bubbles: true }));
    });

    window.EMSDelegate.on("click", "[data-student-chip-remove]", function (event, button) {
        removeSelection(button.getAttribute("data-student-chip-remove"));
    });

    window.EMSDelegate.on("click", "[data-student-picker-clear]", function () {
        clearSelection();
    });

    window.EMSDelegate.on("click", "[data-student-picker-more]", function () {
        if (picker.loading || !picker.hasMore) {
            return;
        }
        picker.page += 1;
        load(true);
    });

    /* ── Qrup seçicisi (müəllimin öz qrupları — kiçik siyahı, serverdən gəlir) ── */
    function updateGroupCount() {
        var container = byId("group_list_container");
        var counter = byId("group_counter");
        if (container && counter) {
            counter.textContent = String(container.querySelectorAll('input[type="checkbox"]:checked').length);
        }
    }

    function filterGroupRows(term) {
        var container = byId("group_list_container");
        if (!container) {
            return;
        }
        Array.prototype.forEach.call(container.querySelectorAll(".list-item-row"), function (row) {
            var haystack = row.getAttribute("data-search") || "";
            row.classList.toggle("is-hidden", term !== "" && haystack.indexOf(term) === -1);
        });
    }

    window.EMSDelegate.on("show.bs.modal", "#addGroupModal", function () {
        filterGroupRows("");
        updateGroupCount();
    });

    window.EMSDelegate.on("input", "#group_search_input", function (event, input) {
        filterGroupRows((input.value || "").toLowerCase());
    });

    window.EMSDelegate.on("change", "#group_list_container .custom-item-checkbox", function () {
        updateGroupCount();
    });

    window.EMSDelegate.on("click", "#group_list_container .list-item-row", function (event, row) {
        if (event.target.closest("input, label")) {
            return;
        }
        var checkbox = row.querySelector(".custom-item-checkbox");
        if (checkbox) {
            checkbox.checked = !checkbox.checked;
            updateGroupCount();
        }
    });

    /* ── Formaların AJAX göndərişi ─────────────────────────────────────────── */
    function submitMembersForm(form, idsField, emptyMessage) {
        var d = cfg();
        var button = form.querySelector('button[type="submit"]');
        var formData = new FormData(form);
        if (formData.getAll(idsField).length === 0) {
            window.alert(emptyMessage);
            return;
        }
        var originalText = button ? button.innerText : "";
        if (button) {
            button.innerText = d.i18nAdding || originalText;
            button.disabled = true;
        }

        function restore() {
            if (button) {
                button.innerText = originalText;
                button.disabled = false;
            }
        }

        window.EMSCore
            .fetchJSON(form.action, { method: "POST", body: formData })
            .then(function (data) {
                if (data && data.success) {
                    window.location.reload();
                    return;
                }
                window.alert((d.i18nErrorPrefix || "") + ((data && data.error) || d.i18nUnknownError || ""));
                restore();
            })
            .catch(function (error) {
                var payloadError = error && error.payload && error.payload.error;
                if (payloadError) {
                    window.alert((d.i18nErrorPrefix || "") + payloadError);
                } else {
                    if (window.console && window.console.error) {
                        window.console.error("Error:", error);
                    }
                    window.alert(d.i18nServerError || "");
                }
                restore();
            });
    }

    window.EMSDelegate.on("submit", "#addStudentForm", function (event, form) {
        event.preventDefault();
        submitMembersForm(form, "user_ids", cfg().i18nMinOneStudent || "");
    });

    window.EMSDelegate.on("submit", "#addGroupForm", function (event, form) {
        event.preventDefault();
        submitMembersForm(form, "group_ids", cfg().i18nMinOneGroup || "");
    });

    /* ── window.deleteMember (üzv silmə düyməsi — csp_event_handlers.js çağırır) ── */
    window.EMSReady(function () {
        var d = cfg();
        if (!d.deleteMemberUrl) {
            return;
        }
        window.deleteMember = function (memberId, name) {
            if (!window.confirm(name + (d.i18nDeleteMemberConfirmSuffix || ""))) {
                return;
            }
            // Şablon URL-i `/members/0/delete/` ilə bitir; sadə `.replace("0", …)`
            // kurs id-sindəki ilk «0»-ı əvəz edirdi (məs. /courses/10/…) — sonluğu hədəfləyirik.
            var url = d.deleteMemberUrl.replace(/\/0\/delete\/?$/, "/" + memberId + "/delete/");
            window.EMSCore
                .fetchJSON(url, { method: "POST" })
                .then(function (data) {
                    if (data && data.success) {
                        window.location.reload();
                    } else {
                        window.alert((d.i18nDeleteFailedPrefix || "") + ((data && data.error) || d.i18nError || ""));
                    }
                })
                .catch(function (error) {
                    if (window.console && window.console.error) {
                        window.console.error("Error:", error);
                    }
                    window.alert(d.i18nServerError || "");
                });
        };
    });
})(window, document);
