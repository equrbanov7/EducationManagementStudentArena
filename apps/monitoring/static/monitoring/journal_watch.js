(function () {
    "use strict";
    const form = document.querySelector("[data-jw-form]");
    if (!form) return;
    const kind = form.elements.kind;
    const people = form.elements.person;
    const query = form.querySelector("[data-jw-query]");
    const status = form.querySelector("[data-jw-status]");
    const button = form.querySelector("[data-jw-search]");
    let sequence = 0;
    kind.addEventListener("change", () => { sequence++; people.replaceChildren(); status.textContent = ""; });
    async function search() {
        const current = ++sequence;
        people.replaceChildren();
        if (query.value.trim().length < 2) { status.textContent = form.dataset.tooShort; return; }
        status.textContent = form.dataset.searching;
        try {
            const data = new URLSearchParams({kind: kind.value, q: query.value.trim()});
            const response = await fetch(form.dataset.search, {
                method: "POST", body: data, credentials: "same-origin",
                headers: {"X-CSRFToken": form.elements.csrfmiddlewaretoken.value}
            });
            if (!response.ok) throw new Error();
            const result = await response.json();
            if (current !== sequence) return;
            const choices = result.people.map(row => new Option(row.label, row.id));
            people.replaceChildren(...choices);
            status.textContent = choices.length ? form.dataset.choose : form.dataset.empty;
        } catch {
            if (current === sequence) status.textContent = form.dataset.retry;
        }
    }
    button.addEventListener("click", search);
    query.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); search(); } });
})();
