"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {JSDOM} = require("jsdom");
const root = path.resolve(__dirname, "../..");
const dir = path.join(root, "apps/accounts/static/accounts/js/rim_center");
function setup() {
    const dom = new JSDOM("<body></body>", {runScripts:"outside-only"});
    const w = dom.window;
    w.eval(fs.readFileSync(path.join(dir, "namespace.js"), "utf8"));
    let click;
    w.EMSReady = {once: (_, fn) => fn()};
    w.EMSDelegate = {on: (_, selector, fn) => {click = fn;}};
    w.eval(fs.readFileSync(path.join(dir, "staff_scope.js"), "utf8"));
    const user = {id:19, staff_scope:{labels:{title:"Lab chair", help:"Only selected role", reason:"Reason", save:"Save"},
        memberships:[{id:"lab-id", unit_id:"old", unit_name:"Social", role_label:"Laborant"}],
        units:[{id:"old", name:"Social"}, {id:"new", name:"Philosophy<script>bad()</script>"}]}};
    w.document.body.innerHTML = w.EMSRimCenter.staffScope.render(user);
    return {w, user, click};
}
test("current selected membership and standardized searchable select preserve escaped labels", () => {
    const {w} = setup();
    const select = w.document.querySelector("select");
    assert.equal(select.value, "old");
    assert.equal(select.dataset.liveSearch, "true");
    assert.equal(select.hasAttribute("data-bootstrap-select"), true);
    assert.equal(select.options[1].textContent, "Philosophy<script>bad()</script>");
    assert.equal(w.document.querySelector("script"), null);
    assert.equal(w.document.querySelector("[data-rim-staff-scope]").dataset.rimStaffScope, "lab-id");
    w.close();
});
test("save sends only chosen affiliation, expected source and reason, without personal edit", async () => {
    const {w, user, click} = setup();
    const ns = w.EMSRimCenter;
    let payload, rendered;
    ns.state = {selectedUser:user};
    ns.config = () => ({actionUrl:"/action/"});
    ns.actions = {search:()=>{}};
    ns.render = {detail:value => {rendered=value;}};
    w.EMSCore = {fetchJSON:(_, options) => {payload=options.data; return Promise.resolve({user:{id:19}});}};
    w.document.querySelector("select").value = "new";
    w.document.querySelector("input").value = "Wrong previous department";
    click({preventDefault(){}}, w.document.querySelector("button"));
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(JSON.parse(JSON.stringify(payload)), {action:"move_staff_scope", user_id:19,
        membership_id:"lab-id", expected_unit_id:"old", unit_id:"new", reason:"Wrong previous department"});
    assert.equal(rendered.id, 19);
    w.close();
});
