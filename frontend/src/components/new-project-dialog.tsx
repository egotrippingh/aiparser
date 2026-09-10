/** Создание проекта: минимум полей, остальное — в настройках. */

import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { api, errText } from "@/lib/api"
import type { Project } from "@/lib/types"

export function NewProjectDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (p: Project) => void
}) {
  const [name, setName] = useState("")
  const [brand, setBrand] = useState("")
  const [brandTouched, setBrandTouched] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) {
      setName("")
      setBrand("")
      setBrandTouched(false)
    }
  }, [open])

  // Чаще всего проект называют по бренду, поэтому второе поле заполняется
  // само, пока пользователь его не тронул.
  const brandValue = brandTouched ? brand : name

  async function create() {
    if (!name.trim() || !brandValue.trim()) return
    setBusy(true)
    try {
      const p = await api.post<Project>("/api/projects", {
        name: name.trim(),
        brand_name: brandValue.trim(),
        brand_aliases: [],
        brand_domains: [],
      })
      onCreated(p)
      onOpenChange(false)
      toast.success("Проект создан", {
        description: "Добавьте домены и алиасы бренда в настройках — по ним ловятся упоминания ссылкой.",
      })
    } catch (e) {
      toast.error(errText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Новый проект</DialogTitle>
          <DialogDescription>
            Проект — это один бренд со своим списком запросов и своей историей проверок.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            create()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="np_name">Название проекта</Label>
            <Input
              id="np_name"
              value={name}
              autoFocus
              onChange={(e) => setName(e.target.value)}
              placeholder="Метизы Опт"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="np_brand">Название бренда</Label>
            <Input
              id="np_brand"
              value={brandValue}
              onChange={(e) => {
                setBrandTouched(true)
                setBrand(e.target.value)
              }}
              placeholder="как бренд пишут в ответах"
            />
            <p className="text-muted-foreground text-xs">
              Именно эту форму программа ищет в ответах ИИ. Другие написания добавите алиасами.
            </p>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Отмена
            </Button>
            <Button type="submit" disabled={busy || !name.trim() || !brandValue.trim()}>
              Создать
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
