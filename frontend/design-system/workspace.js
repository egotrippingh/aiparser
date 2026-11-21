const notify = document.createElement("p");
notify.className = "workspace-toast";
notify.setAttribute("role", "status");
notify.hidden = true;
document.body.append(notify);

function showNotice(message) {
  notify.textContent = message;
  notify.hidden = false;
}

document.addEventListener("click", (event) => {
  const control = event.target.closest("button");
  if (!control) return;
  if (control.matches("[data-dialog]")) document.getElementById(control.dataset.dialog)?.showModal();
  if (control.matches("[data-close]")) control.closest("dialog")?.close();
  if (control.matches("[data-demo]")) showNotice(control.dataset.demo);
  if (control.matches("[data-period]")) {
    const period = control.dataset.period;
    for (const button of document.querySelectorAll("[data-period]")) {
      button.setAttribute("aria-pressed", String(button === control));
    }
    for (const panel of document.querySelectorAll("[data-period-panel]")) {
      panel.hidden = panel.dataset.periodPanel !== period;
    }
  }
  if (control.matches("[data-amount]")) {
    const amount = document.querySelector("#topup-amount");
    amount.value = control.dataset.amount;
    updateAmount();
  }
});

for (const dialog of document.querySelectorAll("dialog")) {
  dialog.addEventListener("close", () => {
    if (dialog.returnValue !== "preview") return;
    dialog.returnValue = "";
    showNotice("В макете данные не меняются.");
  });
}

for (const form of document.querySelectorAll("[data-preview-form]")) {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const status = form.querySelector(".form-result");
    status.textContent = "В макете данные не отправляются.";
  });
}

function filterTable(id) {
  const text = document.querySelector(`[data-filter="${id}"]`)?.value.trim().toLowerCase() ?? "";
  const select = document.querySelector(`[data-select-filter="${id}"]`);
  const rows = document.getElementById(id).tBodies[0].rows;
  let visible = 0;
  for (const row of rows) {
    const column = select ? row.cells[Number(select.dataset.filterColumn)]?.textContent.trim() : "";
    row.hidden = !row.textContent.toLowerCase().includes(text) || Boolean(select?.selectedIndex && column !== select.value);
    if (!row.hidden) visible++;
  }
  const empty = document.querySelector(`[data-empty-for="${id}"]`);
  if (empty) empty.hidden = visible > 0;
}

for (const field of document.querySelectorAll("[data-filter],[data-select-filter]")) {
  field.addEventListener("input", () => filterTable(field.dataset.filter ?? field.dataset.selectFilter));
}

function updateAmount() {
  const amount = document.querySelector("#topup-amount");
  const summary = document.querySelector("#topup-total");
  summary.textContent = amount.checkValidity()
    ? new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB" }).format(amount.valueAsNumber)
    : "—";
}

document.querySelector("#topup-amount")?.addEventListener("input", updateAmount);
document.querySelector("#reader-search")?.addEventListener("input", (event) => {
  const term = event.target.value.trim().toLowerCase();
  for (const link of document.querySelectorAll(".reader-nav nav a")) {
    link.hidden = !link.textContent.toLowerCase().includes(term);
  }
});
