import { useState, useRef } from 'react'
import { audioApi, iaApi } from '../api/client'

export default function AudioRecorder({ onSubido }) {
  const [grabando, setGrabando] = useState(false)
  const [estado, setEstado] = useState('')
  const [error, setError] = useState('')
  const chunksRef = useRef([])
  const mediaRecorderRef = useRef(null)

  const startRecording = async () => {
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/ogg'
      const recorder = new MediaRecorder(stream, { mimeType: mime })
      chunksRef.current = []
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType })
        const ext = blob.type.includes('ogg') ? 'ogg' : 'webm'
        const file = new File([blob], 'grabacion.' + ext, { type: blob.type })
        setEstado('Subiendo...')
        try {
          const res = await audioApi.subir(file)
          setEstado('Transcribiendo...')
          let transcripcion = ''
          for (let i = 0; i < 40; i++) {
            await new Promise((r) => setTimeout(r, 2000))
            const est = await audioApi.estado(res.id_audio)
            if (est.estado === 'completado' && est.transcripcion) {
              transcripcion = est.transcripcion
              break
            }
            if (est.estado === 'fallido') {
              setError(est.error || 'Error')
              setEstado('')
              return
            }
          }
          if (transcripcion) {
            setEstado('Analizando IA...')
            const analisis = await iaApi.analizar(transcripcion, false)
            onSubido(res.id_audio, analisis.texto_corregido || transcripcion)
          } else {
            onSubido(res.id_audio, '')
          }
          setEstado('Listo.')
        } catch (e) {
          setError(e?.data?.detail || e?.message || 'Error')
          setEstado('')
        }
      }
      mediaRecorderRef.current = recorder
      recorder.start()
      setGrabando(true)
      setEstado('Grabando. Suelta para enviar.')
    } catch (e) {
      setError('No se pudo acceder al microfono.')
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && grabando) {
      mediaRecorderRef.current.stop()
      mediaRecorderRef.current = null
      setGrabando(false)
    }
  }

  const handleSubirArchivo = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    setEstado('Subiendo...')
    try {
      const res = await audioApi.subir(file)
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 2000))
        const est = await audioApi.estado(res.id_audio)
        if (est.estado === 'completado' && est.transcripcion) {
          onSubido(res.id_audio, est.transcripcion)
          setEstado('Listo.')
          return
        }
        if (est.estado === 'fallido') {
          setError(est.error || 'Error')
          setEstado('')
          return
        }
      }
      onSubido(res.id_audio, '')
      setEstado('Subido.')
    } catch (err) {
      setError(err?.data?.detail || err?.message || 'Error')
      setEstado('')
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onMouseLeave={stopRecording}
          onTouchStart={startRecording}
          onTouchEnd={stopRecording}
          className={'btn-primary select-none ' + (grabando ? 'bg-red-500 animate-pulse' : '')}
        >
          {grabando ? 'Suelta para enviar' : 'Mantén para grabar'}
        </button>
        <span className="text-sm text-slate-400">o</span>
        <label className="btn-secondary cursor-pointer">
          Subir archivo
          <input type="file" accept="audio/*" className="hidden" onChange={handleSubirArchivo} />
        </label>
      </div>
      {estado && <p className="text-sm text-primary-400">{estado}</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  )
}
