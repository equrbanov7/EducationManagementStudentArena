"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

test("an immediate lab finish posts the current attempt once, including pending text and a pending attachment", async () => {
    const dom = new JSDOM(`
        <div id="labDetailConfig" data-lab-id="7" data-end-time="2999-01-01"></div>
        <form id="labForm">
            <input type="hidden" id="labAttempt" name="attempt_number" value="2">
            <div class="question-card" data-question-id="11"><textarea class="answer-textarea" name="answer_11"></textarea></div>
            <div class="question-card" data-question-id="12"><textarea class="answer-textarea" name="answer_12"></textarea></div>
            <input type="file" class="file-input" id="file-11" name="file_11">
            <button type="submit" id="submitBtn"></button>
        </form>
        <div id="finishLabConfirmModal"><button id="confirmFinishLabBtn"></button></div>`,
    { runScripts: "outside-only", url: "http://localhost/labs/7/" });
    const { window } = dom;
    const { document } = window;
    try {
        if (document.readyState === "loading") {
            await new Promise(resolve => document.addEventListener("DOMContentLoaded", resolve));
        }
        const calls = [];
        window.fetch = (url, options) => {
            calls.push({ url, body: options.body });
            return new Promise(() => {}); // An upload is still in flight when the student confirms.
        };
        window.EMSOverlay = { open() {}, close() {} };
        for (const file of ["static/js/ems_ajax_init.js", "apps/labs/static/labs/js/lab_detail.js"]) {
            window.eval(readFileSync(path.resolve(__dirname, "../..", file), "utf8"));
        }
        const input = document.getElementById("file-11");
        Object.defineProperty(input, "files", { value: [new window.File(["lab"], "lab.txt")] });
        input.dispatchEvent(new window.Event("change", { bubbles: true }));
        await Promise.resolve();
        assert.equal(calls[0].body.get("attempt_number"), "2");
        assert.equal(calls[0].body.get("answer_file").name, "lab.txt");
        for (const text of document.querySelectorAll("textarea")) {
            text.value = text.name;
            text.dispatchEvent(new window.Event("input", { bubbles: true }));
        }
        document.getElementById("submitBtn").click();
        document.getElementById("confirmFinishLabBtn").click();
        document.getElementById("confirmFinishLabBtn").click();
        const finals = calls.filter(call => call.url.endsWith("/submit/"));
        assert.equal(finals.length, 1);
        assert.equal(finals[0].body.get("attempt_number"), "2");
        assert.equal(finals[0].body.get("answer_11"), "answer_11");
        assert.equal(finals[0].body.get("answer_12"), "answer_12");
        assert.ok(finals[0].body.has("file_11"));
    } finally {
        window.close();
    }
});
