
document.addEventListener('DOMContentLoaded', function() {

  // ==========================================================
  // HELPERS
  // ==========================================================

  function escapeHtml(str) {
    return (str || '').replace(/[&<>"']/g, function(m) {
      return ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
      })[m];
    });
  }

  function safeRemoveBackdrop() {
    const bd = document.querySelector('.modal-backdrop');
    if (bd) bd.remove();
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('padding-right');
  }

  function closeBootstrapModal(modalEl) {
    if (!modalEl) return;
    const instance = bootstrap.Modal.getInstance(modalEl);
    if (instance) {
      instance.hide();
      return;
    }
    // fallback
    modalEl.classList.remove('show');
    modalEl.style.display = 'none';
    modalEl.setAttribute('aria-hidden', 'true');
    safeRemoveBackdrop();
  }

  function setSubmitDisabled(formEl, disabled) {
    if (!formEl) return;
    const btn = formEl.querySelector('button[type="submit"]');
    if (btn) btn.disabled = disabled;
  }

  function show(el) { if (el) el.style.display = 'block'; }
  function hide(el) { if (el) el.style.display = 'none'; }

  // ==========================================================
  // SELECTOR LOGIC (search + counter + row click)
  // ==========================================================

  function initSelectorLogic(containerId, searchInputId, counterId) {
    const container = document.getElementById(containerId);
    const searchInput = document.getElementById(searchInputId);
    const counter = document.getElementById(counterId);

    if (!container) return;

    function updateCount() {
      const count = container.querySelectorAll('input[type="checkbox"]:checked').length;
      if (counter) counter.innerText = String(count);
    }

    if (searchInput) {
      searchInput.addEventListener('input', function(e) {
        const term = (e.target.value || '').toLowerCase().trim();
        const rows = container.querySelectorAll('.list-item-row');

        rows.forEach(row => {
          const searchData = (row.getAttribute('data-search') || '').toLowerCase();
          row.style.display = searchData.includes(term) ? 'flex' : 'none';
        });
      });
    }

    // row click toggles checkbox (but not when clicking checkbox/label itself)
    container.addEventListener('click', function(e) {
      const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
      if (e.target && e.target.type === 'checkbox') return;
      if (tag === 'LABEL') return;

      const row = e.target.closest('.list-item-row');
      if (!row) return;

      const checkbox = row.querySelector('input[type="checkbox"]');
      if (!checkbox) return;

      checkbox.checked = !checkbox.checked;
      updateCount();
    });

    container.addEventListener('change', function(e) {
      if (e.target && e.target.type === 'checkbox') updateCount();
    });

    // expose for external usage
    return { updateCount };
  }

  const studentSelector = initSelectorLogic('student_list_container', 'student_search_input', 'student_counter');
  const groupSelector   = initSelectorLogic('group_list_container', 'group_search_input', 'group_counter');

  // ==========================================================
  // REFERENCES
  // ==========================================================

  const courseId = "{{ course.id }}";

  // Student modal elements
  const studentModal = document.getElementById('addStudentModal');
  const studentForm = document.getElementById('addStudentForm');
  const studentLoader = document.getElementById('studentLoadingIndicator');
  const studentListContainer = document.getElementById('student_list_container');
  const studentSearchInput = document.getElementById('student_search_input');
  const studentCounter = document.getElementById('student_counter');
  const groupNameInput = document.getElementById('groupNameInput');

  // Group modal elements
  const groupModal = document.getElementById('addGroupModal');
  const groupForm = document.getElementById('addGroupForm');
  const groupLoader = document.getElementById('groupLoadingIndicator');
  const groupListContainer = document.getElementById('group_list_container');
  const groupSearchInput = document.getElementById('group_search_input');
  const groupCounter = document.getElementById('group_counter');

  // Endpoint (sən yaratmısan)
  const availableStudentsUrl = `/courses/${courseId}/available-students/`;

  // ==========================================================
  // RENDER STUDENTS (AJAX refresh for modal open)
  // ==========================================================

  function renderStudents(users) {
    if (!studentListContainer) return;

    if (!users || users.length === 0) {
      studentListContainer.innerHTML = `<div class="p-3 text-center text-muted">İstifadəçi tapılmadı.</div>`;
      return;
    }

    studentListContainer.innerHTML = users.map(u => {
      const username = escapeHtml(u.username);
      const fullName = escapeHtml(u.full_name || '');
      const search = (username + ' ' + fullName).toLowerCase();

      return `
        <div class="list-item-row" data-search="${search}">
          <input type="checkbox"
                 id="user_${u.id}"
                 name="user_ids"
                 value="${u.id}"
                 class="custom-item-checkbox">
          <label for="user_${u.id}" class="custom-item-label">
            ${username}
            ${fullName ? `<span class="text-muted">(${fullName})</span>` : ``}
          </label>
        </div>
      `;
    }).join('');
  }

  async function refreshAvailableStudents() {
    if (!studentListContainer) return;

    // reset UI
    if (studentSearchInput) studentSearchInput.value = '';
    if (studentCounter) studentCounter.innerText = '0';

    studentListContainer.innerHTML = `<div class="p-3 text-center text-muted">Yüklənir...</div>`;

    try {
      const resp = await fetch(availableStudentsUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      const data = await resp.json();

      if (!resp.ok || !data.success) {
        studentListContainer.innerHTML = `<div class="p-3 text-center text-danger">Xəta baş verdi.</div>`;
        return;
      }

      renderStudents(data.users);

      // counter update (after render)
      if (studentSelector && typeof studentSelector.updateCount === 'function') {
        studentSelector.updateCount();
      }

    } catch (err) {
      console.error(err);
      studentListContainer.innerHTML = `<div class="p-3 text-center text-danger">Şəbəkə xətası.</div>`;
    }
  }

  // ==========================================================
  // RESET MODALS (close/open)
  // ==========================================================

  function resetStudentModalUI() {
    if (groupNameInput) groupNameInput.value = '';
    if (studentSearchInput) studentSearchInput.value = '';
    if (studentCounter) studentCounter.innerText = '0';

    // uncheck everything currently in DOM
    if (studentListContainer) {
      const checks = studentListContainer.querySelectorAll('input[type="checkbox"]');
      checks.forEach(c => c.checked = false);
    }
  }

  function resetGroupModalUI() {
    if (groupSearchInput) groupSearchInput.value = '';
    if (groupCounter) groupCounter.innerText = '0';

    if (groupListContainer) {
      const checks = groupListContainer.querySelectorAll('input[type="checkbox"]');
      checks.forEach(c => c.checked = false);
      // reset filtering
      const rows = groupListContainer.querySelectorAll('.list-item-row');
      rows.forEach(r => r.style.display = 'flex');
    }
  }

  if (studentModal) {
    // every time modal opens -> refresh list
    studentModal.addEventListener('shown.bs.modal', function() {
      resetStudentModalUI();
      refreshAvailableStudents();
    });

    // when closes -> cleanup
    studentModal.addEventListener('hidden.bs.modal', function() {
      resetStudentModalUI();
      hide(studentLoader);
      setSubmitDisabled(studentForm, false);
    });
  }

  if (groupModal) {
    groupModal.addEventListener('shown.bs.modal', function() {
      resetGroupModalUI();
    });

    groupModal.addEventListener('hidden.bs.modal', function() {
      resetGroupModalUI();
      hide(groupLoader);
      setSubmitDisabled(groupForm, false);
    });
  }

  // ==========================================================
  // AJAX SUBMIT: ADD STUDENTS (bulk)
  // ==========================================================

  if (studentForm) {
    studentForm.addEventListener('submit', async function(e) {
      e.preventDefault();

      const formData = new FormData(this);
      const userIds = formData.getAll('user_ids');

      if (!userIds || userIds.length === 0) {
        alert('Ən azı bir tələbə seçin!');
        return;
      }

      show(studentLoader);
      setSubmitDisabled(this, true);

      try {
        const response = await fetch(this.action, {
          method: 'POST',
          body: formData,
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });

        const result = await response.json();

        if (response.ok && result.success) {
          alert(`✅ ${result.message || 'Tələbələr əlavə olundu'}`);

          // modal close
          closeBootstrapModal(studentModal);

          // refresh list after adding (so added ones disappear)
          // and optionally you can refresh members list somewhere else
          await refreshAvailableStudents();

          // Əgər istəyirsənsə yenə də tam reload:
          // location.reload();

        } else {
          alert('❌ ' + (result.error || 'Xəta baş verdi'));
        }
      } catch (error) {
        console.error('Network error:', error);
        alert('❌ Server xətası. Yenidən cəhd edin.');
      } finally {
        hide(studentLoader);
        setSubmitDisabled(studentForm, false);
      }
    });
  }

  // ==========================================================
  // AJAX SUBMIT: ADD GROUPS (bulk)
  // ==========================================================

  if (groupForm) {
    groupForm.addEventListener('submit', async function(e) {
      e.preventDefault();

      const formData = new FormData(this);
      const groupIds = formData.getAll('group_ids');

      if (!groupIds || groupIds.length === 0) {
        alert('Ən azı bir qrup seçin!');
        return;
      }

      show(groupLoader);
      setSubmitDisabled(this, true);

      try {
        const response = await fetch(this.action, {
          method: 'POST',
          body: formData,
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });

        const result = await response.json();

        if (response.ok && result.success) {
          alert(`✅ ${result.message || 'Qruplar əlavə olundu'}`);

          closeBootstrapModal(groupModal);

          // İstəsən reload (çünki kurs üzvləri artacaq):
          location.reload();

        } else {
          alert('❌ ' + (result.error || 'Xəta baş verdi'));
        }
      } catch (error) {
        console.error(error);
        alert('❌ Xəta baş verdi.');
      } finally {
        hide(groupLoader);
        setSubmitDisabled(groupForm, false);
      }
    });
  }

});

