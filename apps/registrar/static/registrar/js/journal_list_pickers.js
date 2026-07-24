/*
 * journal_list_pickers.js
 * Source: apps/registrar/templates/registrar/partials/_journal_list_content.html
 * Searchable cascade pickers (faculty/department/group/teacher) for the broad
 * corrector journal view. URLs come from data-*-url on the form; the current
 * selection is read from the [data-jl-preselect] JSON script.
 */
(function boot() {
    // Axtarışlı seçici komponenti hələ yüklənməyibsə (skript sırası) — gözlə.
    if (!window.EMSSearchableSelect) { setTimeout(boot, 30); return; }
    var form = document.querySelector("[data-jd-filterform]");
    if (!form || form.dataset.jlInit === "1") { return; }
    form.dataset.jlInit = "1";
    var SS = window.EMSSearchableSelect;
    var U = {
        faculty: form.dataset.facultyUrl, department: form.dataset.departmentUrl,
        group: form.dataset.groupUrl, teacher: form.dataset.teacherUrl,
    };
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
    var faculty = SS.create(form.querySelector(".js-jl-faculty"), {
        url: U.faculty, onChange: function () { submitFor("faculty", faculty); },
    });
    var dept = SS.create(form.querySelector(".js-jl-department"), {
        url: U.department, dependParam: "faculty",
        getDependValue: function () { return faculty.value(); },
        onChange: function () { submitFor("department", dept); },
    });
    var group = SS.create(form.querySelector(".js-jl-group"), {
        url: U.group, dependParam: "department",
        getDependValue: function () { return dept.value(); },
        onChange: function () { submitFor("group", group); },
    });
    var teacher = SS.create(form.querySelector(".js-jl-teacher"), {
        url: U.teacher, onChange: function () { submitFor("teacher", teacher); },
    });
    // Cari seçimi göstər (setValue emit edir → initializing bayrağı submit-i saxlayır).
    function pre(pick, name) { var d = PRE[name]; if (pick && d && d.id) { pick.setValue(d.id, d.label || d.id); } }
    pre(faculty, "faculty"); pre(dept, "department"); pre(group, "group"); pre(teacher, "teacher");
    initializing = false;
})();
