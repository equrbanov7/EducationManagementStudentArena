import ExamSupervision from "./state.js?v=20260611-fresh-csrf";
import "./ui.js?v=20260611-fresh-csrf";
import "./event_capture.js?v=20260611-fresh-csrf";
import "./scoring.js?v=20260611-fresh-csrf";
import "./api.js?v=20260611-fresh-csrf";
import "./websocket.js?v=20260611-fresh-csrf";

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
