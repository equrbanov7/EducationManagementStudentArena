/*
 * «Yük bölgüsü» — forma köməkçiləri (`window.EMSWorkloadForms`): oxu / doldurma.
 *
 * 2026-10-15: sətir redaktə modalı əvvəl saatları, ixtisası və qrupları DOLDURMURDU, fənn/semestr
 * açılışları isə doldurmadan SONRA yüklənib dəyəri silirdi — «Redaktə» → «Yadda saxla» saatları 0,
 * qrupları və ixtisası boş göndərirdi. İndi əsas modul açılışları yükləyib BUNU çağırır; sətrin öz
 * dəyəri siyahıda yoxdursa (artıq aktiv olmayan fənn, başqa kafedranın qrupu) seçim kimi əlavə olunur.
 *
 * Saf köməkçidir: listener, fetch, qlobal vəziyyət YOXDUR (AJAX-safe).
 */
(function (window) {
    "use strict";

    var Forms = (window.EMSWorkloadForms = window.EMSWorkloadForms || {});

    function refresh(select) {
        // `group_ids` — stilli çoxseçim (EMSMultiSelect): `option.selected` yazısı mutasiya vermir, açıq yenilə.
        if (select && select.multiple && window.EMSMultiSelect) {
            window.EMSMultiSelect.refresh(select);
            return;
        }
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
    }

    /** Seçim siyahıda yoxdursa əlavə edir (dəyər itməsin). */
    Forms.ensureOption = function ensureOption(select, value, label) {
        if (!select || !value) return;
        var exists = Array.prototype.some.call(select.options, function (option) {
            return option.value === String(value);
        });
        if (exists) return;
        var option = select.ownerDocument.createElement("option");
        option.value = String(value);
        option.textContent = label || String(value);
        select.appendChild(option);
    };

    /** Formanın dəyərləri: checkbox → "1"/"", multiple → massiv. */
    Forms.values = function values(form) {
        if (!form) return {};
        var data = {};
        Array.prototype.forEach.call(form.elements, function (field) {
            if (!field.name) return;
            if (field.type === "checkbox") {
                data[field.name] = field.checked ? "1" : "";
                return;
            }
            if (field.multiple) {
                data[field.name] = Array.prototype.filter
                    .call(field.options, function (option) {
                        return option.selected;
                    })
                    .map(function (option) {
                        return option.value;
                    });
                return;
            }
            data[field.name] = field.value;
        });
        return data;
    };

    Forms.planChoices = function planChoices(select, rows, label) {
        select.replaceChildren();
        var placeholder = select.ownerDocument.createElement("option");
        placeholder.value = "";
        placeholder.textContent = select.dataset.placeholder;
        select.appendChild(placeholder);
        rows.forEach(function (row, index) {
            var option = select.ownerDocument.createElement("option");
            option.value = String(index);
            option.textContent = label(row);
            option.workloadPlanRow = row;
            select.appendChild(option);
        });
        select.value = "";
        refresh(select);
    };

    Forms.applyPlanChoice = function applyPlanChoice(form, select) {
        var option = select.options[select.selectedIndex];
        var row = option && option.workloadPlanRow;
        if (!row) return;
        Forms.ensureOption(form.elements.subject_id, row.subject_id, row.subject_name);
        Forms.ensureOption(form.elements.specialty_id, row.specialty_id, row.specialty_name);
        ["subject_id", "specialty_id", "season", "degree_level", "credits", "credits_value"].forEach(function (name) {
            var field = form.elements[name];
            field.value = row[name] == null ? "" : row[name];
            if (field.tagName === "SELECT") refresh(field);
        });
        form.elements.subject_text.value = "";
    };

    /**
     * Yeni bölgünün saatı — fəaliyyətin QALIĞI (yoxdursa 1). 2026-11-11 («Tədqiqat analitikası»): defolt 1 idi,
     * tələsik «Əlavə et» seminara 1 s yazırdı (qalıq 14 s qalırdı).
     */
    Forms.defaultHours = function defaultHours(form, row, activitySelect) {
        if (!form || !form.elements.hours || !row || !activitySelect) return;
        var info = (row.activities || {})[activitySelect.value];
        form.elements.hours.value = info && info.remaining > 0 ? info.remaining : 1;
    };

    /**
     * «Bölüşdür» tam bölünmüş fəaliyyətdə (qalıq 0) boş «Vakant» forması açırdı — istifadəçi müəllimin
     * silindiyini düşünürdü (sahib 2026-11-28, 535 MRK «Menecment» 45/45). Növün TƏK təyinatı varsa onu
     * redaktə üçün qaytarır; qalıq varsa və ya bir neçə müəllim varsa `null` (yeni təyinat forması).
     */
    Forms.fullAssignment = function fullAssignment(row, activity) {
        var info = row && row.activities ? row.activities[activity] : null;
        if (!info || info.remaining > 0) return null;
        var same = (row.assignments || []).filter(function (item) { return item.activity === activity; });
        return same.length === 1 ? same[0] : null;
    };

    /** Sətir modalını sətrin CARİ dəyərləri ilə doldurur (`row=null` — boş forma). */
    Forms.fillRow = function fillRow(form, row) {
        if (!form) return;
        form.reset();
        var selectedGroups = form.elements.group_ids;
        if (selectedGroups) {
            Array.prototype.forEach.call(selectedGroups.options, function (option) { option.selected = false; });
        }
        if (window.EMSWorkloadTransfer) window.EMSWorkloadTransfer.fill(form, row);
        if (!row) {
            // Boş forma da stilli seçicilərə yansısın (əvvəlki sətrin etiketi/qrupları qalmasın).
            Array.prototype.forEach.call(form.querySelectorAll("select"), refresh);
            return;
        }
        var elements = form.elements;
        Forms.ensureOption(elements.subject_id, row.subject_id, row.subject);
        Forms.ensureOption(elements.period_id, row.period_id, row.period_label);
        Forms.ensureOption(elements.specialty_id, row.specialty_id, row.specialty);
        var mapping = {
            row_id: row.id,
            subject_id: row.subject_id,
            subject_text: row.subject,
            period_id: row.period_id,
            specialty_id: row.specialty_id,
            season: row.season,
            row_kind: row.row_kind,
            education_form: row.education_form,
            degree_level: row.degree_level,
            student_count: row.student_count,
            union_count: row.union_count,
            subgroup_count: row.subgroup_count,
            lab_group_count: row.lab_group_count,
            credits: row.credits,
        };
        Object.keys(row.hours || {}).forEach(function (name) {
            mapping[name] = row.hours[name];
        });
        Object.keys(mapping).forEach(function (name) {
            var field = elements[name];
            if (field && mapping[name] != null) field.value = mapping[name];
        });
        var groups = elements.group_ids;
        if (groups) {
            var wanted = {};
            (row.groups || []).forEach(function (group) {
                Forms.ensureOption(groups, group.id, group.name);
                wanted[group.id] = true;
            });
            Array.prototype.forEach.call(groups.options, function (option) {
                option.selected = !!wanted[option.value];
            });
        }
        Array.prototype.forEach.call(form.querySelectorAll("select"), refresh);
    };
})(window);
