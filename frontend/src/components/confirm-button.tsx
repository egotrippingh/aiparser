/** Кнопка с подтверждением необратимого действия.
 *
 * Нативный confirm() блокирует окно целиком: пока он открыт, не приходят
 * события скана и не отрисовывается прогресс. Поэтому подтверждение —
 * обычный диалог, а не системный.
 */

import { useState, type ComponentProps, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

type ButtonProps = ComponentProps<typeof Button>

export function ConfirmButton({
  title,
  description,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  onConfirm,
  children,
  ...button
}: {
  title: string
  description: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void | Promise<void>
  children: ReactNode
} & Omit<ButtonProps, "onClick">) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true)
    try {
      await onConfirm()
      setOpen(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Button {...button} onClick={() => setOpen(true)}>
        {children}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>{cancelLabel}</DialogClose>
            <Button variant="destructive" onClick={run} disabled={busy}>
              {busy ? "Выполняю…" : confirmLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
