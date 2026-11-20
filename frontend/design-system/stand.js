const dialog = document.querySelector("#example");
document.querySelector("[data-open]").addEventListener("click", () => dialog.showModal());

const play = document.querySelector("#play");
const status = document.querySelector("#motion-status");
const frame = document.querySelector("#motion-frame");
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
let animation;

function pause() {
  if (!animation || animation.isPaused) return;
  animation.pause();
  play.textContent = "Продолжить";
}

play.addEventListener("click", async () => {
  if (animation) {
    if (animation.isPaused) {
      animation.play();
      play.textContent = "Пауза";
    } else {
      pause();
    }
    return;
  }

  play.disabled = true;
  play.textContent = "Загрузка…";
  status.textContent = "";
  try {
    const [{ default: lottie }, response] = await Promise.all([
      import("lottie-web"),
      fetch(new URL("../src/assets/landing/airate-hero.json", import.meta.url)),
    ]);
    if (!response.ok) throw new Error("Cannot load Lottie");
    const animationData = await response.json();
    animation = lottie.loadAnimation({
      container: document.querySelector("#lottie"),
      animationData, renderer: "svg", autoplay: false, loop: true,
    });
    await new Promise((resolve, reject) => {
      animation.addEventListener("DOMLoaded", resolve);
      animation.addEventListener("data_failed", reject);
      animation.addEventListener("error", reject);
    });
    frame.classList.add("is-playing");
    if (!document.hidden) animation.play();
    play.textContent = animation.isPaused ? "Продолжить" : "Пауза";
  } catch {
    animation?.destroy();
    animation = undefined;
    frame.classList.remove("is-playing");
    status.textContent = "Не удалось загрузить анимацию. Можно попробовать ещё раз.";
    play.textContent = "Повторить";
  } finally {
    play.disabled = false;
  }
});

document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); });
reduced.addEventListener("change", () => { if (reduced.matches) pause(); });
