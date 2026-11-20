const spotlight = window.matchMedia("(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)");

for (const card of document.querySelectorAll(".task-grid .task")) {
  card.addEventListener("pointermove", (event) => {
    if (!spotlight.matches || event.pointerType === "touch") return;
    const rect = card.getBoundingClientRect();
    card.style.setProperty("--mouse-x", `${event.clientX - rect.left}px`);
    card.style.setProperty("--mouse-y", `${event.clientY - rect.top}px`);
  });
}
