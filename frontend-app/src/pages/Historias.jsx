import { useState, useEffect } from 'react'
import { historiasApi } from '../api/client'

export default function Historias() {
  const [historias, setHistorias] = useState([])
  const [total, setTotal] = useState(0)
  const [pagina, setPagina] = useState(1)
  const [estadoFiltro, setEstadoFiltro] = useState('')
  const [pacienteFiltro, setPacienteFiltro] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const cargar = async () => {
    setLoading(true)
    setError('')
    try {
      const params = { pagina, por_pagina: 20 }
      if (estadoFiltro) params.estado = estadoFiltro
      if (pacienteFiltro) params.paciente = pacienteFiltro
      const res = await historiasApi.listar(params)
      setHistorias(res.historias || [])
      setTotal(res.total ?? 0)
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Error al cargar')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    cargar()
  }, [pagina, estadoFiltro])

  const aplicarFiltro = () => {
    setPagina(1)
    cargar()
  }

  const cambiarEstado = async (consecutivo, nuevoEstado) => {
    try {
      await historiasApi.actualizarEstado(consecutivo, nuevoEstado)
      cargar()
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Error')
    }
  }

  const eliminar = async (consecutivo) => {
    if (!window.confirm('Eliminar historia ' + consecutivo + '?')) return
    try {
      await historiasApi.eliminar(consecutivo)
      cargar()
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Error')
    }
  }

  const formatFecha = (d) => {
    if (!d) return '-'
    const date = new Date(d)
    return date.toLocaleDateString('es') + ' ' + date.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div>
      <h1 className="font-display text-2xl font-bold text-white mb-2">Historias clínicas</h1>
      <p className="text-slate-400 mb-6">Listado con filtros por estado y paciente.</p>
      <div className="card p-4 mb-4 flex flex-wrap gap-3 items-end">
        <div>
          <label className="label">Estado</label>
          <select className="input w-auto" value={estadoFiltro} onChange={(e) => setEstadoFiltro(e.target.value)}>
            <option value="">Todos</option>
            <option value="incompleta">Incompleta</option>
            <option value="completa">Completa</option>
          </select>
        </div>
        <div>
          <label className="label">Paciente</label>
          <input type="text" className="input w-48" value={pacienteFiltro} onChange={(e) => setPacienteFiltro(e.target.value)} placeholder="Buscar nombre" />
        </div>
        <button type="button" className="btn-primary" onClick={aplicarFiltro}>Filtrar</button>
      </div>
      {error && <div className="rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm p-3 mb-4">{error}</div>}
      {loading ? (
        <div className="text-slate-400 py-8">Cargando…</div>
      ) : historias.length === 0 ? (
        <div className="card p-8 text-center text-slate-400">No hay historias con los filtros actuales.</div>
      ) : (
        <div className="space-y-3">
          {historias.map((h) => (
            <div key={h.consecutivo} className="card p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <span className="font-mono text-primary-400">{h.consecutivo}</span>
                  <span className="mx-2 text-slate-500">|</span>
                  <span className="font-medium text-white">{h.paciente}</span>
                  <span className="text-slate-400 text-sm ml-2">({h.edad} años)</span>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded ${h.estado === 'completa' ? 'bg-green-500/20 text-green-400' : 'bg-amber-500/20 text-amber-400'}`}>{h.estado}</span>
              </div>
              <p className="text-slate-400 text-sm mt-1 line-clamp-2">{h.motivo}</p>
              <p className="text-slate-500 text-xs mt-1">{formatFecha(h.fecha_creacion)}</p>
              <div className="flex gap-2 mt-3">
                <button type="button" className="btn-ghost text-sm" onClick={() => cambiarEstado(h.consecutivo, h.estado === 'completa' ? 'incompleta' : 'completa')}>
                  {h.estado === 'completa' ? 'Marcar incompleta' : 'Marcar completa'}
                </button>
                <button type="button" className="btn-ghost text-sm text-red-400 hover:text-red-300" onClick={() => eliminar(h.consecutivo)}>Eliminar</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {total > 20 && (
        <div className="flex justify-center gap-2 mt-4">
          <button type="button" className="btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>Anterior</button>
          <span className="py-2 text-slate-400">Página {pagina} de {Math.ceil(total / 20)}</span>
          <button type="button" className="btn-ghost" disabled={pagina >= Math.ceil(total / 20)} onClick={() => setPagina((p) => p + 1)}>Siguiente</button>
        </div>
      )}
    </div>
  )
}
