import { bombText } from './bomb_text.js?v=lx20261019s';
import { state } from './state.js?v=lx20261019s';
import { postJson } from './api.js?v=lx20261019s';
import { esc } from './utils.js?v=lx20261019s';

export function mountBombDrawer() {
    const root = document.getElementById("hostBombSection");
    if (!root || CONFIG.controlsEnabled === false) return;
    let questions = [];
    try { questions = JSON.parse(document.getElementById("hostQuestions")?.textContent || "[]"); } catch (_) { return; }
    const labels = bombText(document.documentElement.lang);
    let saving = false;
    function render() {
        const ids = new Set((state.sessionSettings.bomb_questions || []).map(Number));
        const locked = state.sessionState !== "lobby" || saving;
        root.innerHTML = `<div class="host-settings-group__title">💣 ${esc(labels.title)}</div>
            <p>${esc(labels.help)}</p>
            <ol class="hx-typedq">${questions.map(q => `<li class="hx-typedq__item"><label class="host-settings-item">
                <span>${Number(q.index)}. ${esc(q.text || "")}</span>
                <input type="checkbox" data-bomb-question="${Number(q.id)}" aria-label="${esc(`${labels.label} ${q.index}: ${q.text || ""}`)}" ${ids.has(Number(q.id)) ? "checked" : ""} ${locked || (!q.bomb_eligible && !ids.has(Number(q.id))) ? "disabled" : ""}>
            </label></li>`).join("")}</ol><p role="status" data-bomb-status></p>`;
    }
    root.addEventListener("change", async (event) => {
        const input = event.target.closest("[data-bomb-question]");
        if (!input || saving || state.sessionState !== "lobby") return;
        const ids = new Set((state.sessionSettings.bomb_questions || []).map(Number));
        const id = Number(input.dataset.bombQuestion);
        if (input.checked) ids.add(id); else ids.delete(id);
        saving = true;
        render();
        let result;
        try { result = await postJson(CONFIG.urls.settings, { bomb_questions: [...ids] }); }
        catch (_) { result = null; }
        saving = false;
        if (result?.ok) state.sessionSettings = Object.assign({}, state.sessionSettings, result.settings || {});
        render();
        root.querySelector("[data-bomb-status]").textContent = result?.ok ? labels.saved : (result?.message || labels.error);
    });
    window.addEventListener("live-host-state", () => { if (!saving) render(); });
    render();
    root.hidden = false;
}
