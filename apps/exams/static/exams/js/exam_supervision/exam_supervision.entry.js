import ExamSupervision from "./state.js?v=20260914-w4r3";
import "./ui.js?v=20260914-w4r3";
import "./trial_notice.js?v=20260914-w4r3";
import "./event_capture.js?v=20260914-w4r3";
import "./scoring.js?v=20260914-w4r3";
import "./api.js?v=20260914-w4r3";
import "./intervention.js?v=20260914-w4r3";
import "./websocket.js?v=20260914-w4r3";

window.ExamSupervision = ExamSupervision;

function runAutoInit() {
    var opts = window.EXAM_SUPERVISION_INIT_CONFIG;
    if (!opts || ExamSupervision._initialized) return;
    ExamSupervision.init(opts);
}

if (window.EXAM_SUPERVISION_INIT_CONFIG) {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", runAutoInit, { once: true });
    } else {
        runAutoInit();
    }
}

export { ExamSupervision };
export default ExamSupervision;
