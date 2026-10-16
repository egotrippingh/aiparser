import { StrictMode } from "react"
import { createRoot, hydrateRoot } from "react-dom/client"

import { LandingPage } from "./landing-page"
import { initTelemetry, rootOptions } from "./telemetry"

initTelemetry().finally(() => {
  const root = document.getElementById("root")!
  const page = <StrictMode><LandingPage /></StrictMode>
  if (root.hasChildNodes()) hydrateRoot(root, page, rootOptions)
  else createRoot(root, rootOptions).render(page)
})
