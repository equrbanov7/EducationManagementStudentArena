/*
 * project_modals.js
 * Source: apps/projects/templates/projects/partials/_project_modals.html
 * Add/Edit project modalları — qrup/tələbə seçimi, create/edit/delete AJAX axını.
 * Config (course id + i18n) #project-modals-config data-* atributlarından oxunur;
 * CSRF EMSCore-dan. Davranış inline versiya ilə eynidir (delegated click + guard).
 */
(function () {
    if (window._PROJ_MODAL_V4) return;
    window._PROJ_MODAL_V4 = true;

    const cfgEl = document.getElementById('project-modals-config');
    if (!cfgEl) return;
    const cfg = cfgEl.dataset;

    const I18N = {
        loading: cfg.i18nLoading,
        noGroups: cfg.i18nNoGroups,
        noStudents: cfg.i18nNoStudents,
        error: cfg.i18nError,
        selectGroupFirst: cfg.i18nSelectGroupFirst,
        fetchFailed: cfg.i18nFetchFailed,
        serverError: cfg.i18nServerError,
        createErrorPrefix: cfg.i18nCreateErrorPrefix,
        updateErrorPrefix: cfg.i18nUpdateErrorPrefix,
        submitting: cfg.i18nSubmitting,
        add: cfg.i18nAdd,
        save: cfg.i18nSave,
        deleteConfirm: cfg.i18nDeleteConfirm,
    };

    const COURSE_ID = cfg.courseId;
    const CSRF = (window.EMSCore && EMSCore.getCsrfToken())
        || document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    const $ = id => document.getElementById(id);

    function createSelectionState(initialSelectedIds, initialManuallyDeselectedAutoIds) {
        return {
            selectedStudentIds: new Set((initialSelectedIds || []).map(id => String(id))),
            autoSelectedStudentIds: new Set(),
            manuallyDeselectedAutoStudentIds: new Set(
                (initialManuallyDeselectedAutoIds || []).map(id => String(id))
            ),
        };
    }

    const modeSelectionState = {
        add: createSelectionState(),
        edit: createSelectionState(),
    };

    const esc = s => s ? String(s).replace(/[<>&"']/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'})[c]) : '';

    const toLocal = dt => {
        if(!dt) return '';
        const d = new Date(dt);
        if(isNaN(d)) return '';
        const p = n => String(n).padStart(2,'0');
        return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
    };

    const updateCount = mode => {
        const gc = document.querySelectorAll(`#${mode}GroupList input:checked`).length;
        const sc = document.querySelectorAll(`#${mode}StudentList input:checked`).length;
        if($(mode+'GroupCount')) $(mode+'GroupCount').textContent = gc;
        if($(mode+'StudentCount')) $(mode+'StudentCount').textContent = sc;
    };

    function getModeState(mode) {
        if (!modeSelectionState[mode]) {
            modeSelectionState[mode] = createSelectionState();
        }
        return modeSelectionState[mode];
    }

    function resetRemovedAutoSelections(mode) {
        const state = getModeState(mode);
        state.autoSelectedStudentIds.forEach(studentId => {
            state.selectedStudentIds.delete(studentId);
        });
        state.autoSelectedStudentIds.clear();
        state.manuallyDeselectedAutoStudentIds.clear();
    }

    function syncSelectedStudentsFromGroups(mode, students) {
        const state = getModeState(mode);
        const nextAutoSelectedIds = new Set((students || []).map(student => String(student.id)));

        state.autoSelectedStudentIds.forEach(studentId => {
            if (!nextAutoSelectedIds.has(studentId)) {
                state.selectedStudentIds.delete(studentId);
            }
        });

        Array.from(state.manuallyDeselectedAutoStudentIds).forEach(studentId => {
            if (!nextAutoSelectedIds.has(studentId)) {
                state.manuallyDeselectedAutoStudentIds.delete(studentId);
            }
        });

        nextAutoSelectedIds.forEach(studentId => {
            if (!state.manuallyDeselectedAutoStudentIds.has(studentId)) {
                state.selectedStudentIds.add(studentId);
            }
        });

        state.autoSelectedStudentIds = nextAutoSelectedIds;
    }

    function loadGroups(mode, checkedGroups = []) {
        const container = $(mode + 'GroupList');
        container.innerHTML = `<div class="d-flex flex-column gap-2 p-2" aria-hidden="true"><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span></div>`;

        fetch(`/projects/api/groups/?course_id=${COURSE_ID}`)
            .then(r => r.json())
            .then(data => {
                const groups = data.groups || [];
                if(!groups.length) {
                    container.innerHTML = `<p class="text-muted text-center py-3">${I18N.noGroups}</p>`;
                    return;
                }

                container.innerHTML = groups.map(g => `
                    <div class="chk-row">
                        <input type="checkbox" id="${mode}G${g.id}" name="group_names[]" value="${esc(g.name)}"
                               data-group="${esc(g.name)}" ${checkedGroups.includes(g.name)?'checked':''}>
                        <label for="${mode}G${g.id}">${esc(g.name)}</label>
                    </div>
                `).join('');

                container.querySelectorAll('input').forEach(cb => {
                    cb.addEventListener('change', () => {
                        updateCount(mode);
                        loadStudents(mode);
                    });
                });

                updateCount(mode);

                if(checkedGroups.length) loadStudents(mode);
            })
            .catch(() => {
                container.innerHTML = `<p class="text-danger text-center py-3">${I18N.error}</p>`;
            });
    }

    function loadStudents(mode) {
        const container = $(mode + 'StudentList');
        const state = getModeState(mode);

        const groups = Array.from(document.querySelectorAll(`#${mode}GroupList input:checked`))
                           .map(cb => cb.dataset.group);

        if(!groups.length) {
            resetRemovedAutoSelections(mode);
            container.innerHTML = `<p class="text-muted text-center py-3">${I18N.selectGroupFirst}</p>`;
            updateCount(mode);
            return;
        }

        container.innerHTML = `<div class="d-flex flex-column gap-2 p-2" aria-hidden="true"><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span></div>`;

        fetch(`/projects/api/students/?course_id=${COURSE_ID}&groups=${encodeURIComponent(groups.join(','))}`)
            .then(r => r.json())
            .then(data => {
                const students = data.students || [];
                syncSelectedStudentsFromGroups(mode, students);

                if(!students.length) {
                    container.innerHTML = `<p class="text-muted text-center py-3">${I18N.noStudents}</p>`;
                    updateCount(mode);
                    return;
                }

                container.innerHTML = students.map(s => {
                    const studentId = String(s.id);
                    const isChecked = state.selectedStudentIds.has(studentId) ? 'checked' : '';

                    return `
                        <div class="chk-row">
                            <input type="checkbox" id="${mode}S${s.id}" name="students[]" value="${s.id}" ${isChecked}>
                            <label for="${mode}S${s.id}">${esc(s.name)}</label>
                            <span class="badge bg-secondary">${esc(s.group_name)}</span>
                        </div>
                    `;
                }).join('');

                container.querySelectorAll('input').forEach(cb => {
                    cb.addEventListener('change', () => {
                        const studentId = String(cb.value);
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
            .catch(() => {
                container.innerHTML = `<p class="text-danger text-center py-3">${I18N.error}</p>`;
            });
    }

    ['add','edit'].forEach(mode => {
        $(mode+'GroupSearch')?.addEventListener('input', e => {
            const t = e.target.value.toLowerCase();
            document.querySelectorAll(`#${mode}GroupList .chk-row`).forEach(row => {
                row.style.display = row.textContent.toLowerCase().includes(t) ? '' : 'none';
            });
        });
        $(mode+'StudentSearch')?.addEventListener('input', e => {
            const t = e.target.value.toLowerCase();
            document.querySelectorAll(`#${mode}StudentList .chk-row`).forEach(row => {
                row.style.display = row.textContent.toLowerCase().includes(t) ? '' : 'none';
            });
        });
    });

    $('addProjectModal')?.addEventListener('shown.bs.modal', () => {
        modeSelectionState.add = createSelectionState();
        $('addStudentList').innerHTML = `<p class="text-muted text-center py-3">${I18N.selectGroupFirst}</p>`;
        loadGroups('add');
    });

    $('addProjectModal')?.addEventListener('hidden.bs.modal', () => {
        $('createProjectForm').reset();
        modeSelectionState.add = createSelectionState();
    });

    $('createProjectForm')?.addEventListener('submit', e => {
        e.preventDefault();
        const btn = e.target.querySelector('[type=submit]');
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${I18N.submitting}`;

        fetch(`/projects/create/${COURSE_ID}/`, {
            method: 'POST',
            body: new FormData(e.target),
            headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
        })
        .then(r => r.json())
        .then(d => d.success ? location.reload() : alert(`${I18N.createErrorPrefix}${d.error || I18N.fetchFailed}`))
        .catch(() => alert(I18N.serverError))
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = `<i class="bi bi-check"></i> ${I18N.add}`;
        });
    });

    document.addEventListener('click', e => {
        const btn = e.target.closest('.js-edit-project');
        if(!btn) return;
        e.preventDefault();

        const url = btn.dataset.url;

        modeSelectionState.edit = createSelectionState();
        $('editGroupList').innerHTML = `<div class="d-flex flex-column gap-2 p-2" aria-hidden="true"><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span></div>`;
        $('editStudentList').innerHTML = `<div class="d-flex flex-column gap-2 p-2" aria-hidden="true"><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span><span class="skeleton skeleton-line skeleton-line--sm"></span></div>`;

        bootstrap.Modal.getOrCreateInstance($('editProjectModal')).show();

        fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(r => r.json())
            .then(res => {
                if(!res.success) return alert(I18N.fetchFailed);

                const d = res.data;

                $('editProjectId').value = d.id;
                $('editTitle').value = d.title || '';
                $('editDescription').value = d.description || '';
                $('editStartDate').value = toLocal(d.start_date);
                $('editDeadline').value = toLocal(d.deadline);
                $('editMaxAttempts').value = d.max_attempts || 1;
                $('editMaxScore').value = d.max_score || 100;
                $('editStatus').value = d.status || 'active';
                $('editStatus')._refreshBootstrapSelect && $('editStatus')._refreshBootstrapSelect();

                modeSelectionState.edit = createSelectionState(
                    d.student_ids || [],
                    d.group_excluded_student_ids || []
                );
                loadGroups('edit', d.group_names || []);
            })
            .catch(() => alert(I18N.error));
    });

    $('editProjectForm')?.addEventListener('submit', e => {
        e.preventDefault();
        const projectId = $('editProjectId').value;
        if(!projectId) return;

        const btn = e.target.querySelector('[type=submit]');
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${I18N.submitting}`;

        fetch(`/projects/${projectId}/edit/`, {
            method: 'POST',
            body: new FormData(e.target),
            headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
        })
        .then(r => r.json())
        .then(d => d.success ? location.reload() : alert(`${I18N.updateErrorPrefix}${d.error || I18N.fetchFailed}`))
        .catch(() => alert(I18N.serverError))
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = `<i class="bi bi-check"></i> ${I18N.save}`;
        });
    });

    document.addEventListener('click', e => {
        const btn = e.target.closest('.js-delete-project');
        if(!btn) return;
        e.preventDefault();

        const executeDelete = () => fetch(btn.dataset.url, {
            method: 'POST',
            headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
        })
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                location.reload();
                return true;
            }
            alert(I18N.error);
            return false;
        })
        .catch(() => {
            alert(I18N.serverError);
            return false;
        });

        if (typeof window.openActionConfirmModal === 'function') {
            window.openActionConfirmModal({
                title: btn.textContent.trim() || I18N.deleteConfirm,
                message: I18N.deleteConfirm,
                confirmLabel: btn.textContent.trim() || I18N.deleteConfirm,
                confirmButtonClass: 'btn btn-danger',
                onConfirm: executeDelete,
            });
            return;
        }

        if(!confirm(I18N.deleteConfirm)) return;
        executeDelete();
    });

})();
