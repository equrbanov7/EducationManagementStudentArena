/* =========================================================================
   «Fənləri birləşdir» — fənn kataloqu dialoqu (2026-10-19).

   Axın: hədəf (tək) + mənbə(lər) (çox) seçilir → «Önizlə» POST (dry-run) →
   cədvəl sayları, toqquşmalar (linklərlə), xəbərdarlıqlar və İZ (digest) →
   səbəb ≥20 → «Birləşdir» POST (iz ilə). Seçim dəyişən kimi iz sıfırlanır və
   «Birləşdir» yenidən bağlanır — köhnə önizləmə ilə yazı getmir.

   AJAX-SAFE: skript panel swap-da yenidən icra oluna bilər — qlobal bayraq
   ikinci qeydiyyatı kəsir; bütün hadisələr `EMSDelegate` ilə sənəd səviyyəsində.
   URL-lər və mətnlər dialoqun `data-sm-*` atributlarındadır (CSP: inline yoxdur).
   Server mətnləri YALNIZ `textContent` ilə yazılır.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSSubjectMerge) {
        return;
    }

    var MIN_REASON = 20;

    function dialog() {
        return document.querySelector("[data-sm-root]");
    }

    function text(root, key) {
        return (root && root.getAttribute("data-sm-text-" + key)) || "";
    }

    function el(tag, className, content) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (content !== undefined && content !== null) {
            node.textContent = String(content);
        }
        return node;
    }

    function csrf(root) {
        var field = root.querySelector('input[name="csrfmiddlewaretoken"]');
        return (field && field.value) || (window.EMSCore && window.EMSCore.getCsrfToken && window.EMSCore.getCsrfToken()) || "";
    }

    function post(root, url, payload) {
        var body = new URLSearchParams();
        Object.keys(payload).forEach(function (key) {
            var value = payload[key];
            (Array.isArray(value) ? value : [value]).forEach(function (item) {
                if (item !== null && item !== undefined) {
                    body.append(key, item);
                }
            });
        });
        return window.EMSCore.fetchJSON(url, {
            method: "POST",
            body: body.toString(),
            headers: {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-CSRFToken": csrf(root),
            },
        });
    }

    function showError(root, message) {
        var box = root.querySelector("[data-ems-form-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
    }

    /* ---- Seçicilər --------------------------------------------------------- */

    function pickers(root) {
        if (root._smPickers && document.contains(root._smPickers.target.el)) {
            return root._smPickers;
        }
        var url = root.getAttribute("data-sm-lookup-url") || "";
        var targetHost = root.querySelector("[data-sm-target-picker]");
        var sourcesHost = root.querySelector("[data-sm-sources-picker]");
        if (!url || !targetHost || !sourcesHost || !window.EMSSearchableSelect) {
            return null;
        }
        var invalidate = function () {
            resetPreview(root, true);
        };
        root._smPickers = {
            target: window.EMSSearchableSelect.create(targetHost, {
                url: url,
                multi: false,
                skeleton: true,
                emptyText: targetHost.getAttribute("data-empty") || "",
                onChange: invalidate,
            }),
            sources: window.EMSSearchableSelect.create(sourcesHost, {
                url: url + (url.indexOf("?") === -1 ? "?" : "&") + "archived=1",
                multi: true,
                skeleton: true,
                emptyText: sourcesHost.getAttribute("data-empty") || "",
                onChange: invalidate,
            }),
        };
        return root._smPickers;
    }

    function selection(root) {
        var pick = pickers(root);
        if (!pick) {
            return { target: "", sources: [] };
        }
        var target = pick.target.value();
        var sources = pick.sources.ids().filter(function (id) {
            return id && id !== target;
        });
        return { target: target, sources: sources };
    }

    function label(subject) {
        return subject.code + " — " + subject.name + " (" + subject.ects + " ECTS)";
    }

    function applyGroup(root, group) {
        var pick = pickers(root);
        if (!pick || !group) {
            return;
        }
        pick.target.reset();
        pick.sources.reset();
        group.subjects.forEach(function (subject) {
            if (subject.id === group.target) {
                pick.target.setValue(subject.id, label(subject));
            } else {
                pick.sources.setValue(subject.id, label(subject));
            }
        });
        resetPreview(root, true);
    }

    /* ---- Dublikat qrupları (hazır təklif) ---------------------------------- */

    function renderGroups(root, groups, focusSubject) {
        var list = root.querySelector("[data-sm-groups]");
        var box = root.querySelector("[data-sm-groups-box]");
        if (!list) {
            return;
        }
        list.textContent = "";
        if (!groups.length) {
            list.appendChild(el("p", "sm-muted", text(root, "no-groups")));
            return;
        }
        var chosen = null;
        groups.forEach(function (group, index) {
            var row = el("div", "sm-group");
            var names = el("div", "sm-group__names");
            group.subjects.forEach(function (subject) {
                var item = el("span", "sm-group__item" + (subject.id === group.target ? " is-keep" : ""));
                item.appendChild(el("strong", "", subject.code));
                item.appendChild(document.createTextNode(" " + subject.name));
                var meta = subject.offerings + " " + text(root, "offerings");
                if (subject.id === group.target) {
                    meta += " · " + text(root, "keep");
                }
                item.appendChild(el("small", "sm-muted", " (" + meta + ")"));
                names.appendChild(item);
                if (focusSubject && subject.id === focusSubject) {
                    chosen = group;
                }
            });
            var use = el("button", "ems-btn ems-btn--sm", text(root, "use"));
            use.type = "button";
            use.setAttribute("data-sm-use-group", String(index));
            row.appendChild(names);
            row.appendChild(use);
            list.appendChild(row);
        });
        root._smGroups = groups;
        if (chosen) {
            applyGroup(root, chosen);
        } else if (box && !focusSubject) {
            box.open = true;
        }
    }

    function loadGroups(root, focusSubject) {
        var url = root.getAttribute("data-sm-groups-url");
        if (!url || typeof window.fetch !== "function") {
            return;
        }
        window
            .fetch(url, { credentials: "same-origin", headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" } })
            .then(function (response) {
                return response.ok ? response.json() : { groups: [] };
            })
            .then(function (payload) {
                renderGroups(root, (payload && payload.groups) || [], focusSubject);
            })
            .catch(function () {
                renderGroups(root, [], focusSubject);
            });
    }

    /* ---- Önizləmə ---------------------------------------------------------- */

    function resetPreview(root, stale) {
        var result = root.querySelector("[data-sm-result]");
        var digest = root.querySelector("[data-sm-digest]");
        var reasonBox = root.querySelector("[data-sm-reason-box]");
        if (digest) {
            digest.value = "";
        }
        if (result && stale && !result.hidden) {
            result.textContent = "";
            result.appendChild(el("p", "ems-msg ems-msg--info", text(root, "stale")));
        } else if (result && !stale) {
            result.textContent = "";
            result.hidden = true;
        }
        if (reasonBox) {
            reasonBox.hidden = true;
        }
        syncSubmit(root);
    }

    function safeHref(url) {
        var value = String(url || "");
        return value.charAt(0) === "/" && value.charAt(1) !== "/" ? value : "";
    }

    function messageList(root, title, items, tone, total) {
        var section = el("section", "sm-block sm-block--" + tone);
        section.appendChild(el("h3", "sm-block__title", title));
        var list = el("ul", "sm-list");
        items.forEach(function (item) {
            var li = el("li", "sm-list__item");
            li.appendChild(el("span", "", typeof item === "string" ? item : item.message));
            (item.links || []).forEach(function (link) {
                var href = safeHref(link.url);
                if (!href) {
                    return;
                }
                var anchor = el("a", "sm-link", link.label);
                anchor.href = href;
                anchor.target = "_blank";
                anchor.rel = "noopener";
                li.appendChild(anchor);
            });
            list.appendChild(li);
        });
        section.appendChild(list);
        if (total && total > items.length) {
            section.appendChild(el("p", "sm-muted", text(root, "more").replace("{n}", String(total - items.length))));
        }
        return section;
    }

    function renderPreview(root, data) {
        var result = root.querySelector("[data-sm-result]");
        if (!result) {
            return;
        }
        result.textContent = "";
        result.hidden = false;

        var tables = el("section", "sm-block");
        var rows = data.tables.filter(function (table) {
            return table.count > 0;
        });
        if (!rows.length) {
            tables.appendChild(el("p", "sm-muted", text(root, "nothing")));
        } else {
            var list = el("dl", "sm-counts");
            rows.forEach(function (table) {
                list.appendChild(el("dt", "sm-counts__name", table.title));
                var suffix = table.strategy === "keep" ? text(root, "keeps") : text(root, "moves");
                var detail = table.by_source
                    .map(function (part) {
                        return part.code + ": " + part.count;
                    })
                    .join(", ");
                list.appendChild(el("dd", "sm-counts__value", table.count + " · " + suffix + (detail ? " (" + detail + ")" : "")));
            });
            tables.appendChild(list);
        }
        tables.appendChild(el("p", "sm-muted", text(root, "archive") + " «" + data.archive_reason + "»"));
        result.appendChild(tables);

        if (data.blocking.length) {
            result.appendChild(messageList(root, text(root, "blocking"), data.blocking, "danger", data.blocking_total));
        }
        if (data.resolvable.length) {
            result.appendChild(messageList(root, text(root, "resolvable"), data.resolvable, "info", data.resolvable_total));
        }
        if (data.warnings.length) {
            result.appendChild(messageList(root, text(root, "warnings"), data.warnings, "warning"));
        }
        if (data.info.length) {
            result.appendChild(messageList(root, text(root, "info"), data.info, "info"));
        }
        if (data.can_apply) {
            result.appendChild(el("p", "ems-msg ems-msg--success", text(root, "ready")));
        }
        var digest = root.querySelector("[data-sm-digest]");
        if (digest) {
            digest.value = data.can_apply ? data.digest : "";
        }
        var reasonBox = root.querySelector("[data-sm-reason-box]");
        if (reasonBox) {
            reasonBox.hidden = !data.can_apply;
        }
        syncSubmit(root);
    }

    function syncSubmit(root) {
        var submit = root.querySelector("[data-sm-submit]");
        var digest = root.querySelector("[data-sm-digest]");
        var reason = root.querySelector("[data-sm-reason]");
        if (!submit) {
            return;
        }
        var ok = !!(digest && digest.value) && !!reason && reason.value.trim().length >= MIN_REASON;
        submit.disabled = !ok || root._smBusy === true;
    }

    function runPreview(root) {
        var picked = selection(root);
        showError(root, "");
        if (!picked.target || !picked.sources.length) {
            showError(root, text(root, "pick"));
            return;
        }
        var button = root.querySelector("[data-sm-preview]");
        if (button) {
            button.disabled = true;
        }
        post(root, root.getAttribute("data-sm-preview-url"), { target: picked.target, sources: picked.sources })
            .then(function (payload) {
                renderPreview(root, payload.preview);
            })
            .catch(function (err) {
                var payload = err && err.payload;
                showError(root, (payload && payload.message) || text(root, "error"));
                resetPreview(root, false);
            })
            .then(function () {
                if (button) {
                    button.disabled = false;
                }
            });
    }

    /* ---- Hadisələr --------------------------------------------------------- */

    window.EMSDelegate.on("click", "[data-sm-open]", function (event, btn) {
        event.preventDefault();
        var root = dialog();
        if (!root) {
            return;
        }
        showError(root, "");
        var reason = root.querySelector("[data-sm-reason]");
        if (reason) {
            reason.value = "";
        }
        if (window.EMSOverlay) {
            window.EMSOverlay.open(root);
        }
        var pick = pickers(root);
        if (pick) {
            pick.target.reset();
            pick.sources.reset();
        }
        resetPreview(root, false);
        loadGroups(root, btn.getAttribute("data-sm-subject") || "");
    });

    window.EMSDelegate.on("click", "[data-sm-use-group]", function (event, btn) {
        event.preventDefault();
        var root = dialog();
        var groups = (root && root._smGroups) || [];
        applyGroup(root, groups[Number(btn.getAttribute("data-sm-use-group"))]);
    });

    window.EMSDelegate.on("click", "[data-sm-preview]", function (event) {
        event.preventDefault();
        var root = dialog();
        if (root) {
            runPreview(root);
        }
    });

    window.EMSDelegate.on("input", "[data-sm-reason]", function () {
        var root = dialog();
        if (root) {
            syncSubmit(root);
        }
    });

    window.EMSDelegate.on("submit", "form[data-sm-form]", function (event, form) {
        event.preventDefault();
        var root = dialog();
        if (!root) {
            return;
        }
        var picked = selection(root);
        var digest = root.querySelector("[data-sm-digest]");
        var reason = root.querySelector("[data-sm-reason]");
        if (!digest || !digest.value || !reason || reason.value.trim().length < MIN_REASON) {
            syncSubmit(root);
            return;
        }
        root._smBusy = true;
        syncSubmit(root);
        post(root, root.getAttribute("data-sm-apply-url"), {
            target: picked.target,
            sources: picked.sources,
            digest: digest.value,
            reason: reason.value,
        })
            .then(function (payload) {
                if (window.EMSOverlay) {
                    window.EMSOverlay.close(form.closest(".ems-overlay"));
                }
                if (window.EMSToast && typeof window.EMSToast.show === "function") {
                    window.EMSToast.show((payload && payload.message) || "", "success");
                }
                var office = window.EMSTeachingOffice;
                var host = office && office.root();
                if (office && host) {
                    var section = host.getAttribute("data-tof-section");
                    office.reload(section, office.sectionUrl(section, {}));
                }
            })
            .catch(function (err) {
                var payload = err && err.payload;
                showError(root, (payload && payload.message) || text(root, "error"));
                if (payload && (payload.error === "drift" || payload.error === "conflicts")) {
                    resetPreview(root, true);
                }
            })
            .then(function () {
                root._smBusy = false;
                syncSubmit(root);
            });
    });

    window.EMSSubjectMerge = { selection: selection, renderPreview: renderPreview };
})(window, document);
