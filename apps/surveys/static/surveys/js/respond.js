/* =========================================================================
   Ümumi sorğu forması (sorğu qurucusu, 2026-09-30) — irəliləyiş, avtomatik saxlama,
   müştəri tərəfli yoxlama.

   * İrəliləyiş: cavablanmış sual sayı / cəmi (yapışqan zolaq).
   * Avtomatik saxlama:
       - ŞƏXSLİ sorğu (`data-draft-url`): 1.2 s gecikmə ilə server qaralaması (EMSCore.fetchJSON);
       - ANONİM sorğu (`data-storage-key`): YALNIZ bu tabın sessionStorage-ı — serverə heç nə
         getmir, tab bağlananda silinir (paylaşılan kompüterdə növbəti istifadəçi görmür).
   * Yoxlama: məcburi sual və çox seçimin min/max həddi; server yenə də yoxlayır (bu yalnız UX).
     `survey_form.js` göndərişi kilidləyir — səhv olanda kilid burada açılır.

   AJAX-SAFE: EMSDelegate + EMSReady. Mətnlər formanın data-* atributlarından gəlir.
   ========================================================================= */
(function (window, document) {
    "use strict";

    var timers = {};

    function fields(form) {
        return form.querySelectorAll("[name^='q_']");
    }

    function serialize(form) {
        var data = {};
        var items = fields(form);
        for (var i = 0; i < items.length; i += 1) {
            var el = items[i];
            if ((el.type === "radio" || el.type === "checkbox") && !el.checked) {
                if (el.type === "checkbox" && !data[el.name]) {
                    data[el.name] = [];
                }
                continue;
            }
            if (el.type === "checkbox") {
                data[el.name] = (data[el.name] || []).concat([el.value]);
            } else if (el.type === "radio" || (el.value || "").trim()) {
                data[el.name] = el.value;
            }
        }
        return data;
    }

    function answered(fieldset) {
        var inputs = fieldset.querySelectorAll("input, textarea");
        for (var i = 0; i < inputs.length; i += 1) {
            var el = inputs[i];
            if (el.type === "radio" || el.type === "checkbox") {
                if (el.checked) {
                    return true;
                }
            } else if ((el.value || "").trim()) {
                return true;
            }
        }
        return false;
    }

    function updateProgress(form) {
        var sets = form.querySelectorAll("[data-svr-q]");
        var done = 0;
        for (var i = 0; i < sets.length; i += 1) {
            if (answered(sets[i])) {
                done += 1;
            }
        }
        var bar = document.querySelector("[data-svr-progress-bar]");
        var label = document.querySelector("[data-svr-progress-label]");
        if (bar) {
            bar.value = done;
        }
        if (label) {
            label.textContent = (form.getAttribute("data-label-progress") || "__N__ / __T__")
                .replace("__N__", String(done))
                .replace("__T__", String(sets.length));
        }
    }

    function status(text) {
        var node = document.querySelector("[data-svr-status]");
        if (node) {
            node.textContent = text || "";
        }
    }

    function storage() {
        try {
            return window.sessionStorage;
        } catch (error) {
            return null;
        }
    }

    function saveLocal(form) {
        var key = form.getAttribute("data-storage-key");
        var store = storage();
        if (!key || !store) {
            return;
        }
        try {
            store.setItem(key, JSON.stringify(serialize(form)));
            status(form.getAttribute("data-label-local"));
        } catch (error) {
            /* kvota / məxfi rejim — sadəcə saxlanmır */
        }
    }

    function restoreLocal(form) {
        var key = form.getAttribute("data-storage-key");
        var store = storage();
        if (!key || !store) {
            return;
        }
        var raw = null;
        try {
            raw = JSON.parse(store.getItem(key) || "null");
        } catch (error) {
            raw = null;
        }
        if (!raw || typeof raw !== "object") {
            return;
        }
        var items = fields(form);
        for (var i = 0; i < items.length; i += 1) {
            var el = items[i];
            var value = raw[el.name];
            if (value === undefined) {
                continue;
            }
            if (el.type === "checkbox") {
                el.checked = Array.isArray(value) && value.indexOf(el.value) !== -1;
            } else if (el.type === "radio") {
                el.checked = el.value === value;
            } else if (!(el.value || "").trim()) {
                el.value = String(value);
                el.dispatchEvent(new Event("input", { bubbles: true }));
            }
        }
    }

    function saveServer(form) {
        var url = form.getAttribute("data-draft-url");
        if (!url || !window.EMSCore || !window.EMSCore.fetchJSON) {
            return;
        }
        window.clearTimeout(timers[url]);
        timers[url] = window.setTimeout(function () {
            window.EMSCore.fetchJSON(url, { method: "POST", data: { data: serialize(form) } })
                .then(function (payload) {
                    var label = form.getAttribute("data-label-saved") || "";
                    status(payload && payload.saved_at ? label + " · " + payload.saved_at : label);
                })
                .catch(function () {
                    status("");
                });
        }, 1200);
    }

    function onChange(form) {
        updateProgress(form);
        if (form.getAttribute("data-draft-url")) {
            saveServer(form);
        } else {
            saveLocal(form);
        }
    }

    function showError(fieldset, text) {
        var node = fieldset.querySelector("[data-svr-error]");
        fieldset.classList.toggle("is-invalid", Boolean(text));
        if (node) {
            node.textContent = text || "";
            node.hidden = !text;
        }
    }

    function setError(form, set) {
        var text = "";
        var chosen = set.querySelectorAll("input[type='checkbox']:checked").length;
        var min = parseInt(set.getAttribute("data-min"), 10) || 0;
        var max = parseInt(set.getAttribute("data-max"), 10) || 0;
        if (set.getAttribute("data-required") === "1" && !answered(set)) {
            text = form.getAttribute("data-label-required") || "";
        } else if (set.getAttribute("data-kind") === "multi" && chosen) {
            if (min && chosen < min) {
                text = (form.getAttribute("data-label-min") || "").replace("__N__", String(min));
            } else if (max && chosen > max) {
                text = (form.getAttribute("data-label-max") || "").replace("__N__", String(max));
            }
        }
        return text;
    }

    function validate(form) {
        var sets = form.querySelectorAll("[data-svr-q]");
        var first = null;
        for (var i = 0; i < sets.length; i += 1) {
            var text = setError(form, sets[i]);
            showError(sets[i], text);
            if (text && !first) {
                first = sets[i];
            }
        }
        return first;
    }

    // QA 2026-09-30: səhv göstərilmiş sual cavablananda qırmızı işarə dərhal yox olur
    // (əvvəl növbəti göndərişə qədər qalırdı). Yalnız artıq səhvli sual yenidən yoxlanılır —
    // hələ toxunulmamış suallar yazarkən qırmızı olmur.
    function recheck(field) {
        var set = field.closest ? field.closest("[data-svr-q]") : null;
        if (set && set.classList.contains("is-invalid")) {
            showError(set, setError(field.form, set));
        }
    }

    function unlock(form) {
        form.removeAttribute("data-svy-sending");
        form.removeAttribute("aria-busy");
        var button = form.querySelector("[data-svy-submit]");
        if (button) {
            button.removeAttribute("disabled");
        }
    }

    function bindDelegates() {
        if (!window.EMSDelegate || window.__emsSurveyRespondBound) {
            return;
        }
        window.__emsSurveyRespondBound = true;
        window.EMSDelegate.on("change", "form[data-svr-form] [name^='q_']", function (event, field) {
            onChange(field.form);
            recheck(field);
        });
        window.EMSDelegate.on("input", "form[data-svr-form] [name^='q_']", function (event, field) {
            onChange(field.form);
            recheck(field);
        });
        window.EMSDelegate.on("submit", "form[data-svr-form]", function (event, form) {
            var invalid = validate(form);
            if (invalid) {
                event.preventDefault();
                unlock(form);
                var focusable = invalid.querySelector("input, textarea");
                invalid.scrollIntoView({ behavior: "smooth", block: "center" });
                if (focusable) {
                    focusable.focus({ preventScroll: true });
                }
                return;
            }
            var key = form.getAttribute("data-storage-key");
            var store = storage();
            if (key && store) {
                try {
                    store.removeItem(key);
                } catch (error) {
                    /* yox */
                }
            }
        });
    }

    function init() {
        bindDelegates();
        var form = document.querySelector("form[data-svr-form]");
        if (!form) {
            return;
        }
        restoreLocal(form);
        updateProgress(form);
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    } else {
        document.addEventListener("DOMContentLoaded", init);
    }
})(window, document);
