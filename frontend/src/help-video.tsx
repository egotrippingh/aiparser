import { useCallback, useRef, useState, type CSSProperties, type PointerEvent } from "react"
import { Play } from "lucide-react"

export function ProjectVideo() {
  const video = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [failed, setFailed] = useState(false)
  const [duration, setDuration] = useState(0)
  const [position, setPosition] = useState(0)
  const [scrubbing, setScrubbing] = useState(false)
  const resumeAfterSeek = useRef(false)
  const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`

  const attachVideo = useCallback((element: HTMLVideoElement | null) => {
    video.current = element
    if (!element) return
    // Metadata can finish loading from prerendered HTML before React hydrates.
    setDuration(Number.isFinite(element.duration) ? Math.max(0, element.duration) : 0)
    setPosition(element.currentTime)
    if (element.error) setFailed(true)
  }, [])

  async function play() {
    const element = video.current
    if (!element) return
    setFailed(false)
    try { await element.play() }
    catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) setFailed(true)
    }
  }

  function seek(value: number) {
    if (!video.current || !duration || !Number.isFinite(value)) return
    const target = Math.max(0, Math.min(duration, value))
    video.current.currentTime = target
    setPosition(target)
  }

  function beginSeek(event: PointerEvent<HTMLInputElement>) {
    if (event.button !== 0) return
    event.currentTarget.setPointerCapture(event.pointerId)
    resumeAfterSeek.current = video.current ? !video.current.paused : false
    setScrubbing(true)
    video.current?.pause()
  }

  function endSeek() {
    setScrubbing(false)
    if (resumeAfterSeek.current) { resumeAfterSeek.current = false; void play() }
  }

  return <>
    <div className="help-video" data-playing={playing || undefined} data-scrubbing={scrubbing || undefined}>
      <button type="button" className="help-video-toggle" aria-label={`${playing ? "Приостановить" : "Воспроизвести"} видео о создании проекта`} onClick={() => { if (video.current?.paused) void play(); else video.current?.pause() }}>
        <video ref={attachVideo} src="/assets/help/create-project.mp4" width={1720} height={1080} playsInline preload="metadata" aria-hidden="true" onLoadedMetadata={event => attachVideo(event.currentTarget)} onTimeUpdate={event => setPosition(event.currentTarget.currentTime)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onError={() => { setPlaying(false); setFailed(true) }} />
        {!playing && !scrubbing && <span className="help-video-icon"><Play size={25} fill="currentColor" aria-hidden="true" /></span>}
      </button>
      <div className="help-video-seek">
        <input type="range" min={0} max={duration || 1} step={0.1} value={position} disabled={!duration} aria-label="Перемотка видео о создании проекта" aria-valuetext={`${clock(position)} из ${clock(duration)}`} style={{ "--video-progress": `${duration ? position / duration * 100 : 0}%` } as CSSProperties} onChange={event => seek(event.currentTarget.valueAsNumber)} onPointerDown={beginSeek} onPointerUp={endSeek} onPointerCancel={endSeek} onLostPointerCapture={endSeek} />
        <div className="help-video-time" aria-hidden="true"><span>{clock(position)}</span><span>{clock(duration)}</span></div>
      </div>
    </div>
    {failed && <p role="alert">Не удалось воспроизвести видео. <a href="/assets/help/create-project.mp4">Открыть файл</a>.</p>}
  </>
}
