/* «Müraciətlərim» — DETAL MODALININ QABIĞI (aç / bağla / fokus / əməl).
 *
 * Detal əvvəl sağdakı yapışqan sütun idi; indi MODAL-dır: siyahı tam eni tutur,
 * yazışma isə oxunaqlı ölçüdə açılır. Markup `applications_thread.js`-dədir —
 * burada yalnız DAVRANIŞ var:
 *
 *   • sorğu gedərkən modal DƏRHAL skeletlə açılır (boş gözləmə yoxdur),
 *   • qıraqa klik / Esc / ✕ bağlayır,
 *   • cavab yazılıb GÖNDƏRİLMƏYİBSƏ bağlamazdan əvvəl xəbərdarlıq çıxır,
 *   • arxa fon scroll-u kilidlənir (`html.apx-modal-open`).
 *
 * Düymələr YALNIZ server-in `allowed_actions` siyahısından doğulur — UI-da
 * rol/status məntiqi yoxdur (backend müqaviləsi §8.2).
 */
(function () {
    "use strict";

    var NS = (window.EMSApplications = window.EMSApplications || {});

    //: Cavab qutusunun mətnini İŞLƏDƏN əməllər — qalanları öz dialoqunu açır.
    //: `min`: mətn həddi ("note" = `rules.note`, "one" = 1 simvol).
    //: `files`: server həmin əməldə sənəd qəbul edirmi (`views._action_kwargs`).
    //: Rədd/qaytar/ləğv yalnız SƏBƏB alır — fayl seçilibsə istifadəçi xəbərdarlıq
    //: görür, fayl səssizcə İTMİR.
    var INLINE_ACTIONS = {
        resolve: { min: "note", files: true },
        request_info: { min: "note", files: true },
        add_comment: { min: "one", files: true },
        reject: { min: "note", files: false },
    };

    function host() {
        return NS.root && NS.root.querySelector("[data-apx-detail]");
    }

    function panel() {
        var box = host();
        return box ? box.querySelector("[data-apx-modal-panel]") : null;
    }

    function isOpen() {
        var box = host();
        return !!box && !box.hidden;
    }

    function lock(on) {
        document.documentElement.classList.toggle("apx-modal-open", !!on);
    }

    function focusPanel() {
        var body = panel();
        if (!body) {
            return;
        }
        try {
            body.focus();
        } catch (error) {
            /* fokus alınmasa da modal işləyir */
        }
    }

    function show(markup) {
        var box = host();
        var body = panel();
        if (!box || !body) {
            return null;
        }
        body.__files = [];
        body.innerHTML = markup;
        box.hidden = false;
        lock(true);
        focusPanel();
        return body;
    }

    /* Skelet — detal sorğusu gedərkən. */
    function openSkeleton() {
        show(NS.thread.skeleton());
    }

    function render(app) {
        NS.current = app;
        var body = show(NS.thread.html(app, INLINE_ACTIONS));
        if (!body) {
            return;
        }
        NS.paintSwatches(body);
        NS.thread.scrollToLatest(body);
    }

    /* Yazılmış, amma GÖNDƏRİLMƏMİŞ məzmun varmı? */
    function isDirty() {
        var body = panel();
        if (!body || !isOpen()) {
            return false;
        }
        var field = body.querySelector("[data-apx-reply]");
        if (field && field.value.trim().length) {
            return true;
        }
        return !!(body.__files && body.__files.length);
    }

    function close() {
        var box = host();
        if (!box) {
            return;
        }
        NS.current = null;
        box.hidden = true;
        var body = panel();
        if (body) {
            body.innerHTML = "";
            body.__files = [];
        }
        lock(false);
        if (NS.state) {
            NS.state.selectedId = "";
        }
        if (NS.renderList) {
            NS.renderList();
        }
    }

    /* Bağlama İSTƏYİ — göndərilməmiş mətn/sənəd varsa əvvəlcə təsdiq istənilir.
     * `true` qaytarır = istək qəbul olundu (Esc zənciri dayanır). */
    function requestClose() {
        if (!isOpen()) {
            return false;
        }
        if (!isDirty()) {
            close();
            return true;
        }
        NS.dialogs.confirm(NS.t("closeDirtyTitle"), NS.t("closeDirtyText"), function () {
            NS.dialogs.close("confirm");
            close();
        });
        return true;
    }

    function errors(messages) {
        var body = panel();
        if (body && NS.dialogs && NS.dialogs.showErrors) {
            NS.dialogs.showErrors(body, messages);
        }
    }

    /* Mətn tələb edən əməllər cavab qutusunun UZUNLUĞUNA görə açılır/bağlanır.
     * Tək mənbə: həm yazarkən, həm də uğursuz göndərişdən sonra bura qayıdılır —
     * əks halda `busy(false)` qısa mətndə də bütün düymələri açardı. */
    function syncGates(box) {
        if (!box) {
            return;
        }
        var field = box.querySelector("[data-apx-reply]");
        var length = field ? field.value.trim().length : 0;
        box.querySelectorAll("[data-apx-action]").forEach(function (button) {
            var need = INLINE_ACTIONS[button.getAttribute("data-apx-action")];
            button.disabled = need ? (need.min === "one" ? length < 1 : length < NS.rules.note) : false;
        });
    }

    /* Göndəriş anında bütün əməl düymələri kilidlənir — ikiqat klik yeni sətir
     * yaradırdı (eyni sinif problem `submit.DUPLICATE_WINDOW`-da server tərəfdə
     * bağlanıb; burada UI tərəfi). */
    function busy(on) {
        var body = panel();
        if (!body) {
            return;
        }
        if (on) {
            body.querySelectorAll("[data-apx-action]").forEach(function (button) {
                button.disabled = true;
            });
        } else {
            syncGates(body.querySelector(".apx-act"));
        }
        body.setAttribute("aria-busy", on ? "true" : "false");
    }

    NS.detail = {
        render: render,
        clear: close,
        openSkeleton: openSkeleton,
        requestClose: requestClose,
        isOpen: isOpen,
        isDirty: isDirty,
        INLINE_ACTIONS: INLINE_ACTIONS,
    };

    /* ── Delegasiya (bir dəfə) ──────────────────────────────────────────── */
    function start() {
        if (NS.__detailWired) {
            return;
        }
        NS.__detailWired = true;

        window.EMSDelegate.on("input", "[data-apx-reply]", function (event, node) {
            syncGates(node.closest(".apx-act"));
        });

        window.EMSDelegate.on("click", "[data-apx-detail-close]", function () {
            requestClose();
        });

        // Yalnız overlay-in ÖZÜNƏ klik bağlayır (panelin içi qabarcıqlanmır).
        window.EMSDelegate.on("click", "[data-apx-detail]", function (event, node) {
            if (event.target === node) {
                requestClose();
            }
        });

        window.EMSDelegate.on("click", "[data-apx-action]", function (event, node) {
            var action = node.getAttribute("data-apx-action");
            var app = NS.current;
            if (!app) {
                return;
            }
            var inline = INLINE_ACTIONS[action];
            if (!inline) {
                NS.dialogs.openForAction(action, app);
                return;
            }
            var body = panel();
            var field = body && body.querySelector("[data-apx-reply]");
            var files = (body && body.__files) || [];
            if (files.length && !inline.files) {
                errors([NS.t("filesNotAllowed", { action: node.textContent.trim() })]);
                return;
            }
            errors([]);
            busy(true);
            NS.submitAction(app.id, action, { text: field ? field.value.trim() : "" }, files).catch(function (error) {
                busy(false);
                errors(NS.errorList(error));
            });
        });
    }

    /* Panel script-ləri `<body>` içindədir və `ems_ajax_init.js`-dən ƏVVƏL
     * parse oluna bilər (AJAX swap-da isə dinamik script sırası zəmanətli
     * deyil), ona görə qeydiyyat primitivlər hazır olana qədər gözləyir.
     * `defer` ilk yüklənmədə bunu onsuz da tez edir — bu, ikinci qapıdır. */
    (function ready(attempt) {
        if (window.EMSDelegate && window.EMSReady && NS.api) {
            start();
            return;
        }
        if (attempt > 200) {
            return;
        }
        window.setTimeout(function () {
            ready(attempt + 1);
        }, 25);
    })(0);

    /* Əməli göndərir və cavabdakı DETAL payload-unu yerində tətbiq edir. */
    NS.submitAction = function (id, action, fields, files) {
        var form = new FormData();
        form.append("action", action);
        Object.keys(fields || {}).forEach(function (key) {
            form.append(key, fields[key]);
        });
        (files || []).forEach(function (file) {
            form.append("files", file);
        });
        return NS.api.action(id, form).then(function (payload) {
            var app = payload.application;
            NS.applyDetail(app);
            NS.toast(NS.t("toastDone", { no: app.number, status: app.status.label }));
            return app;
        });
    };
})();
