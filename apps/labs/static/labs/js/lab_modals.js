/*
 * lab_modals.js
 * Source: apps/labs/templates/labs/partials/lab_modals/_scripts.html
 * Add/Edit lab modals: group/student lazy loading + selection state, AJAX
 * create/edit, delete (confirm-gated). COURSE_ID + i18n read from
 * #labModalsConfig data-*; CSRF from EMSCore. escapeHtml from utils/escape.js.
 */
(function () {
    const cfgEl = document.getElementById("labModalsConfig");
    if (!cfgEl) return;
    const ds = cfgEl.dataset;

    const COURSE_ID = parseInt(ds.courseId, 10);
    const CSRF = EMSCore.getCsrfToken();
    const $ = id => document.getElementById(id);

    const I18N = {
        modalNotFound: ds.i18nModalNotFound,
        loading: ds.i18nLoading,
        errorDataNotLoaded: ds.i18nErrorDataNotLoaded,
        errorUnknown: ds.i18nErrorUnknown,
        errorGeneric: ds.i18nErrorGeneric,
        confirmDeleteLab: ds.i18nConfirmDeleteLab,
        errorPrefix: ds.i18nErrorPrefix,
        errorServer: ds.i18nErrorServer,
        noGroups: ds.i18nNoGroups,
        selectGroupFirst: ds.i18nSelectGroupFirst,
        noStudents: ds.i18nNoStudents,
        existingFile: ds.i18nExistingFile,
        buttonCreate: ds.i18nButtonCreate,
        buttonSave: ds.i18nButtonSave,
        stateError: ds.i18nStateError
    };

    // escapeHtml is provided by labs/js/utils/escape.js

    function createSelectionState(initialSelectedIds, initialManuallyDeselectedAutoIds) {
        var normalizedIds = (initialSelectedIds || []).map(function(id) {
            return String(id);
        });
        var normalizedDeselectedIds = (initialManuallyDeselectedAutoIds || []).map(function(id) {
            return String(id);
        });
        return {
            selectedStudentIds: new Set(normalizedIds),
            autoSelectedStudentIds: new Set(),
            manuallyDeselectedAutoStudentIds: new Set(normalizedDeselectedIds),
        };
    }

    var modeSelectionState = {
        add: createSelectionState(),
        edit: createSelectionState(),
    };

    function getModeState(mode) {
        if (!modeSelectionState[mode]) {
            modeSelectionState[mode] = createSelectionState();
        }
        return modeSelectionState[mode];
    }

    function resetRemovedAutoSelections(mode) {
        var state = getModeState(mode);
        state.autoSelectedStudentIds.forEach(function(studentId) {
            state.selectedStudentIds.delete(studentId);
        });
        state.autoSelectedStudentIds.clear();
        state.manuallyDeselectedAutoStudentIds.clear();
    }

    function syncSelectedStudentsFromGroups(mode, students) {
        var state = getModeState(mode);
        var nextAutoSelectedIds = new Set((students || []).map(function(student) {
            return String(student.id);
        }));

        state.autoSelectedStudentIds.forEach(function(studentId) {
            if (!nextAutoSelectedIds.has(studentId)) {
                state.selectedStudentIds.delete(studentId);
            }
        });

        Array.from(state.manuallyDeselectedAutoStudentIds).forEach(function(studentId) {
            if (!nextAutoSelectedIds.has(studentId)) {
                state.manuallyDeselectedAutoStudentIds.delete(studentId);
            }
        });

        nextAutoSelectedIds.forEach(function(studentId) {
            if (!state.manuallyDeselectedAutoStudentIds.has(studentId)) {
                state.selectedStudentIds.add(studentId);
            }
        });

        state.autoSelectedStudentIds = nextAutoSelectedIds;
    }

    function openDeleteConfirmation(options) {
        if (typeof window.openActionConfirmModal === 'function') {
            window.openActionConfirmModal(options);
            return;
        }

        if (!confirm(options.message || I18N.confirmDeleteLab)) return;
        Promise.resolve(options.onConfirm && options.onConfirm()).catch(function() {
            alert(I18N.errorServer);
        });
    }

    window.openEditLabModal = function(url) {
        const modalEl = $('editLabModal');
        if (!modalEl) {
            alert(I18N.modalNotFound);
            return;
        }

        modeSelectionState.edit = createSelectionState();
        $('editLabGroupList').innerHTML = '<div class="d-flex flex-column gap-2 p-2" aria-hidden="true"><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span></div>';
        $('editLabStudentList').innerHTML = '<div class="d-flex flex-column gap-2 p-2" aria-hidden="true"><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span></div>';

        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();

        fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}})
        .then(r => r.json())
        .then(res => {
            if (!res.success) {
                alert(I18N.errorDataNotLoaded + ': ' + (res.error || I18N.errorUnknown));
                return;
            }

            const d = res.data;

            if ($('editLabId')) $('editLabId').value = d.id;
            if ($('editLabTitle')) $('editLabTitle').value = d.title || '';
            if ($('editLabDescription')) $('editLabDescription').value = d.description || '';
            if ($('editLabStart')) $('editLabStart').value = d.start_datetime || '';
            if ($('editLabEnd')) $('editLabEnd').value = d.end_datetime || '';
            if ($('editLabMaxScore')) $('editLabMaxScore').value = d.max_score || 100;
            if ($('editLabMaxAttempts')) $('editLabMaxAttempts').value = d.max_attempts || 1;
            if ($('editLabStatus')) {
                $('editLabStatus').value = d.status || 'draft';
                $('editLabStatus')._refreshBootstrapSelect && $('editLabStatus')._refreshBootstrapSelect();
            }
            if ($('editLabQPS')) $('editLabQPS').value = d.questions_per_student || 0;
            if ($('editAllowLate')) $('editAllowLate').checked = d.allow_late_submission;
            if ($('editLatePenalty')) $('editLatePenalty').value = d.late_penalty_percent || 0;
            if ($('editAllowFile')) $('editAllowFile').checked = d.allow_file_upload;
            if ($('editAllowLink')) $('editAllowLink').checked = d.allow_link_submission;
            if ($('editMaxFileSize')) $('editMaxFileSize').value = d.max_file_size_mb || 50;
            if ($('editAllowedExt')) $('editAllowedExt').value = d.allowed_extensions || '';
            if ($('editLabInstructions')) $('editLabInstructions').value = d.teacher_instructions || '';

            if (d.teacher_files_url && $('editCurrentFile')) {
                $('editCurrentFile').innerHTML = '<a href="' + d.teacher_files_url + '" target="_blank" class="btn btn-sm btn-outline-primary"><i class="fas fa-download me-1"></i> ' + I18N.existingFile + '</a>';
            } else if ($('editCurrentFile')) {
                $('editCurrentFile').innerHTML = '';
            }

            modeSelectionState.edit = createSelectionState(
                d.student_ids || [],
                d.group_excluded_student_ids || []
            );
            loadGroups('edit', d.group_names || []);
        })
        .catch(function() {
            alert(I18N.errorGeneric);
        });
    };

    window.deleteLabConfirm = function(url, trigger) {
        openDeleteConfirmation({
            title: (trigger && trigger.textContent ? trigger.textContent.trim() : '') || I18N.confirmDeleteLab,
            message: I18N.confirmDeleteLab,
            confirmLabel: (trigger && trigger.textContent ? trigger.textContent.trim() : '') || 'Sil',
            confirmButtonClass: 'btn btn-danger',
            onConfirm: function() {
                return fetch(url, {
                    method: 'POST',
                    headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
                })
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    if (d.success) {
                        location.reload();
                        return true;
                    }
                    alert(I18N.errorPrefix + ': ' + (d.error || I18N.errorUnknown));
                    return false;
                })
                .catch(function() {
                    alert(I18N.errorServer);
                    return false;
                });
            }
        });
    };

    document.addEventListener('click', function(event) {
        const editBtn = event.target.closest('.js-edit-lab');
        if (editBtn) {
            event.preventDefault();
            window.openEditLabModal(editBtn.dataset.url);
            return;
        }

        const deleteBtn = event.target.closest('.js-delete-lab');
        if (deleteBtn) {
            event.preventDefault();
            window.deleteLabConfirm(deleteBtn.dataset.url, deleteBtn);
        }
    });

    function loadGroups(mode, checkedGroups) {
        checkedGroups = checkedGroups || [];
        const container = $(mode + 'LabGroupList');
        if (!container) return;

        container.innerHTML = '<div class="d-flex flex-column gap-2 p-2" aria-hidden="true"><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span></div>';

        fetch('/labs/api/groups/' + COURSE_ID + '/')
        .then(r => r.json())
        .then(function(data) {
            const groups = data.groups || [];
            if (!groups.length) {
                container.innerHTML = '<p class="text-muted text-center py-3">' + I18N.noGroups + '</p>';
                return;
            }

            var html = '';
            for (var i = 0; i < groups.length; i++) {
                var g = groups[i];
                var checked = checkedGroups.indexOf(g.name) > -1 ? 'checked' : '';
                var escapedName = escapeHtml(g.name);
                html += '<div class="lab-chk-row">' +
                    '<input type="checkbox" id="' + escapeHtml(mode) + 'LabG_' + escapedName + '" name="group_names[]" value="' + escapedName + '" data-group="' + escapedName + '" ' + checked + '>' +
                    '<label for="' + escapeHtml(mode) + 'LabG_' + escapedName + '">' + escapedName + '</label>' +
                    '</div>';
            }
            container.innerHTML = html;

            container.querySelectorAll('input').forEach(function(cb) {
                cb.addEventListener('change', function() {
                    updateCount(mode);
                    loadStudents(mode);
                });
            });

            updateCount(mode);
            if (checkedGroups.length) loadStudents(mode);
        })
        .catch(function() {
            container.innerHTML = '<p class="text-danger text-center py-3">' + I18N.stateError + '</p>';
        });
    }

    function loadStudents(mode) {
        const container = $(mode + 'LabStudentList');
        if (!container) return;
        var state = getModeState(mode);

        var groupInputs = document.querySelectorAll('#' + mode + 'LabGroupList input:checked');
        var groups = [];
        groupInputs.forEach(function(cb) { groups.push(cb.dataset.group); });

        if (!groups.length) {
            resetRemovedAutoSelections(mode);
            container.innerHTML = '<p class="text-muted text-center py-3">' + I18N.selectGroupFirst + '</p>';
            updateCount(mode);
            return;
        }

        container.innerHTML = '<div class="d-flex flex-column gap-2 p-2" aria-hidden="true"><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span></div>';

        fetch('/labs/api/students/' + COURSE_ID + '/?groups=' + encodeURIComponent(groups.join(',')))
        .then(r => r.json())
        .then(function(data) {
            const students = data.students || [];
            syncSelectedStudentsFromGroups(mode, students);
            if (!students.length) {
                container.innerHTML = '<p class="text-muted text-center py-3">' + I18N.noStudents + '</p>';
                updateCount(mode);
                return;
            }

            var html = '';
            for (var i = 0; i < students.length; i++) {
                var s = students[i];
                var studentId = String(s.id);
                var isChecked = state.selectedStudentIds.has(studentId) ? 'checked' : '';
                var escapedName = escapeHtml(s.name);
                var escapedGroupName = escapeHtml(s.group_name || '');
                html += '<div class="lab-chk-row">' +
                    '<input type="checkbox" id="' + escapeHtml(mode) + 'LabS' + studentId + '" name="student_ids[]" value="' + studentId + '" ' + isChecked + '>' +
                    '<label for="' + escapeHtml(mode) + 'LabS' + studentId + '">' + escapedName + '</label>' +
                    '<span class="badge bg-secondary">' + escapedGroupName + '</span>' +
                    '</div>';
            }
            container.innerHTML = html;

            container.querySelectorAll('input').forEach(function(cb) {
                cb.addEventListener('change', function() {
                    var studentId = String(cb.value);
                    if (cb.checked) {
                        state.selectedStudentIds.add(studentId);
                    } else {
                        state.selectedStudentIds.delete(studentId);
                    }

                    if (state.autoSelectedStudentIds.has(studentId)) {
                        if (cb.checked) {
                            state.manuallyDeselectedAutoStudentIds.delete(studentId);
                        } else {
                            state.manuallyDeselectedAutoStudentIds.add(studentId);
                        }
                    }

                    updateCount(mode);
                });
            });

            updateCount(mode);
        })
        .catch(function() {
            container.innerHTML = '<p class="text-danger text-center py-3">' + I18N.stateError + '</p>';
        });
    }

    function updateCount(mode) {
        var gc = document.querySelectorAll('#' + mode + 'LabGroupList input:checked').length;
        var sc = document.querySelectorAll('#' + mode + 'LabStudentList input:checked').length;
        if ($(mode + 'LabGroupCount')) $(mode + 'LabGroupCount').textContent = gc;
        if ($(mode + 'LabStudentCount')) $(mode + 'LabStudentCount').textContent = sc;
    }

    var addModal = $('addLabModal');
    if (addModal) {
        addModal.addEventListener('shown.bs.modal', function() {
            modeSelectionState.add = createSelectionState();
            $('addLabStudentList').innerHTML = '<p class="text-muted text-center py-3">' + I18N.selectGroupFirst + '</p>';
            loadGroups('add');
        });

        addModal.addEventListener('hidden.bs.modal', function() {
            $('createLabForm').reset();
            modeSelectionState.add = createSelectionState();
        });
    }

    var createForm = $('createLabForm');
    if (createForm) {
        createForm.addEventListener('submit', function(e) {
            e.preventDefault();
            var btn = this.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

            fetch('/labs/create/' + COURSE_ID + '/', {
                method: 'POST',
                body: new FormData(this),
                headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
            })
            .then(r => r.json())
            .then(function(d) {
                if (d.success) location.reload();
                else alert(I18N.errorPrefix + ': ' + (d.error || I18N.errorUnknown));
            })
            .catch(function() { alert(I18N.errorServer); })
            .finally(function() {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-check me-1"></i> ' + I18N.buttonCreate;
            });
        });
    }

    var editForm = $('editLabForm');
    if (editForm) {
        editForm.addEventListener('submit', function(e) {
            e.preventDefault();
            var labId = $('editLabId').value;
            if (!labId) return;

            var btn = this.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

            fetch('/labs/' + labId + '/edit/', {
                method: 'POST',
                body: new FormData(this),
                headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
            })
            .then(r => r.json())
            .then(function(d) {
                if (d.success) location.reload();
                else alert(I18N.errorPrefix + ': ' + (d.error || I18N.errorUnknown));
            })
            .catch(function() { alert(I18N.errorServer); })
            .finally(function() {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-save me-1"></i> ' + I18N.buttonSave;
            });
        });
    }

    var addGSearch = $('addLabGroupSearch');
    if (addGSearch) {
        addGSearch.addEventListener('input', function(e) {
            var t = e.target.value.toLowerCase();
            document.querySelectorAll('#addLabGroupList .lab-chk-row').forEach(function(row) {
                row.style.display = row.textContent.toLowerCase().indexOf(t) > -1 ? '' : 'none';
            });
        });
    }

    var editGSearch = $('editLabGroupSearch');
    if (editGSearch) {
        editGSearch.addEventListener('input', function(e) {
            var t = e.target.value.toLowerCase();
            document.querySelectorAll('#editLabGroupList .lab-chk-row').forEach(function(row) {
                row.style.display = row.textContent.toLowerCase().indexOf(t) > -1 ? '' : 'none';
            });
        });
    }
})();
