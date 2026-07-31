/*
 * assignment_modals.js
 * Source: apps/assignments/templates/assignments/partials/_assignment_modals.html
 * Add/Edit assignment modals: group/student lazy loading + selection state,
 * AJAX create/edit, delete (confirm-gated). COURSE_ID + i18n read from
 * #assignmentModalsConfig data-*; CSRF from EMSCore.
 */
(function () {
    if (window._ASN_MODAL_V2) return;
    window._ASN_MODAL_V2 = true;

    const cfgEl = document.getElementById("assignmentModalsConfig");
    if (!cfgEl) return;
    const ds = cfgEl.dataset;

    const I18N = {
        loading: ds.i18nLoading,
        noGroup: ds.i18nNoGroup,
        error: ds.i18nError,
        selectGroupFirst: ds.i18nSelectGroupFirst,
        noStudent: ds.i18nNoStudent,
        dataNotReceived: ds.i18nDataNotReceived,
        serverError: ds.i18nServerError,
        errorPrefix: ds.i18nErrorPrefix,
        add: ds.i18nAdd,
        save: ds.i18nSave,
        confirmDelete: ds.i18nConfirmDelete,
    };

    const COURSE_ID = parseInt(ds.courseId, 10);
    const CSRF = EMSCore.getCsrfToken();
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
        const gc = document.querySelectorAll(`#${mode}AsnGroupList input:checked`).length;
        const sc = document.querySelectorAll(`#${mode}AsnStudentList input:checked`).length;
        if($(mode+'AsnGroupCount')) $(mode+'AsnGroupCount').textContent = gc;
        if($(mode+'AsnStudentCount')) $(mode+'AsnStudentCount').textContent = sc;
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

    function loadingHtml() {
        return '<div class="d-flex flex-column gap-2 p-2" aria-hidden="true">'
            + '<span class="skeleton skeleton-line skeleton-line--sm"></span>'
            + '<span class="skeleton skeleton-line skeleton-line--sm"></span>'
            + '<span class="skeleton skeleton-line skeleton-line--sm"></span>'
            + '</div>';
    }

    function loadGroups(mode, checkedGroups = []) {
        const container = $(mode + 'AsnGroupList');
        container.innerHTML = loadingHtml();

        fetch(`/assignments/search-groups/?course_id=${COURSE_ID}`)
            .then(r => r.json())
            .then(data => {
                const groups = data.results || [];
                if(!groups.length) {
                    container.innerHTML = `<p class="text-muted text-center py-3">${I18N.noGroup}</p>`;
                    return;
                }

                container.innerHTML = groups.map(g => `
                    <div class="asn-chk-row">
                        <input type="checkbox" id="${mode}AsnG${g.id}" name="group_names[]" value="${esc(g.text)}"
                               data-group="${esc(g.text)}" ${checkedGroups.includes(g.text)?'checked':''}>
                        <label for="${mode}AsnG${g.id}">${esc(g.text)}</label>
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
        const container = $(mode + 'AsnStudentList');
        const state = getModeState(mode);

        const groups = Array.from(document.querySelectorAll(`#${mode}AsnGroupList input:checked`))
                           .map(cb => cb.dataset.group);

        if(!groups.length) {
            resetRemovedAutoSelections(mode);
            container.innerHTML = `<p class="text-muted text-center py-3">${I18N.selectGroupFirst}</p>`;
            updateCount(mode);
            return;
        }

        container.innerHTML = loadingHtml();

        fetch(`/assignments/students-by-groups/?course_id=${COURSE_ID}&groups=${encodeURIComponent(groups.join(','))}`)
            .then(r => r.json())
            .then(data => {
                const students = data.students || [];
                syncSelectedStudentsFromGroups(mode, students);

                if(!students.length) {
                    container.innerHTML = `<p class="text-muted text-center py-3">${I18N.noStudent}</p>`;
                    updateCount(mode);
                    return;
                }

                container.innerHTML = students.map(s => {
                    const studentId = String(s.id);
                    const isChecked = state.selectedStudentIds.has(studentId) ? 'checked' : '';

                    return `
                        <div class="asn-chk-row">
                            <input type="checkbox" id="${mode}AsnS${s.id}" name="students[]" value="${s.id}" ${isChecked}>
                            <label for="${mode}AsnS${s.id}">${esc(s.name)}</label>
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
        $(mode+'AsnGroupSearch')?.addEventListener('input', e => {
            const t = e.target.value.toLowerCase();
            document.querySelectorAll(`#${mode}AsnGroupList .asn-chk-row`).forEach(row => {
                row.style.display = row.textContent.toLowerCase().includes(t) ? '' : 'none';
            });
        });
        $(mode+'AsnStudentSearch')?.addEventListener('input', e => {
            const t = e.target.value.toLowerCase();
            document.querySelectorAll(`#${mode}AsnStudentList .asn-chk-row`).forEach(row => {
                row.style.display = row.textContent.toLowerCase().includes(t) ? '' : 'none';
            });
        });
    });

    $('addAssignmentModal')?.addEventListener('shown.bs.modal', () => {
        modeSelectionState.add = createSelectionState();
        $('addAsnStudentList').innerHTML = `<p class="text-muted text-center py-3">${I18N.selectGroupFirst}</p>`;
        loadGroups('add');
    });

    $('addAssignmentModal')?.addEventListener('hidden.bs.modal', () => {
        $('createAssignmentForm').reset();
        modeSelectionState.add = createSelectionState();
    });

    $('createAssignmentForm')?.addEventListener('submit', e => {
        e.preventDefault();
        const btn = $('createAssignmentSubmitBtn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

        fetch(`/assignments/create/${COURSE_ID}/`, {
            method: 'POST',
            body: new FormData(e.target),
            headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
        })
        .then(r => r.json())
        .then(d => d.success ? location.reload() : alert(`${I18N.errorPrefix}: ` + (d.error || '')))
        .catch(() => alert(I18N.serverError))
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = `<i class="fas fa-check"></i> ${I18N.add}`;
        });
    });

    document.addEventListener('click', e => {
        const btn = e.target.closest('.js-edit-assignment');
        if(!btn) return;
        e.preventDefault();

        const url = btn.dataset.url;

        modeSelectionState.edit = createSelectionState();
        $('editAsnGroupList').innerHTML = loadingHtml();
        $('editAsnStudentList').innerHTML = loadingHtml();

        bootstrap.Modal.getOrCreateInstance($('editAssignmentModal')).show();

        fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(r => r.json())
            .then(res => {
                if(!res.success) return alert(I18N.dataNotReceived);

                const d = res.data;

                $('editAsnId').value = d.id;
                $('editAsnTitle').value = d.title || '';
                $('editAsnDescription').value = d.description || '';
                $('editAsnStartDate').value = toLocal(d.start_date);
                $('editAsnDeadline').value = toLocal(d.deadline);
                $('editAsnMaxAttempts').value = d.max_attempts || 3;
                $('editAsnStatus').value = d.status || 'active';
                $('editAsnStatus')._refreshBootstrapSelect && $('editAsnStatus')._refreshBootstrapSelect();

                modeSelectionState.edit = createSelectionState(
                    d.student_ids || [],
                    d.group_excluded_student_ids || []
                );

                loadGroups('edit', d.group_names || []);
            })
            .catch(() => alert(I18N.error));
    });

    $('editAssignmentForm')?.addEventListener('submit', e => {
        e.preventDefault();
        const assignmentId = $('editAsnId').value;
        if(!assignmentId) return;

        const btn = $('editAssignmentSubmitBtn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

        fetch(`/assignments/${assignmentId}/edit/`, {
            method: 'POST',
            body: new FormData(e.target),
            headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
        })
        .then(r => r.json())
        .then(d => d.success ? location.reload() : alert(`${I18N.errorPrefix}: ` + (d.error || '')))
        .catch(() => alert(I18N.serverError))
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = `<i class="fas fa-check"></i> ${I18N.save}`;
        });
    });

    document.addEventListener('click', e => {
        const btn = e.target.closest('.js-delete-assignment');
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
                title: btn.textContent.trim() || I18N.confirmDelete,
                message: I18N.confirmDelete,
                confirmLabel: btn.textContent.trim() || I18N.confirmDelete,
                confirmButtonClass: 'btn btn-danger',
                onConfirm: executeDelete,
            });
            return;
        }

        if(!confirm(I18N.confirmDelete)) return;
        executeDelete();
    });

})();
