import { renderToString } from "react-dom/server"
import { LandingPage } from "./landing-page"

export function renderLandingPage() {
  return renderToString(<LandingPage />)
}
