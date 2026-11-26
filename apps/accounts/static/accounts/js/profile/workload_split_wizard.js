/*
 * «Bölgü sehrbazı» — ƏSAS modul (`window.EMSWorkloadWizard`, sahib 2026-11-26).
 *
 * Sahib: «seminar 2-yə bölünür, lab-da hər seminar alt qrupu yenə 2-yə … hansı tələbə haraya düşür bilinmir.
 * İmtahan yaratma forması kimi addımlı modal olsun, rahat və aydın görünsün.»
 *
 * Addımlar: groups → seminar → lab → teachers → review. Bu modul: vəziyyət, açılış (GET `bolgu/sehrbaz/`),
 * naviqasiya, müəllim hovuzu, yadda saxlama (POST `bolgu/sehrbaz/yadda-saxla/` — `EMSWorkloadAmend.write`, 409 →
 * düzəliş dialoqu). Addımların render-i: `workload_split_wizard_groups.js` (qruplar), `workload_split_wizard_sections.js` (seminar, lab) və
 * `workload_split_wizard_units.js` (müəllimlər, yoxlama, gövdə). Fayllar istənilən sırada yüklənə bilər — hamısı
 * eyni ad sahəsini (`window.EMSWorkloadWizard`) genişləndirir.
 *
 * AJAX-safe: dinləyicilər `EMSDelegate.on` ilə BİR dəfə; DOM hər çağırışda `EMSWorkloadDist.q` ilə axtarılır.
 * Xarici JS template-dən keçmir — URL-lər modalın data-atributlarından, mətnlər `gettext`.
 */
