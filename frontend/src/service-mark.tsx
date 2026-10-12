import { SCAN_SERVICES } from "./lib/scan-preferences"
export const serviceColors: Record<string, string> = {chatgpt:"#236ac6",perplexity:"#288d90",gemini:"#7778db",google_aio:"#e88035",yandex_neuro:"#895caf",alice:"#895caf"}
export const serviceName = (id: string) => SCAN_SERVICES.find(service => service.id === id)?.label || (id === "alice" ? "Алиса AI" : id)
const assets: Record<string, string> = {chatgpt:"chatgpt.svg",perplexity:"perplexity.svg",gemini:"gemini.png",google_aio:"google.svg",yandex_neuro:"yandex.ico"}
export function ServiceMark({ id }: { id: string }) {
  return <span className="service-mark">{assets[id] ? <img src={`/assets/services/${assets[id]}`} alt=""/> : id.slice(0, 1)}</span>
}
