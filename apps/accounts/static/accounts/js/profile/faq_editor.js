(() => {
    const form = document.querySelector(".faq-editor__form");
    if (!form) return;
    const everyone = form.elements.all_roles;
    form.addEventListener("change", ({target}) => {
        if (!target.checked) return;
        if (target.name === "audience") everyone.checked = false;
        if (target === everyone) {
            form.querySelectorAll('input[name="audience"]').forEach(role => { role.checked = false; });
        }
    });
})();
