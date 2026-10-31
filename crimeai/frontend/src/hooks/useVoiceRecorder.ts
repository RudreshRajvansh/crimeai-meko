import { useCallback, useEffect, useRef, useState } from 'react'

const MAX_SECONDS = 180
const BARS = 24
// Chrome and Android record WebM/Opus, Safari and iPhone record MP4/AAC; the server reads all of them.
const TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']

/**
 * Records a spoken complaint from the microphone. `levels` drives a live waveform while recording;
 * `onDone` receives the finished recording once `stop` is called (or the 3-minute cap is reached).
 */
export function useVoiceRecorder(onDone: (audio: File) => void) {
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0))
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const cleanupRef = useRef<() => void>(() => {})
  const doneRef = useRef(onDone)
  doneRef.current = onDone
  const supported = typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

  const stop = useCallback(() => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }, [])

  const start = useCallback(async (stream?: MediaStream) => {
    setError(null)
    // Created inside the click, before any await: a context made later starts suspended and the meter stays flat.
    const context = new AudioContext()
    void context.resume()
    let input: MediaStream
    try {
      input = stream ?? await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
    } catch {
      void context.close()
      setError('Microphone permission is needed to record the complaint.')
      return
    }
    const mimeType = TYPES.find((t) => MediaRecorder.isTypeSupported(t))
    const recorder = new MediaRecorder(input, mimeType ? { mimeType } : undefined)
    const chunks: Blob[] = []
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }

    const analyser = context.createAnalyser()
    analyser.fftSize = 64
    context.createMediaStreamSource(input).connect(analyser)
    const bins = new Uint8Array(analyser.frequencyBinCount)
    let frame = 0
    const draw = () => {
      analyser.getByteFrequencyData(bins)
      setLevels(Array.from({ length: BARS }, (_, i) => bins[Math.floor((i / BARS) * bins.length)] / 255))
      frame = requestAnimationFrame(draw)
    }
    draw()
    const startedAt = Date.now()
    const timer = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000)
      setSeconds(elapsed)
      if (elapsed >= MAX_SECONDS) recorder.stop()
    }, 250)

    cleanupRef.current = () => {
      cancelAnimationFrame(frame)
      window.clearInterval(timer)
      void context.close()
      if (!stream) input.getTracks().forEach((t) => t.stop())
    }
    recorder.onstop = () => {
      cleanupRef.current()
      setRecording(false)
      setLevels(Array(BARS).fill(0))
      const type = (recorder.mimeType || 'audio/webm').split(';')[0]
      const blob = new Blob(chunks, { type })
      if (blob.size > 0) doneRef.current(new File([blob], `complaint.${type.split('/')[1]}`, { type }))
    }
    recorderRef.current = recorder
    setSeconds(0)
    try {
      recorder.start(1000)
    } catch {
      cleanupRef.current()
      setError('The microphone could not start recording. Try again.')
      return
    }
    setRecording(true)
  }, [])

  useEffect(() => () => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    cleanupRef.current()
  }, [])

  return { supported, recording, seconds, levels, error, start, stop }
}
