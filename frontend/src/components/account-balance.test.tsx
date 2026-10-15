import {renderToStaticMarkup} from "react-dom/server"
import {expect, it} from "vitest"
import {AccountBalance} from "./account-balance"

it("shows spendable money and reserves to an administrator with paid recompute", () => {
  const html = renderToStaticMarkup(<AccountBalance available="12,34 ₽" balance="20 ₽" reserved="7,66 ₽" admin paidRecompute />)
  expect(html).toContain("12,34 ₽")
  expect(html).toContain("На балансе 20 ₽")
  expect(html).toContain("В резерве 7,66 ₽")
  expect(html).toContain("Обычные проверки бесплатны")
  expect(html).toContain("0,80 ₽")
  expect(html).not.toContain("Безлимитно")
})
