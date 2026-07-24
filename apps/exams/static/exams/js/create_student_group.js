/*
 * create_student_group.js
 * Source template: apps/exams/templates/exams/teacher/create_student_group.html
 * Client-side filtering of the primary-teacher <select> from a search input.
 * The target select id is bridged via #primaryTeacherSearch[data-teacher-select-id].
 */
(function () {
  const searchInput = document.getElementById("primaryTeacherSearch");
  if (!searchInput) return;

  const teacherSelectId = searchInput.dataset.teacherSelectId;
  const teacherSelect = teacherSelectId ? document.getElementById(teacherSelectId) : null;

  if (!teacherSelect) return;

  searchInput.addEventListener("input", function () {
    const filter = (this.value || "").toLowerCase();
    const options = Array.from(teacherSelect.options);

    options.forEach((option) => {
      option.hidden = !(option.text || "").toLowerCase().includes(filter);
    });

    const selectedVisible = options.find((option) => option.selected && !option.hidden);
    if (!selectedVisible) {
      const firstVisible = options.find((option) => !option.hidden);
      if (firstVisible) {
        firstVisible.selected = true;
      }
    }
  });
})();
