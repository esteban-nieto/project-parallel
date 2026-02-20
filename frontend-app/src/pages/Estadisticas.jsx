import { useState, useEffect } from 'react'
import { historiasApi, iaApi } from '../api/client'

export default function Estadisticas() {
  const [histStats, setHistStats] = useState(null)
  const [iaStats, setIaStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const [h, i] = await Promise.all([
          historiasApi.estadisticas().catch(() => null),
          iaApi.estadisticas().catch(() => null),
        ])
        if (!cancelled) {
          setHistStats(h)
          setIaStats(i)
        }
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Error al cargar')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return (
      <div className="text-slate-400 py-8">Cargando estadísticas…</div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 p-4">
        {error}
      </div>
    )
  }

  return (
    <div>
      <h1 className="font-display text-2xl font-bold text-white mb-2">
        Estadísticas
      </h1>
      <p className="text-slate-400 mb-6">
        Resumen de historias clínicas y uso de IA.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-6">
          <h2 className="font-display font-semibold text-lg text-white mb-4">
            Historias clínicas
          </h2>
          {histStats ? (
            <ul className="space-y-3 text-slate-300">
              <li>
                <span className="text-slate-500">Total:</span>{' '}
                <strong className="text-white">{histStats.total_historias ?? 0}</strong>
              </li>
              <li>
                <span className="text-slate-500">Completas:</span>{' '}
                <strong className="text-green-400">{histStats.completas ?? 0}</strong>
              </li>
              <li>
                <span className="text-slate-500">Incompletas:</span>{' '}
                <strong className="text-amber-400">{histStats.incompletas ?? 0}</strong>
              </li>
              {histStats.ultima_historia && (
                <li className="pt-2 border-t border-slate-700">
                  <span className="text-slate-500">Última:</span>{' '}
                  {histStats.ultima_historia.consecutivo} – {histStats.ultima_historia.paciente}
                </li>
              )}
            </ul>
          ) : (
            <p className="text-slate-500">No hay datos.</p>
          )}
        </div>

        <div className="card p-6">
          <h2 className="font-display font-semibold text-lg text-white mb-4">
            Uso de IA
          </h2>
          {iaStats ? (
            <ul className="space-y-3 text-slate-300">
              <li>
                <span className="text-slate-500">Análisis totales:</span>{' '}
                <strong className="text-white">{iaStats.total_analisis ?? 0}</strong>
              </li>
              <li>
                <span className="text-slate-500">Desde caché:</span>{' '}
                <strong className="text-primary-400">{iaStats.desde_cache ?? 0}</strong>
              </li>
              <li>
                <span className="text-slate-500">Nuevos análisis:</span>{' '}
                <strong>{iaStats.nuevos_analisis ?? 0}</strong>
              </li>
              <li>
                <span className="text-slate-500">Tiempo promedio:</span>{' '}
                {iaStats.tiempo_promedio_ms ?? 0} ms
              </li>
              <li>
                <span className="text-slate-500">% caché:</span>{' '}
                {iaStats.porcentaje_cache ?? 0}%
              </li>
            </ul>
          ) : (
            <p className="text-slate-500">No hay datos de IA.</p>
          )}
        </div>
      </div>
    </div>
  )
}
