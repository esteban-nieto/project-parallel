import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { historiasApi, iaApi } from '../api/client'
import AudioRecorder from '../components/AudioRecorder'

export default function NuevaHistoria() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    paciente: '',
    edad: '',
    motivo: '',
    diagnostico: '',
    tratamiento: '',
    id_audio: null,
    transcripcion: '',
    texto_corregido: '',
    ubicacion: '',
    signos_vitales: '',
    observaciones: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [analizando, setAnalizando] = useState(false)

  const update = (key, value) => setForm((f) => ({ ...f, [key]: value }))

  const handleAnalizarTexto = async () => {
    const texto = form.transcripcion || form.observaciones
    if (!texto || texto.length < 10) {
      setError('Escribe o pega al menos 10 caracteres para analizar.')
      return
    }
    setError('')
    setAnalizando(true)
    try {
      const res = await iaApi.analizar(texto, true)
      setForm((f) => ({
        ...f,
        paciente: res.campos_extraidos?.paciente ?? f.paciente,
        edad: res.campos_extraidos?.edad ?? f.edad,
        motivo: res.campos_extraidos?.motivo ?? f.motivo,
        diagnostico: res.campos_extraidos?.diagnostico ?? f.diagnostico,
        tratamiento: res.campos_extraidos?.tratamiento ?? f.tratamiento,
        texto_corregido: res.texto_corregido ?? f.texto_corregido,
      }))
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Error al analizar')
    } finally {
      setAnalizando(false)
    }
  }

  const onAudioSubido = (idAudio, transcripcion) => {
    update('id_audio', idAudio)
    update('transcripcion', transcripcion || '')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const payload = {
        paciente: form.paciente.trim(),
        edad: Number(form.edad) || 0,
        motivo: form.motivo.trim(),
        diagnostico: form.diagnostico || null,
        tratamiento: form.tratamiento || null,
        id_audio: form.id_audio || null,
        transcripcion: form.transcripcion || null,
        texto_corregido: form.texto_corregido || null,
        ubicacion: form.ubicacion || null,
        signos_vitales: form.signos_vitales || null,
        observaciones: form.observaciones || null,
      }
      if (payload.paciente.length < 3) {
        setError('El nombre del paciente debe tener al menos 3 caracteres.')
        return
      }
      if (payload.motivo.length < 10) {
        setError('El motivo debe tener al menos 10 caracteres.')
        return
      }
      await historiasApi.crear(payload)
      navigate('/historias')
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Error al crear historia')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1 className="font-display text-2xl font-bold text-white mb-2">Nueva historia clínica</h1>
      <p className="text-slate-400 mb-6">Graba audio o escribe/pega texto y usa IA para rellenar campos.</p>
      <div className="card p-6 mb-6">
        <h2 className="font-display font-semibold text-white mb-3">Grabar audio</h2>
        <AudioRecorder onSubido={onAudioSubido} />
      </div>
      <form onSubmit={handleSubmit} className="card p-6 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label">Paciente *</label>
            <input type="text" className="input" value={form.paciente} onChange={(e) => update('paciente', e.target.value)} placeholder="Nombre completo" minLength={3} required />
          </div>
          <div>
            <label className="label">Edad *</label>
            <input type="number" className="input" value={form.edad} onChange={(e) => update('edad', e.target.value)} placeholder="0" min={0} max={150} required />
          </div>
        </div>
        <div>
          <label className="label">Motivo de atención *</label>
          <textarea className="input min-h-[80px]" value={form.motivo} onChange={(e) => update('motivo', e.target.value)} placeholder="Descripción del motivo" minLength={10} required />
        </div>
        <div>
          <label className="label">Transcripción / texto para analizar con IA</label>
          <div className="flex gap-2">
            <textarea className="input flex-1 min-h-[80px]" value={form.transcripcion} onChange={(e) => update('transcripcion', e.target.value)} placeholder="Pega aquí transcripción o texto a corregir" />
            <button type="button" className="btn-secondary self-end" onClick={handleAnalizarTexto} disabled={analizando}>
              {analizando ? 'Analizando…' : 'Analizar con IA'}
            </button>
          </div>
        </div>
        <div>
          <label className="label">Diagnóstico</label>
          <input type="text" className="input" value={form.diagnostico} onChange={(e) => update('diagnostico', e.target.value)} placeholder="Impresión diagnóstica" />
        </div>
        <div>
          <label className="label">Tratamiento</label>
          <input type="text" className="input" value={form.tratamiento} onChange={(e) => update('tratamiento', e.target.value)} placeholder="Tratamiento realizado" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label">Ubicación</label>
            <input type="text" className="input" value={form.ubicacion} onChange={(e) => update('ubicacion', e.target.value)} placeholder="Lugar del incidente" />
          </div>
          <div>
            <label className="label">Signos vitales</label>
            <input type="text" className="input" value={form.signos_vitales} onChange={(e) => update('signos_vitales', e.target.value)} placeholder="Ej. TA 120/80, FC 72" />
          </div>
        </div>
        <div>
          <label className="label">Observaciones</label>
          <textarea className="input min-h-[60px]" value={form.observaciones} onChange={(e) => update('observaciones', e.target.value)} placeholder="Notas adicionales" />
        </div>
        {error && <div className="rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm px-3 py-2">{error}</div>}
        <div className="flex gap-2">
          <button type="submit" className="btn-primary" disabled={loading}>{loading ? 'Guardando…' : 'Crear historia'}</button>
          <button type="button" className="btn-ghost" onClick={() => navigate('/historias')}>Cancelar</button>
        </div>
      </form>
    </div>
  )
}
