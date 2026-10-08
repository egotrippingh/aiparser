import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { LandingPage } from "./landing-page"
import { initTelemetry, rootOptions } from "./telemetry"

initTelemetry().finally(() => createRoot(document.getElementById("root")!, rootOptions).render(<StrictMode><LandingPage /></StrictMode>))
