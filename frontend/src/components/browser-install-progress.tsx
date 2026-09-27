export type InstallProgress = {
  stage: "preparing" | "downloading" | "extracting" | "verifying" | "complete"
  downloaded_bytes: number
  total_bytes: number | null
  percent: number | null
}

const labels = {
  preparing: "Подготавливаем установку…",
  downloading: "Скачиваем браузер",
  extracting: "Распаковываем браузер…",
  verifying: "Проверяем файлы…",
  complete: "Браузер готов к работе",
}
const size = (bytes: number) => `${(bytes / 1024 / 1024).toLocaleString("ru-RU", {maximumFractionDigits: 1})} МБ`

export function BrowserInstallProgress({progress}: {progress: InstallProgress}) {
  const downloading = progress.stage === "downloading"
  const complete = progress.stage === "complete"
  const value = complete ? 100 : downloading ? progress.percent ?? undefined : undefined
  return <div className="agent-install-progress">
    <div className="agent-install-heading">
      <span role="status">{labels[progress.stage]}</span>
      {downloading && progress.percent !== null && <b>{progress.percent}%</b>}
    </div>
    <progress max={100} value={value} aria-label={labels[progress.stage]}/>
    {downloading && <small>{size(progress.downloaded_bytes)}{progress.total_bytes ? ` из ${size(progress.total_bytes)}` : " скачано"}</small>}
  </div>
}
