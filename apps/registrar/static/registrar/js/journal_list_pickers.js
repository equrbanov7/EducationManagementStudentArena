/*
 * journal_list_pickers.js
 * Source: apps/registrar/templates/registrar/partials/_journal_list_content.html
 * Searchable cascade pickers (faculty/department/group/teacher) for the broad
 * corrector journal view. URLs come from data-*-url on the form; the current
 * selection is read from the [data-jl-preselect] JSON script.
 *
 * 2026-10-29 (sahib: «müəllim axtarışı düzgün işləmir»):
 *   • müəllim namizədləri `registrar:journal_list_teachers`-dən gəlir — siyahının ÖZ
 *     əhatəsi (journal_list_scope); əvvəlki «Akademik qeydlər» endpoint-i başqa açar /
 *     əhatə ilə işləyirdi və çox rolda boş menyu qaytarırdı;
 *   • nəticə yoxdursa menyu səssizcə bağlanmır — «Nəticə tapılmadı» (data-empty-text);
 *   • açılan menyu ekranın altından çıxırsa səhifə onu görünən edir (sürüşdürmədən
 *     nəticə görünməli idi);
 *   • AJAX-safe: EMSReady (kabinet qabığında swap-dan sonra da), idempotent (data-jl-init).
 */
window.EMSReady(function () {
    var form = document.querySelector("[data-jd-filterform]");
    if (!form || form.dataset.jlInit === "1" || !window.EMSSearchableSelect) { return; }
    if (!form.querySelector(".js-jl-teacher")) { return; } // dar (müəllim) görünüş — seçici yoxdur
    form.dataset.jlInit = "1";
    var SS = window.EMSSearchableSelect;
    var U = {
        faculty: form.dataset.facultyUrl, department: form.dataset.departmentUrl,
        group: form.dataset.groupUrl, teacher: form.dataset.teacherUrl,
    };
    var emptyText = form.dataset.emptyText || "";
    var PRE = {};
    try {
        var pnode = form.querySelector("[data-jl-preselect]");
        PRE = pnode ? JSON.parse(pnode.textContent || "{}") : {};
    } catch (e) { PRE = {}; }
    var initializing = true;
    function hidden(name) { return form.querySelector('[data-jl-hidden="' + name + '"]'); }
    function submitFor(name, pick) {
        if (initializing) { return; }
        var h = hidden(name); if (h) { h.value = pick.value() || ""; }
        // Kaskad: üst dəyişəndə alt filtrləri sıfırla (stale qalmasın).
        if (name === "faculty") { ["department", "group"].forEach(function (n) { var x = hidden(n); if (x) x.value = ""; }); }
        if (name === "department") { var g = hidden("group"); if (g) g.value = ""; }
        if (window.jlShowLoading) { window.jlShowLoading(); }
        form.submit();
    }
    // Menyu açılanda / nəticə gələndə: ekranın altından çıxırsa səhifəni azca sürüşdür.
    // (Komponent yalnız kəsən valideyn olanda fixed + yuxarı açılır; burada yoxdur.)
    function keepMenuVisible(root) {
        if (!root || typeof window.MutationObserver !== "function") { return; }
        var menu = root.querySelector(".ems-ss__menu");
        if (!menu) { return; }
        var reveal = function () {
            if (!root.classList.contains("is-open") || menu.style.position === "fixed") { return; }
            var rect = menu.getBoundingClientRect();
            var overflow = rect.bottom + 12 - window.innerHeight;
            if (overflow > 0 && rect.height > 0) {
                var room = Math.max(0, root.getBoundingClientRect().top - 12); // input yuxarıdan çıxmasın
                window.scrollBy({ top: Math.min(overflow, room), behavior: "smooth" });
            }
        };
        new window.MutationObserver(function () { window.requestAnimationFrame(reveal); })
            .observe(root, { attributes: true, attributeFilter: ["class"], childList: true, subtree: true });
    }
    function create(hook, opts) {
        var root = form.querySelector(".js-jl-" + hook);
        if (!root) { return null; }
        opts.emptyText = emptyText;
        var pick = SS.create(root, opts);
        keepMenuVisible(root);
        return pick;
    }
    var faculty = create("faculty", {
        url: U.faculty, onChange: function () { submitFor("faculty", faculty); },
    });
    var dept = create("department", {
        url: U.department, dependParam: "faculty",
        getDependValue: function () { return faculty ? faculty.value() : ""; },
        onChange: function () { submitFor("department", dept); },
    });
    // Qrup FAKÜLTƏDƏN asılıdır (kafedradan yox): köçürülmüş strukturda qrup kafedranın
    // altında deyil (ixtisas → fakültə) — kafedra seçiləndə qrup siyahısı boş qalırdı.
    var group = create("group", {
        url: U.group, dependParam: "faculty",
        getDependValue: function () { return faculty ? faculty.value() : ""; },
        onChange: function () { submitFor("group", group); },
    });
    var teacher = create("teacher", {
        url: U.teacher, onChange: function () { submitFor("teacher", teacher); },
    });
    // Cari seçimi göstər (setValue emit edir → initializing bayrağı submit-i saxlayır).
    function pre(pick, name) { var d = PRE[name]; if (pick && d && d.id) { pick.setValue(d.id, d.label || d.id); } }
    pre(faculty, "faculty"); pre(dept, "department"); pre(group, "group"); pre(teacher, "teacher");
    initializing = false;
});
