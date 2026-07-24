/*
 * review_page.js
 * Source: apps/assignments/templates/assignments/review.html
 * Exposes COURSE_ID / ALL_GROUPS / COURSE_STUDENTS globals (consumed by
 * assignment_modal.js) from data-* + JSON data islands in the template.
 */
(function () {
    "use strict";

    var cfgEl = document.getElementById("review-page-config");
    window.COURSE_ID = cfgEl ? parseInt(cfgEl.dataset.courseId, 10) : undefined;

    var groupsEl = document.getElementById("all-groups-data");
    var allGroups = [];
    try {
        var allGroupsPayload = JSON.parse(groupsEl.textContent);
        allGroups = typeof allGroupsPayload === "string" ? JSON.parse(allGroupsPayload) : allGroupsPayload;
    } catch (error) {
        console.warn("Unable to parse group payload.", error);
    }
    window.ALL_GROUPS = allGroups;

    var studentsEl = document.getElementById("course-students-data");
    window.COURSE_STUDENTS = studentsEl ? JSON.parse(studentsEl.textContent) : [];
})();
