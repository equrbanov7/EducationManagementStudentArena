/* =========================================================================
   Ekran 09 «Tələbə reyestri və hərəkəti» — panel davranışı (Mərhələ 3).

   NƏ EDİR
   -------
   * sətrin «Kart» düyməsi → serverdən JSON kart + hərəkət tarixçəsi çəkir və
     çekmecəni doldurur (25 kartı əvvəlcədən render etmirik);
   * «Hərəkət əmri» → dialoqu açır, hədəf seçicilərini doldurur və SEÇİLƏN
     NÖVƏ görə hansı sahənin görünəcəyini serverdən gələn qaydaya
     (`#srMovementKinds` JSON) uyğun açıb-bağlayır;
   * formu `FormData` (multipart — əmr sənədi) kimi göndərir, uğurda paneli
     yeniləyir.

   NƏ ETMİR
   --------
   Səbəb sayğacı/≥20 qapısı, fokus tələsi, Escape, filtr draft↔applied məntiqi
   ORTAQ qatdadır (`static/js/ems_ui/*.js`) — burada TƏKRARLANMIR. State maşını
   da təkrarlanmır: hansı sahənin məcburi olduğu SERVERDƏN gəlir.

   AJAX-SAFE: yalnız `EMSDelegate` (sənəd səviyyəli) + `EMSReady`;
   `[data-sr-root]` yoxdursa heç nə etmir.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSStudentRegistry) {
        return;
    }

    var PLACEHOLDER = "00000000-0000-0000-0000-000000000000";

    function root() {
        return document.querySelector("[data-sr-root]");
    }

    function toast(message, kind) {
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function csrfToken(form) {
        var field = form && form.querySelector('input[name="csrfmiddlewaretoken"]');
        if (field && field.value) {
            return field.value;
        }
        return (window.EMSCore && window.EMSCore.getCsrfToken && window.EMSCore.getCsrfToken()) || "";
    }

    function urlFor(base, id) {
        return String(base || "").replace(PLACEHOLDER, encodeURIComponent(id));
    }

    function kindRules() {
        var node = document.getElementById("srMovementKinds");
        if (!node) {
            return [];
        }
        try {
            return JSON.parse(node.textContent) || [];
        } catch (err) {
            return [];
        }
    }

    function setText(scope, name, value) {
        var node = scope.querySelector('[data-sr-field="' + name + '"]');
        if (node) {
            node.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
        }
    }

    /* ---- Çekmecə (tələbə kartı) ------------------------------------------ */

    function fillCard(payload) {
        var body = document.querySelector("[data-sr-card-body]");
        if (!body) {
            return;
        }
        [
            "name",
            "program_label",
            "student_code",
            "fin",
            "group_name",
            "admission_year",
            "admission_score",
            "admission_exam_type",
            "atis_id",
            "form_label",
            "funding_label",
            "credits_earned"
        ].forEach(function (key) {
            setText(body, key, payload[key]);
        });
        setText(body, "gpa", payload.gpa_available ? payload.gpa : "");
        var initials = body.querySelector('[data-sr-field="initials"]');
        if (initials) {
            initials.textContent = String(payload.name || "?")
                .split(" ")
                .map(function (part) {
                    return part.charAt(0);
                })
                .slice(0, 2)
                .join("")
                .toUpperCase();
        }
        fillHistory(body, payload.movements || []);
    }

    function fillHistory(body, rows) {
        var list = body.querySelector("[data-sr-history]");
        var empty = body.querySelector("[data-sr-history-empty]");
        if (!list) {
            return;
        }
        list.textContent = "";
        if (empty) {
            empty.hidden = rows.length > 0;
        }
        var host = root();
        var docBase = host ? host.getAttribute("data-sr-document-url") : "";
        rows.forEach(function (row) {
            list.appendChild(historyItem(row, docBase));
        });
    }

    function historyItem(row, docBase) {
        var li = document.createElement("li");
        li.className = "ems-tl__item";

        var gutter = document.createElement("div");
        gutter.className = "ems-tl__gutter";
        gutter.setAttribute("aria-hidden", "true");
        var dot = document.createElement("span");
        dot.className = "ems-tl__dot ems-tl__dot--info";
        var line = document.createElement("span");
        line.className = "ems-tl__line";
        gutter.appendChild(dot);
        gutter.appendChild(line);

        var main = document.createElement("div");
        main.className = "ems-tl__main";

        var head = document.createElement("div");
        head.className = "ems-tl__head";
        var who = document.createElement("span");
        who.className = "ems-tl__who";
        who.textContent = row.kind_label || "";
        var when = document.createElement("span");
        when.className = "ems-tl__when";
        when.textContent = (row.order_number || "") + " · " + (row.order_date || "");
        head.appendChild(who);
        head.appendChild(when);

        var what = document.createElement("div");
        what.className = "ems-tl__what";
        what.textContent = (row.from_label || "—") + " → " + (row.to_label || "—");

        var reason = document.createElement("div");
        reason.className = "ems-tl__reason";
        reason.textContent = row.reason || "";

        main.appendChild(head);
        main.appendChild(what);
        main.appendChild(reason);

        if (row.has_document && docBase) {
            var link = document.createElement("a");
            link.className = "stsvc__doclink";
            link.href = urlFor(docBase, row.id);
            link.textContent = document.documentElement.lang === "en" ? "Document" : "Sənəd";
            main.appendChild(link);
        }

        li.appendChild(gutter);
        li.appendChild(main);
        return li;
    }

    window.EMSDelegate.on("click", "[data-sr-card]", function (event, btn) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        var drawer = document.getElementById("srStudentCard");
        window.EMSCore.fetchJSON(urlFor(host.getAttribute("data-sr-card-url"), btn.getAttribute("data-sr-card")))
            .then(function (payload) {
                fillCard(payload);
                if (window.EMSOverlay && drawer) {
                    window.EMSOverlay.open(drawer);
                }
            })
            .catch(function (err) {
                toast((err && err.payload && err.payload.message) || "", "error");
            });
    });

    /* ---- Hərəkət dialoqu -------------------------------------------------- */

    function applyKindVisibility(form) {
        var checked = form.querySelector("[data-sr-kind]:checked");
        var key = checked ? checked.value : "";
        var rules = kindRules();
        var rule = null;
        rules.forEach(function (item) {
            if (item.key === key) {
                rule = item;
            }
        });
        var needs = {
            group: rule ? rule.requires_group : false,
            program: rule ? rule.requires_program : false,
            form: rule ? rule.requires_form : false,
            until: rule ? rule.requires_until : false
        };
        Object.keys(needs).forEach(function (name) {
            var box = form.querySelector('[data-sr-need="' + name + '"]');
            if (box) {
                box.hidden = !needs[name];
            }
        });
    }

    function fillSelect(select, rows, placeholderText) {
        if (!select) {
            return;
        }
        select.textContent = "";
        var first = document.createElement("option");
        first.value = "";
        first.textContent = placeholderText;
        select.appendChild(first);
        rows.forEach(function (row) {
            var option = document.createElement("option");
            option.value = row.id;
            option.textContent = row.text;
            select.appendChild(option);
        });
        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.sync(select);
        }
    }

    function loadTargets(form) {
        var host = root();
        if (!host) {
            return;
        }
        var placeholder = form.querySelector("[data-sr-group-select] option");
        var text = placeholder ? placeholder.textContent : "—";
        window.EMSCore.fetchJSON(host.getAttribute("data-sr-groups-url") + "?limit=50")
            .then(function (payload) {
                fillSelect(form.querySelector("[data-sr-group-select]"), payload.results || [], text);
            })
            .catch(function () {
                /* seçici boş qalır — server onsuz da məcburiyyəti yoxlayır */
            });
        window.EMSCore.fetchJSON(host.getAttribute("data-sr-programs-url"))
            .then(function (payload) {
                fillSelect(form.querySelector("[data-sr-program-select]"), payload.results || [], text);
            })
            .catch(function () {
                /* eyni səbəb */
            });
    }

    window.EMSDelegate.on("click", "[data-sr-move]", function (event, btn) {
        event.preventDefault();
        var dialog = document.getElementById("srMovementDialog");
        if (!dialog) {
            return;
        }
        var form = dialog.querySelector("form");
        if (!form) {
            return;
        }
        form.reset();
        var hidden = form.querySelector('input[name="record_id"]');
        if (hidden) {
            hidden.value = btn.getAttribute("data-sr-move");
        }
        var target = form.querySelector("[data-sr-target-name]");
        if (target) {
            target.textContent =
                (btn.getAttribute("data-sr-name") || "") + " · " + (btn.getAttribute("data-sr-group") || "—");
        }
        var box = form.querySelector("[data-ems-form-error]");
        if (box) {
            box.hidden = true;
            box.textContent = "";
        }
        applyKindVisibility(form);
        loadTargets(form);
        if (window.EMSOverlay) {
            window.EMSOverlay.open(dialog);
            window.EMSOverlay.syncReason(dialog);
        }
    });

    window.EMSDelegate.on("change", "[data-sr-kind]", function (event, input) {
        var form = input.form;
        if (form) {
            applyKindVisibility(form);
        }
    });

    window.EMSDelegate.on("submit", "form[data-sr-form]", function (event, form) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        var url = form.getAttribute("data-sr-url") || host.getAttribute("data-sr-action-url");
        var submit = form.querySelector('[type="submit"]');
        if (submit) {
            submit.disabled = true;
        }
        var body = new FormData(form);
        body.delete("csrfmiddlewaretoken");
        fetch(url, {
            method: "POST",
            body: body,
            credentials: "same-origin",
            headers: { "X-CSRFToken": csrfToken(form), "X-Requested-With": "XMLHttpRequest" }
        })
            .then(function (response) {
                return response.json().then(function (payload) {
                    return { ok: response.ok, payload: payload };
                });
            })
            .then(function (result) {
                if (!result.ok) {
                    var box = form.querySelector("[data-ems-form-error]");
                    if (box) {
                        box.textContent = (result.payload && result.payload.message) || "";
                        box.hidden = !box.textContent;
                    }
                    return;
                }
                if (window.EMSOverlay) {
                    window.EMSOverlay.close(form.closest(".ems-overlay"));
                }
                toast(form.getAttribute("data-sr-success") || "", "success");
                if (window.EMSProfileLoadSection) {
                    window.EMSProfileLoadSection("student-registry", window.location.href);
                } else {
                    window.location.reload();
                }
            })
            .catch(function () {
                var box = form.querySelector("[data-ems-form-error]");
                if (box) {
                    box.textContent = form.getAttribute("data-sr-error-text") || "";
                    box.hidden = !box.textContent;
                }
            })
            .then(function () {
                if (submit) {
                    submit.disabled = false;
                }
            });
    });

    window.EMSStudentRegistry = { urlFor: urlFor };
})(window, document);
