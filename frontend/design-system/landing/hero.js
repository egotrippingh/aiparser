import desktop from "./hero-lavender-desktop.json?url";
import mobile from "./hero-lavender-mobile.json?url";

const container = document.querySelector("#hero-lottie");
const artwork = document.querySelector(".hero-art");
const portrait = matchMedia("(max-aspect-ratio: 1/1)");
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
let controller;
let player;

function syncPlayback() {
  if (!player) return;
  if (document.hidden) player.pause();
  else player.play();
}

function reset() {
  controller?.abort();
  player?.destroy();
  player = undefined;
  artwork.classList.remove("is-ready");
}

async function load() {
  reset();
  if (reduced.matches) return;
  controller = new AbortController();
  const { signal } = controller;
  try {
    const [response, { default: lottie }] = await Promise.all([
      fetch(portrait.matches ? mobile : desktop, { signal }),
      import("lottie-web"),
    ]);
    if (!response.ok) throw new Error("Hero animation unavailable");
    const animationData = await response.json();
    if (signal.aborted) return;
    player = lottie.loadAnimation({ container, animationData, renderer: "svg", loop: true, autoplay: false });
    player.addEventListener("DOMLoaded", () => {
      if (signal.aborted) return;
      artwork.classList.add("is-ready");
      syncPlayback();
    });
    player.addEventListener("data_failed", () => { if (!signal.aborted) reset(); });
  } catch {
    if (!signal.aborted) reset();
  }
}

document.addEventListener("visibilitychange", syncPlayback);
portrait.addEventListener("change", load);
reduced.addEventListener("change", load);
void load();

if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    reset();
    document.removeEventListener("visibilitychange", syncPlayback);
    portrait.removeEventListener("change", load);
    reduced.removeEventListener("change", load);
  });
}
