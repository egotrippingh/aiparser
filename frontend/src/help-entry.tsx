import { StrictMode } from "react"
import { hydrateRoot } from "react-dom/client"
import { HELP_ARTICLES } from "./help-content"
import { HelpPage } from "./help-page"
import { initTelemetry, rootOptions } from "./telemetry"
import "./help.css"

const slug = location.pathname.split("/")[2] || "quick-start"
const article = HELP_ARTICLES.find(item => item.slug === slug) || HELP_ARTICLES[0]
initTelemetry().finally(() => hydrateRoot(document.getElementById("root")!, <StrictMode><HelpPage article={article} /></StrictMode>, rootOptions))
