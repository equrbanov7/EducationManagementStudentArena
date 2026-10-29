/*
 * «Yük bölgüsü» — forma köməkçiləri (`window.EMSWorkloadForms`): oxu / doldurma.
 *
 * 2026-10-15: sətir redaktə modalı əvvəl saatları, ixtisası və qrupları DOLDURMURDU, fənn/semestr
 * açılışları isə doldurmadan SONRA yüklənib dəyəri silirdi — «Redaktə» → «Yadda saxla» saatları 0,
 * qrupları və ixtisası boş göndərirdi. İndi əsas modul açılışları yükləyib BUNU çağırır; sətrin öz
 * dəyəri siyahıda yoxdursa (fənn həddi — `SUBJECT_OPTIONS_LIMIT`, başqa kafedranın qrupu) seçim kimi əlavə olunur.
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

    function reset(form) {
        Array.prototype.forEach.call(form.elements, function (field) {
            if (!field.name) return;
            if (field.type === "checkbox") {
                field.checked = false;
                return;
            }
            if (field.multiple) {
                Array.prototype.forEach.call(field.options, function (option) {
                    option.selected = false;
                });
                return;
            }
            field.value = field.type === "number" ? "0" : "";
        });
    }

    /** Sətir modalını sətrin CARİ dəyərləri ilə doldurur (`row=null` — boş forma). */
    Forms.fillRow = function fillRow(form, row) {
        if (!form) return;
        reset(form);
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
