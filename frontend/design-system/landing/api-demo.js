const button = document.querySelector("#copy-api");
const command = document.querySelector("#api-request");
const response = document.querySelector("#api-response");
const status = document.querySelector("#api-copy-status");
const fullCommand = command.textContent;
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
let finishTyping;

function prepareTyping(code, delay, duration) {
  const length = code.textContent.length;
  const visual = code.cloneNode(true);
  visual.removeAttribute("id");
  visual.setAttribute("aria-hidden", "true");
  visual.classList.add("api-visual");
  const walker = document.createTreeWalker(visual, NodeFilter.SHOW_TEXT);
  const parts = [];
  for (let node; (node = walker.nextNode());) {
    parts.push([node, node.data]);
    node.data = "";
  }
  code.classList.add("api-readable");
  code.after(visual);

  function reveal() {
    visual.remove();
    code.classList.remove("api-readable");
  }

  return {
    reveal,
    render(elapsed) {
      if (elapsed < delay || !visual.isConnected) return;
      if (elapsed >= delay + duration) {
        reveal();
        return;
      }
      visual.classList.add("api-typing");
      let remaining = Math.floor((elapsed - delay) * length / duration);
      for (const [node, text] of parts) {
        node.data = text.slice(0, Math.max(0, remaining));
        remaining -= text.length;
      }
    },
  };
}

if (!reduced.matches && "IntersectionObserver" in window) {
  const observer = new IntersectionObserver(([entry]) => {
    if (!entry.isIntersecting) return;
    observer.disconnect();
    if (reduced.matches) return;

    const commandDuration = 2800;
    const responseDuration = 1450;
    const stages = [
      prepareTyping(command, 0, commandDuration),
      prepareTyping(response, commandDuration, responseDuration),
    ];
    const start = performance.now();
    let frame;
    finishTyping = () => {
      cancelAnimationFrame(frame);
      for (const stage of stages) stage.reveal();
      reduced.removeEventListener("change", finishTyping);
      finishTyping = undefined;
    };
    reduced.addEventListener("change", finishTyping);

    function render(now) {
      const elapsed = now - start;
      if (elapsed >= commandDuration + responseDuration) {
        finishTyping();
        return;
      }
      for (const stage of stages) stage.render(elapsed);
      frame = requestAnimationFrame(render);
    }
    render(start);
  }, { threshold: 0.2 });
  observer.observe(command.closest("pre"));
  for (const code of [command, response]) {
    code.closest("pre").addEventListener("focus", () => {
      observer.disconnect();
      finishTyping?.();
    });
  }
}

if (navigator.clipboard?.writeText) {
  button.hidden = false;
  button.addEventListener("click", async () => {
    finishTyping?.();
    try {
      await navigator.clipboard.writeText(fullCommand);
      status.textContent = "Команда скопирована.";
    } catch {
      status.textContent = "Не удалось скопировать. Выделите команду и скопируйте её вручную.";
    }
  });
}
