/**
 * Backward-compatible entrypoint for the authoritative full exam flow.
 *
 * The old script silently defaulted to 1 VU / 1 iteration and stopped after a
 * coding autosave. The shared implementation now requires an explicit
 * K6_PROFILE and covers start, readback reconciliation, submit and result.
 */
export { default, options } from "./full-exam-flow-test.js";
