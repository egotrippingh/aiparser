const panels = new Map([...document.querySelectorAll(".auth-form")].map(panel => [panel.id, panel]));
const message = document.querySelector("#auth-message");

function showForm(focus = false) {
  const hash = location.hash.slice(1);
  if (hash === "main" && focus) return;
  const active = panels.get(hash) ?? panels.get("login");
  for (const panel of panels.values()) panel.hidden = panel !== active;
  message.textContent = "";
  document.title = active.querySelector("h1").textContent + " · Аирейт";
  if (focus) {
    const heading = active.querySelector("h1");
    heading.tabIndex = -1;
    heading.focus();
  }
}

window.addEventListener("hashchange", () => showForm(true));
showForm();

for (const button of document.querySelectorAll("[data-password]")) {
  button.addEventListener("click", () => {
    const field = document.getElementById(button.dataset.password);
    const visible = field.type === "password";
    field.type = visible ? "text" : "password";
    button.setAttribute("aria-pressed", String(visible));
    button.setAttribute("aria-label", visible ? "Скрыть пароль" : "Показать пароль");
  });
}

for (const button of document.querySelectorAll("[data-provider]")) {
  button.addEventListener("click", () => {
    message.textContent = "Вход через Яндекс ID доступен в действующем кабинете.";
  });
}

for (const form of document.querySelectorAll("[data-mode]")) {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    switch (form.dataset.mode) {
      case "register":
        location.hash = "confirm";
        break;
      case "confirm": {
        if (form.querySelector("#new-password").value !== form.querySelector("#repeat-password").value) {
          message.textContent = "Пароли не совпадают. Проверьте их и попробуйте ещё раз.";
          return;
        }
        form.reset();
        message.textContent = "Это макет: аккаунт не создан.";
        break;
      }
      case "forgot":
        message.textContent = "Это макет: письмо для восстановления не отправляется.";
        break;
      case "login":
        form.reset();
        message.textContent = "Это макет: вход в аккаунт не выполняется.";
        break;
    }
  });
}