(function (window) {
    "use strict";

    var gettext = window.gettext || function (value) { return value; };
    var W = (window.EMSWorkloadWizard = window.EMSWorkloadWizard || {});
    W.render = W.render || {};
    W.validate = W.validate || {};
    W.STEPS = ["groups", "seminar", "lab", "teachers", "review"];
    W.VACANT = "vacant";
    W.S = null;
    var pool = { key: "", items: [], promise: null };
    var SEQ = 0; // açılış sessiyasının nişanı — gecikmiş cavab yeni sessiyaya yazılmır

    // ── ortaq köməkçilər ────────────────────────────────────────────────────
    W.dist = function () { return window.EMSWorkloadDist || null; };
    W.q = function (selector) { var D = W.dist(); return D ? D.q(selector) : null; };
    W.esc = function (value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    };
    W.fmt = function (template, params) {
        if (typeof window.interpolate === "function") return window.interpolate(template, params, true);
        return template.replace(/%\((\w+)\)s/g, function (_, key) { return params[key] == null ? "" : String(params[key]); });
    };
    W.hours = function (value) { return W.fmt(gettext("%(hours)s s"), { hours: value == null ? 0 : value }); };
    W.gettext = gettext;

    W.row = function (rowId) {
        var rows = (W.S && W.S.data && W.S.data.rows) || [];
        for (var i = 0; i < rows.length; i += 1) if (rows[i].id === rowId) return rows[i];
        return null;
    };
    W.group = function (groupId) {
        var groups = (W.S && W.S.data && W.S.data.groups) || [];
        for (var i = 0; i < groups.length; i += 1) if (groups[i].id === groupId) return groups[i];
        return null;
    };
    /** Seçilmiş sətirlər (seçilmiş qrupun sətri bütövlükdə seçilir). */
    W.selectedRows = function () {
        if (!W.S) return [];
        return (W.S.data.rows || []).filter(function (row) {
            return row.groups.some(function (id) { return W.S.selected[id]; });
        });
    };
    W.selectedGroups = function () {
        var rows = W.selectedRows();
        var out = [];
        rows.forEach(function (row) { row.groups.forEach(function (id) { var g = W.group(id); if (g) out.push(g); }); });
        return out;
    };
    /** Sətirdə fəaliyyət aktivdirmi (cəmi > 0) — server `split_wizard_apply._active` ilə eyni qayda. */
    W.active = function (row, activity) { return (row.totals[activity] || 0) > 0; };
    W.anyActive = function (activity) {
        return W.selectedRows().some(function (row) { return W.active(row, activity); });
    };

    W.select = function (attrs, options, search) {
        return (
            '<div class="bootstrap-single-select"><select class="form-select bootstrap-single-select__native js-bootstrap-single-select" data-bootstrap-select' +
            (search ? ' data-live-search="true" data-live-search-placeholder="' + W.esc(gettext("Müəllim axtar…")) + '"' : "") +
            " " + attrs + ">" + options + "</select></div>"
        );
    };
    W.initSelects = function (host) { if (host && window.EMSBootstrapSelect) window.EMSBootstrapSelect.init(host); };

    /** Kafedranın müəllim hovuzu (kənar daxil) — bölgü modalı ilə eyni endpoint; kafedra/il üzrə bir dəfə. */
    W.loadPool = function () {
        var D = W.dist();
        var host = D ? D.root() : null;
        if (!host) return Promise.resolve([]);
        var params = D.filters();
        var key = params.chair + "|" + params.year;
        if (pool.key === key && pool.promise) return pool.promise;
        pool.key = key;
        pool.promise = window.EMSCore.fetchJSON(
            host.dataset.teachersUrl + "?chair=" + encodeURIComponent(params.chair) + "&year=" + encodeURIComponent(params.year) + "&outside=1"
        )
            .then(function (payload) { pool.items = (payload && payload.results) || []; return pool.items; })
            .catch(function () { pool.items = []; return pool.items; });
        return pool.promise;
    };

    /** Müəllim seçimi: «— seçilməyib —», «Vakant», hovuz; hovuzda olmayan mövcud müəllim itmir. */
    W.teacherOptions = function (selected, extra) {
        selected = selected == null ? "" : String(selected);
        var html = '<option value=""' + (!selected ? " selected" : "") + ">" + W.esc(gettext("— Müəllim seçilməyib —")) + "</option>" +
            '<option value="' + W.VACANT + '"' + (selected === W.VACANT ? " selected" : "") + ">" + W.esc(gettext("Vakant (müəllim sonra)")) + "</option>";
        var seen = {};
        pool.items.forEach(function (item) {
            seen[String(item.id)] = true;
            var mark = item.is_outside ? " — " + W.fmt(gettext("kənar, ştat: %(chair)s"), { chair: item.home_chair || "—" }) : "";
            var suffix = item.current_hours != null ? " · " + item.current_hours + "s" : "";
            html += '<option value="' + W.esc(item.id) + '"' + (String(item.id) === selected ? " selected" : "") + ">" + W.esc(item.full_name + suffix + mark) + "</option>";
        });
        (extra || []).forEach(function (item) {
            if (!item.id || seen[String(item.id)]) return;
            seen[String(item.id)] = true;
            html += '<option value="' + W.esc(item.id) + '"' + (String(item.id) === selected ? " selected" : "") + ">" + W.esc(item.name) + "</option>";
        });
        return html;
    };
    W.teacherName = function (id) {
        if (!id) return gettext("— seçilməyib —");
        if (id === W.VACANT) return gettext("Vakant");
        for (var i = 0; i < pool.items.length; i += 1) if (String(pool.items[i].id) === String(id)) return pool.items[i].full_name;
        var found = "";
        ((W.S && W.S.data.rows) || []).forEach(function (row) {
            row.assignments.forEach(function (a) { if (!found && String(a.teacher_id) === String(id)) found = a.teacher_name; });
        });
        return found || "—";
    };

    W.showError = function (message) {
        var node = W.q("[data-wl-wiz-error]");
        if (!node) return;
        node.textContent = message || "";
        node.hidden = !message;
    };

    // ── açılış ──────────────────────────────────────────────────────────────
    W.open = function (cardId, kind) {
        if (W.bindModules) W.bindModules();
        var D = W.dist();
        var modalNode = W.q("[data-wl-wiz-modal]");
        if (!D || !modalNode || !D.state.task) return;
        var card = D.cardById ? D.cardById(cardId) : null;
        if (!card) return;
        // QA 2026-11-26: eyni kart üçün təkrar açılış (bağla → aç, və ya düyməyə təkrar klik) köhnə vəziyyəti və
        // gecikmiş cavabı yeni sessiyaya qarışdırırdı — seminar addımı «ölü» qalırdı. İndi: modal artıq açıqdırsa
        // heç nə etmirik; əks halda köhnə vəziyyət atılır, yeni sessiya öz nişanı (`token`) ilə BİR dəfə yüklənir.
        var existing = D.modal("[data-wl-wiz-modal]");
        var visible = modalNode.classList.contains("show") || !!(existing && existing._isShown);
        if (W.S && W.S.card && W.S.card.id === card.id && visible) return;
        SEQ += 1;
        W.S = {
            token: SEQ, card: card, kind: kind || "", data: null, step: 0, selected: {}, rows: {}, groups: {}, units: {},
            lecture: {}, saving: false, loading: null,
        };
        var subject = W.q("[data-wl-wiz-subject]");
        if (subject) subject.textContent = card.subject + " · " + (card.season_label || "");
        W.showError("");
        W.STEPS.forEach(function (name) {
            var panel = W.q('[data-wl-wiz-panel="' + name + '"]');
            if (panel) panel.innerHTML = "";
        });
        W.setLoading(true);
        W.go(0);
        var instance = D.modal("[data-wl-wiz-modal]");
        if (instance) instance.show();
        W.reload();
    };

    W.reload = function () {
        var D = W.dist();
        var modalNode = W.q("[data-wl-wiz-modal]");
        if (!W.S || !modalNode || !D.state.task) return Promise.resolve();
        if (W.S.loading) return W.S.loading; // eyni sessiyada ikinci GET yoxdur
        var session = W.S;
        var token = session.token;
        var url = modalNode.dataset.stateUrl + "?task=" + encodeURIComponent(D.state.task.id) + "&rows=" + encodeURIComponent((session.card.row_ids || []).join(","));
        var current = function () { return W.S === session && W.S.token === token; };
        W.setLoading(true);
        session.loading = Promise.all([window.EMSCore.fetchJSON(url), W.loadPool()])
            .then(function (results) {
                session.loading = null;
                if (!current()) return; // köhnə (bağlanmış / əvəz olunmuş) sessiyanın cavabı — atılır
                session.data = results[0];
                if (W.init) W.init(session.data);
                W.setLoading(false);
                W.go(session.step);
            })
            .catch(function (err) {
                session.loading = null;
                if (!current()) return;
                W.setLoading(false);
                var payload = (err && err.payload) || {};
                W.showError(payload.message || gettext("Məlumat yüklənmədi. Səhifəni yeniləyib yenidən cəhd edin."));
            });
        return session.loading;
    };

    /** Modal bağlananda vəziyyət atılır (yadda saxlama gedirsə — düzəliş dialoquna keçid — saxlanır). */
    W.discard = function () {
        if (W.S && !W.S.saving) W.S = null;
    };

    W.setLoading = function (busy) {
        var node = W.q("[data-wl-wiz-loading]");
        if (node) node.hidden = !busy;
        if (busy) {
            W.STEPS.forEach(function (name) {
                var panel = W.q('[data-wl-wiz-panel="' + name + '"]');
                if (panel) panel.hidden = true;
            });
        }
    };

    // ── naviqasiya ──────────────────────────────────────────────────────────
    /** Addım tətbiq olunurmu (məs. seçilmiş sətirlərdə lab saatı yoxdursa «Laboratoriya» keçilir). */
    W.applies = function (name) {
        if (!W.S || !W.S.data) return true;
        if (name === "seminar") return W.anyActive("seminar");
        if (name === "lab") return W.anyActive("lab");
        return true;
    };

    W.go = function (index) {
        if (!W.S) return;
        index = Math.max(0, Math.min(index, W.STEPS.length - 1));
        W.S.step = index;
        var name = W.STEPS[index];
        var ready = !!W.S.data;
        W.STEPS.forEach(function (step, i) {
            var panel = W.q('[data-wl-wiz-panel="' + step + '"]');
            if (panel) panel.hidden = !ready || i !== index;
            var nav = W.q('[data-wl-wiz-step-nav="' + step + '"]');
            if (!nav) return;
            nav.classList.toggle("is-active", i === index);
            nav.classList.toggle("is-done", ready && i < index && W.applies(step));
            nav.classList.toggle("is-skipped", ready && !W.applies(step));
            if (i === index) nav.setAttribute("aria-current", "step");
            else nav.removeAttribute("aria-current");
        });
        var panel = W.q('[data-wl-wiz-panel="' + name + '"]');
        var title = W.q("[data-wl-wiz-title]");
        var desc = W.q("[data-wl-wiz-desc]");
        if (title && panel) title.textContent = panel.dataset.title || "";
        if (desc && panel) desc.textContent = panel.dataset.desc || "";
        var prog = W.q("[data-wl-wiz-prog]");
        if (prog) prog.textContent = W.fmt(gettext("Addım %(n)s / %(total)s"), { n: index + 1, total: W.STEPS.length });
        var back = W.q("[data-wl-wiz-back]");
        if (back) back.hidden = index === 0;
        var next = W.q("[data-wl-wiz-next]");
        if (next) next.hidden = index === W.STEPS.length - 1;
        var submit = W.q("[data-wl-wiz-submit]");
        if (submit) submit.hidden = index !== W.STEPS.length - 1;
        if (ready && W.render[name]) W.render[name](panel);
        var body = W.q("[data-wl-wiz-body]");
        if (body) body.scrollTop = 0;
    };

    /** Cari addımın yoxlaması — xəta mətni (boş = keçmək olar). */
    W.check = function (name) {
        var fn = W.validate[name];
        return fn ? fn() || "" : "";
    };

    W.move = function (delta) {
        if (!W.S || !W.S.data) return;
        var index = W.S.step;
        if (delta > 0) {
            var problem = W.check(W.STEPS[index]);
            if (problem) { W.showError(problem); return; }
        }
        W.showError("");
        var target = index + delta;
        while (target > 0 && target < W.STEPS.length - 1 && !W.applies(W.STEPS[target])) target += delta;
        W.go(target);
    };

    W.jump = function (name) {
        if (!W.S || !W.S.data) return;
        var target = W.STEPS.indexOf(name);
        if (target < 0 || !W.applies(name)) return;
        for (var i = W.S.step; i < target; i += 1) {
            var problem = W.check(W.STEPS[i]);
            if (problem) { W.showError(problem); W.go(i); return; }
        }
        W.showError("");
        W.go(target);
    };

    // ── yadda saxlama ───────────────────────────────────────────────────────
    W.submit = function () {
        var D = W.dist();
        var modalNode = W.q("[data-wl-wiz-modal]");
        if (!W.S || !W.S.data || !modalNode || W.S.saving || !W.payload) return;
        var problem = W.check("review");
        if (problem) { W.showError(problem); return; }
        var button = W.q("[data-wl-wiz-submit]");
        if (button) button.disabled = true;
        W.S.saving = true;
        W.showError("");
        var done = function (result) {
            if (W.S) W.S.saving = false;
            if (button) button.disabled = false;
            var instance = D.modal("[data-wl-wiz-modal]");
            if (instance) instance.hide();
            if (window.EMSToast) window.EMSToast.show(gettext("Bölgü yadda saxlandı."), "success");
            if (result && result.summary && W.S) W.S.lastSummary = result.summary;
            D.loadRows();
        };
        var opts = { url: modalNode.dataset.saveUrl, data: W.payload(), modal: "[data-wl-wiz-modal]", error: "[data-wl-wiz-error]", done: done };
        var write = window.EMSWorkloadAmend ? window.EMSWorkloadAmend.write(opts) : window.EMSCore.fetchJSON(opts.url, { method: "POST", data: opts.data }).then(done);
        Promise.resolve(write).then(function () {
            if (W.S) W.S.saving = false;
            if (button) button.disabled = false;
        }, function (err) {
            if (W.S) W.S.saving = false;
            if (button) button.disabled = false;
            var payload = (err && err.payload) || {};
            W.showError(payload.message || gettext("Yadda saxlanmadı."));
        });
    };

    /** «Jurnalı indi yarat» — mövcud açılış sinxronu; sonra sehrbaz yenidən yüklənir. */
    W.createJournals = function () {
        var D = W.dist();
        var modalNode = W.q("[data-wl-wiz-modal]");
        if (!W.S || !modalNode || !D.state.task) return;
        var rows = W.selectedRows().map(function (row) { return row.id; });
        if (!rows.length) rows = W.S.card.row_ids || [];
        window.EMSCore.fetchJSON(modalNode.dataset.journalsUrl, { method: "POST", data: { task_id: D.state.task.id, row_ids: rows } })
            .then(function () { return W.reload(); })
            .catch(function (err) {
                var payload = (err && err.payload) || {};
                W.showError(payload.message || gettext("Jurnal yaradılmadı."));
            });
    };

    function bind() {
        var EMSDelegate = window.EMSDelegate;
        // QA 2026-11-26: dinləyicilər səhifədə BİR dəfə (skript AJAX ilə təkrar icra olunsa da) — qlobal bayraq.
        if (!EMSDelegate || window.__emsWorkloadWizardBound) return;
        window.__emsWorkloadWizardBound = true;
        EMSDelegate.on("hidden.bs.modal", "[data-wl-wiz-modal]", function () { W.discard(); });
        EMSDelegate.on("click", "[data-wl-wiz-open]", function (event, btn) { W.open(btn.dataset.cardId, btn.dataset.kind); });
        EMSDelegate.on("click", "[data-wl-wiz-next]", function () { W.move(1); });
        EMSDelegate.on("click", "[data-wl-wiz-back]", function () { W.move(-1); });
        EMSDelegate.on("click", "[data-wl-wiz-step-nav]", function (event, btn) { W.jump(btn.dataset.wlWizStepNav); });
        EMSDelegate.on("click", "[data-wl-wiz-submit]", function () { W.submit(); });
        EMSDelegate.on("click", "[data-wl-wiz-journal-create]", function () { W.createJournals(); });
        bindModules();
    }

    // QA 2026-11-26: alt modullar (sections / units) bu fayldan SONRA yüklənə bilər — onların dinləyiciləri öz
    // bayrağı ilə, modul hazır olan kimi bağlanır (bind-da və hər açılışda yoxlanır), bir dəfə.
    function bindModules() {
        var EMSDelegate = window.EMSDelegate;
        if (!EMSDelegate) return;
        if (W.bindSections && !window.__emsWorkloadWizardSectionsBound) {
            window.__emsWorkloadWizardSectionsBound = true;
            W.bindSections(EMSDelegate);
        }
        if (W.bindUnits && !window.__emsWorkloadWizardUnitsBound) {
            window.__emsWorkloadWizardUnitsBound = true;
            W.bindUnits(EMSDelegate);
        }
    }
    W.bindModules = bindModules;

    W.bind = bind;
    if (window.EMSReady) {
        window.EMSReady.once("workload-split-wizard-bind", function () {
            // Alt modullar (sections / units) bu fayldan SONRA yüklənə bilər — bağlama bir növbə sonra.
            window.setTimeout(bind, 0);
        });
        window.EMSReady(function () { pool = { key: "", items: [], promise: null }; });
    }
})(window);
