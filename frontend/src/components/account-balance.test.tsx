import {renderToStaticMarkup} from "react-dom/server"
import {expect, it} from "vitest"
import {AccountBalance} from "./account-balance"

it("shows unlimited free checks and recompute to an administrator", () => {
  const html = renderToStaticMarkup(<AccountBalance available="12,34 ₽" balance="20 ₽" reserved="7,66 ₽" admin />)
  expect(html).toContain("Безлимитно")
  expect(html).toContain("На балансе 20 ₽")
  expect(html).toContain("В резерве 7,66 ₽")
  expect(html).toContain("Проверки и пересчёт сохранённых ответов бесплатны")
  expect(html).not.toContain("1,20 ₽")
})

it("keeps the available balance for an ordinary account", () => {
  const html = renderToStaticMarkup(<AccountBalance available="0 ₽" balance="0 ₽" admin={false} />)
  expect(html).toContain("Доступно для проверок")
  expect(html).toContain("0 ₽")
  expect(html).not.toContain("Безлимитно")
  expect(html).not.toContain("бесплатны")
})
