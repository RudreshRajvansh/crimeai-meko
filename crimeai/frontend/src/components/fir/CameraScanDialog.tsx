import { useCallback, useEffect, useRef, useState } from 'react'
import { Camera, RefreshCcw, X } from 'lucide-react'

/**
 * Live camera capture for paper FIRs. Works with a laptop webcam or a phone's rear camera
 * (getUserMedia needs https or localhost). The captured frame is handed back as a JPEG file.
 */
export default function CameraScanDialog({ onCapture, onClose }: { onCapture: (file: File) => void; onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [facing, setFacing] = useState<'environment' | 'user'>('environment')
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  useEffect(() => {
    let cancelled = false
    setReady(false)
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('This browser cannot open the camera here. Use https or localhost, or upload a photo instead.')
      return
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: facing }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return }
        stop()
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          void videoRef.current.play().then(() => setReady(true)).catch(() => setReady(true))
        }
      })
      .catch((err: DOMException) => {
        setError(err.name === 'NotAllowedError'
          ? 'Camera permission was denied. Allow the camera in the browser bar and try again.'
          : 'No camera found. Plug one in, or upload a photo instead.')
      })
    return () => { cancelled = true }
  }, [facing, stop])

  useEffect(() => stop, [stop])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const capture = () => {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d')?.drawImage(video, 0, 0)
    canvas.toBlob((blob) => {
      if (!blob) return
      stop()
      onCapture(new File([blob], `fir-scan-${Date.now()}.jpg`, { type: 'image/jpeg' }))
    }, 'image/jpeg', 0.92)
  }

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/80 p-4" role="dialog" aria-modal="true" aria-label="Scan FIR with camera">
      <div className="w-full max-w-3xl overflow-hidden rounded-xl border border-border-subtle bg-bg-secondary shadow-2xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-4 py-2.5">
          <p className="flex items-center gap-2 text-sm font-semibold text-text-primary"><Camera size={15} /> Scan a paper FIR</p>
          <button type="button" onClick={onClose} className="btn-ghost p-1" aria-label="Close"><X size={16} /></button>
        </div>
        <div className="relative aspect-video bg-black">
          {error ? (
            <p className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-text-secondary">{error}</p>
          ) : (
            <>
              <video ref={videoRef} playsInline muted className="h-full w-full object-contain" />
              {/* Document guide and moving scan line */}
              <div className="pointer-events-none absolute inset-[7%] rounded-lg border-2 border-dashed border-accent-blue/70">
                <span className="absolute inset-x-0 top-0 h-0.5 animate-scan-line bg-accent-blue shadow-glow-blue" />
              </div>
              {!ready && <p className="absolute inset-0 flex items-center justify-center text-sm text-text-secondary">Opening camera…</p>}
            </>
          )}
        </div>
        <div className="flex items-center justify-between gap-2 px-4 py-3">
          <p className="text-2xs text-text-muted">Fit the FIR inside the frame. Printed or handwritten, any Indian language.</p>
          <div className="flex gap-2">
            <button type="button" onClick={() => setFacing((f) => (f === 'environment' ? 'user' : 'environment'))} className="btn-secondary text-xs" title="Switch camera">
              <RefreshCcw size={13} />
            </button>
            <button type="button" onClick={capture} disabled={!ready || !!error} className="btn-primary text-xs">
              <Camera size={13} /> Capture & read
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
