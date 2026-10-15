import { renderToStaticMarkup } from "react-dom/server"
import { expect, it } from "vitest"
import { TopupForm } from "./topup-form"

it("keeps the payment provider out of the rendered top-up surface", () => {
  const markup = renderToStaticMarkup(<TopupForm token="test" minimum={30000} checkPrice={120} />)
  expect(markup).not.toContain("Coinso")
  expect(markup).toContain("Платёжный сервис может взимать комиссию")
})
